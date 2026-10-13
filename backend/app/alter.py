"""ALTERED check for a forwarded Proof Card image (Telegram photo or web upload).

Why not a byte hash: Telegram recompresses photos, so the sha256 of a forwarded card
never matches (DECISIONS D7). Instead:

1. Read the QR -> card id (zxing-cpp, Apache-2.0).
2. Load the immutable card and re-render the original (card_image.render is deterministic).
3. Align the upload to 1080x1350 and compare each layout band (verdict, claim,
   explanation, sources) on blurred grayscale: mean absolute difference survives JPEG
   recompression and downscaling, but jumps when a word or number is edited.
4. Any band over its threshold -> ALTERED, and we say which band changed.
Global perceptual hash distance (imagehash, BSD-2) is recorded for analytics.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import imagehash
import numpy as np
import zxingcpp
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from app.card_image import BANDS, H, W, render
from app.schemas import CardDoc

Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression bomb guard
MAX_UPLOAD_BYTES = 10_000_000
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
# Calibrated (tests/test_alter.py): clean copies down to JPEG q=30 at 50-60% scale max ~3,
# a one word or one number edit in any band lands at 19+.
BAND_THRESHOLD = 8.0
ASPECT_TOLERANCE = 0.03
TILE = (24, 48)  # rows, cols at half scale = 48x96 px on the card
CARD_ID_RE = re.compile(r"/v/([A-Za-z0-9_-]{8,64})/?$")

Result = Literal["VERIFIED", "ALTERED", "UNKNOWN"]
QR_ONLY = zxingcpp.barcode_formats_from_str("QRCode")


@dataclass
class CheckResult:
    result: Result
    reason: str
    card_id: str | None = None
    changed: list[str] = field(default_factory=list)
    band_scores: dict[str, float] = field(default_factory=dict)
    phash_distance: int | None = None


def load_image(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("image too large")
    try:
        raw = Image.open(io.BytesIO(data))
        if raw.format not in ALLOWED_FORMATS:
            raise ValueError("unsupported image format")
        img = ImageOps.exif_transpose(raw).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("not an image") from exc
    return img


def read_card_id(img: Image.Image) -> str | None:
    for bc in zxingcpp.read_barcodes(img, formats=QR_ONLY):
        m = CARD_ID_RE.search(bc.text.split("?")[0])
        if m:
            return m.group(1)
    return None


def _gray_blur(img: Image.Image) -> np.ndarray:
    small = img.convert("L").resize((W // 2, H // 2), Image.Resampling.LANCZOS)
    return np.asarray(small.filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float32)


def band_scores(upload: Image.Image, original: Image.Image) -> dict[str, float]:
    a, b = _gray_blur(upload), _gray_blur(original)
    out: dict[str, float] = {}
    for name, (x0, t, x1, btm) in BANDS.items():
        if name == "qr":
            continue
        diff = np.abs(
            a[t // 2 : btm // 2, x0 // 2 : x1 // 2] - b[t // 2 : btm // 2, x0 // 2 : x1 // 2]
        )
        # Max over small tiles: a one word edit is local, a band wide mean would dilute it.
        th, tw = TILE
        rows, cols = diff.shape[0] // th, diff.shape[1] // tw
        tiles = diff[: rows * th, : cols * tw].reshape(rows, th, cols, tw).mean(axis=(1, 3))
        out[name] = round(float(tiles.max()), 2)
    return out


def check_image(
    data: bytes,
    get_card: Callable[[str], CardDoc | None],
    base_url: str,
    bot_username: str = "",
) -> CheckResult:
    try:
        img = load_image(data)
    except ValueError as exc:
        return CheckResult("UNKNOWN", str(exc))
    card_id = read_card_id(img)
    if card_id is None:
        return CheckResult("UNKNOWN", "no Proof Card QR found (cropped or not a Proof Card)")
    card = get_card(card_id)
    if card is None:
        return CheckResult("ALTERED", "QR points to a card that does not exist", card_id)
    if abs(img.width / img.height - W / H) > ASPECT_TOLERANCE:
        return CheckResult("UNKNOWN", "image is cropped, send the full card", card_id)
    original = render(card, card_id, base_url, bot_username)
    upload = img.resize((W, H), Image.Resampling.LANCZOS)
    scores = band_scores(upload, original)
    changed = [k for k, v in scores.items() if v > BAND_THRESHOLD]
    dist = int(imagehash.phash(upload) - imagehash.phash(original))
    if changed:
        return CheckResult(
            "ALTERED", "edited: " + ", ".join(changed), card_id, changed, scores, dist
        )
    return CheckResult("VERIFIED", "matches the original card", card_id, [], scores, dist)


def text_similarity(a: str, b: str) -> tuple[float, list[str], list[str]]:
    """Word level similarity + removed / added words (for the web text check)."""
    wa = re.findall(r"\w+", a.lower())
    wb = re.findall(r"\w+", b.lower())
    sa, sb = set(wa), set(wb)
    if not sa and not sb:
        return 1.0, [], []
    sim = len(sa & sb) / len(sa | sb)
    return round(sim, 3), sorted(sa - sb), sorted(sb - sa)
