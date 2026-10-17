"""p57: a fact plus a judgment is proven only in part (sample brief review, 17 Oct: the
Iran card went TRUE on proof of the withdrawal alone)."""

from app.model import ASSESS_PROMPT, Assessment
from app.pipeline import build_card
from app.proof import opinion_words
from app.schemas import Verdict
from app.store import InMemoryStore
from tests.test_pipeline import FakeModel, MapFetcher, deps

IRAN = (
    "I withdrew the United States from the disastrous Iran Nuclear Deal, which was the "
    "worst deal ever negotiated."
)
WIKI = (
    "<p>On 8 May 2018, the United States withdrew from the Iran Nuclear Deal, formally "
    "the Joint Comprehensive Plan of Action, and the United States reimposed sanctions.</p>"
)


def test_opinion_words_found_in_order() -> None:
    assert opinion_words(IRAN) == ["disastrous", "worst"]
    assert opinion_words("India has 28 states") == []
    assert opinion_words("Inflation hit the highest level in 40 years") == []  # a fact


def test_fact_plus_judgment_is_partly_proven_not_true() -> None:
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.TRUE, ["https://en.wikipedia.org/wiki/x"]),
        MapFetcher({"https://en.wikipedia.org/wiki/x": WIKI}),
    )
    a = d.model.assess("")
    # the model restates the claim; its fact part is what the page proves
    a = Assessment(
        a.verdict,
        a.explanation,
        a.evidence,
        "The United States withdrew from the Iran Nuclear Deal",
    )
    card = build_card(IRAN, a, d)
    assert card is not None
    assert card.verdict is Verdict.UNVERIFIABLE
    assert card.explanation.startswith("Partly proven:")
    assert '"worst"' in card.explanation
    assert card.sources  # the withdrawal proof is still shown


def test_a_false_fact_with_a_judgment_stays_false() -> None:
    page = "<p>The United States never withdrew from the Iran Nuclear Deal in 2019.</p>"
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.FALSE, ["https://en.wikipedia.org/wiki/y"]),
        MapFetcher({"https://en.wikipedia.org/wiki/y": page}),
    )
    card = build_card("We left the disastrous Iran Nuclear Deal in 2019", d.model.assess(""), d)
    assert card is None or card.verdict is not Verdict.TRUE


def test_prompt_asks_for_every_part() -> None:
    assert "EVERY part is proven" in ASSESS_PROMPT
