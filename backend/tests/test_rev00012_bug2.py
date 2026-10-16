"""Bug 2 of the rev00012 prod verify (16 Oct 2026): a checkable line got `heard`, then
nothing. Root cause: the pre filter needed a digit or superlative (fixed in #35), and
nothing told the user when a line produced no card. Now every heard line ends in a
visible outcome, and a spotter failure falls back to the heuristic instead of dropping.
Also: a stalled model call left a brief in "prebunking" with 0 claims forever."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

import app.live as live_mod
from app.config import Settings
from app.live import HashEmbedder, HeuristicSpotter, LiveDeps, LiveEngine
from app.model import StubModel
from app.pipeline import Deps, run_prebunk
from app.proof import FixtureFetcher, InMemorySnapshots
from app.schemas import ClaimSource, SessionDoc
from app.store import InMemoryStore
from tests.test_live import _client, _session, _until

LINE_E = "India ka per capita GDP Japan se zyada hai"  # the dropped line, verbatim


class _Spot:
    def __init__(self, result: Any = None, exc: Exception | None = None, sleep: float = 0) -> None:
        self.result, self.exc, self.sleep = result, exc, sleep

    def spot_claims(self, sentence: str) -> list[str]:
        if self.sleep:
            time.sleep(self.sleep)
        if self.exc:
            raise self.exc
        return list(self.result or [])


def _engine(spotter: Any) -> tuple[LiveEngine, list[dict[str, Any]]]:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    events: list[dict[str, Any]] = []

    async def emit(ev: dict[str, Any]) -> None:
        events.append(ev)

    return LiveEngine(sid, LiveDeps(deps, HashEmbedder(), spotter), emit), events


def _run(eng: LiveEngine, *lines: str) -> None:
    async def go() -> None:
        for line in lines:
            await eng.on_sentence(line)
        await eng.drain()

    asyncio.run(go())


def _kinds(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def test_line_e_reaches_a_card_over_the_socket(settings: Settings) -> None:
    c, store = _client(settings)
    sid = _session(c)
    with c.websocket_connect(f"/api/live/{sid}") as ws:
        ws.send_json({"type": "auth", "token": "admin-token"})
        ws.receive_json()
        ws.send_json({"type": "text", "text": LINE_E})
        assert _until(ws, "heard")["text"] == LINE_E
        assert _until(ws, "checking")["text"] == LINE_E
        assert _until(ws, "proved", limit=4)["card_id"]
        ws.send_json({"type": "stop"})
    assert [d.text for _, d in store.list_claims(sid) if d.source == ClaimSource.LIVE] == [LINE_E]


def test_no_claim_says_so_instead_of_silence() -> None:
    eng, events = _engine(_Spot([]))  # model: nothing checkable
    _run(eng, "Biden let the price of eggs get out of control")
    assert _kinds(events) == ["heard", "skipped"]
    assert events[1]["reason"] == "not_checkable"


def test_spotter_error_falls_back_to_the_heuristic() -> None:
    eng, events = _engine(_Spot(exc=RuntimeError("vertex 503")))
    _run(eng, LINE_E)
    assert _kinds(events) == ["heard", "checking", "proved"]


def test_spotter_timeout_falls_back_to_the_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_mod, "SPOT_TIMEOUT_S", 0.05)
    eng, events = _engine(_Spot([], sleep=0.3))
    _run(eng, LINE_E)
    assert _kinds(events) == ["heard", "checking", "proved"]


def test_repeat_is_named() -> None:
    eng, events = _engine(HeuristicSpotter())
    _run(eng, LINE_E, LINE_E)
    assert sorted(_kinds(events)) == ["checking", "heard", "heard", "proved", "skipped"]
    assert next(e for e in events if e["type"] == "skipped")["reason"] == "repeat"


def test_a_crash_in_one_line_is_reported_and_the_next_line_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eng, events = _engine(HeuristicSpotter())
    real = eng.match
    calls = {"n": 0}

    def flaky(text: str) -> tuple[str | None, float]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("embedder down")
        return real(text)

    monkeypatch.setattr(eng, "match", flaky)
    _run(eng, LINE_E, "Mumbai has 40 million cars on the road today")
    assert _kinds(events)[:2] == ["heard", "skipped"]
    assert events[1]["reason"] == "error"
    assert _kinds(events)[2:] == ["heard", "checking", "proved"]  # socket and engine alive


def test_cold_check_crash_still_resolves_the_tile(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any) -> str:
        raise RuntimeError("firestore down")

    monkeypatch.setattr(live_mod, "verify_claim", boom)
    eng, events = _engine(HeuristicSpotter())
    _run(eng, LINE_E)
    assert _kinds(events) == ["heard", "checking", "failed"]


# ---------- brief never stuck in "prebunking" ----------


class _Boom(StubModel):
    def predict_claims(self, topic: str, speaker: str, n: int) -> Any:
        raise TimeoutError("vertex timed out")


def test_prediction_failure_ends_the_brief_as_failed() -> None:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="India", status="prebunking"))
    out = run_prebunk(sid, Deps(store, _Boom(), FixtureFetcher(), InMemorySnapshots()))
    assert out == {"predicted": 0, "proved": 0}
    assert store.get_session(sid).status == "failed"  # type: ignore[union-attr]
    assert store.list_claims(sid) == []


def test_task_retry_finishes_the_same_bank() -> None:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="India", status="prebunking"))
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    first = run_prebunk(sid, deps)
    second = run_prebunk(sid, deps)  # Cloud Tasks redelivery
    assert first["predicted"] > 0
    assert second == first
    assert len(store.list_claims(sid)) == first["predicted"]
    assert store.get_session(sid).status == "ready"  # type: ignore[union-attr]
