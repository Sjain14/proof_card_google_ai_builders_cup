"""Prebunk pipeline (Before): predict likely claims, verify each, issue Proof Cards.

verify_claim() is also the cold path for live claims (During), so Before and During
produce identical, comparable cards.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.model import Assessment, ModelClient
from app.proof import (
    Fetcher,
    FetchError,
    SnapshotStore,
    best_contradiction,
    best_match,
    extract_text,
    snapshot,
)
from app.schemas import (
    CardDoc,
    ClaimDoc,
    ClaimSource,
    ClaimStatus,
    SourceProof,
    Verdict,
    gate_verdict,
)
from app.security import card_fingerprint
from app.store import Store, new_card_id

log = logging.getLogger("proofcard.pipeline")

MIN_PASSAGE_SCORE = 0.35


@dataclass(frozen=True)
class Deps:
    store: Store
    model: ModelClient
    fetcher: Fetcher
    snapshots: SnapshotStore
    max_sources: int = 3
    workers: int = 4


def support_for(claim: str, a: Assessment, snippet: str, text: str) -> tuple[str, float]:
    """Best passage for the claim as said, its English restatement and the model's
    supporting sentence. For FALSE / MISLEADING an on topic passage with a different
    number is support too: it is the evidence that the claim is wrong."""
    queries = [q for q in dict.fromkeys([claim, a.claim_en, snippet]) if q]
    best = max((best_match(q, text) for q in queries), key=lambda m: m.score)
    passage, score = best.passage, best.score
    if a.verdict in (Verdict.FALSE, Verdict.MISLEADING):
        for q in [claim, a.claim_en]:
            c = best_contradiction(q, text) if q else None
            if c and c.topic > score:
                passage, score = c.passage, c.topic
    return passage, score


def _host(url: str) -> str:
    return urlsplit(url).hostname or "?"


def _skip(url: str, reason: str, **more: object) -> None:
    """One log line per dropped source, so a claim that ends as COULDN'T CHECK says why."""
    log.info(
        "source skipped", extra={"fields": {"host": _host(url), "reason": reason[:80], **more}}
    )


def build_card(claim: str, assessment: Assessment, deps: Deps) -> CardDoc | None:
    proofs: list[SourceProof] = []
    scores: list[float] = []
    seen: set[str] = set()
    for ev in assessment.evidence:
        if len(proofs) >= deps.max_sources:
            break
        try:
            fetched = deps.fetcher.fetch(ev.url)
        except FetchError as exc:
            _skip(ev.url, str(exc))
            continue
        if fetched.final_url in seen:
            _skip(fetched.final_url, "duplicate")
            continue
        seen.add(fetched.final_url)
        text = extract_text(fetched.body, fetched.content_type)
        if not text:
            _skip(fetched.final_url, "no text", content_type=fetched.content_type)
            continue
        passage, score = support_for(claim, assessment, ev.model_snippet, text)
        if score < MIN_PASSAGE_SCORE or not passage:
            _skip(fetched.final_url, "low support", score=round(score, 3))
            continue
        digest = snapshot(fetched, deps.snapshots)
        proofs.append(
            SourceProof(
                url=fetched.final_url,
                snippet=passage,
                snapshot_sha256=digest,
                fetched_at=fetched.fetched_at,
            )
        )
        scores.append(score)
    if not proofs:
        log.info(
            "no proof",
            extra={
                "fields": {
                    "evidence": len(assessment.evidence),
                    "model_verdict": str(assessment.verdict),
                }
            },
        )
        return None
    # The gate needs ONE snapshotted source that backs the verdict, not an average:
    # a second, weaker source used to drag a well proven TRUE claim under the gate
    # (prod verify rev00012: 10 of 11 brief claims ended UNVERIFIABLE, true ones too).
    support = round(max(scores), 3)
    verdict = gate_verdict(assessment.verdict, support)
    fields = {
        "claim": claim,
        "verdict": verdict,
        "explanation": assessment.explanation,
        "sources": [p.model_dump(mode="json") for p in proofs],
        "support_score": support,
    }
    return CardDoc(
        card_sha256=card_fingerprint(fields),
        search_suggestion_html=assessment.search_suggestion_html or None,
        **fields,
    )


def verify_claim(session_id: str, claim_id: str, deps: Deps) -> str | None:
    """Check one stored claim end to end. Returns the card id or None."""
    claim = deps.store.get_claim(session_id, claim_id)
    if claim is None:
        return None
    deps.store.update_claim(session_id, claim_id, status=ClaimStatus.CHECKING)
    try:
        card = build_card(claim.text, deps.model.assess(claim.text), deps)
    except Exception:
        log.exception("verify failed")
        card = None
    if card is None:
        deps.store.update_claim(session_id, claim_id, status=ClaimStatus.FAILED)
        return None
    card_id = new_card_id()
    deps.store.put_card(card_id, card)
    deps.store.update_claim(
        session_id,
        claim_id,
        status=ClaimStatus.PROVED,
        card_id=card_id,
        verdict=card.verdict,
    )
    return card_id


def run_prebunk(session_id: str, deps: Deps, n: int = 12) -> dict[str, int]:
    """Build the brief bank. Never leaves a session stuck in "prebunking": a model failure
    ends it as "failed" (the UI says so). Idempotent: a Cloud Tasks retry (instance died,
    deadline hit) finishes the same bank instead of adding a second one."""
    session = deps.store.get_session(session_id)
    if session is None:
        return {"predicted": 0, "proved": 0}
    deps.store.update_session(session_id, status="prebunking")
    bank = [
        (cid, c)
        for cid, c in deps.store.list_claims(session_id)
        if c.source == ClaimSource.PREDICTED
    ]
    if not bank:
        try:
            predicted = deps.model.predict_claims(session.topic, session.speaker, n)
        except Exception:
            log.exception("prebunk prediction failed")
            deps.store.update_session(session_id, status="failed")
            return {"predicted": 0, "proved": 0}
        for p in predicted:
            doc = ClaimDoc(text=p.text, lang=p.lang, source=ClaimSource.PREDICTED)
            bank.append((deps.store.add_claim(session_id, doc), doc))
    todo = [cid for cid, c in bank if c.status not in (ClaimStatus.PROVED, ClaimStatus.FAILED)]
    with ThreadPoolExecutor(max_workers=deps.workers) as pool:
        list(pool.map(lambda cid: verify_claim(session_id, cid, deps), todo))
    proved = sum(
        1
        for _, c in deps.store.list_claims(session_id)
        if c.source == ClaimSource.PREDICTED and c.status == ClaimStatus.PROVED
    )
    deps.store.update_session(session_id, status="ready")
    log.info("prebunk done", extra={"fields": {"predicted": len(bank), "proved": proved}})
    return {"predicted": len(bank), "proved": proved}
