import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps
from app.proof import FixtureFetcher, InMemorySnapshots
from app.schemas import CardDoc, SessionDoc, SourceProof, Verdict
from app.security import card_fingerprint, sha256_hex
from app.store import InMemoryStore
from app.tasks import SyncQueue
from tests.conftest import WEBHOOK_SECRET, fake_oidc, fake_verifier

ADMIN = {"Authorization": "Bearer admin-token"}
ANON = {"Authorization": "Bearer anon-token"}


def _card(claim: str = "India has 22 scheduled languages") -> CardDoc:
    fields = {
        "claim": claim,
        "verdict": Verdict.TRUE,
        "explanation": "Eighth Schedule lists 22 languages.",
        "sources": [
            SourceProof(
                url="https://example.org/eighth-schedule",
                snippet="The Eighth Schedule ... 22 languages",
                snapshot_sha256=sha256_hex(b"page"),
                fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
            )
        ],
        "support_score": 0.9,
    }
    fp = card_fingerprint({k: str(v) for k, v in fields.items()})
    return CardDoc(card_sha256=fp, **fields)


def test_healthz_has_security_headers(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}  # Cloud Run + Hosting probe
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_prebunk_requires_token(client: TestClient) -> None:
    assert client.post("/api/prebunk", json={"topic": "x"}).status_code == 401


