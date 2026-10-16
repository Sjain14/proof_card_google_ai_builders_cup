"""Research fact bank (app/facts.py): build, verify sources, reuse, rule lines against it."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.facts import (
    MIN_REUSE,
    Candidate,
    Ruling,
    bank_key,
    build_bank,
    candidates_from,
    checked_ruling,
    ensure_bank,
    official,
    parse_json_list,
    render_facts,
    verify_candidate,
)
from app.model import Assessment
from app.pipeline import Deps, run_prebunk, verify_claim
from app.proof import Fetched, FetchError, InMemorySnapshots
from app.schemas import (
    ClaimDoc,
    ClaimSource,
    ClaimStatus,
    Fact,
    FactBankDoc,
    SessionDoc,
    Verdict,
)
from app.store import InMemoryStore

GDP = "<p>Real GDP grew 8.2 per cent in 2023-24, the National Statistics Office said.</p>"
CPI = "<p>Retail inflation eased to 5.4 per cent in 2023-24, the ministry said.</p>"
CHATTER = "<p>Growth was strong this year, analysts said.</p>"


class MapFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str) -> Fetched:
        self.calls.append(url)
        if url not in self.pages:
            raise FetchError("nope")
        return Fetched(url, url, self.pages[url].encode(), "text/html", datetime.now(UTC))


GDP_FACT = Candidate(
    "India's real GDP grew 8.2 per cent in 2023-24",
    value="8.2 per cent",
    as_of="2023-24",
    angle="growth",
    trigger="we grew at 8.2%",
    urls=("https://mospi.gov.in/gdp",),
)
CPI_FACT = Candidate(
    "Retail inflation eased to 5.4 per cent in 2023-24",
    value="5.4",
    angle="prices",
    urls=("https://news.example.com/cpi",),
)


@dataclass
class FakeDesk:
    cands: list[Candidate] = field(default_factory=lambda: [CPI_FACT, GDP_FACT, GDP_FACT])
    ruling: Ruling | None = None
    angle_calls: int = 0
    seen: list[str] = field(default_factory=list)

    def angles(self, topic: str, speaker: str, k: int) -> list[str]:
        self.angle_calls += 1
        return ["growth", "prices"]

    def research(self, topic: str, speaker: str, angle: str, n: int) -> list[Candidate]:
        return [c for c in self.cands if c.angle == angle]

    def rule(self, claim: str, facts: list[Fact]) -> Ruling | None:
        self.seen.append(claim)
        return checked_ruling(self.ruling, facts)


PAGES = {"https://mospi.gov.in/gdp": GDP, "https://news.example.com/cpi": CPI}


def _fact(i: int, url: str = "https://mospi.gov.in/gdp") -> Fact:
    return Fact(
        id=i,
        statement="India's real GDP grew 8.2 per cent in 2023-24",
        source_url=url,
        passage="Real GDP grew 8.2 per cent in 2023-24",
        support=0.9,
        official=official(url),
    )


def test_bank_key_is_stable_and_valid() -> None:
    k = bank_key("India's economic growth!", "Nirmala Sitharaman")
    assert k == bank_key("india's  economic growth", "nirmala sitharaman")
    assert k.startswith("india-s-economic-growth-nirmala-sitharaman-")
    hindi = bank_key("भारत की जीडीपी", "")
    assert len(hindi) == 12
    assert hindi != bank_key("भारत की महंगाई", "")
    FactBankDoc(key=k, topic="t", prompt_version="v")  # pattern accepts it


def test_official_hosts() -> None:
    assert official("https://pib.gov.in/x")
    assert official("https://www.bls.gov/cpi")
    assert official("https://data.worldbank.org/x")
    assert official("https://www.imf.org/en")
    assert not official("https://www.legal500.com/x")
    assert not official("https://thehindu.com")


def test_verify_candidate_needs_page_and_figure() -> None:
    f = MapFetcher({**PAGES, "https://blog.example/a": CHATTER})
    got = verify_candidate(GDP_FACT, f)
    assert not isinstance(got, str)
    url, passage, score = got
    assert url == "https://mospi.gov.in/gdp"
    assert "8.2" in passage
    assert score >= 0.35
    on_topic_no_figure = Candidate(GDP_FACT.statement, "8.2", urls=("https://blog.example/a",))
    assert verify_candidate(on_topic_no_figure, f) in ("figure_missing", "low_support:0.00")
    assert verify_candidate(Candidate("x"), f) == "no_url"
    assert str(verify_candidate(Candidate("x", urls=("https://dead/x",)), f)).startswith("fetch:")
    fallback = Candidate(GDP_FACT.statement, "8.2", urls=("https://dead/x", GDP_FACT.urls[0]))
    assert verify_candidate(fallback, f)[0] == GDP_FACT.urls[0]


def test_build_bank_keeps_verified_official_first() -> None:
    desk = FakeDesk(
        cands=[
            *FakeDesk().cands,
            Candidate("Made up fact 99", angle="growth", urls=("https://x/y",)),
        ]
    )
    bank = build_bank("growth", "Nirmala Sitharaman", desk, MapFetcher(PAGES))
    assert bank.researched == 3  # duplicate GDP fact dropped before verification
    assert [f.statement for f in bank.facts] == [GDP_FACT.statement, CPI_FACT.statement]
    assert [f.id for f in bank.facts] == [0, 1]
    assert bank.facts[0].official
    assert not bank.facts[1].official
    assert bank.facts[0].trigger == "we grew at 8.2%"
    assert bank.stats["angles"] == 2
    assert bank.stats["drop_fetch"] == 1
    assert bank.samples[0].startswith("fetch:")


def test_verify_candidate_survives_broken_page() -> None:
    class Broken(MapFetcher):
        def fetch(self, url: str) -> Fetched:
            return Fetched(url, url, b"%PDF-1.4 broken", "application/pdf", datetime.now(UTC))

    got = verify_candidate(GDP_FACT, Broken({}))
    assert isinstance(got, str)


def test_build_bank_skips_invalid_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kw: Any) -> Fact:
        raise ValueError("odd")

    monkeypatch.setattr("app.facts.Fact", boom)
    bank = build_bank("growth", "", FakeDesk(cands=[GDP_FACT]), MapFetcher(PAGES))
    assert bank.facts == []
    assert bank.stats["drop_invalid"] == 1


def test_build_bank_survives_desk_failures() -> None:
    class Broken(FakeDesk):
        def angles(self, topic: str, speaker: str, k: int) -> list[str]:
            raise RuntimeError("down")

        def research(self, topic: str, speaker: str, angle: str, n: int) -> list[Candidate]:
            raise RuntimeError("down")

    assert build_bank("growth", "", Broken(), MapFetcher(PAGES)).facts == []


def test_ensure_bank_reuses_fresh_and_rebuilds_stale() -> None:
    store, desk = InMemoryStore(), FakeDesk()
    key = bank_key("growth", "")
    full = FactBankDoc(
        key=key, topic="growth", prompt_version="v", facts=[_fact(i) for i in range(MIN_REUSE)]
    )
    store.put_fact_bank(full)
    assert ensure_bank(store, desk, MapFetcher(PAGES), "growth", "") == key
    assert desk.angle_calls == 0  # reused, no research
    later = datetime.now(UTC) + timedelta(days=8)
    assert ensure_bank(store, desk, MapFetcher(PAGES), "growth", "", now=later) == key
    assert desk.angle_calls == 1
    assert len(store.get_fact_bank(key).facts) == 2  # type: ignore[union-attr]


def test_ensure_bank_stores_empty_bank_for_its_diagnostics() -> None:
    store = InMemoryStore()
    key = ensure_bank(store, FakeDesk(), MapFetcher({}), "growth", "")
    bank = store.get_fact_bank(key or "")
    assert bank is not None
    assert bank.facts == []
    assert bank.stats["drop_fetch"] == 2


def test_failed_rebuild_keeps_old_facts() -> None:
    store = InMemoryStore()
    key = bank_key("growth", "")
    old = FactBankDoc(
        key=key,
        topic="growth",
        prompt_version="v",
        facts=[_fact(0)],
        created_at=datetime.now(UTC) - timedelta(days=30),
    )
    store.put_fact_bank(old)
    assert ensure_bank(store, FakeDesk(), MapFetcher({}), "growth", "") == key
    assert store.get_fact_bank(key) == old


def test_checked_ruling_guards() -> None:
    facts = [_fact(0), _fact(1)]
    assert checked_ruling(None, facts) is None
    assert checked_ruling(Ruling(Verdict.UNVERIFIABLE, [0], "x"), facts) is None
    assert checked_ruling(Ruling(Verdict.TRUE, [7], "x"), facts) is None
    r = checked_ruling(Ruling(Verdict.FALSE, [1, 1, 7, 0], "x"), facts)
    assert r is not None
    assert r.fact_ids == [1, 0]
    assert render_facts([_fact(0)]).startswith("[0] India's real GDP")


class CountingModel:
    def __init__(self) -> None:
        self.assessed: list[str] = []

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[Any]:
        return [SimpleNamespace(text="Real GDP grew 8.2 per cent in 2023-24", lang="en")]

    def assess(self, claim: str, hint: str = "") -> Assessment:
        self.assessed.append(claim)
        return Assessment(Verdict.UNVERIFIABLE, "web", [])


def _session(store: InMemoryStore, key: str | None) -> str:
    sid = store.create_session(SessionDoc(owner_uid="u", topic="growth", fact_bank_key=key))
    return sid


def test_verify_claim_rules_against_fact_bank_first() -> None:
    store, model = InMemoryStore(), CountingModel()
    store.put_fact_bank(
        FactBankDoc(key="growth-k", topic="growth", prompt_version="v", facts=[_fact(0)])
    )
    desk = FakeDesk(ruling=Ruling(Verdict.FALSE, [0], "GDP grew 8.2%, not 12%.", "We grew 12%"))
    d = Deps(store, model, MapFetcher(PAGES), InMemorySnapshots(), facts=desk)
    sid = _session(store, "growth-k")
    cid = store.add_claim(
        sid, ClaimDoc(text="hum 12% se badhe 2023-24 me", source=ClaimSource.LIVE)
    )
    card_id = verify_claim(sid, cid, d)
    claim = store.get_claim(sid, cid)
    assert card_id
    assert claim
    assert claim.fact_ids == [0]
    assert claim.verdict is Verdict.FALSE
    card = store.get_card(card_id)
    assert card
    assert str(card.sources[0].url) == "https://mospi.gov.in/gdp"
    assert model.assessed == []  # the web check never ran


def test_verify_claim_falls_back_to_web_when_no_fact_decides() -> None:
    store, model = InMemoryStore(), CountingModel()
    store.put_fact_bank(FactBankDoc(key="k", topic="growth", prompt_version="v", facts=[_fact(0)]))
    d = Deps(store, model, MapFetcher(PAGES), InMemorySnapshots(), facts=FakeDesk())
    sid = _session(store, "k")
    cid = store.add_claim(sid, ClaimDoc(text="unrelated line", source=ClaimSource.LIVE))
    assert verify_claim(sid, cid, d, race_hint=True) is None
    assert model.assessed == ["unrelated line"]
    claim = store.get_claim(sid, cid)
    assert claim
    assert claim.status is ClaimStatus.FAILED
    assert claim.fact_ids == []


def test_prebunk_attaches_fact_bank_and_rules_bank_claims() -> None:
    store, model = InMemoryStore(), CountingModel()
    desk = FakeDesk(ruling=Ruling(Verdict.TRUE, [0], "MoSPI: 8.2%."))
    d = Deps(store, model, MapFetcher(PAGES), InMemorySnapshots(), facts=desk)
    sid = _session(store, None)
    out = run_prebunk(sid, d, n=1)
    s = store.get_session(sid)
    assert s
    assert s.fact_bank_key == bank_key("growth", "")
    assert s.status == "ready"
    assert out == {"predicted": 1, "proved": 1}
    assert model.assessed == []


def test_prebunk_continues_when_fact_bank_crashes() -> None:
    class BrokenStore(InMemoryStore):
        def put_fact_bank(self, doc: FactBankDoc) -> None:
            raise RuntimeError("firestore down")

    store = BrokenStore()
    d = Deps(store, CountingModel(), MapFetcher(PAGES), InMemorySnapshots(), facts=FakeDesk())
    sid = _session(store, None)
    run_prebunk(sid, d, n=1)
    s = store.get_session(sid)
    assert s
    assert s.fact_bank_key is None
    assert s.status == "ready"


def test_prebunk_without_verified_facts_links_empty_bank() -> None:
    store = InMemoryStore()
    d = Deps(store, CountingModel(), MapFetcher({}), InMemorySnapshots(), facts=FakeDesk())
    sid = _session(store, None)
    run_prebunk(sid, d, n=1)
    s = store.get_session(sid)
    assert s
    assert s.fact_bank_key == bank_key("growth", "")
    assert s.status == "ready"


def test_parse_json_list() -> None:
    assert parse_json_list('```json\n[{"statement": "a"}]\n```') == [{"statement": "a"}]
    assert parse_json_list("no json") == []
    assert parse_json_list("[oops]") == []
    assert parse_json_list('{"a": [1]}') == []
    assert parse_json_list('Facts [1]:\n[{"statement": "a"}]\nSources [2]') == [{"statement": "a"}]


def _resp(chunk_uris: list[str], seg: str) -> Any:
    chunks = [SimpleNamespace(web=SimpleNamespace(uri=u)) for u in chunk_uris]
    sup = SimpleNamespace(
        segment=SimpleNamespace(text=seg),
        grounding_chunk_indices=[0, 1, 9],
        confidence_scores=[0.4, 0.9],
    )
    meta = SimpleNamespace(grounding_chunks=chunks, grounding_supports=[sup])
    return SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=meta)])


def test_candidates_from_grounded_answer() -> None:
    raw = (
        '[{"statement": "India real GDP grew 8.2 per cent in 2023-24", "value": "8.2",'
        ' "source_url": "https://mospi.gov.in/gdp", "trigger": "8.2%"}, {"statement": ""}, 5]'
    )
    resp = _resp(
        ["https://r/a", "https://r/b"], '"statement": "India real GDP grew 8.2 per cent in 2023-24"'
    )
    [c] = candidates_from(raw, resp, "growth")
    assert c.urls == ("https://mospi.gov.in/gdp", "https://r/b", "https://r/a")
    assert c.angle == "growth"
    assert c.trigger == "8.2%"
    assert candidates_from(raw, SimpleNamespace(), "g")[0].urls == ("https://mospi.gov.in/gdp",)


def test_facts_endpoint_owner_only(client: TestClient) -> None:
    hdr = {"Authorization": "Bearer admin-token"}
    sid = client.post("/api/prebunk", json={"topic": "growth"}, headers=hdr).json()["session_id"]
    assert client.get(f"/api/sessions/{sid}/facts", headers=hdr).status_code == 404
    store = client.app.state.store  # type: ignore[attr-defined]
    store.put_fact_bank(FactBankDoc(key="k1", topic="growth", prompt_version="v", facts=[_fact(0)]))
    store.update_session(sid, fact_bank_key="k1")
    claims = client.get(f"/api/sessions/{sid}", headers=hdr).json()["claims"]
    assert all(c["fact_ids"] == [] for c in claims)
    r = client.get(f"/api/sessions/{sid}/facts", headers=hdr)
    assert r.status_code == 200
    assert r.json()["facts"][0]["official"] is True
    anon = {"Authorization": "Bearer anon-token"}
    assert client.get(f"/api/sessions/{sid}/facts", headers=anon).status_code == 404
    store.update_session(sid, fact_bank_key="gone")
    assert client.get(f"/api/sessions/{sid}/facts", headers=hdr).status_code == 404
