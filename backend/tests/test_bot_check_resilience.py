"""The bot answers every claim even when one Telegram call fails (p62): a failed
"checking" ack must not leave the check unqueued, and one failed verdict send must not
drop the other verdicts of a forward."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps
from app.proof import FixtureFetcher, InMemorySnapshots
from app.store import InMemoryStore
from app.tasks import SyncQueue
from tests.conftest import WEBHOOK_SECRET, fake_oidc, fake_verifier

BASE = "https://proof.example"
A = "India has 22 languages in the Eighth Schedule of the Constitution"
B = "India's GDP grew 8.2 percent in 2023-24 says the statistics ministry"


class FlakyBot:
    """Raises (a network error, like httpx timing out) on chosen calls."""

    def __init__(self, fail: Any) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail(method, payload):
            raise TimeoutError("telegram unreachable")
        self.calls.append((method, payload))
        return {"ok": True}

    def download(self, file_id: str) -> bytes:
        return b""


def client(bot: FlakyBot) -> TestClient:
    store = InMemoryStore()
    settings = Settings(
        env="test",
        telegram_webhook_secret=SecretStr(WEBHOOK_SECRET),
        telegram_bot_username="ProofCardAgentBot",
        public_base_url=BASE,
        public_rate_per_min=100,
    )
    app = create_app(
        settings=settings,
        verifier=fake_verifier,
        store=store,
        deps=Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots()),
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
        bot_api=bot,
    )
    return TestClient(app)


def tg(c: TestClient, text: str) -> None:
    hdr = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
    msg = {"message_id": 7, "chat": {"id": 42, "type": "private"}, "text": text}
    r = c.post("/tg/webhook", json={"update_id": 1, "message": msg}, headers=hdr)
    assert r.json() == {"ok": True}


def verdicts(bot: FlakyBot) -> list[dict[str, Any]]:
    return [p for m, p in bot.calls if "Checking" not in str(p.get("text", ""))]


def test_failed_ack_still_checks_and_answers() -> None:
    bot = FlakyBot(lambda m, p: "Checking this claim" in str(p.get("text", "")))
    c = client(bot)
    tg(c, B)
    out = verdicts(bot)
    assert len(out) == 1
    assert out[0]["chat_id"] == 42


def test_one_failed_verdict_send_keeps_the_others() -> None:
    sent: list[str] = []

    def fail(method: str, payload: dict[str, Any]) -> bool:
        body = str(payload.get("caption") or payload.get("text") or "")
        if body.startswith("<b>Claim "):
            sent.append(body)
            return len(sent) == 1  # the first verdict to go out hits a network error
        return False

    bot = FlakyBot(fail)
    c = client(bot)
    c.app.state.live.spotter.spot_claims = lambda t: [A, B]  # type: ignore[attr-defined]
    long = f"{A}. {B}. " + "Share this with every family group before it gets deleted. " * 3
    tg(c, long)
    out = [p for p in verdicts(bot) if str(p.get("caption") or p.get("text")).startswith("<b>")]
    assert len(sent) == 2  # both verdicts were attempted
    assert len(out) == 1  # the second still reached the chat
    store = c.app.state.store  # type: ignore[attr-defined]
    assert all(s.status == "closed" for s in store.sessions.values() if s.alert_chat_id == 42)