def test_prebunk_rejects_bad_token(client: TestClient) -> None:
    r = client.post("/api/prebunk", json={"topic": "x"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthorized"


def test_prebunk_allows_anonymous(client: TestClient) -> None:
    r = client.post("/api/prebunk", json={"topic": "budget test"}, headers=ANON)
    assert r.status_code == 201
    assert "session_id" in r.json()


def test_anonymous_cannot_get_other_user_session(client: TestClient) -> None:
    r = client.post("/api/prebunk", json={"topic": "admin topic"}, headers=ADMIN)
    assert r.status_code == 201
    sid = r.json()["session_id"]
    r_anon = client.get(f"/api/sessions/{sid}", headers=ANON)
    assert r_anon.status_code == 404
    assert r_anon.json()["detail"] == "not found"


def test_anonymous_per_uid_cap_not_bypassed_by_fake_xff(client: TestClient) -> None:
    client.app.state.prebunk_limiter.rate_per_min = 60  # type: ignore[attr-defined]
    # Anonymous user gets 5 briefs per day
    for i in range(5):
        hdr = {**ANON, "X-Forwarded-For": f"192.168.1.{i}"}
        r = client.post("/api/prebunk", json={"topic": f"topic {i}"}, headers=hdr)
        assert r.status_code == 201

    # 6th request with spoofed IP must still be blocked by per-uid daily cap
    hdr_spoofed = {**ANON, "X-Forwarded-For": "203.0.113.195"}
    r = client.post("/api/prebunk", json={"topic": "topic 5"}, headers=hdr_spoofed)
    assert r.status_code == 429
    assert r.json()["detail"] == "daily brief limit reached"


def test_anonymous_global_daily_cap_not_bypassed_by_fake_xff(
    settings: Settings, store: InMemoryStore
) -> None:
    settings.prebunk_anon_daily_cap = 2
    deps = Deps(
        store=store, model=StubModel(), fetcher=FixtureFetcher(), snapshots=InMemorySnapshots()
    )
    app = create_app(
        settings=settings,
        verifier=fake_verifier,
        store=store,
        deps=deps,
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
    )
    c = TestClient(app)
    # Anon user 1 creates 1 brief with spoofed XFF
    r1 = c.post(
        "/api/prebunk",
        json={"topic": "t1"},
        headers={"Authorization": "Bearer anon-user-1", "X-Forwarded-For": "10.0.0.1"},
    )
    assert r1.status_code == 201

    # Anon user 2 creates 1 brief with spoofed XFF
    r2 = c.post(
        "/api/prebunk",
        json={"topic": "t2"},
        headers={"Authorization": "Bearer anon-user-2", "X-Forwarded-For": "10.0.0.2"},
    )
    assert r2.status_code == 201

    # Anon user 3 attempts with a different fake X-Forwarded-For -> hit global cap
    r3 = c.post(
        "/api/prebunk",
        json={"topic": "t3"},
        headers={"Authorization": "Bearer anon-user-3", "X-Forwarded-For": "10.0.0.3"},
    )
    assert r3.status_code == 429
    assert r3.json()["detail"] == "daily anonymous brief limit reached"

    # Authenticated user is NOT blocked by anonymous global cap
    r_auth = c.post(
        "/api/prebunk",
        json={"topic": "auth topic"},
        headers={**ADMIN, "X-Forwarded-For": "10.0.0.4"},
    )
    assert r_auth.status_code == 201


def test_current_principal_unexpected_error_gives_500(
    settings: Settings, store: InMemoryStore
) -> None:
    def broken_verifier(token: str) -> dict[str, Any]:
        raise RuntimeError("Google IAM internal error")

    app = create_app(settings=settings, verifier=broken_verifier, store=store)
    c = TestClient(app)
    hdr = {"Authorization": "Bearer any-token"}
    r = c.post("/api/prebunk", json={"topic": "test"}, headers=hdr)
    assert r.status_code == 500
    assert "auth verification failed" in r.json()["detail"]


def test_prebunk_creates_owned_session(client: TestClient, store: InMemoryStore) -> None:
    r = client.post(
        "/api/prebunk",
        json={"topic": "budget speech", "youtube_url": "https://youtu.be/abc"},
        headers=ADMIN,
    )
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert store.sessions[sid].owner_uid == "admin-1"
    # SyncQueue runs the prebunk job inline: offline fixtures give 6 proved cards.
    assert store.sessions[sid].status == "ready"
    claims = store.list_claims(sid)
    assert len(claims) == 6
    assert all(c.card_id for _, c in claims)


def test_prebunk_link_only_takes_video_title(client: TestClient, store: InMemoryStore) -> None:
    url = "https://www.youtube.com/watch?v=7dhIVHRKhvo"
    # stub mode has no title lookup: a link alone is refused with a clear reason
    r = client.post("/api/prebunk", json={"youtube_url": url}, headers=ADMIN)
    assert r.status_code == 422
    assert "add a topic" in r.json()["detail"]
    state = client.app.state  # type: ignore[attr-defined]
    state.deps = dataclasses.replace(
        state.deps, video_title=lambda u: "  Union Budget 2022 speech, Nirmala Sitharaman  "
    )
    r = client.post("/api/prebunk", json={"youtube_url": url}, headers=ADMIN)
    assert r.status_code == 201
    s = store.get_session(r.json()["session_id"])
    assert s is not None
    assert s.topic == "Union Budget 2022 speech, Nirmala Sitharaman"
    assert s.youtube_url == url


@pytest.mark.parametrize(
    "body",
    [
        {"topic": ""},
        {"topic": "   "},
        {"topic": "x" * 501},
        {"topic": "x", "is_admin": True},
        {"topic": "x", "youtube_url": "https://evil.example/watch"},
        {"topic": "x", "youtube_url": "http://youtube.com/watch?v=1"},
    ],
)
def test_prebunk_validates_input(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/api/prebunk", json=body, headers=ADMIN).status_code == 422


def test_body_size_limit(client: TestClient) -> None:
    r = client.post("/api/prebunk", content=b"x" * 6_000, headers=ADMIN)
    assert r.status_code == 413


def test_card_lookup_and_check(client: TestClient, store: InMemoryStore) -> None:
    card = _card()
    store.put_card("card_abcdefgh", card)
    assert client.get("/api/cards/card_abcdefgh").json()["verdict"] == "TRUE"
    assert client.get("/api/cards/missing1234").status_code == 404
    assert client.get("/api/cards/..%2Fx").status_code == 404
    ok = client.post("/api/check", json={"card_id": "card_abcdefgh", "text": card.claim})
    assert ok.json()["result"] == "VERIFIED"
    bad = client.post("/api/check", json={"card_id": "card_abcdefgh", "text": "India has 2"})
    assert bad.json()["result"] == "ALTERED"


def test_check_unknown_card_is_404(client: TestClient) -> None:
    r = client.post("/api/check", json={"card_id": "nocard1234", "text": "x"})
    assert r.status_code == 404


def test_public_check_is_rate_limited(client: TestClient, store: InMemoryStore) -> None:
    store.put_card("card_abcdefgh", _card())
    body = {"card_id": "card_abcdefgh", "text": "x"}
    codes = [client.post("/api/check", json=body).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]


def test_webhook_rejects_missing_or_wrong_secret(client: TestClient) -> None:
    upd = {"update_id": 1}
    assert client.post("/tg/webhook", json=upd).status_code == 404
    wrong = {"X-Telegram-Bot-Api-Secret-Token": "nope"}
    assert client.post("/tg/webhook", json=upd, headers=wrong).status_code == 404


def test_webhook_accepts_valid_update(client: TestClient) -> None:
    hdr = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
    upd = {
        "update_id": 7,
        "message": {
            "message_id": 1,
            "chat": {"id": 123456, "type": "private"},
            "from": {"id": 123456},
            "text": "/start card_abcdefgh",
            "future_field": {"ignored": True},
        },
    }
    r = client.post("/tg/webhook", json=upd, headers=hdr)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_webhook_acks_junk_without_crashing(client: TestClient) -> None:
    hdr = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
    r = client.post("/tg/webhook", content=b"not json", headers=hdr)
    assert r.status_code == 200


def test_rate_limit_ignores_spoofed_forwarded_for(client: TestClient, store: InMemoryStore) -> None:
    store.put_card("card_abcdefgh", _card())
    body = {"card_id": "card_abcdefgh", "text": "x"}
    codes = [
        client.post(
            "/api/check", json=body, headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"}
        ).status_code
        for i in range(5)
    ]
    assert 429 in codes


def test_prebunk_burst_limit_per_user(client: TestClient) -> None:
    codes = [
        client.post("/api/prebunk", json={"topic": f"topic {i}"}, headers=ADMIN).status_code
        for i in range(5)
    ]
    assert codes[:3] == [201, 201, 201]  # prebunk_per_min default 3
    assert codes[3:] == [429, 429]


def test_prebunk_daily_cap_is_durable(settings: Settings, store: InMemoryStore) -> None:
    # The cap counts stored sessions, so it holds across instances and restarts.
    capped = settings.model_copy(update={"prebunk_daily_cap": 2, "prebunk_per_min": 60})
    app = create_app(
        settings=capped,
        verifier=fake_verifier,
        store=store,
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
    )
    c = TestClient(app)
    codes = [
        c.post("/api/prebunk", json={"topic": "t"}, headers=ADMIN).status_code for _ in range(3)
    ]
    assert codes == [201, 201, 429]
    assert store.count_sessions_since("admin-1", "2000-01-01") == 2
    assert store.count_sessions_since("admin-1", "2999-01-01") == 0


def test_local_stub_mode_runs_without_gcp() -> None:
    # README "Run locally" crashed with DefaultCredentialsError before (audit #15).
    app = create_app(settings=Settings(_env_file=None, env="local", auth_disabled=True))
    assert isinstance(app.state.store, InMemoryStore)
    c = TestClient(app)
    r = c.post("/api/prebunk", json={"topic": "India"}, headers={"Authorization": "Bearer x"})
    assert r.status_code == 201


def test_snapshot_download_proves_the_hash(client: TestClient, store: InMemoryStore) -> None:
    sid = client.post("/api/prebunk", json={"topic": "India"}, headers=ADMIN).json()["session_id"]
    claim = next(c for _, c in store.list_claims(sid) if c.card_id)
    digest = store.cards[str(claim.card_id)].sources[0].snapshot_sha256
    r = client.get(f"/api/snapshots/{digest}")
    assert r.status_code == 200
    assert sha256_hex(r.content) == digest
    assert r.headers["content-type"] == "application/octet-stream"  # never rendered here
    assert r.headers["content-disposition"].startswith("attachment")
    page = client.get(f"/v/{claim.card_id}").text
    assert f'href="/api/snapshots/{digest}"' in page
    snaps = client.app.state.deps.snapshots  # type: ignore[attr-defined]
    assert client.get(f"/api/snapshots/{'0' * 64}").status_code == 404
    snaps.blobs[digest] = b"tampered"
    assert client.get(f"/api/snapshots/{digest}").status_code == 404
    assert client.get("/api/snapshots/not-a-hash").status_code == 404
    assert client.get(f"/api/snapshots/{digest}").status_code == 429  # public limit, 3/min here


CHIP = (
    "<style>.chip{color:#1f1f1f}</style>"
    '<a class="chip" href="https://www.google.com/search?q=22+languages">22 languages</a>'
)


def test_search_suggestion_frame_and_route(client: TestClient, store: InMemoryStore) -> None:
    sid = client.post("/api/prebunk", json={"topic": "India"}, headers=ADMIN).json()["session_id"]
    claim = next(c for _, c in store.list_claims(sid) if c.card_id)
    cid = str(claim.card_id)
    plain = store.cards[cid]
    assert client.get(f"/api/cards/{cid}/search-suggestion").status_code == 404
    assert 'class="gsugg"' not in client.get(f"/v/{cid}").text
    store.cards[cid] = plain.model_copy(update={"search_suggestion_html": CHIP})
    # presentation only: the proof fingerprint does not move
    assert card_fingerprint(store.cards[cid].model_dump(mode="json")) == card_fingerprint(
        plain.model_dump(mode="json")
    )
    r = client.get(f"/api/cards/{cid}/search-suggestion")
    assert r.status_code == 200
    assert CHIP in r.text  # byte for byte, unmodified
    assert '<base target="_blank">' in r.text
    assert "script-src" not in r.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    page = client.get(f"/v/{cid}")
    assert f'src="/api/cards/{cid}/search-suggestion"' in page.text
    assert 'sandbox="allow-popups allow-popups-to-escape-sandbox"' in page.text
    assert "frame-src 'self'" in page.headers["content-security-policy"]
    assert CHIP not in page.text  # never inline on our origin
    assert client.get("/api/cards/bad!/search-suggestion").status_code == 404


def test_stalled_prebunk_is_requeued_on_read(client: TestClient, store: InMemoryStore) -> None:
    # A revision swap killed the job mid run (16 Oct): the brief sat in "prebunking".
    old = datetime.now(UTC) - timedelta(minutes=30)
    sid = store.create_session(
        SessionDoc(owner_uid="admin-1", topic="budget speech", status="prebunking", created_at=old)
    )
    r = client.get(f"/api/sessions/{sid}", headers=ADMIN)
    assert r.status_code == 200
    # SyncQueue ran the re-queued job inline: the brief finished.
    assert store.sessions[sid].status == "ready"
    assert len(store.list_claims(sid)) == 6


def test_live_prebunk_is_left_alone(client: TestClient, store: InMemoryStore) -> None:
    sid = store.create_session(
        SessionDoc(
            owner_uid="admin-1",
            topic="budget speech",
            status="prebunking",
            prebunk_beat=datetime.now(UTC),
        )
    )
    assert client.get(f"/api/sessions/{sid}", headers=ADMIN).status_code == 200
    assert store.sessions[sid].status == "prebunking"
    assert store.list_claims(sid) == []
