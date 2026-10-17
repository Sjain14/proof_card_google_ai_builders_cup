"""p56: a card shows only sources that prove the claim on their own (sample brief review,
17 Oct: eight wars card proved by a World War I inflation line; an unrelated third source)."""

from app.pipeline import build_card
from app.proof import best_contradiction, match_passage
from app.schemas import Verdict
from app.store import InMemoryStore
from tests.test_pipeline import FakeModel, MapFetcher, deps

EIGHT_WARS = "I settled eight different wars during my presidency."
INFLATION = (
    "And by some estimates, inflation approached 20% during World War I. Inflation had been "
    "falling during the first few months of Trump's presidency."
)


def test_a_number_about_something_else_is_not_a_contradiction() -> None:
    assert not match_passage(EIGHT_WARS, INFLATION).conflict
    assert best_contradiction(EIGHT_WARS, INFLATION).passage == ""


def test_a_count_of_the_same_thing_still_contradicts() -> None:
    assert match_passage(
        "India has 40 states", "India has 28 states and 8 union territories."
    ).conflict
    assert (
        match_passage(EIGHT_WARS, "Experts count two wars that actually ended, not eight.").conflict
        is False
    )
    assert match_passage(EIGHT_WARS, "Analysts found only 3 wars were settled.").conflict
    assert match_passage("Inflation hit 9.1 percent", "Inflation was 6.2 percent in May.").conflict


def test_eight_wars_card_is_not_proved_by_the_inflation_page() -> None:
    page = f"<p>{INFLATION}</p>"
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.FALSE, ["https://news.example/a"]),
        MapFetcher({"https://news.example/a": page}),
    )
    card = build_card(EIGHT_WARS, d.model.assess(""), d)
    assert card is None or card.verdict is Verdict.UNVERIFIABLE


def test_a_hard_verdict_drops_a_weaker_extra_source() -> None:
    strong = "<p>The Eighth Schedule lists 22 languages of India today.</p>"
    weak = "<p>At Davos, talk of Greenland and the Eighth Schedule of India went on.</p>"
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.TRUE, ["https://x.gov/a", "https://x.gov/b"]),
        MapFetcher({"https://x.gov/a": strong, "https://x.gov/b": weak}),
    )
    card = build_card("India has 22 languages in the Eighth Schedule", d.model.assess(""), d)
    assert card is not None
    assert card.verdict is Verdict.TRUE
    assert [str(s.url) for s in card.sources] == ["https://x.gov/a"]
