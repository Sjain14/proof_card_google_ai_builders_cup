"""Google Fact Check Tools API: existing fact checks first (plan A3).

If a recognised fact checker (BOOM, Alt News, PIB Fact Check, AFP ...) already reviewed
a claim, its article is the strongest source we can show. We add those review URLs ahead
of the grounding evidence. They go through the same pipeline as every other source: our
own fetch, passage match, sha256 snapshot, faithfulness gate. The model still writes the
verdict; the review's rating is only a hint in the snippet we match on.

Off unless PC_FACTCHECK_API_KEY is set (a Google Cloud API key restricted to this API).
Docs: https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/search
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Any

import httpx

from app.model import Assessment, Evidence, ModelClient, PredictedClaim

log = logging.getLogger("proofcard.factcheck")

ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
MAX_REVIEWS = 2


@dataclass(frozen=True)
class Review:
    url: str
    publisher: str
    rating: str
    claim_text: str
    claimant: str = ""


class FactCheckClient:
    def __init__(
        self,
        api_key: str,
        timeout: float = 4.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport  # tests inject httpx.MockTransport

    def search(self, claim: str, page_size: int = 5, limit: int = MAX_REVIEWS) -> list[Review]:
        """Best effort: any failure means "no prior fact checks", never a failed claim."""
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as c:
                r = c.get(
                    ENDPOINT,
                    params={"query": claim[:300], "pageSize": page_size},
                    # Header, not ?key=, so the key never lands in URLs or access logs.
                    headers={"X-Goog-Api-Key": self.api_key},
                )
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.info("fact check lookup skipped", extra={"fields": {"reason": type(exc).__name__}})
            return []
        return parse_reviews(data, limit)


def parse_reviews(data: Any, limit: int = MAX_REVIEWS) -> list[Review]:
    out: list[Review] = []
    seen: set[str] = set()
    claims = data.get("claims", []) if isinstance(data, dict) else []
    for cl in claims if isinstance(claims, list) else []:
        if not isinstance(cl, dict):
            continue
        for rv in cl.get("claimReview") or []:
            url = str(rv.get("url", "")) if isinstance(rv, dict) else ""
            if not url.startswith("https://") or url in seen:
                continue
            seen.add(url)
            pub = rv.get("publisher") or {}
            out.append(
                Review(
                    url=url,
                    publisher=str(pub.get("name") or pub.get("site") or "")[:100],
                    rating=str(rv.get("textualRating", ""))[:100],
                    claim_text=str(cl.get("text", ""))[:500],
                    claimant=str(cl.get("claimant", ""))[:100],
                )
            )
    return out[:limit]


def _said_by(review: Review, speaker: str) -> bool:
    """The review's claimant is this speaker: any name part of 4+ letters in common."""
    parts = {w for w in re.findall(r"[a-z]+", speaker.lower()) if len(w) >= 4}
    return bool(parts & set(re.findall(r"[a-z]+", review.claimant.lower())))


def _lang(text: str) -> str:
    return "hi" if re.search(r"[\u0900-\u097F]", text) else "en"


def rated_claims(reviews: list[Review], speaker: str, n: int) -> list[PredictedClaim]:
    """Claims this speaker really said that a fact checker already rated, as quoted
    in the review. These are the lines most likely to be repeated on air (bug 3 of
    the rev00012 prod verify: no live line matched the brief, because the bank only
    held the model's guesses)."""
    out: list[PredictedClaim] = []
    seen: set[str] = set()
    for r in reviews:
        text = r.claim_text.strip().strip('"“”')
        key = text.lower()
        if len(text) < 15 or key in seen or not _said_by(r, speaker):
            continue
        seen.add(key)
        why = f"already rated {r.rating} by {r.publisher}".strip()
        out.append(PredictedClaim(text=text, lang=_lang(text), why=why[:200]))
        if len(out) >= n:
            break
    return out


class FactCheckedModel:
    """ModelClient wrapper: prior fact check articles first, then grounding evidence."""

    def __init__(self, inner: ModelClient, client: FactCheckClient) -> None:
        self.inner = inner
        self.client = client

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]:
        """Up to half the bank = the speaker's own already fact checked claims on this
        topic (then on anything), the rest = the model's predictions. No key or no hits
        = the model's list unchanged."""
        seeds: list[PredictedClaim] = []
        if speaker.strip():
            for query in (f"{speaker} {topic}", speaker):
                found = self.client.search(query[:300], page_size=30, limit=30)
                seeds = rated_claims(found, speaker, n // 2)
                if seeds:
                    break
        model = self.inner.predict_claims(topic, speaker, n)
        known = {s.text.lower() for s in seeds}
        merged = seeds + [p for p in model if p.text.lower() not in known]
        log.info("bank seeded", extra={"fields": {"rated": len(seeds), "model": len(model)}})
        return merged[:n]

    def assess(self, claim: str) -> Assessment:
        a = self.inner.assess(claim)
        reviews = self.client.search(claim)
        if not reviews:
            return a
        prior = [
            Evidence(
                url=r.url,
                title=f"{r.publisher}: {r.rating}".strip(": "),
                model_snippet=r.claim_text,
                confidence=1.0,
            )
            for r in reviews
        ]
        known = {r.url for r in reviews}
        return replace(a, evidence=prior + [e for e in a.evidence if e.url not in known])
