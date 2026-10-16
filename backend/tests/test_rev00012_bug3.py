"""Bug 3 of the rev00012 prod verify (16 Oct 2026): no live line matched the brief."""

from typing import Any

import httpx

from app.factcheck import FactCheckClient, FactCheckedModel, Review, rated_claims
from app.model import Assessment, PredictedClaim
from app.schemas import Verdict

# ---------- bug 3: no live line matched the brief ----------

RATED: dict[str, Any] = {
    "claims": [
        {
            "text": "We have the worst inflation in 48 years, perhaps in history",
            "claimant": "Donald Trump",
            "claimReview": [
                {
                    "publisher": {"name": "FactCheck.org"},
                    "url": "https://www.factcheck.org/2025/03/a",
                    "textualRating": "False",
                }
            ],
        },
        {
            "text": "Biden closed more than 100 power plants",
            "claimant": "President Trump",
            "claimReview": [{"url": "https://www.politifact.com/b", "textualRating": "False"}],
        },
        {
            "text": "Somebody else said a thing with numbers 12",
            "claimant": "Kamala Harris",
            "claimReview": [{"url": "https://www.politifact.com/c", "textualRating": "True"}],
        },
    ]
}


class Inner:
    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]:
        return [PredictedClaim(f"model guess {i} with 1{i} percent") for i in range(n)]

    def assess(self, claim: str) -> Assessment:
        return Assessment(Verdict.UNVERIFIABLE, "x", [], claim_en=claim)


def fc(data: Any, seen: list[httpx.Request] | None = None) -> FactCheckClient:
    def h(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(req)
        return httpx.Response(200, json=data)

    return FactCheckClient("k", transport=httpx.MockTransport(h))


def test_bank_starts_with_the_speakers_rated_claims() -> None:
    seen: list[httpx.Request] = []
    m = FactCheckedModel(Inner(), fc(RATED, seen))
    bank = m.predict_claims("address to Congress", "Donald Trump", 6)
    assert len(bank) == 6
    assert bank[0].text.startswith("We have the worst inflation in 48 years")
    assert bank[1].text == "Biden closed more than 100 power plants"
    assert "FactCheck.org" in bank[0].why
    assert all("Somebody else" not in c.text for c in bank)
    assert seen[0].url.params["query"] == "Donald Trump address to Congress"


def test_seeds_are_capped_at_half_and_no_hits_keep_the_model_list() -> None:
    m = FactCheckedModel(Inner(), fc(RATED))
    assert sum(c.text.startswith("model") for c in m.predict_claims("t", "Donald Trump", 2)) == 1
    empty = FactCheckedModel(Inner(), fc({}))
    assert [c.text for c in empty.predict_claims("t", "Donald Trump", 3)] == [
        c.text for c in Inner().predict_claims("t", "Donald Trump", 3)
    ]


def test_rated_claims_language_and_dedup() -> None:
    r = Review("https://x.in/a", "BOOM", "False", "भारत में 25 भाषाएं हैं संविधान में", "Narendra Modi")
    dup = Review("https://x.in/b", "Alt News", "False", "भारत में 25 भाषाएं हैं संविधान में", "Modi")
    got = rated_claims([r, dup], "Narendra Modi", 5)
    assert len(got) == 1
    assert got[0].lang == "hi"
