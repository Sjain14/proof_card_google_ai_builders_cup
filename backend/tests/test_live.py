"""Live bridge: spotting, instant match vs cold path, websocket auth and protocol."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.live import (
    HashEmbedder,
    HeuristicSpotter,
    LiveDeps,
    cosine,
    final_text,
    heuristic_spot,
    vocabulary_for,
)
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps
from app.proof import FixtureFetcher, InMemorySnapshots
from app.store import InMemoryStore
from app.tasks import SyncQueue
from tests.conftest import fake_oidc, fake_verifier

ADMIN = {"Authorization": "Bearer admin-token"}
PREBUNKED = "India has 22 languages in the Eighth Schedule of the Constitution"


def _client(settings: Settings, transcriber: Any = None) -> tuple[TestClient, InMemoryStore]:
    store = InMemoryStore()
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    app = create_app(
        settings=settings,
        verifier=fake_verifier,
        store=store,
        deps=deps,
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
        live=LiveDeps(deps, HashEmbedder(), HeuristicSpotter(), threshold=0.80),
        transcriber=transcriber,
    )
    return TestClient(app), store


def _session(c: TestClient) -> str:
    sid: str = c.post("/api/prebunk", json={"topic": "India"}, headers=ADMIN).json()["session_id"]
    return sid


def _until(ws: Any, kind: str, limit: int = 10) -> dict[str, Any]:
    for _ in range(limit):
        ev: dict[str, Any] = ws.receive_json()
        if ev["type"] == kind:
            return ev
    raise AssertionError(f"no {kind} event")


# ---------- units ----------


def test_heuristic_spot() -> None:
    assert heuristic_spot("GDP grew 8.2 percent last year in India") != []
    assert heuristic_spot("Bharat sabse badi democracy hai duniya mein") != []
    assert heuristic_spot("namaste doston aaj hum baat karenge") == []
    assert heuristic_spot("kya 22 languages hain?") == []
    assert heuristic_spot("22 hain") == []  # too short to be a claim


def test_hash_embedder_separates_restatement_from_other_claim() -> None:
    e = HashEmbedder()
    a, same, other = e.embed(
        [
            PREBUNKED,
            "india has 22 languages in the eighth schedule of the constitution!",
            "GDP grew 8 percent",
        ]
    )
    assert cosine(a, same) > 0.95
    assert cosine(a, other) < 0.3


# ---------- websocket ----------


def test_live_instant_match_then_cold_check(settings: Settings) -> None:
    c, store = _client(settings)
    sid = _session(c)
    with c.websocket_connect(f"/api/live/{sid}") as ws:
        ws.send_json({"type": "auth", "token": "admin-token"})
        assert ws.receive_json() == {"type": "ready", "audio": False}

        ws.send_json({"type": "text", "text": PREBUNKED + "."})
        assert _until(ws, "heard")["text"].startswith("India has 22")
        hit = _until(ws, "match")
        assert hit["card_id"]
        assert hit["similarity"] >= 0.8
        assert hit["latency_ms"] < 1500

        ws.send_json({"type": "text", "text": PREBUNKED + "."})  # repeated: no second card
        ws.send_json({"type": "text", "text": "Mumbai has 40 million cars on the road today"})
        assert _until(ws, "checking")["text"].startswith("Mumbai")
        done = _until(ws, "proved", limit=4)
        assert done["card_id"]
        ws.send_json({"type": "stop"})

    live = [d for _, d in store.list_claims(sid) if d.source == "live"]
    assert len(live) == 2
    assert live[0].matched_claim_id
    assert live[0].latency_ms is not None
    assert live[1].status == "proved"
    assert live[1].latency_ms is not None
    assert store.get_session(sid).status == "ready"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "first",
    [
        None,
        {"type": "auth", "token": "nope"},
        {"type": "auth", "token": "anon-token"},
        {"type": "hello", "token": "admin-token"},
    ],
)
def test_live_rejects_bad_auth(settings: Settings, first: dict[str, str] | None) -> None:
    c, _ = _client(settings)
    sid = _session(c)
    with c.websocket_connect(f"/api/live/{sid}") as ws:
        if first is None:
            ws.send_text("not json")
        else:
            ws.send_json(first)
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_live_rejects_other_users_session(settings: Settings) -> None:
    c, _ = _client(settings)
    for path in ["/api/live/doesnotexist1", "/api/live/bad"]:
        with c.websocket_connect(path) as ws:
            ws.send_json({"type": "auth", "token": "admin-token"})
            with pytest.raises(WebSocketDisconnect) as e:
                ws.receive_json()
        assert e.value.code == 4401


def test_live_audio_without_transcriber_says_so(settings: Settings) -> None:
    c, _ = _client(settings)
    sid = _session(c)
    with c.websocket_connect(f"/api/live/{sid}") as ws:
        ws.send_json({"type": "auth", "token": "admin-token"})
        ws.receive_json()
        ws.send_bytes(b"\x00\x00" * 1600)
        assert ws.receive_json() == {"type": "error", "code": "audio_unavailable"}
        ws.send_text("[1,2]")  # ignored, not a dict
        ws.send_json({"type": "stop"})


class FakeTranscriber:
    """Stands in for the Gemini Live relay: every audio frame "hears" one sentence."""

    def __init__(self) -> None:
        self.frames = 0
        self.vocabulary: list[str] = []

    async def run(
        self,
        audio: asyncio.Queue[bytes | None],
        on_final: Callable[[str], Awaitable[None]],
        vocabulary: Sequence[str] = (),
    ) -> None:
        self.vocabulary = list(vocabulary)
        while await audio.get() is not None:
            self.frames += 1
            if self.frames == 1:
                await on_final(PREBUNKED)


def test_live_audio_path_relays_to_transcriber(settings: Settings) -> None:
    t = FakeTranscriber()
    c, _ = _client(settings, transcriber=t)
    sid = _session(c)
    with c.websocket_connect(f"/api/live/{sid}") as ws:
        ws.send_json({"type": "auth", "token": "admin-token"})
        assert ws.receive_json()["audio"] is True
        ws.send_bytes(b"\x01\x00" * 1600)
        assert _until(ws, "match")["card_id"]
        ws.send_bytes(b"\x00" * 70_000)  # oversize frame refused
        assert _until(ws, "error")["code"] == "audio_unavailable"
        ws.send_json({"type": "stop"})
    assert t.frames == 1
    assert t.vocabulary  # prebunked claims bias the transcriber


def test_vocabulary_from_prebunked_claims() -> None:
    v = vocabulary_for(
        [
            "UPI processed 20 billion transactions, says NPCI",
            "Chandrayaan-3 landed near the south pole",
            "संविधान में 22 भाषाएँ हैं, says NPCI",
        ]
    )
    assert v == ["UPI", "NPCI", "Chandrayaan-3", "संविधान", "भाषाएँ"]
    assert len(vocabulary_for([f"Name{i} x" for i in range(300)])) == 100


def test_every_input_transcription_is_final() -> None:
    # Before: text waited for a `finished` flag that transcribe-live may never set.
    final = SimpleNamespace(input_transcription=SimpleNamespace(text=" GDP grew 8% "))
    interim = SimpleNamespace(
        input_transcription=None, interim_input_transcription=SimpleNamespace(text="GDP gr")
    )
    assert final_text(final) == "GDP grew 8%"
    assert final_text(interim) == ""
    assert final_text(None) == ""


def test_live_origin_guard_in_prod(settings: Settings) -> None:
    prod = settings.model_copy(
        update={"env": "prod", "public_base_url": "https://proofcard.web.app"}
    )
    c, _ = _client(prod)
    with (
        pytest.raises(WebSocketDisconnect) as e,
        c.websocket_connect("/api/live/whatever123", headers={"origin": "https://evil.example"}),
    ):
        pass
    assert e.value.code == 4403
    with c.websocket_connect(
        "/api/live/whatever123", headers={"origin": "https://proofcard.web.app"}
    ) as ws:
        ws.send_json({"type": "auth", "token": "admin-token"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401  # origin ok, session unknown


def test_dev_verifier_only_when_auth_disabled() -> None:
    from app.main import dev_verifier

    s = Settings(env="local", auth_disabled=True)
    app = create_app(
        settings=s,
        store=InMemoryStore(),
        deps=Deps(InMemoryStore(), StubModel(), FixtureFetcher(), InMemorySnapshots()),
        queue=SyncQueue(),
    )
    assert app.state.verifier is dev_verifier
    assert (
        TestClient(app)
        .post(
            "/api/prebunk", json={"topic": "India"}, headers={"Authorization": "Bearer local-dev"}
        )
        .status_code
        == 201
    )
