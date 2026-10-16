"""Telegram alerts: deep link mint/redeem, bot /start, capped sendPhoto, live engine hook."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import alerts, alter
from app.config import Settings
from app.live import HashEmbedder, HeuristicSpotter, LiveDeps, LiveEngine
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps
from app.proof import FixtureFetcher, InMemorySnapshots
from app.schemas import ClaimDoc, ClaimSource, ClaimStatus, SessionDoc, TgUpdate, Verdict
from app.store import InMemoryStore
from app.tasks import SyncQueue
from app.telegram import BotDeps, handle_update
from tests.conftest import WEBHOOK_SECRET, fake_oidc, fake_verifier

BASE = "https://proof.example"


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, payload))
        return {"ok": True}

    def download(self, file_id: str) -> bytes:
        return b""


def _session(store: InMemoryStore, owner: str = "u") -> str:
    return store.create_session(SessionDoc(owner_uid=owner, topic="Budget <speech>"))


def _payload(url: str) -> str:
    return url.split("?start=", 1)[1]


def test_link_is_single_use_and_expires() -> None:
    store = InMemoryStore()
    sid = _session(store)
    url = alerts.new_link(store, sid, "ProofCardAgentBot")
    assert url.startswith("https://t.me/ProofCardAgentBot?start=alert" + sid)
    p = _payload(url)
    assert len(p) <= 64
    stored = store.get_session(sid)
    assert stored is not None
    assert stored.tg_link_hash
    assert p[-22:] not in stored.tg_link_hash  # only the hash is stored

    assert alerts.redeem(store, p[:-1] + ("A" if p[-1] != "A" else "B"), 7) is None  # bad secret
    assert alerts.redeem(store, "card_abcdefgh", 7) is None
    assert alerts.redeem(store, p, 42) is not None
    linked = store.get_session(sid)
    assert linked is not None
    assert linked.alert_chat_id == 42
    assert alerts.redeem(store, p, 43) is None  # burned

    url2 = alerts.new_link(store, sid, "b", now=datetime.now(UTC) - timedelta(minutes=16))
    assert alerts.redeem(store, _payload(url2), 44) is None  # expired


def test_alerter_sends_only_false_or_misleading_and_caps() -> None:
    store, bot = InMemoryStore(), FakeBot()
    sid = _session(store)
    a = alerts.Alerter(bot, store, BASE)
    assert a.alert(sid, "card-1", Verdict.FALSE, "x") is False  # not linked yet
    store.update_session(sid, alert_chat_id=99)
    assert a.alert(sid, "card-1", Verdict.TRUE, "x") is False
    assert a.alert(sid, "card-1", "UNVERIFIABLE", "x") is False
    assert a.alert(sid, "card-1", Verdict.MISLEADING, "<b>said</b>") is True
    method, body = bot.calls[0]
    assert method == "sendPhoto"
    assert body["chat_id"] == 99
    assert body["photo"] == f"{BASE}/v/card-1.png"
    assert "&lt;b&gt;said" in body["caption"]
    assert "&lt;speech&gt;" in body["caption"]
    for _ in range(alerts.MAX_ALERTS + 3):
        a.alert(sid, "card-2", "FALSE", "y")
    assert len(bot.calls) == alerts.MAX_ALERTS


def test_bot_start_alert_links_chat() -> None:
    store, bot = InMemoryStore(), FakeBot()
    sid = _session(store)
    p = _payload(alerts.new_link(store, sid, "b"))

    def link(payload: str, chat: int) -> str | None:
        s = alerts.redeem(store, payload, chat)
        return s.topic if s else None

    deps = BotDeps(bot, store.get_card, lambda b: alter.CheckResult("UNKNOWN", ""), BASE)
    deps.link_alerts = link

    def start(text: str) -> str:
        upd = {
            "update_id": 1,
            "message": {"message_id": 1, "chat": {"id": 555, "type": "private"}, "text": text},
        }
        handle_update(TgUpdate.model_validate(upd), deps)
        return str(bot.calls[-1][1]["text"])

    assert "Alerts on" in start(f"/start {p}")
    linked = store.get_session(sid)
    assert linked is not None
    assert linked.alert_chat_id == 555
    assert "expired" in start(f"/start {p}")


def test_engine_alerts_on_false_match() -> None:
    store = InMemoryStore()
    sid = _session(store)
    text = "India has 22 languages in the Eighth Schedule of the Constitution"
    store.add_claim(
        sid,
        ClaimDoc(
            text=text,
            source=ClaimSource.PREDICTED,
            status=ClaimStatus.PROVED,
            card_id="card-9",
            verdict=Verdict.FALSE,
        ),
    )
    sent: list[tuple[str, str, Any, str]] = []

    def alert(s: str, c: str, v: Any, t: str, at: float | None = None) -> bool:
        sent.append((s, c, v, t))
        return True

    async def emit(ev: dict[str, Any]) -> None:
        return None

    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    eng = LiveEngine(sid, LiveDeps(deps, HashEmbedder(), HeuristicSpotter()), emit, alert)

    async def run() -> None:
        await eng.on_sentence(text + ".")
        await eng.drain()

    asyncio.run(run())
    assert len(sent) == 1
    assert sent[0][1] == "card-9"


def _client(username: str) -> tuple[TestClient, InMemoryStore]:
    store = InMemoryStore()
    settings = Settings(
        env="test",
        telegram_webhook_secret=SecretStr(WEBHOOK_SECRET),
        telegram_bot_username=username,
    )
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    app = create_app(
        settings=settings,
        verifier=fake_verifier,
        store=store,
        deps=deps,
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
        bot_api=FakeBot(),
    )
    return TestClient(app), store


def test_link_endpoint_owner_only() -> None:
    c, store = _client("ProofCardAgentBot")
    sid = _session(store, owner="admin-1")
    path = f"/api/sessions/{sid}/telegram-link"
    r = c.post(path, headers={"Authorization": "Bearer admin-token"})
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://t.me/ProofCardAgentBot?start=alert")
    assert c.post(path, headers={"Authorization": "Bearer anon-token"}).status_code == 404
    assert c.post(path).status_code == 401

    c2, store2 = _client("")
    sid2 = _session(store2, owner="admin-1")
    r2 = c2.post(
        f"/api/sessions/{sid2}/telegram-link", headers={"Authorization": "Bearer admin-token"}
    )
    assert r2.status_code == 503
