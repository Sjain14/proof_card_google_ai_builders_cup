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

    def search(self, claim: str) -> list[Review]:
        """Best effort: any failure means "no prior fact checks", never a failed claim."""
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as c:
                r = c.get(
                    ENDPOINT,
                    params={"query": claim[:300], "pageSize": 5},
                    # Header, not ?key=, so the key never lands in URLs or access logs.
                    headers={"X-Goog-Api-Key": self.api_key},
                )
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.info("fact check lookup skipped", extra={"fields": {"reason": type(exc).__name__}})
            return []
        return parse_reviews(data)


def parse_reviews(data: Any) -> list[Review]:
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
                )
            )
    return out[:MAX_REVIEWS]


class FactCheckedModel:
    """ModelClient wrapper: prior fact check articles first, then grounding evidence."""

    def __init__(self, inner: ModelClient, client: FactCheckClient) -> None:
        self.inner = inner
        self.client = client

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]:
        return self.inner.predict_claims(topic, speaker, n)

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
