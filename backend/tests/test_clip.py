"""Clip upload fallback (B2): transcript -> the same live engine as tab audio."""

from collections.abc import Sequence
from types import SimpleNamespace as Ns

from fastapi.testclient import TestClient

from app.clip import MAX_CLIP_BYTES, clip_mime, sentences, text_from_response
from app.config import Settings
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps
from app.proof import FixtureFetcher, InMemorySnapshots
from app.store import InMemoryStore
from app.tasks import SyncQueue
from tests.conftest import fake_oidc, fake_verifier

ADMIN = {"Authorization": "Bearer admin-token"}


class FakeClip:
    def __init__(self, transcript: str = "", fail: bool = False) -> None:
        self.transcript, self.fail = transcript, fail
        self.calls: list[tuple[int, str, list[str]]] = []

    def transcribe(self, data: bytes, mime: str, vocabulary: Sequence[str] = ()) -> str:
        self.calls.append((len(data), mime, list(vocabulary)))
        if self.fail:
            raise RuntimeError("vertex down")
        return self.transcript


def app_with(settings: Settings, store: InMemoryStore, clip: FakeClip | None) -> TestClient:
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    s = settings.model_copy(update={"prebunk_per_min": 60})
    return TestClient(
        create_app(
            settings=s,
            verifier=fake_verifier,
            store=store,
            deps=deps,
            queue=SyncQueue(),
            oidc_verifier=fake_oidc,
            clip_transcriber=clip,
        )
    )


def test_helpers() -> None:
    assert clip_mime("audio/mp3") == "audio/mpeg"
    assert clip_mime("audio/x-m4a; codecs=mp4a") == "audio/mp4"
    assert clip_mime("video/mp4") is None
    assert clip_mime(None) is None
    got = sentences(
        "Namaste dosto. ok\nIndia has 22 languages in the Eighth Schedule। अगला सवाल यह है"
    )
    assert got == ["India has 22 languages in the Eighth Schedule।", "अगला सवाल यह है"]
    part = Ns(text="", audio_transcription=Ns(text="hello there"))
    resp = Ns(candidates=[Ns(content=Ns(parts=[Ns(text="first"), part, Ns(text=None)]))])
    assert text_from_response(resp) == "first\nhello there"
    assert text_from_response(Ns(parts=[Ns(text="flat")])) == "flat"


def test_clip_runs_the_live_engine(settings: Settings, store: InMemoryStore) -> None:
    clip = FakeClip("")
    c = app_with(settings, store, clip)
    sid = c.post("/api/prebunk", json={"topic": "India"}, headers=ADMIN).json()["session_id"]
    claim = next(cl for _, cl in store.list_claims(sid) if cl.card_id)
    clip.transcript = f"Good evening and welcome to the show. {claim.text}."
    r = c.post(
        f"/api/sessions/{sid}/clip",
        files={"file": ("talk.mp3", b"ID3fake-mp3-bytes", "audio/mpeg")},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sentences"] == 2
    kinds = [e["type"] for e in body["events"]]
    assert "match" in kinds  # the prebunked claim hit instantly, like live speech
    hit = next(e for e in body["events"] if e["type"] == "match")
    assert hit["card_id"] == claim.card_id
    assert clip.calls[0][1] == "audio/mpeg"
    assert store.get_session(sid).status == "ready"  # type: ignore[union-attr]


def test_clip_rejections(settings: Settings, store: InMemoryStore) -> None:
    c = app_with(settings, store, FakeClip("x y z", fail=True))
    sid = c.post("/api/prebunk", json={"topic": "India"}, headers=ADMIN).json()["session_id"]
    url = f"/api/sessions/{sid}/clip"
    mp3 = {"file": ("a.mp3", b"abc", "audio/mpeg")}
    assert c.post(url, files=mp3).status_code == 401
    other = {"Authorization": "Bearer anon-token"}
    assert c.post(url, files=mp3, headers=other).status_code in (401, 403, 404)
    assert c.post("/api/sessions/nope-nope-nope/clip", files=mp3, headers=ADMIN).status_code == 404
    vid = {"file": ("a.mp4", b"abc", "video/mp4")}
    assert c.post(url, files=vid, headers=ADMIN).status_code == 415
    big = {"file": ("a.mp3", b"x" * (MAX_CLIP_BYTES + 1), "audio/mpeg")}
    assert c.post(url, files=big, headers=ADMIN).status_code == 413
    assert c.post(url, files=mp3, headers=ADMIN).status_code == 502  # transcription failed
    none = app_with(settings, store, None)
    assert none.post(url, files=mp3, headers=ADMIN).status_code == 503


def test_clip_cors_only_for_our_origins(settings: Settings, store: InMemoryStore) -> None:
    s = settings.model_copy(update={"public_base_url": "https://proofcard.web.app"})
    c = app_with(s, store, FakeClip())
    pre = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization",
    }
    ok = c.options("/api/sessions/x/clip", headers={"Origin": "https://proofcard.web.app", **pre})
    assert ok.headers.get("access-control-allow-origin") == "https://proofcard.web.app"
    bad = c.options("/api/sessions/x/clip", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in bad.headers
