"""A verdict or alert must always reach the chat: captions never cut inside HTML, and a
refused photo falls back to the same text as a message (p61)."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import pytest

from app import alerts
from app.model import StubModel
from app.pipeline import Deps, run_prebunk
from app.proof import FixtureFetcher, InMemorySnapshots
from app.schemas import CardDoc, SessionDoc
from app.store import InMemoryStore
from app.telegram import CAPTION_MAX, fit_caption, send_claim_result

BASE = "https://proof.example"


@pytest.fixture(scope="module")
def cards() -> InMemoryStore:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="India"))
    run_prebunk(sid, Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots()), n=3)
    return store


def first(store: InMemoryStore) -> tuple[str, CardDoc]:
    return next(iter(store.cards.items()))


class Bot:
    def __init__(self, photo_ok: bool = True) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.photo_ok = photo_ok

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, payload))
        if method == "sendPhoto" and not self.photo_ok:
            return {"ok": False, "error_code": 400, "description": "failed to get HTTP URL"}
        return {"ok": True}

    def download(self, file_id: str) -> bytes:
        return b""


class Balanced(HTMLParser):
    """Telegram's HTML mode needs closed tags and whole entities."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack, tag
        assert self.stack[-1] == tag, tag
        self.stack.pop()


def well_formed(text: str) -> bool:
    p = Balanced()
    p.feed(text)
    p.close()
    # no cut entity like "&#x2" or "&am" at the end or before a space
    return not p.stack and not re.search(r"&[#\w]*(?![#\w;])", text.replace("&amp;", ""))


def test_long_card_caption_keeps_html_sources_and_id(cards: InMemoryStore) -> None:
    cid, card = first(cards)
    # Apostrophes escape to &#x27; (6 chars): the old [:997] cut could land inside one.
    for n in range(0, 12):
        long = card.model_copy(
            update={"explanation": "x" * n + "India's " * 300, "claim": "x" * n + "it's " * 40}
        )
        cap = fit_caption("<b>Claim 1/3</b> · ", long, cid)
        assert len(cap) <= CAPTION_MAX
        assert well_formed(cap), cap[-80:]
        assert "Sources:" in cap
        assert f"<code>{cid}</code>" in cap
        assert "…" in cap


def test_short_caption_unchanged(cards: InMemoryStore) -> None:
    from app.telegram import card_text

    cid, card = first(cards)
    assert fit_caption("", card, cid) == card_text(card, cid)


def test_refused_photo_falls_back_to_text(cards: InMemoryStore) -> None:
    cid, card = first(cards)
    bot = Bot(photo_ok=False)
    send_claim_result(bot, 5, "c", card, cid, BASE, reply_to=9, label="1/2")
    assert [m for m, _ in bot.calls] == ["sendPhoto", "sendMessage"]
    msg = bot.calls[-1][1]
    assert msg["chat_id"] == 5
    assert "photo" not in msg
    assert "caption" not in msg
    assert msg["text"] == bot.calls[0][1]["caption"]
    assert msg["reply_markup"] == bot.calls[0][1]["reply_markup"]
    assert msg["reply_parameters"]["message_id"] == 9


def test_accepted_photo_sends_once(cards: InMemoryStore) -> None:
    cid, card = first(cards)
    bot = Bot()
    send_claim_result(bot, 5, "c", card, cid, BASE)
    assert [m for m, _ in bot.calls] == ["sendPhoto"]


def test_live_alert_falls_back_to_text() -> None:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="Budget", alert_chat_id=7))
    bot = Bot(photo_ok=False)
    al = alerts.Alerter(bot, store, BASE)
    assert al.alert(sid, "card12345", "FALSE", "a false line")
    assert [m for m, _ in bot.calls] == ["sendPhoto", "sendMessage"]
    assert "FALSE" in bot.calls[-1][1]["text"]
    assert bot.calls[-1][1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Open proof"
