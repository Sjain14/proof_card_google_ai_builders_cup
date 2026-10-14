from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas import CardDoc, SourceProof, Verdict
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


def test_prebunk_forbids_anonymous(client: TestClient) -> None:
    assert client.post("/api/prebunk", json={"topic": "x"}, headers=ANON).status_code == 403


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


@pytest.mark.parametrize(
    "body",
    [
        {"topic": ""},
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
