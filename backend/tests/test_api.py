from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.schemas import CardDoc, SourceProof, Verdict
from app.security import card_fingerprint, sha256_hex
from app.store import InMemoryStore
from tests.conftest import WEBHOOK_SECRET

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
    assert store.sessions[sid].status == "prebunking"


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
