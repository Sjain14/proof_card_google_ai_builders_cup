"""Fact Check Tools API lookup on httpx.MockTransport (no network, no key)."""

from typing import Any

import httpx

from app.factcheck import FactCheckClient, FactCheckedModel, parse_reviews
from app.model import Assessment, Evidence, PredictedClaim
from app.schemas import Verdict

SAMPLE: dict[str, Any] = {
    "claims": [
        {
            "text": "India has 25 languages in the Eighth Schedule",
            "claimReview": [
                {
                    "publisher": {"name": "BOOM", "site": "boomlive.in"},
                    "url": "https://www.boomlive.in/fact-check/22-languages",
                    "textualRating": "False",
                },
                {"url": "http://insecure.example/x", "textualRating": "False"},
            ],
        },
        {
            "text": "same claim, other checker",
            "claimReview": [
                {
                    "publisher": {"site": "altnews.in"},
                    "url": "https://www.altnews.in/22",
                    "textualRating": "Misleading",
                },
                {"url": "https://www.boomlive.in/fact-check/22-languages"},  # duplicate
                {"url": "https://third.example/a"},
            ],
        },
        "junk",
    ]
}


def client(handler: Any) -> FactCheckClient:
    return FactCheckClient("test-key", transport=httpx.MockTransport(handler))


def test_parse_reviews_keeps_https_dedups_and_caps() -> None:
    got = parse_reviews(SAMPLE)
    assert [r.url for r in got] == [
        "https://www.boomlive.in/fact-check/22-languages",
        "https://www.altnews.in/22",
    ]
    assert (got[0].publisher, got[0].rating) == ("BOOM", "False")
    assert got[1].publisher == "altnews.in"
    assert parse_reviews([]) == []
    assert parse_reviews({"claims": "x"}) == []


def test_search_sends_key_in_header_not_url() -> None:
    seen: list[httpx.Request] = []

    def h(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=SAMPLE)

    assert len(client(h).search("India 25 languages")) == 2
    req = seen[0]
    assert req.url.host == "factchecktools.googleapis.com"
    assert req.headers["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(req.url)
    assert req.url.params["query"] == "India 25 languages"


def test_search_failures_mean_no_prior_checks() -> None:
    assert client(lambda _r: httpx.Response(403, json={})).search("x") == []
    assert client(lambda _r: httpx.Response(200, text="not json")).search("x") == []

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=req)

    assert client(boom).search("x") == []


class Inner:
    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]:
        return [PredictedClaim("c")]

    def assess(self, claim: str) -> Assessment:
        return Assessment(
            Verdict.FALSE,
            "why",
            [Evidence("https://www.altnews.in/22"), Evidence("https://en.wikipedia.org/x")],
            claim_en=claim,
        )


def test_reviews_come_first_and_verdict_stays_with_the_model() -> None:
    m = FactCheckedModel(Inner(), client(lambda _r: httpx.Response(200, json=SAMPLE)))
    a = m.assess("India has 25 languages")
    assert [e.url for e in a.evidence] == [
        "https://www.boomlive.in/fact-check/22-languages",
        "https://www.altnews.in/22",
        "https://en.wikipedia.org/x",
    ]
    assert a.evidence[0].title == "BOOM: False"
    assert a.verdict is Verdict.FALSE
    assert a.claim_en == "India has 25 languages"
    assert m.predict_claims("t", "s", 1) == [PredictedClaim("c")]
    empty = FactCheckedModel(Inner(), client(lambda _r: httpx.Response(200, json={})))
    assert len(empty.assess("x").evidence) == 2
