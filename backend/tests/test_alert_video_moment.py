"""Team lead flow step 4 + 6: the Telegram alert links the speech video at the moment the
claim was said, so a user can hear it themselves next to the proof."""

from __future__ import annotations

from typing import Any

import pytest

from app import alerts
from app.schemas import SessionDoc, Verdict
from app.store import InMemoryStore

BASE = "https://proofcard.test"
VID = "dQw4w9WgXcQ"


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, payload))
        return {"ok": True}

    def download(self, file_id: str) -> bytes:
        raise AssertionError


@pytest.mark.parametrize(
    ("url", "t", "want"),
    [
        (f"https://youtu.be/{VID}", 75.9, f"https://youtu.be/{VID}?t=75"),
        (f"https://www.youtube.com/watch?v={VID}&list=x", 0, f"https://youtu.be/{VID}?t=0"),
        (f"https://m.youtube.com/watch?v={VID}", None, f"https://youtu.be/{VID}"),
        (f"https://youtube.com/shorts/{VID}", 5, f"https://youtu.be/{VID}?t=5"),
        (f"https://www.youtube.com/live/{VID}?si=a", 3725, f"https://youtu.be/{VID}?t=3725"),
        ("https://www.youtube.com/watch?v=short", 5, None),
        ("https://example.com/watch?v=" + VID, 5, None),
        (None, 5, None),
    ],
)
def test_youtube_moment(url: str | None, t: float | None, want: str | None) -> None:
    assert alerts.youtube_moment(url, t) == want


def _linked(store: InMemoryStore, youtube: str | None) -> str:
    sid = store.create_session(SessionDoc(owner_uid="u", topic="Rally", youtube_url=youtube))
    store.update_session(sid, alert_chat_id=7)
    return sid


def _buttons(bot: FakeBot) -> list[dict[str, str]]:
    row: list[dict[str, str]] = bot.calls[-1][1]["reply_markup"]["inline_keyboard"][0]
    return row


def test_alert_has_watch_button_at_the_moment() -> None:
    store, bot = InMemoryStore(), FakeBot()
    sid = _linked(store, f"https://youtu.be/{VID}")
    assert alerts.Alerter(bot, store, BASE).alert(sid, "c1", Verdict.FALSE, "x", 3725.2)
    b = _buttons(bot)
    assert b[0]["text"] == "Open proof"
    assert b[1] == {"text": "Watch at 1:02:05", "url": f"https://youtu.be/{VID}?t=3725"}


def test_alert_without_time_links_video_start() -> None:
    store, bot = InMemoryStore(), FakeBot()
    sid = _linked(store, f"https://youtu.be/{VID}")
    alerts.Alerter(bot, store, BASE).alert(sid, "c1", "MISLEADING", "x")
    assert _buttons(bot)[1] == {"text": "Watch speech", "url": f"https://youtu.be/{VID}"}


def test_alert_without_video_has_only_proof_button() -> None:
    store, bot = InMemoryStore(), FakeBot()
    sid = _linked(store, None)
    alerts.Alerter(bot, store, BASE).alert(sid, "c1", "FALSE", "x", 12.0)
    assert [x["text"] for x in _buttons(bot)] == ["Open proof"]
