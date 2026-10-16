"""Public viewer feed (/watch/:id): opt in only, owner toggle, no owner data, cursor."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.schemas import ClaimDoc, ClaimSource, ClaimStatus, SessionDoc, Verdict
from app.store import InMemoryStore

ADMIN = {"Authorization": "Bearer admin-token"}
OTHER = {"Authorization": "Bearer user-other"}


def _session(store: InMemoryStore, public: bool = False) -> str:
    sid = store.create_session(
        SessionDoc(owner_uid="admin-1", topic="press conference", public_view=public)
    )
    store.add_claim(sid, ClaimDoc(text="bank claim", source=ClaimSource.PREDICTED))
    return sid


def test_feed_is_404_until_owner_opts_in(client: TestClient, store: InMemoryStore) -> None:
    sid = _session(store)
    assert client.get(f"/api/sessions/{sid}/feed").status_code == 404
    assert client.get("/api/sessions/bad!/feed").status_code == 404
    assert client.get("/api/sessions/missing-session-id/feed").status_code == 404


def test_only_owner_can_toggle_share(client: TestClient, store: InMemoryStore) -> None:
    sid = _session(store)
    url = f"/api/sessions/{sid}/share"
    assert client.post(url, json={"public_view": True}).status_code == 401
    assert client.post(url, json={"public_view": True}, headers=OTHER).status_code == 404
    assert client.post(url, json={"public_view": "yes please"}, headers=ADMIN).status_code == 422
    r = client.post(url, json={"public_view": True}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"public_view": True}
    assert client.get(f"/api/sessions/{sid}", headers=ADMIN).json()["public_view"] is True
    assert client.get(f"/api/sessions/{sid}/feed").status_code == 200
    client.post(url, json={"public_view": False}, headers=ADMIN)
    assert client.get(f"/api/sessions/{sid}/feed").status_code == 404


def test_feed_shows_live_claims_only_and_never_owner_data(
    client: TestClient, store: InMemoryStore
) -> None:
    sid = _session(store, public=True)
    bank = store.list_claims(sid)[0][0]
    store.add_claim(
        sid,
        ClaimDoc(
            text="inflation halved",
            source=ClaimSource.LIVE,
            status=ClaimStatus.PROVED,
            card_id="card-12345678",
            verdict=Verdict.FALSE,
            matched_claim_id=bank,
            latency_ms=900,
        ),
    )
    store.add_claim(sid, ClaimDoc(text="new claim", source=ClaimSource.LIVE))
    r = client.get(f"/api/sessions/{sid}/feed")
    assert r.status_code == 200
    body = r.json()
    assert "owner_uid" not in r.text
    assert "admin-1" not in r.text
    assert "bank claim" not in r.text
    assert [c["text"] for c in body["claims"]] == ["inflation halved", "new claim"]
    assert body["claims"][0]["matched"] is True
    assert body["claims"][0]["verdict"] == "FALSE"
    assert body["claims"][1]["matched"] is False
    assert set(body) == {"id", "topic", "speaker", "status", "claims", "cursor"}


def test_feed_cursor_returns_new_and_updated_claims(
    client: TestClient, store: InMemoryStore
) -> None:
    sid = _session(store, public=True)
    old = ClaimDoc(
        text="old claim",
        source=ClaimSource.LIVE,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    cid = store.add_claim(sid, old)
    since = (datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None).isoformat()
    assert client.get(f"/api/sessions/{sid}/feed", params={"since": since}).json()["claims"] == []
    store.update_claim(sid, cid, status=ClaimStatus.PROVED, card_id="card-12345678")
    claims = client.get(f"/api/sessions/{sid}/feed", params={"since": since}).json()["claims"]
    assert [c["status"] for c in claims] == ["proved"]
    cursor = client.get(f"/api/sessions/{sid}/feed").json()["cursor"]
    assert datetime.fromisoformat(cursor) < datetime.now(UTC)


def test_feed_is_rate_limited(client: TestClient, store: InMemoryStore) -> None:
    sid = _session(store, public=True)
    client.app.state.feed_limiter.rate_per_min = 2  # type: ignore[attr-defined]
    codes = [client.get(f"/api/sessions/{sid}/feed").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
