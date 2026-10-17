"""Prebunk first, add the live link later (team lead VN, 17 Oct 2026).

An announced event has no stream link yet. The brief is built from topic + speaker; when the
channel publishes the live link the owner adds it, and the same checked claims are what the
live page matches speech against.
"""

from fastapi.testclient import TestClient

from app.store import InMemoryStore

ADMIN = {"Authorization": "Bearer admin-token"}
ANON = {"Authorization": "Bearer anon-token"}
LIVE = "https://www.youtube.com/live/abcdefghijk"


def _brief_without_link(client: TestClient) -> str:
    r = client.post(
        "/api/prebunk",
        json={"topic": "White House briefing on the attack", "speaker": "Press Secretary"},
        headers=ADMIN,
    )
    assert r.status_code == 201
    sid: str = r.json()["session_id"]
    return sid


def test_owner_adds_live_link_later_and_checked_claims_stay(
    client: TestClient, store: InMemoryStore
) -> None:
    sid = _brief_without_link(client)
    before = [(cid, c.card_id, c.status) for cid, c in store.list_claims(sid)]
    assert store.sessions[sid].youtube_url is None
    assert before
    assert all(card for _, card, _ in before)

    r = client.post(f"/api/sessions/{sid}/video", json={"youtube_url": LIVE}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"youtube_url": LIVE}
    assert store.sessions[sid].youtube_url == LIVE
    assert store.sessions[sid].status == "ready"
    after = [(cid, c.card_id, c.status) for cid, c in store.list_claims(sid)]
    assert after == before  # no re-check, no lost card: the prebunks are reused as they are

    view = client.get(f"/api/sessions/{sid}", headers=ADMIN).json()
    assert view["youtube_url"] == LIVE


def test_owner_can_swap_the_link(client: TestClient, store: InMemoryStore) -> None:
    sid = _brief_without_link(client)
    client.post(f"/api/sessions/{sid}/video", json={"youtube_url": LIVE}, headers=ADMIN)
    new = "https://youtu.be/zyxwvutsrqp"
    r = client.post(f"/api/sessions/{sid}/video", json={"youtube_url": new}, headers=ADMIN)
    assert r.status_code == 200
    assert store.sessions[sid].youtube_url == new


def test_only_the_owner_can_add_a_link(client: TestClient, store: InMemoryStore) -> None:
    sid = _brief_without_link(client)
    r = client.post(f"/api/sessions/{sid}/video", json={"youtube_url": LIVE}, headers=ANON)
    assert r.status_code == 404
    assert store.sessions[sid].youtube_url is None
    r = client.post(f"/api/sessions/{sid}/video", json={"youtube_url": LIVE})
    assert r.status_code == 401
    r = client.post("/api/sessions/nope/video", json={"youtube_url": LIVE}, headers=ADMIN)
    assert r.status_code == 404


def test_only_https_youtube_links(client: TestClient, store: InMemoryStore) -> None:
    sid = _brief_without_link(client)
    for bad in ("https://evil.example/watch?v=abcdefghijk", "http://youtu.be/abcdefghijk", ""):
        r = client.post(f"/api/sessions/{sid}/video", json={"youtube_url": bad}, headers=ADMIN)
        assert r.status_code == 422, bad
    assert store.sessions[sid].youtube_url is None
