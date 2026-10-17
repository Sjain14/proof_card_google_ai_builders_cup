"""Telegram caches a photo by URL: card image URLs must change when the renderer does."""

from __future__ import annotations

import pytest

from app import card_image
from app.card_image import RENDER_REV, card_image_url

BASE = "https://proof.example"


def test_card_image_url_carries_render_rev() -> None:
    assert card_image_url(BASE + "/", "abc12345") == f"{BASE}/v/abc12345.png?r={RENDER_REV}"
    assert card_image_url(BASE, "abc12345", "jpg").endswith(f".jpg?r={RENDER_REV}")


def test_url_changes_when_renderer_bumps(monkeypatch: pytest.MonkeyPatch) -> None:
    old = card_image_url(BASE, "abc12345")
    monkeypatch.setattr(card_image, "RENDER_REV", "next")
    assert card_image_url(BASE, "abc12345") != old
