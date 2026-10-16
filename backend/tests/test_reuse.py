from datetime import UTC, datetime, timedelta

from app.live import HashEmbedder
from app.model import StubModel
from app.pipeline import Deps, Trace, claim_key, verify_claim
from app.proof import FixtureFetcher, InMemorySnapshots
from app.reuse import SimilarCards, negated
from app.schemas import (
    CardDoc,
    ClaimDoc,
    ClaimSource,
    ClaimStatus,
    SessionDoc,
    SourceProof,
    Verdict,
)
from app.store import InMemoryStore


class Fixed:
    """Cosine set by a lookup table on the query text; stored texts embed to [1, 0]."""

    def __init__(self, sims: dict[str, float]) -> None:
        self.sims = sims

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            s = self.sims.get(t, 1.0)
            out.append([s, (1 - s * s) ** 0.5])
        return out


class Judge:
    def __init__(self, same: bool) -> None:
        self.same, self.calls = same, 0

    def same_claim(self, heard: str, checked: str) -> bool:
        self.calls += 1
        return self.same


SAID = "India is the fourth largest economy in 2025"


def card(text: str = SAID) -> CardDoc:
    return CardDoc(
        card_sha256="b" * 64,
        claim=text,
        verdict=Verdict.TRUE,
        explanation="why",
        sources=[
            SourceProof(
                url="https://example.org/a",
                snippet="India is the fourth largest economy",
                snapshot_sha256="a" * 64,
                fetched_at=datetime.now(UTC),
            )
        ],
        support_score=0.9,
    )


def seeded(sims: dict[str, float], judge: Judge | None = None, ctx: str = "") -> SimilarCards:
    store = InMemoryStore()
    store.put_card("card-1", card())
    store.put_claim_card(claim_key(SAID, ctx), "card-1", SAID, ctx)
    sim = SimilarCards(store, Fixed(sims), judge)
    sim.refresh()
    return sim


def test_same_claim_in_other_words_reuses_the_card() -> None:
    q = "In 2025 India became the world's fourth largest economy"
    sim = seeded({q: 0.98})
    assert len(sim) == 1
    assert sim.lookup(q, "") == ("card-1", 0.98)


def test_other_numbers_never_reuse() -> None:
    q = "India is the third largest economy in 2025"
    assert seeded({q: 0.99}).lookup(q, "") is None


def test_negation_never_reuses() -> None:
    q = "India is not the fourth largest economy in 2025"
    assert negated(q)
    assert not negated(SAID)
    assert seeded({q: 0.99}).lookup(q, "") is None


def test_gray_zone_asks_the_judge() -> None:
    q = "India ranks fourth among economies in 2025"
    yes, no = Judge(True), Judge(False)
    assert seeded({q: 0.85}, yes).lookup(q, "") == ("card-1", 0.85)
    assert seeded({q: 0.85}, no).lookup(q, "") is None
    assert yes.calls == no.calls == 1
    assert seeded({q: 0.85}).lookup(q, "") is None  # no judge: only the direct bar


def test_far_claims_never_reach_the_judge() -> None:
    q = "India grows at 2025 pace in fourth quarter"
    j = Judge(True)
    assert seeded({q: 0.5}, j).lookup(q, "") is None
    assert j.calls == 0


def test_speech_reuses_its_own_and_bot_cards_only() -> None:
    q = "In 2025 India became the world's fourth largest economy"
    other = seeded({q: 0.99}, ctx="https://youtu.be/other")
    assert other.lookup(q, "https://youtu.be/this") is None
    assert other.lookup(q, "") is not None  # the bot reuses any
    assert seeded({q: 0.99}).lookup(q, "https://youtu.be/this") is not None


def test_old_cards_are_not_indexed() -> None:
    store = InMemoryStore()
    store.put_claim_card("k", "card-1", SAID, "")
    store.claim_cards["k"] = ("card-1", datetime.now(UTC) - timedelta(days=8))
    sim = SimilarCards(store, HashEmbedder())
    sim.refresh()
    assert len(sim) == 0


def test_lookup_before_any_refresh_never_blocks() -> None:
    sim = SimilarCards(InMemoryStore(), HashEmbedder())
    assert sim.lookup(SAID, "") is None


def test_pipeline_reuses_a_similar_card_without_a_check() -> None:
    q = "In 2025 India became the world's fourth largest economy"
    store = InMemoryStore()
    store.put_card("card-1", card())
    store.put_claim_card(claim_key(SAID), "card-1", SAID, "")
    similar = SimilarCards(store, Fixed({q: 0.99}))
    similar.refresh()
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots(), similar=similar)
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    cid = store.add_claim(sid, ClaimDoc(text=q, source=ClaimSource.LIVE))
    t = Trace()
    assert verify_claim(sid, cid, deps, t) == "card-1"
    claim = store.get_claim(sid, cid)
    assert claim is not None
    assert claim.status == ClaimStatus.PROVED
    assert t.reason == "cache"


def test_proved_card_is_added_to_the_index() -> None:
    store = InMemoryStore()
    similar = SimilarCards(store, HashEmbedder())
    similar.add("k", SAID, "", "card-9")
    hit = similar.lookup(SAID, "")
    assert hit is not None
    assert hit[0] == "card-9"
    rows = store.recent_claim_cards(datetime.now(UTC) - timedelta(days=1), 10)
    assert rows == []  # add() is index-only; the pipeline writes the store row
