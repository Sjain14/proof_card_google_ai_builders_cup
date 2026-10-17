"""p58: "did X actually say it" runs for every way a line puts words in a named person's
mouth (prod bot 17 Oct: "Narendra Modi said India became the world's fourth largest
economy in 2025" skipped the attribution check; only the number was checked)."""

import pytest

from app.live import IMAGE_PROMPT, SPOT_PROMPT
from app.pipeline import CACHE_VERSION
from app.quotes import attribution, surname
from app.schemas import Verdict
from tests.test_quotes import _content_card

MODI = "Narendra Modi said India became the world's fourth largest economy in 2025."


@pytest.mark.parametrize(
    ("text", "who", "quote"),
    [
        (MODI, "Narendra Modi", "India became the world's fourth largest economy in 2025"),
        (
            "PM Modi claims India has the fastest growing economy",
            "PM Modi",
            "India has the fastest growing economy",
        ),
        (
            "Modi ji said India is the third largest economy",
            "Modi ji",
            "India is the third largest economy",
        ),
        (
            "According to Nirmala Sitharaman, GST collections hit a record high",
            "Nirmala Sitharaman",
            "GST collections hit a record high",
        ),
        (
            "Modi ji ke mutabik bharat teesri sabse badi economy hai",
            "Modi ji",
            "bharat teesri sabse badi economy hai",
        ),
    ],
)
def test_more_attribution_forms(text: str, who: str, quote: str) -> None:
    a = attribution(text)
    assert a is not None
    assert (a.speaker, a.quote) == (who, quote)


@pytest.mark.parametrize(
    "text",
    [
        "The report said inflation fell to 4 percent last year",
        "The Government said exports rose 5 percent in March",
        "Experts said the economy grew 7 percent this year",
        "India has 40 states.",
    ],
)
def test_still_not_an_attribution(text: str) -> None:
    assert attribution(text) is None


def test_surname_skips_honorifics() -> None:
    assert surname("Modi ji") == "modi"
    assert surname("PM Modi") == "modi"


def test_a_bare_modi_line_with_no_record_is_never_true() -> None:
    out = _content_card(Verdict.TRUE, MODI)
    assert out.verdict is Verdict.UNVERIFIABLE
    assert out.explanation.startswith("Unproven quote: no record of Narendra Modi")


def test_spotters_keep_the_speaker() -> None:
    assert "Keep who said it" in SPOT_PROMPT
    assert "WITH the name" in IMAGE_PROMPT


def test_cache_version_bumped() -> None:
    assert CACHE_VERSION == "v4"
