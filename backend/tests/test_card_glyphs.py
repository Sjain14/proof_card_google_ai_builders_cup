"""Card image never draws .notdef (tofu) boxes, e.g. curly quotes around a Hindi claim."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PIL import ImageDraw, ImageFont

from app import alter
from app.card_image import encode, fit_text, font, has_glyph, render
from app.schemas import CardDoc, SourceProof, Verdict
from app.security import card_fingerprint, sha256_hex

BASE = "https://proof.example"
CARD_ID = "hiQuoteCard01"
HINDI_CLAIM = "पीयूष गोयल ने कहा कि भारत ने 2025 में 1000 अरब डॉलर का निर्यात किया"
HINDI_EXPL = "आधिकारिक आंकड़े “825 अरब डॉलर” बताते हैं \u2013 दावा गलत है…"


def _card(claim: str, explanation: str) -> CardDoc:
    fields = {
        "claim": claim,
        "verdict": Verdict.FALSE,
        "explanation": explanation,
        "sources": [
            SourceProof(
                url="https://example.org/exports",
                snippet="exports ... 825 billion",
                snapshot_sha256=sha256_hex(b"page"),
                fetched_at=datetime(2026, 10, 17, tzinfo=UTC),
            )
        ],
        "support_score": 0.9,
    }
    fp = card_fingerprint({k: str(v) for k, v in fields.items()})
    return CardDoc(card_sha256=fp, **fields)


def _drawn(
    monkeypatch: pytest.MonkeyPatch, card: CardDoc, glyph_fallback: bool = True
) -> list[tuple[str, ImageFont.FreeTypeFont]]:
    seen: list[tuple[str, ImageFont.FreeTypeFont]] = []
    real = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *a, **k):  # type: ignore[no-untyped-def]
        seen.append((text, k["font"]))
        return real(self, xy, text, *a, **k)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    render(card, CARD_ID, BASE, glyph_fallback=glyph_fallback)
    return seen


def test_devanagari_font_lacks_curly_quotes_so_detector_works() -> None:
    dev = font(40, "SemiBold", True)
    assert not has_glyph(dev, "“")  # the bug: Noto Sans Devanagari has no curly quotes
    assert has_glyph(dev, "क")
    assert has_glyph(dev, '"')
    assert has_glyph(dev, " ")
    assert has_glyph(font(40, "SemiBold"), "“")  # Latin font has them, keep them there


def test_fit_text_swaps_only_missing_glyphs() -> None:
    dev, lat = font(40, "SemiBold", True), font(40, "SemiBold")
    assert fit_text(f"“{HINDI_CLAIM}”", dev) == f'"{HINDI_CLAIM}"'
    assert fit_text("“India”", lat) == "“India”"


def test_hindi_card_draws_no_notdef_glyphs(monkeypatch: pytest.MonkeyPatch) -> None:
    drawn = _drawn(monkeypatch, _card(HINDI_CLAIM, HINDI_EXPL))
    assert any("गोयल" in t for t, _ in drawn)
    for text, f in drawn:
        missing = [c for c in text if not has_glyph(f, c)]
        assert not missing, (text, missing)


def test_old_render_had_tofu(monkeypatch: pytest.MonkeyPatch) -> None:
    drawn = _drawn(monkeypatch, _card(HINDI_CLAIM, HINDI_EXPL), glyph_fallback=False)
    assert any(not has_glyph(f, c) for t, f in drawn for c in t)


def test_english_card_render_unchanged() -> None:
    card = _card("India exported $1 trillion in 2025", "Official data says “$825 bn”.")
    new = render(card, CARD_ID, BASE)
    assert new.tobytes() == render(card, CARD_ID, BASE, glyph_fallback=False).tobytes()


def _jpeg(img) -> bytes:  # type: ignore[no-untyped-def]
    return encode(img, "JPEG")


def test_card_downloaded_before_fix_still_verifies() -> None:
    card = _card(HINDI_CLAIM, HINDI_EXPL)
    old = render(card, CARD_ID, BASE, glyph_fallback=False, shaped=False)
    res = alter.check_image(_jpeg(old), lambda cid: card if cid == CARD_ID else None, BASE)
    assert res.result == "VERIFIED", res
    fresh = alter.check_image(_jpeg(render(card, CARD_ID, BASE)), lambda cid: card, BASE)
    assert fresh.result == "VERIFIED", fresh


def test_edited_hindi_card_still_altered() -> None:
    card = _card(HINDI_CLAIM, HINDI_EXPL)
    fake = _card(HINDI_CLAIM.replace("1000", "9000"), HINDI_EXPL)
    img = render(fake, CARD_ID, BASE)
    res = alter.check_image(_jpeg(img), lambda cid: card, BASE)
    assert res.result == "ALTERED"
    assert "claim" in res.changed
    legacy_fake = render(fake, CARD_ID, BASE, glyph_fallback=False, shaped=False)
    assert alter.check_image(_jpeg(legacy_fake), lambda cid: card, BASE).result == "ALTERED"
