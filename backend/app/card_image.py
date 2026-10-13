"""Proof Card image (1080x1350 PNG / JPEG) with a QR to /v/<card_id>.

The layout is FIXED and deterministic (same card -> same pixels), which is what makes
the ALTERED check possible: alter.py re-renders the original and compares it region by
region against a forwarded copy. Never change BANDS without bumping LAYOUT_VERSION.

Fonts: Noto Sans + Noto Sans Devanagari, SIL Open Font License 1.1 (assets/fonts/OFL.txt).
"""

from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import zxingcpp
from PIL import Image, ImageDraw, ImageFont

from app.schemas import CardDoc, Verdict

LAYOUT_VERSION = 1
W, H = 1080, 1350
PAD = 72

# Regions compared by the ALTERED check: (name, (left, top, right, bottom)).
BANDS: dict[str, tuple[int, int, int, int]] = {
    "verdict": (PAD, 150, W - PAD, 300),
    "claim": (PAD, 330, W - PAD, 760),
    "explanation": (PAD, 780, W - PAD, 1010),
    "sources": (PAD, 1040, W - PAD - 300, 1290),
    "qr": (W - PAD - 270, 1030, W - PAD, 1300),
}

INK = (17, 24, 39)
PAPER = (250, 250, 247)
BRAND = (31, 79, 255)
MUTED = (107, 114, 128)
VERDICT_STYLE: dict[Verdict, tuple[tuple[int, int, int], str, str]] = {
    Verdict.TRUE: ((21, 128, 61), "TRUE", "सही"),
    Verdict.MISLEADING: ((180, 83, 9), "MISLEADING", "भ्रामक"),
    Verdict.FALSE: ((185, 28, 28), "FALSE", "गलत"),
    Verdict.UNVERIFIABLE: ((107, 114, 128), "NOT ENOUGH PROOF", "पुख्ता सबूत नहीं"),
}

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
Weight = Literal["Regular", "Medium", "SemiBold", "Bold"]


@lru_cache(maxsize=32)
def font(size: int, weight: Weight = "Regular", devanagari: bool = False) -> ImageFont.FreeTypeFont:
    name = "NotoSansDevanagari.ttf" if devanagari else "NotoSans.ttf"
    f = ImageFont.truetype(str(FONT_DIR / name), size)
    f.set_variation_by_name(weight)
    return f


def _font_for(text: str, size: int, weight: Weight = "Regular") -> ImageFont.FreeTypeFont:
    return font(size, weight, bool(_DEVANAGARI.search(text)))


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if f.getlength(cand) <= width:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and f.getlength(last + "…") > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def qr_image(url: str, size: int) -> Image.Image:
    bc = zxingcpp.create_barcode(url, zxingcpp.BarcodeFormat.QRCode, ec_level="Q")
    arr = np.asarray(bc.to_image(scale=8, add_quiet_zones=True))
    return Image.fromarray(arr).convert("RGB").resize((size, size), Image.Resampling.NEAREST)


def share_url(base_url: str, card_id: str) -> str:
    return f"{base_url.rstrip('/')}/v/{card_id}"


def _domain(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url


def render(card: CardDoc, card_id: str, base_url: str, bot_username: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    colour, word_en, word_hi = VERDICT_STYLE[card.verdict]

    # header
    d.rectangle((0, 0, W, 12), fill=colour)
    d.text((PAD, 92), "PROOF CARD", font=font(30, "Bold"), fill=BRAND, anchor="ls")
    d.text((W - PAD, 92), f"id {card_id}", font=font(26, "Medium"), fill=MUTED, anchor="rs")

    # verdict pill
    vf = font(64, "Bold")
    tw = int(vf.getlength(word_en))
    x0, y0 = BANDS["verdict"][0], BANDS["verdict"][1] + 10
    d.rounded_rectangle((x0, y0, x0 + tw + 64, y0 + 108), radius=54, fill=colour)
    d.text((x0 + 32, y0 + 54), word_en, font=vf, fill=PAPER, anchor="lm")
    d.text(
        (x0 + tw + 96, y0 + 54), word_hi, font=font(40, "SemiBold", True), fill=colour, anchor="lm"
    )

    # claim
    cl = f"“{card.claim}”"
    top, bottom = BANDS["claim"][1] + 10, BANDS["claim"][3]
    for size in (76, 66, 58, 50):  # biggest size that fits the band without truncation
        cf = _font_for(cl, size, "SemiBold")
        step = int(size * 1.32)
        lines = wrap(cl, cf, W - 2 * PAD, max(1, (bottom - top) // step))
        if not lines[-1].endswith("…"):
            break
    y = top
    for line in lines:
        d.text((PAD, y), line, font=cf, fill=INK)
        y += step

    # explanation
    ef = _font_for(card.explanation, 34)
    y = BANDS["explanation"][1] + 10
    for line in wrap(card.explanation, ef, W - 2 * PAD, 5):
        d.text((PAD, y), line, font=ef, fill=INK)
        y += 46

    # sources + footer
    d.line((PAD, 1020, W - PAD, 1020), fill=(229, 231, 235), width=2)
    sf = font(28, "Medium")
    y = BANDS["sources"][1] + 10
    d.text(
        (PAD, y),
        f"{len(card.sources)} source(s) · support {card.support_score:.2f}",
        font=sf,
        fill=MUTED,
    )
    y += 46
    for s in card.sources[:3]:
        d.text((PAD, y), "• " + _domain(str(s.url))[:34], font=sf, fill=INK)
        y += 40
    hint = f"Verify: forward to @{bot_username}" if bot_username else "Verify: scan the QR"
    d.text(
        (PAD, BANDS["sources"][3] - 10), hint, font=font(26, "SemiBold"), fill=BRAND, anchor="ls"
    )

    q = BANDS["qr"]
    img.paste(qr_image(share_url(base_url, card_id), q[2] - q[0]), (q[0], q[1]))
    d.text((W // 2, H - 22), card.card_sha256[:24], font=font(18), fill=MUTED, anchor="ms")
    return img


def encode(img: Image.Image, fmt: Literal["PNG", "JPEG"]) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.save(buf, "JPEG", quality=90, optimize=True)
    else:
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
