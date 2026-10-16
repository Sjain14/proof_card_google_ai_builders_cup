"""Prebunk pipeline (Before): predict likely claims, verify each, issue Proof Cards.

verify_claim() is also the cold path for live claims (During), so Before and During
produce identical, comparable cards.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.facts import FactDesk, Ruling, ensure_bank
from app.govsources import search_hint
from app.model import Assessment, Evidence, ModelClient, PredictedClaim
from app.officialdata import is_worldbank, official_evidence, official_proof
from app.officialdata import render as render_official
from app.proof import (
    Fetched,
    Fetcher,
    FetchError,
    SnapshotStore,
    best_contradiction,
    best_match,
    comparison_match,
    extract_text,
    is_comparison,
    snapshot,
)
from app.schemas import (
    CardDoc,
    ClaimDoc,
    ClaimSource,
    ClaimStatus,
    SessionDoc,
    SourceProof,
    Verdict,
    gate_verdict,
)
from app.security import card_fingerprint
from app.store import Store, new_card_id

log = logging.getLogger("proofcard.pipeline")

MIN_PASSAGE_SCORE = 0.35
# ONE fetch budget for the whole card. Without it, 8 s per source over ~10 grounding
# chunks made one live card take 120 s (rev00012 prod verify, "power plants" line).
# A source still loading at the deadline is skipped like any other failed fetch.
FETCH_BUDGET_S = 25.0


@dataclass(frozen=True)
class Deps:
    store: Store
    model: ModelClient
    fetcher: Fetcher
    snapshots: SnapshotStore
    max_sources: int = 3
    workers: int = 4
    # YouTube URL -> video title, so the bank is predicted for THIS video, not the topic in
    # general. None = off (tests, stub). Prod: youtube_title() below.
    video_title: Callable[[str], str] | None = None
    # Research fact bank (app/facts.py): checked first on every claim. None = off.
    facts: FactDesk | None = None


@dataclass
class Trace:
    """Why a cold check ended the way it did, returned on the live event: stage times in
    ms and, for a line with no card, the reason (no_evidence, low_support, fetch_failed,
    weak_sources_only, error). Replay 7dhIVHRKhvo: 4 of 6 lines failed with no reason."""

    stages: dict[str, int] = field(default_factory=dict)
    reason: str = ""
    skips: dict[str, int] = field(default_factory=dict)

    def add(self, stage: str, t0: float) -> None:
        self.stages[stage] = self.stages.get(stage, 0) + int((time.monotonic() - t0) * 1000)

    def skip(self, kind: str) -> None:
        self.skips[kind] = self.skips.get(kind, 0) + 1


# Sources an UNVERIFIABLE card may cite. A hard verdict is backed by its passage score; an
# UNVERIFIABLE card has no verdict to back, so its source is the whole value of the card
# and a law firm directory (legal500, replay 7dhIVHRKhvo) or a content farm is worse than
# no card. Official, international and established newsroom / fact checker hosts only.
_REPUTABLE_SUFFIXES = (
    ".gov",
    ".gov.in",
    ".nic.in",
    ".gov.uk",
    ".gc.ca",
    ".gov.au",
    ".int",
    ".europa.eu",
    ".edu",
    ".ac.in",
    ".ac.uk",
)
_REPUTABLE_HOSTS = frozenset(
    [
        "rbi.org.in",
        "sansad.in",
        "eci.gov.in",
        "imf.org",
        "worldbank.org",
        "un.org",
        "oecd.org",
        "wto.org",
        "who.int",
        "adb.org",
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "bbc.co.uk",
        "thehindu.com",
        "indianexpress.com",
        "hindustantimes.com",
        "livemint.com",
        "economictimes.indiatimes.com",
        "timesofindia.indiatimes.com",
        "business-standard.com",
        "ndtv.com",
        "indiatoday.in",
        "scroll.in",
        "thequint.com",
        "theprint.in",
        "thewire.in",
        "moneycontrol.com",
        "financialexpress.com",
        "deccanherald.com",
        "altnews.in",
        "boomlive.in",
        "factly.in",
        "factchecker.in",
        "newschecker.in",
        "vishvasnews.com",
        "politifact.com",
        "factcheck.org",
        "fullfact.org",
        "snopes.com",
        "nytimes.com",
        "washingtonpost.com",
        "wsj.com",
        "ft.com",
        "bloomberg.com",
        "cnbc.com",
        "cnn.com",
        "npr.org",
        "theguardian.com",
        "economist.com",
        "aljazeera.com",
        "dw.com",
        "pewresearch.org",
        "ourworldindata.org",
        "statista.com",
        "wikipedia.org",
    ]
)


def reputable(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return (
        host in _REPUTABLE_HOSTS
        or any(host.endswith("." + h) for h in _REPUTABLE_HOSTS)
        or host.endswith(_REPUTABLE_SUFFIXES)
    )


def youtube_title(url: str) -> str:  # pragma: no cover - network
    """Title via YouTube oEmbed (no key). Docs: https://oembed.com/ ; any error -> ""."""
    try:
        q = urllib.parse.urlencode({"url": url, "format": "json"})
        req = urllib.request.Request(
            f"https://www.youtube.com/oembed?{q}", headers={"User-Agent": "proofcard"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 - fixed https host
            return str(json.loads(r.read(200_000)).get("title", ""))[:200]
    except Exception:
        log.info("video title lookup failed", exc_info=True)
        return ""


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
    # "X is higher than Y" with no figure: proof is each side's figure, wherever on the
    # page it sits (tables), plus the line naming the metric. Either verdict direction.
    for q in [claim, a.claim_en]:
        if q and is_comparison(q):
            c = comparison_match(q, text)
            if c.score > score:
                passage, score = c.passage, c.score
    return passage, score


def _host(url: str) -> str:
    return urlsplit(url).hostname or "?"


def _skip(url: str, reason: str, **more: object) -> None:
    """One log line per dropped source, so a claim that ends as COULDN'T CHECK says why."""
    log.info(
        "source skipped", extra={"fields": {"host": _host(url), "reason": reason[:80], **more}}
    )


def fetch_all(
    evidence: list[Evidence],
    fetcher: Fetcher,
    budget_s: float = FETCH_BUDGET_S,
    trace: Trace | None = None,
) -> Iterator[tuple[Evidence, Fetched]]:
    """Sources in the model's order (best first), one at a time, under ONE budget for the
    whole card. Each fetch runs in a worker so a slow drip page can't outlive the budget.
    Sequential on purpose: the parallel version (#41) sent up to 8 requests at once
    through the grounding redirect host and the per capita comparison card stopped
    proving on prod (FAILED 3 of 3 vs FALSE before)."""
    deadline = time.monotonic() + budget_s
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fetch")
    try:
        for ev in evidence:
            left = deadline - time.monotonic()
            if left <= 0:
                _skip(ev.url, "fetch budget")
                if trace:
                    trace.skip("budget")
                continue
            fut: Future[Fetched] = pool.submit(fetcher.fetch, ev.url)
            try:
                yield ev, fut.result(timeout=left)
            except FetchError as exc:
                _skip(ev.url, str(exc))
                if trace:
                    trace.skip("fetch_error")
            except TimeoutError:
                _skip(ev.url, "fetch budget")
                if trace:
                    trace.skip("budget")
                pool.shutdown(wait=False, cancel_futures=True)
                pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fetch")
            except Exception as exc:  # one broken source never fails the card
                _skip(ev.url, type(exc).__name__)
                if trace:
                    trace.skip("fetch_error")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def build_card(
    claim: str, assessment: Assessment, deps: Deps, trace: Trace | None = None
) -> CardDoc | None:
    proofs: list[SourceProof] = []
    scores: list[float] = []
    seen: set[str] = set()
    # Official statistics first when the claim names a country figure (app/officialdata.py).
    official = official_evidence(claim, assessment.claim_en)
    known = {e.url for e in official}
    evidence = official + [e for e in assessment.evidence if e.url not in known]
    trace = trace if trace is not None else Trace()
    for ev, fetched in fetch_all(evidence, deps.fetcher, trace=trace):
        if len(proofs) >= deps.max_sources:
            break
        if fetched.final_url in seen:
            _skip(fetched.final_url, "duplicate")
            continue
        seen.add(fetched.final_url)
        if is_worldbank(fetched.final_url):
            text = render_official(fetched.body)
        else:
            text = extract_text(fetched.body, fetched.content_type)
        if not text:
            _skip(fetched.final_url, "no text", content_type=fetched.content_type)
            trace.skip("no_text")
            continue
        if is_worldbank(fetched.final_url) and (
            is_comparison(claim) or is_comparison(assessment.claim_en)
        ):
            # "X ka GDP Y se bada": both figures are the proof. A claim WITH a figure
            # ("8.2% now 7.4%") still has to match its number (replay 7dhIVHRKhvo showed a
            # 2025 growth row as proof of a 2022 IMF forecast).
            passage, score = official_proof(fetched.final_url, text)
        else:
            passage, score = support_for(claim, assessment, ev.model_snippet, text)
        if score < MIN_PASSAGE_SCORE or not passage:
            _skip(fetched.final_url, "low support", score=round(score, 3))
            trace.skip("low_support")
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
        if not evidence:
            trace.reason = "no_evidence"
        elif trace.skips.get("low_support"):
            trace.reason = "low_support"
        else:
            trace.reason = "fetch_failed"
        log.info(
            "no proof",
            extra={
                "fields": {
                    "evidence": len(evidence),
                    "model_verdict": str(assessment.verdict),
                }
            },
        )
        return None
    # The gate needs ONE snapshotted source that backs the verdict, not an average:
    # a second, weaker source used to drag a well proven TRUE claim under the gate
    # (prod verify rev00012: 10 of 11 brief claims ended UNVERIFIABLE, true ones too).
    verdict = gate_verdict(assessment.verdict, max(scores))
    if verdict == Verdict.UNVERIFIABLE:
        kept = [(p, sc) for p, sc in zip(proofs, scores, strict=True) if reputable(str(p.url))]
        if not kept:
            log.info("unverifiable on weak sources only, no card")
            trace.reason = "weak_sources_only"
            return None
        proofs, scores = [p for p, _ in kept], [sc for _, sc in kept]
    support = round(max(scores), 3)
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


def _attempt(text: str, hint: str, deps: Deps, trace: Trace, name: str) -> CardDoc | None:
    """One assess + proof pass. Stage times land in trace as <name>_assess / <name>_fetch."""
    t0 = time.monotonic()
    assessment = deps.model.assess(text, hint) if hint else deps.model.assess(text)
    trace.add(f"{name}_assess", t0)
    t1 = time.monotonic()
    try:
        return build_card(text, assessment, deps, trace)
    finally:
        trace.add(f"{name}_fetch", t1)


def _fact_attempt(
    text: str, key: str, deps: Deps, trace: Trace
) -> tuple[CardDoc | None, list[int]]:
    """Rule the line against the session's fact bank; a deciding ruling becomes a card
    citing those facts' pages, through the same proof gate as any card."""
    if deps.facts is None:
        return None, []
    t0 = time.monotonic()
    bank = deps.store.get_fact_bank(key)
    ruling: Ruling | None = deps.facts.rule(text, bank.facts) if bank and bank.facts else None
    trace.add("facts_rule", t0)
    if ruling is None or bank is None:
        trace.skip("no_fact")
        return None, []
    by_id = {f.id: f for f in bank.facts}
    chosen = [by_id[i] for i in ruling.fact_ids if i in by_id]
    evidence = [Evidence(str(f.source_url), f.angle, f.statement, 1.0) for f in chosen]
    t1 = time.monotonic()
    try:
        card = build_card(
            text,
            Assessment(ruling.verdict, ruling.explanation, evidence, ruling.claim_en),
            deps,
            trace,
        )
    finally:
        trace.add("facts_fetch", t1)
    return (card, [f.id for f in chosen]) if card else (None, [])


def verify_claim(
    session_id: str,
    claim_id: str,
    deps: Deps,
    trace: Trace | None = None,
    race_hint: bool = False,
) -> str | None:
    """Check one stored claim end to end. Returns the card id or None.

    Plain check first, exactly as before #50: the speaker-country hint only ever adds a
    card, never replaces one (hint on every call, #50, cut bank fill to 4/12). Bank
    (race_hint=False): hinted pass only after the plain one found no proof. Live
    (race_hint=True): both start together, plain still wins when it proves, so a line
    that needs the hint costs one pass, not two in a row (replay: 108 to 145 s)."""
    trace = trace if trace is not None else Trace()
    claim = deps.store.get_claim(session_id, claim_id)
    if claim is None:
        return None
    deps.store.update_claim(session_id, claim_id, status=ClaimStatus.CHECKING)
    fact_ids: list[int] = []
    try:
        session = deps.store.get_session(session_id)
        hint = search_hint(session.speaker if session else "", claim.text)
        card = None
        if session is not None and session.fact_bank_key:
            card, fact_ids = _fact_attempt(claim.text, session.fact_bank_key, deps, trace)
        if card is None and race_hint and hint:
            plain_t, hint_t = Trace(), Trace()
            pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="race")
            try:
                plain = pool.submit(_attempt, claim.text, "", deps, plain_t, "plain")
                hinted = pool.submit(_attempt, claim.text, hint, deps, hint_t, "hint")
                card = _result(plain)
                used = plain_t
                if card is None:
                    card, used = _result(hinted), hint_t
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            trace.stages.update(plain_t.stages)
            trace.stages.update(hint_t.stages)
            trace.reason = used.reason or plain_t.reason
            trace.skips = used.skips
        elif card is None:
            card = _attempt(claim.text, "", deps, trace, "plain")
            if card is None and hint:
                first = trace.reason
                card = _attempt(claim.text, hint, deps, trace, "hint")
                trace.reason = trace.reason or first
    except Exception:
        log.exception("verify failed")
        trace.reason = "error"
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
        fact_ids=fact_ids,
    )
    return card_id


