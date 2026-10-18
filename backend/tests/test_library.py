"""p75 Proof Library: listing, search, filters, pagination, incremental reads, no PII."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.library import Library, row_from_dict
from app.schemas import CardDoc, SourceProof, Verdict
from app.security import sha256_hex
from app.store import InMemoryStore

T0 = datetime(2026, 10, 10, tzinfo=UTC)


def _card(claim: str, verdict: Verdict, day: int, expl: str = "Official data shows it.") -> CardDoc:
    return CardDoc(
        claim=claim,
        verdict=verdict,
        explanation=expl,
        sources=[
            SourceProof(
                url="https://www.pib.gov.in/release/1",
                snippet="snippet",
                snapshot_sha256=sha256_hex(b"p"),
                fetched_at=T0,
            )
        ],
        support_score=0.91,
        card_sha256=sha256_hex(claim.encode()),
        created_at=T0 + timedelta(days=day),
    )


def _seed(store: InMemoryStore) -> None:
    store.put_card("card_gdp00001", _card("India GDP grew 8.2 percent in 2024", Verdict.TRUE, 0))
    store.put_card("card_inf00002", _card("Inflation is at a 40 year high", Verdict.FALSE, 1))
    store.put_card("card_lng00003", _card("India has 22 scheduled languages", Verdict.TRUE, 2))
    store.put_card(
        "card_hin00004", _card("भारत में 22 अनुसूचित भाषाएं हैं", Verdict.MISLEADING, 3, "संविधान")
    )
    store.put_card("card_unv00005", _card("Aliens built the parliament", Verdict.UNVERIFIABLE, 4))


class CountingSource:
    def __init__(self, store: InMemoryStore) -> None:
        self.store, self.calls = store, 0

    def cards_page(self, after: Any, limit: int) -> Any:
        self.calls += 1
        return self.store.cards_page(after, limit)


def test_lists_newest_first_with_public_safe_fields(
    client: TestClient, store: InMemoryStore
) -> None:
    _seed(store)
    r = client.get("/api/cards")
    assert r.status_code == 200
    assert "s-maxage=60" in r.headers["cache-control"]
    body = r.json()
    assert body["total"] == 5
    assert body["matched"] == 5
    assert [c["id"] for c in body["items"]][:2] == ["card_unv00005", "card_hin00004"]
    assert set(body["items"][0]) == {
        "id", "claim", "verdict", "excerpt",
        "support_score", "created_at", "domains", "source_count",
    }  # fmt: skip
    assert body["items"][0]["domains"] == ["pib.gov.in"]
    assert body["counts"] == {"TRUE": 2, "FALSE": 1, "MISLEADING": 1, "UNVERIFIABLE": 1}


def test_search_ranks_relevance_typos_and_hindi(client: TestClient, store: InMemoryStore) -> None:
    _seed(store)
    hits = client.get("/api/cards", params={"q": "scheduled languages"}).json()["items"]
    assert hits[0]["id"] == "card_lng00003"
    assert (
        client.get("/api/cards", params={"q": "inflaton"}).json()["items"][0]["id"]
        == "card_inf00002"
    )
    assert client.get("/api/cards", params={"q": "gd"}).json()["items"][0]["id"] == "card_gdp00001"
    hi = client.get("/api/cards", params={"q": "अनुसूचित भाषाएं"}).json()["items"]
    assert hi[0]["id"] == "card_hin00004"
    assert client.get("/api/cards", params={"q": "zebra crossing"}).json()["matched"] == 0


def test_filters_verdict_and_time(client: TestClient, store: InMemoryStore) -> None:
    _seed(store)
    got = client.get("/api/cards", params={"verdict": "true,false"}).json()
    assert {c["verdict"] for c in got["items"]} == {"TRUE", "FALSE"}
    assert got["matched"] == 3
    assert got["counts"]["MISLEADING"] == 1  # chips still show every verdict's count
    since = (T0 + timedelta(days=2)).isoformat()
    assert client.get("/api/cards", params={"since": since}).json()["matched"] == 3
    until = (T0 + timedelta(days=1)).isoformat()
    assert client.get("/api/cards", params={"until": until}).json()["matched"] == 2
    assert client.get("/api/cards", params={"verdict": "maybe"}).status_code == 422


def test_keyset_pages_never_repeat_when_a_card_lands(store: InMemoryStore) -> None:
    for n in range(30):
        store.put_card(f"card_p{n:07d}", _card(f"claim number {n}", Verdict.TRUE, n))
    lib = Library(store, refresh_s=0)
    first = lib.search(limit=24)
    assert len(first["items"]) == 24
    assert first["next_cursor"]
    store.put_card("card_newest01", _card("brand new", Verdict.FALSE, 99))
    second = lib.search(cursor=first["next_cursor"], limit=24)
    ids = [c["id"] for c in first["items"]] + [c["id"] for c in second["items"]]
    assert len(ids) == len(set(ids)) == 30
    assert second["next_cursor"] is None


def test_search_pages_by_offset(store: InMemoryStore) -> None:
    for n in range(30):
        store.put_card(f"card_q{n:07d}", _card(f"wheat price {n}", Verdict.TRUE, n))
    lib = Library(store)
    a = lib.search(q="wheat")
    b = lib.search(q="wheat", cursor=a["next_cursor"])
    assert len(a["items"]) == 24
    assert len(b["items"]) == 6


def test_bad_cursor_is_422(client: TestClient, store: InMemoryStore) -> None:
    _seed(store)
    assert client.get("/api/cards", params={"cursor": "%%%not-base64"}).status_code == 422
    assert client.get("/api/cards", params={"cursor": "eyJ0Ijoibm9wZSJ9"}).status_code == 422


def test_reads_only_new_cards_after_first_load(store: InMemoryStore) -> None:
    _seed(store)
    now = [0.0]
    src = CountingSource(store)
    lib = Library(src, clock=lambda: now[0], refresh_s=30)
    assert lib.total() == 5
    first_calls = src.calls
    assert lib.total() == 5
    assert src.calls == first_calls
    store.put_card("card_late0001", _card("late claim", Verdict.TRUE, 10))
    now[0] = 31.0
    assert lib.total() == 6
    assert src.calls - first_calls <= 2  # one page of new cards, one empty page


def test_malformed_docs_are_skipped() -> None:
    assert (
        row_from_dict("x", {"claim": "c", "verdict": "SURE", "created_at": T0.isoformat()}) is None
    )
    assert row_from_dict("x", {"claim": "c", "verdict": "TRUE", "created_at": "yesterday"}) is None
    assert (
        row_from_dict("x", {"claim": "c", "verdict": "TRUE", "created_at": "2026-10-10T00:00:00"})
        is None
    )
    row = row_from_dict(
        "x", {"claim": "c", "verdict": "TRUE", "created_at": "2026-10-10T00:00:00Z"}
    )
    assert row is not None
    assert row.source_count == 0
    assert row.domains == ()


def test_unknown_or_repeated_params_are_rejected_so_the_cdn_key_stays_clean(
    client: TestClient, store: InMemoryStore
) -> None:
    _seed(store)
    r = client.get("/api/cards", params={"cb": "123"})
    assert r.status_code == 400
    assert "cache-control" not in r.headers  # a 400 is never cached at the CDN
    assert client.get("/api/cards?q=gdp&q=tax").status_code == 400
    assert client.get("/api/cards", params={"q": "gdp", "_": "1"}).status_code == 400
    ok = client.get(
        "/api/cards",
        params={
            "q": "gdp",
            "verdict": "true",
            "since": "2026-10-01T00:00:00Z",
            "until": "2026-10-30T00:00:00Z",
        },
    )
    assert ok.status_code == 200


def test_library_rate_limit_is_per_real_client_behind_firebase_hosting(
    client: TestClient, store: InMemoryStore
) -> None:
    _seed(store)
    client.app.state.library_limiter.rate_per_min = 2  # type: ignore[attr-defined]

    # Firebase Hosting: XFF is "<client>, <Google proxy>", a different proxy per hit (p77).
    def hit(edge: str, who: str = "203.0.113.7") -> Any:
        return client.get("/api/cards", headers={"x-forwarded-for": f"{who}, {edge}"})

    assert hit("66.249.82.98").status_code == 200
    assert hit("192.178.14.5").status_code == 200
    r = hit("66.249.82.224")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "30"
    assert r.headers["cache-control"] == "no-store"
    assert hit("66.249.82.69", who="198.51.100.9").status_code == 200  # someone else is fine
    # A spoofed left entry can't dodge it: the real client is the hop before the edge.
    assert (
        client.get(
            "/api/cards", headers={"x-forwarded-for": "10.9.9.9, 203.0.113.7, 66.249.82.98"}
        ).status_code
        == 429
    )
    # Direct to Cloud Run (no CDN hop): the rightmost entry is the client, as before.
    assert (
        client.get("/api/cards", headers={"x-forwarded-for": "1.2.3.4, 203.0.113.7"}).status_code
        == 429
    )


def test_cdn_hop_detection() -> None:
    from app.security import is_cdn_hop

    assert is_cdn_hop("66.249.82.98")
    assert is_cdn_hop("192.178.14.5")
    assert is_cdn_hop("2a00:1450::1")
    assert not is_cdn_hop("151.101.65.140")  # Fastly is not in the Hosting chain
    assert not is_cdn_hop("34.100.1.1")  # Cloud customer range
    assert not is_cdn_hop("203.0.113.7")
    assert not is_cdn_hop("not-an-ip")
    assert not is_cdn_hop("::1")
