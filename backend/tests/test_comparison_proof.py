"""Prod 16 Oct (brief sMHV3ThmpAigYXsuXqpsZQ, 4e59b1f): "India per capita GDP is higher
than Japan." The model said FALSE with the IMF figures (Japan $35,700, India $2,810), but
the best 2 sentence window on worldometers scored 0.429 and the faithfulness gate turned the
card UNVERIFIABLE. The Hinglish line found no source over 0.35 and ended `failed`.
A source proves a comparison by stating both figures (here: table rows 90 lines apart,
metric in the heading), never by repeating "higher than"."""

from app.pipeline import build_card
from app.proof import comparison_match, is_comparison, reports_claim
from app.schemas import Verdict
from app.store import InMemoryStore
from tests.test_pipeline import FakeModel, MapFetcher, deps

# Shape of the real page after extract_text: caption, then one row per country.
ROWS = "\n".join(
    f"| {i} | Country{i} | ${90_000 - i * 300:,} | {200 - i}% |" for i in range(1, 140)
)
TABLE = (
    "GDP per Capita by Country (2026)\n"
    "- GDP per Capita represents the total monetary value of all goods and services produced "
    "within a country over one year, divided by its population.\n"
    + ROWS.replace("Country43", "Japan").replace("Country133", "India")
)
PAGE = "<pre>" + TABLE + "</pre>"
EN = "India per capita GDP is higher than Japan."
HINGLISH = "India ka per capita GDP Japan se zyada hai"


def test_comparison_is_spotted_in_every_script() -> None:
    assert is_comparison(EN)
    assert is_comparison(HINGLISH)
    assert is_comparison("भारत की प्रति व्यक्ति जीडीपी जापान से ज़्यादा है")
    assert is_comparison("India's GDP is ahead of Japan's")
    assert not is_comparison("India per capita GDP is higher than 3000 dollars")  # has a figure
    assert not is_comparison("Japan has the largest economy")  # superlative, no other side


def test_both_sides_and_the_metric_are_found_far_apart() -> None:
    for q in (EN, HINGLISH, "India's per capita GDP is higher than Japan's."):
        m = comparison_match(q, TABLE)
        assert m.score == 1.0, q
        assert "| Japan |" in m.passage
        assert "| India |" in m.passage
        assert "GDP per Capita" in m.passage


def test_one_side_only_is_not_proof() -> None:
    one_side = TABLE.replace("| Japan |", "| Country43 |")
    assert comparison_match(EN, one_side).score == 0.0
    assert comparison_match(EN, "India and Japan are both in Asia.").score == 0.0
    assert comparison_match("than", TABLE).score == 0.0  # nothing but relation words


def test_false_comparison_keeps_its_verdict() -> None:
    for claim in (EN, HINGLISH):
        d = deps(
            InMemoryStore(),
            FakeModel(Verdict.FALSE, ["https://w/gdp"]),
            MapFetcher({"https://w/gdp": PAGE}),
        )
        card = build_card(claim, d.model.assess(claim), d)
        assert card is not None, claim  # was: no source over 0.35 -> `failed`
        assert card.verdict is Verdict.FALSE, claim  # was: UNVERIFIABLE (0.429 < 0.6)
        assert card.support_score == 1.0
        assert "| India |" in card.sources[0].snippet


def test_a_number_claim_is_untouched() -> None:
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.FALSE, ["https://w/gdp"]),
        MapFetcher({"https://w/gdp": PAGE}),
    )
    card = build_card("India per capita GDP is 99,999 dollars", d.model.assess(""), d)
    assert card is None or card.support_score < 1.0


def test_both_sides_in_one_sentence() -> None:
    page = (
        "According to the IMF, Japan's nominal GDP per capita is estimated at $35,700, "
        "while India's per capita GDP is $2,810 in 2026."
    )
    for q in (EN, HINGLISH):
        m = comparison_match(q, page)
        assert m.score == 1.0, q
        assert "$2,810" in m.passage
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.FALSE, ["https://w/one"]),
        MapFetcher({"https://w/one": f"<p>{page}</p>"}),
    )
    card = build_card(EN, d.model.assess(EN), d)
    assert card is not None
    assert card.verdict is Verdict.FALSE
    # one side named, one figure: still not proof
    assert comparison_match(EN, "India's per capita GDP is $2,810, below Japan.").score < 1.0


def test_reports_claim_spots_the_speaker_relayed_not_the_fact() -> None:
    claim = "I got all the hostages back"
    assert reports_claim(claim, 'Trump said, "I got all the hostages back," at the rally.')
    assert reports_claim(claim, "Trump said he got all the hostages back from Gaza.")
    assert reports_claim(claim, "He claimed every hostage was home.")
    # independent statements of the fact pass
    assert not reports_claim(claim, "Hamas released all 20 living hostages on 13 October.")
    assert not reports_claim(
        "We grew at 8.2 per cent", "The NSO said real GDP grew 8.2 per cent in 2023-24."
    )
    assert not reports_claim("", "Trump said he did it.")


def test_true_card_never_rests_on_a_quote_of_the_speaker() -> None:
    quote = "<p>Trump said he got all the hostages back, speaking at the rally on Monday.</p>"
    fact = "<p>All the hostages were back in Israel after Hamas released them, officials said.</p>"
    claim = "I got all the hostages back"
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.TRUE, ["https://w/q"]),
        MapFetcher({"https://w/q": quote}),
    )
    card = build_card(claim, d.model.assess(claim), d)
    assert card is None or card.verdict is not Verdict.TRUE
    d = deps(
        InMemoryStore(), FakeModel(Verdict.TRUE, ["https://w/f"]), MapFetcher({"https://w/f": fact})
    )
    card = build_card(claim, d.model.assess(claim), d)
    assert card is not None
    assert card.verdict is Verdict.TRUE
