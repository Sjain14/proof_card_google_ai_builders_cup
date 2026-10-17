"""Hindi conjuncts and matras are shaped (libraqm), so "दिल्ली" never draws as "दलि्ली"."""

from __future__ import annotations

from PIL import ImageFont, features

from app import alter
from app.card_image import BANDS, encode, font, render
from tests.test_card_glyphs import BASE, CARD_ID, _card

WORDS = ("दिल्ली", "प्रदर्शन", "छात्रों")
GOYAL_CLAIM = "पीयूष गोयल ने कहा कि दिल्ली में छात्रों का प्रदर्शन सबसे अच्छा रहा"
GOYAL_EXPL = "आधिकारिक आंकड़े यह नहीं दिखाते, दावा गलत है"


def test_shaping_engine_present() -> None:
    # Same check the deploy image runs: without libraqm Pillow silently falls back.
    assert features.check("raqm")


def test_devanagari_font_uses_raqm_latin_stays_basic() -> None:
    assert font(50, "SemiBold", True).layout_engine == ImageFont.Layout.RAQM
    assert font(50, "SemiBold", True, shaped=False).layout_engine == ImageFont.Layout.BASIC
    assert font(50, "SemiBold").layout_engine == ImageFont.Layout.BASIC


def test_conjuncts_are_shaped() -> None:
    shaped, plain = font(76, "SemiBold", True), font(76, "SemiBold", True, shaped=False)
    for w in WORDS:
        # Shaping joins half letters and drops the visible halant, so the word gets
        # narrower and its pixels differ from the codepoint by codepoint render.
        assert shaped.getlength(w) < plain.getlength(w), w
        assert bytes(shaped.getmask(w)) != bytes(plain.getmask(w)), w


def test_i_matra_drawn_before_its_consonant() -> None:
    f = font(120, "Regular", True)
    # "दि": shaped, the i-matra sits left of द, so the cluster is wider than द alone and
    # the left edge of "दि" starts at or before द's left edge.
    assert f.getlength("दि") > 0
    assert f.getbbox("दि")[0] <= f.getbbox("द")[0]
    plain = font(120, "Regular", True, shaped=False)
    assert bytes(f.getmask("दि")) != bytes(plain.getmask("दि"))


def test_english_claim_pixels_unchanged() -> None:
    # Only the Hindi verdict word in the pill changes on an English card.
    card = _card("India exported $1 trillion in 2025", "Official data says $825 bn.")
    new, old = render(card, CARD_ID, BASE), render(card, CARD_ID, BASE, shaped=False)
    for band in ("claim", "explanation", "sources", "qr"):
        assert new.crop(BANDS[band]).tobytes() == old.crop(BANDS[band]).tobytes(), band


def test_unshaped_card_downloaded_earlier_still_verifies() -> None:
    card = _card(GOYAL_CLAIM, GOYAL_EXPL)
    get = lambda cid: card if cid == CARD_ID else None  # noqa: E731
    for old in (
        render(card, CARD_ID, BASE, shaped=False),
        render(card, CARD_ID, BASE, glyph_fallback=False, shaped=False),
    ):
        res = alter.check_image(encode(old, "JPEG"), get, BASE)
        assert res.result == "VERIFIED", res
    new = alter.check_image(encode(render(card, CARD_ID, BASE), "JPEG"), get, BASE)
    assert new.result == "VERIFIED", new


def test_edited_unshaped_card_still_altered() -> None:
    card = _card(GOYAL_CLAIM, GOYAL_EXPL)
    fake = _card(GOYAL_CLAIM.replace("सबसे अच्छा", "सबसे खराब"), GOYAL_EXPL)
    for img in (render(fake, CARD_ID, BASE), render(fake, CARD_ID, BASE, shaped=False)):
        res = alter.check_image(encode(img, "JPEG"), lambda cid: card, BASE)
        assert res.result == "ALTERED"
        assert "claim" in res.changed
