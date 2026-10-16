"""Live bridge: spotting, instant match vs cold path, websocket auth and protocol."""

from __future__ import annotations

import asyncio
import math
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
    LiveEngine,
    cosine,
    final_text,
    heuristic_spot,
    numbers,
    vocabulary_for,
)
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps
from app.proof import FixtureFetcher, InMemorySnapshots
from app.schemas import ClaimDoc, ClaimSource, ClaimStatus, SessionDoc
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


def test_numbers() -> None:
    assert numbers("RBI ne repo rate 2025 me 4 percent kar diya") == {"2025", "4"}
    assert numbers("1,40,000 log") == {"140000"}
    assert numbers("12.5 crore, 140 crore") == {"12.5", "140"}
    assert numbers("India chauthi sabse badi economy") == frozenset()


class _SameVec:
    """Every text embeds to the same vector: cosine 1.0, so only the number guard decides."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_match_never_borrows_a_card_with_different_numbers() -> None:
    # Live run 15 Oct: "repo rate 4% in 2025" took the "4th largest economy by 2025" card
    # (cosine 0.806) and "per capita GDP" took a population card. Same numbers or no match.
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    texts = {
        "econ": "India will become the fourth largest economy by 2025",
        "pop": "Japan has 12.5 crore people and India 140 crore",
    }
    ids = {
        k: store.add_claim(
            sid,
            ClaimDoc(
                text=t,
                source=ClaimSource.PREDICTED,
                status=ClaimStatus.PROVED,
                card_id="card-" + k,
            ),
        )
        for k, t in texts.items()
    }
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())

    async def emit(ev: dict[str, Any]) -> None:
        return None

    eng = LiveEngine(sid, LiveDeps(deps, _SameVec(), HeuristicSpotter()), emit)
    assert eng.match("RBI cut the repo rate to 4 percent in 2025")[0] is None
    assert eng.match("India per capita GDP is higher than Japan")[0] is None
    assert eng.match("IMF says India is the fourth largest economy in 2025")[0] == ids["econ"]
    assert eng.match("India 140 crore, Japan 12.5 crore log")[0] == ids["pop"]


class _Judge:
    def __init__(self, same: bool) -> None:
        self.same, self.calls = same, 0

    def same_claim(self, heard: str, checked: str) -> bool:
        self.calls += 1
        return self.same


class _Vec:
    """Cosine set per text: 'gray' texts score 0.85 against everything, others 1.0."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.85, math.sqrt(1 - 0.85**2)] if "gray" in t else [1.0, 0.0] for t in texts]


def _engine(judge: Any, embedder: Any = None) -> tuple[LiveEngine, list[dict[str, Any]], str]:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    pid = store.add_claim(
        sid,
        ClaimDoc(
            text="India has 22 scheduled languages",
            source=ClaimSource.PREDICTED,
            status=ClaimStatus.PROVED,
            card_id="card-1",
        ),
    )
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    events: list[dict[str, Any]] = []

    async def emit(ev: dict[str, Any]) -> None:
        events.append(ev)

    live = LiveDeps(deps, embedder or _Vec(), HeuristicSpotter(), judge=judge)
    return LiveEngine(sid, live, emit), events, pid


def test_gray_zone_match_needs_the_judge() -> None:
    no = _Judge(False)
    eng, events, _ = _engine(no)
    asyncio.run(eng.warm())
    asyncio.run(eng.on_sentence("gray zone: India has 22 official languages in total"))
    asyncio.run(eng.drain())
    kinds = [e["type"] for e in events]
    assert "match" not in kinds
    assert "checking" in kinds
    assert no.calls == 1

    yes = _Judge(True)
    eng, events, _ = _engine(yes)
    asyncio.run(eng.on_sentence("gray zone: India has 22 official languages in total"))
    hit = next(e for e in events if e["type"] == "match")
    assert hit["card_id"] == "card-1"
    assert yes.calls == 1


def test_strong_match_is_instant_and_shown_once() -> None:
    judge = _Judge(False)  # never consulted above the instant threshold
    eng, events, _ = _engine(judge)
    asyncio.run(eng.on_sentence("India has 22 scheduled languages, everyone knows"))
    asyncio.run(eng.on_sentence("as I said, India has 22 scheduled languages for sure"))
    asyncio.run(eng.drain())
    assert [e["type"] for e in events].count("match") == 1
    assert judge.calls == 0


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