def _result(fut: Future[CardDoc | None]) -> CardDoc | None:
    try:
        return fut.result()
    except Exception:
        log.exception("verify attempt failed")
        return None


def _predict(
    deps: Deps, topic: str, speaker: str, n: int, base_topic: str = ""
) -> list[PredictedClaim]:
    """First prediction that answers, in order: topic (+ video title) with speaker, the bare
    topic with speaker, the bare topic alone. Prod 16 Oct 2026: Trump hung predict_claims
    (280 s, #53), and with the 40 s cap 2 of 3 Sitharaman replay briefs then failed outright
    (0 claims). A slow attempt costs the extra angle, never the whole brief."""
    tries = list(
        dict.fromkeys([(topic, speaker), (base_topic or topic, speaker), (base_topic or topic, "")])
    )
    for i, (t, sp) in enumerate(tries):
        try:
            return deps.model.predict_claims(t, sp, n)
        except Exception:
            if i == len(tries) - 1:
                raise
            log.warning(
                "prediction failed, next fallback", extra={"fields": {"try": i}}, exc_info=True
            )
    raise AssertionError("unreachable")


def _with_fact_bank(session_id: str, session: SessionDoc, deps: Deps, desk: FactDesk) -> SessionDoc:
    """Attach the topic + speaker fact bank (reused when fresh) before any claim is
    checked, so the brief bank is ruled against it too. A research failure costs the
    bank, never the brief."""
    about = session.topic
    if session.youtube_url and deps.video_title is not None:
        title = deps.video_title(session.youtube_url)
        about = f"{about}. Video: {title}" if title else about
    try:
        key = ensure_bank(deps.store, desk, deps.fetcher, session.topic, session.speaker, about)
    except Exception:
        log.exception("fact bank failed, brief continues without it")
        return session
    if key is None:
        return session
    deps.store.update_session(session_id, fact_bank_key=key)
    return deps.store.get_session(session_id) or session


def run_prebunk(session_id: str, deps: Deps, n: int = 12) -> dict[str, int]:
    """Build the brief bank. Never leaves a session stuck in "prebunking": a model failure
    ends it as "failed" (the UI says so). Idempotent: a Cloud Tasks retry (instance died,
    deadline hit) finishes the same bank instead of adding a second one."""
    session = deps.store.get_session(session_id)
    if session is None:
        return {"predicted": 0, "proved": 0}
    deps.store.update_session(session_id, status="prebunking")
    if deps.facts is not None and not session.fact_bank_key:
        session = _with_fact_bank(session_id, session, deps, deps.facts)
    bank = [
        (cid, c)
        for cid, c in deps.store.list_claims(session_id)
        if c.source == ClaimSource.PREDICTED
    ]
    if not bank:
        try:
            topic = session.topic
            if session.youtube_url and deps.video_title is not None:
                title = deps.video_title(session.youtube_url)
                if title:
                    topic = f"{topic}. Video being fact checked: {title}"
            predicted = _predict(deps, topic, session.speaker, n, session.topic)
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
