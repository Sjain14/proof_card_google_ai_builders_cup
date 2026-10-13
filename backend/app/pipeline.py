"""Prebunk pipeline (Before): predict likely claims, verify each, issue Proof Cards.

verify_claim() is also the cold path for live claims (During), so Before and During
produce identical, comparable cards.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.model import Assessment, ModelClient
from app.proof import Fetcher, FetchError, SnapshotStore, best_passage, extract_text, snapshot
from app.schemas import CardDoc, ClaimDoc, ClaimSource, ClaimStatus, SourceProof, gate_verdict
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
            log.info("source skipped", extra={"fields": {"reason": str(exc)[:80]}})
            continue
        if fetched.final_url in seen:
            continue
        seen.add(fetched.final_url)
        text = extract_text(fetched.body, fetched.content_type)
        # Match against the claim and the model's supporting sentence, keep the better.
        passage, score = best_passage(claim, text)
        if ev.model_snippet:
            p2, s2 = best_passage(ev.model_snippet, text)
            if s2 > score:
                passage, score = p2, s2
        if score < MIN_PASSAGE_SCORE or not passage:
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
        return None
    support = round(sum(scores) / len(scores), 3)
    verdict = gate_verdict(assessment.verdict, support)
    fields = {
        "claim": claim,
        "verdict": verdict,
        "explanation": assessment.explanation,
        "sources": [p.model_dump(mode="json") for p in proofs],
        "support_score": support,
    }
    return CardDoc(card_sha256=card_fingerprint(fields), **fields)


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
    session = deps.store.get_session(session_id)
    if session is None:
        return {"predicted": 0, "proved": 0}
    deps.store.update_session(session_id, status="prebunking")
    predicted = deps.model.predict_claims(session.topic, session.speaker, n)
    ids = [
        deps.store.add_claim(
            session_id, ClaimDoc(text=p.text, lang=p.lang, source=ClaimSource.PREDICTED)
        )
        for p in predicted
    ]
    with ThreadPoolExecutor(max_workers=deps.workers) as pool:
        results = list(pool.map(lambda cid: verify_claim(session_id, cid, deps), ids))
    proved = sum(1 for r in results if r)
    deps.store.update_session(session_id, status="ready")
    log.info("prebunk done", extra={"fields": {"predicted": len(ids), "proved": proved}})
    return {"predicted": len(ids), "proved": proved}