def test_anonymous_cannot_connect_to_other_user_live_ws(settings: Settings) -> None:
    c, _ = _client(settings)
    sid = _session(c)  # created by admin-token
    with c.websocket_connect(f"/api/live/{sid}") as ws:
        ws.send_json({"type": "auth", "token": "anon-token"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_anonymous_can_connect_to_own_live_ws(settings: Settings) -> None:
    c, _ = _client(settings)
    hdr = {"Authorization": "Bearer anon-token"}
    r = c.post("/api/prebunk", json={"topic": "India"}, headers=hdr)
    sid = r.json()["session_id"]
    with c.websocket_connect(f"/api/live/{sid}") as ws:
        ws.send_json({"type": "auth", "token": "anon-token"})
        msg = ws.receive_json()
        assert msg["type"] == "ready"


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


def test_heuristic_lets_comparatives_through() -> None:
    # Prod check 16 Oct: comparatives without a digit were dropped before the spotter.
    assert heuristic_spot("India per capita GDP is higher than Japan")
    assert heuristic_spot("We now have fewer jobs than China")
    assert heuristic_spot("India ki GDP Japan se zyada hai ab")
    assert not heuristic_spot("Thank you all for coming tonight")
    assert not heuristic_spot("Good evening and welcome everyone")


class _Ortho:
    """Lines naming Japan sit orthogonal to the prebunked claim: no match, a cold check."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 1.0] if "Japan" in t or "जापान" in t else [1.0, 0.0] for t in texts]


def test_country_figure_without_a_number_is_still_checked() -> None:
    # prod 16 Oct 2026: the spotter returned [] for these comparisons -> skipped not_checkable
    lines = ("भारत की प्रति व्यक्ति आय जापान से अधिक है।", "India ka per capita GDP Japan se zyada hai")
    for line in lines:
        eng, events, _ = _engine(_Judge(False), _Ortho())
        asyncio.run(eng.on_sentence(line))
        asyncio.run(eng.drain())
        kinds = [e["type"] for e in events]
        assert "checking" in kinds, kinds
        assert "skipped" not in kinds


def test_line_with_no_figure_stays_skipped() -> None:
    eng, events, _ = _engine(_Judge(False), _Ortho())
    asyncio.run(eng.on_sentence("Japan is a really beautiful country to visit"))
    assert events[-1] == {
        "type": "skipped",
        "text": "Japan is a really beautiful country to visit",
        "reason": "not_checkable",
    }


# ---------- recall (replay 7dhIVHRKhvo: 0 of 6 lines matched the bank) ----------


class _Cos:
    """Fixed cosine 0.72 for every pair: under MATCH_THRESHOLD, over RECALL_THRESHOLD."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.72, math.sqrt(1 - 0.72**2)] if "spoken" in t else [1.0, 0.0] for t in texts]


def test_loose_candidate_reaches_the_judge_and_only_its_yes_counts() -> None:
    # Bank says "22", the line states no number at cosine 0.72: before, the exact number
    # gate and the 0.80 floor dropped it before the judge ever saw it.
    line = "spoken: our country has the most scheduled languages"
    yes = _Judge(True)
    eng, _, pid = _engine(yes, _Cos())
    assert asyncio.run(eng._find_match(line))[0] == pid
    assert yes.calls == 1
    no = _Judge(False)
    eng, _, _ = _engine(no, _Cos())
    assert asyncio.run(eng._find_match(line))[0] is None
    assert no.calls == 1


def test_disjoint_numbers_never_reach_the_judge() -> None:
    judge = _Judge(True)
    eng, _, _ = _engine(judge, _Cos())
    assert asyncio.run(eng._find_match("spoken: India has 24 scheduled languages"))[0] is None
    assert judge.calls == 0


def test_without_a_judge_loose_candidates_are_ignored() -> None:
    eng, _, _ = _engine(None, _Cos())
    assert eng.candidates("spoken: our country has the most scheduled languages") == []


def test_failed_cold_check_says_why() -> None:
    eng, events, _ = _engine(_Judge(False))

    async def run() -> None:
        await eng.on_sentence("Mumbai has 40 million cars on the road today")
        await eng.drain()

    asyncio.run(run())
    end = next(e for e in events if e["type"] in ("proved", "failed"))
    assert "stages" in end
    if end["type"] == "failed":
        assert end["reason"]


def test_heuristic_lets_done_deeds_and_absolutes_reach_the_model() -> None:
    # Trump demo (16 Oct): skipped as not_checkable before the model ever saw them.
    assert heuristic_spot("I got all the hostages back, every single one of them")
    assert heuristic_spot("We ended the war between those two countries")
    assert heuristic_spot("Iran will never have a nuclear weapon")  # the model rules it a pledge
    assert heuristic_spot("humne sabhi bandhak wapas la diye hain")
    assert not heuristic_spot("Thank you so much, it is great to be here tonight")
    assert not heuristic_spot("Did they get the hostages back?")


# ---------- one card per claim on screen (p42) ----------


def test_same_claim_in_other_words_is_checked_once() -> None:
    # Team lead, Trump demo 16 Oct: two wordings of one line -> two identical cards.
    eng, events, _ = _engine(_Judge(False))

    async def run() -> None:
        await eng.on_sentence("Mumbai has 40 million cars on the road today")
        await eng.on_sentence("There are 40 million cars on Mumbai roads right now")
        await eng.drain()

    asyncio.run(run())
    assert [e["type"] for e in events].count("checking") == 1
    assert any(e["type"] == "skipped" and e["reason"] == "repeat" for e in events)


def test_other_numbers_are_a_new_claim() -> None:
    eng, events, _ = _engine(_Judge(True))

    async def run() -> None:
        await eng.on_sentence("Mumbai has 40 million cars on the road today")
        await eng.on_sentence("Delhi has 12 million cars on the road today")
        await eng.drain()

    asyncio.run(run())
    assert [e["type"] for e in events].count("checking") == 2


def test_two_prebunked_claims_sharing_a_card_show_it_once() -> None:
    eng, events, pid = _engine(_Judge(False))
    store = eng.live.deps.store
    twin = store.add_claim(
        eng.sid,
        ClaimDoc(
            text="The Eighth Schedule lists 22 languages",
            source=ClaimSource.PREDICTED,
            status=ClaimStatus.PROVED,
            card_id="card-1",
        ),
    )

    async def run() -> tuple[bool | None, bool | None]:
        a = await eng._push_match("22 languages", pid, 0.99, 0.0)
        b = await eng._push_match("22 scheduled languages", twin, 0.99, 0.0)
        return a, b

    assert asyncio.run(run()) == (True, False)
    assert [e["type"] for e in events].count("match") == 1
