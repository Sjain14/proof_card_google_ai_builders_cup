from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.model import (
    Assessment,
    Evidence,
    StubModel,
    evidence_from_grounding,
    parse_assessment_text,
    parse_predictions,
)
from app.pipeline import Deps, build_card, run_prebunk, verify_claim
from app.proof import (
    Fetched,
    FetchError,
    FixtureFetcher,
    InMemorySnapshots,
    best_passage,
    extract_text,
    score_passage,
)
from app.schemas import ClaimDoc, ClaimSource, ClaimStatus, SessionDoc, Verdict
from app.security import card_fingerprint, sha256_hex
from app.store import InMemoryStore
from app.tasks import InlineQueue

ADMIN = {"Authorization": "Bearer admin-token"}


def deps(store: InMemoryStore, model: Any = None, fetcher: Any = None) -> Deps:
    return Deps(
        store=store,
        model=model or StubModel(),
        fetcher=fetcher or FixtureFetcher(),
        snapshots=InMemorySnapshots(),
    )


# ---------- parsing ----------


def test_parse_assessment_strict_format() -> None:
    v, e = parse_assessment_text("VERDICT: false\nEXPLANATION: It is 22, not 24.")
    assert v is Verdict.FALSE
    assert e == "It is 22, not 24."


@pytest.mark.parametrize("text", ["", "I think it's true", "VERDICT: MAYBE"])
def test_parse_assessment_malformed_is_unverifiable(text: str) -> None:
    v, e = parse_assessment_text(text)
    assert v is Verdict.UNVERIFIABLE
    assert e


def test_parse_predictions_dedupes_and_sanitises() -> None:
    raw = (
        '[{"text":"A claim","lang":"hi-Latn","why":"x"},{"text":"a claim","lang":"en"},'
        '{"text":"","lang":"en"},{"text":"B","lang":"fr"},"junk"]'
    )
    out = parse_predictions(raw, 10)
    assert [p.text for p in out] == ["A claim", "B"]
    assert out[1].lang == "en"


@pytest.mark.parametrize("raw", ["not json", '{"a":1}', ""])
def test_parse_predictions_bad_json(raw: str) -> None:
    assert parse_predictions(raw, 5) == []


def test_parse_predictions_caps_n() -> None:
    raw = "[" + ",".join(f'{{"text":"c{i}","lang":"en"}}' for i in range(30)) + "]"
    assert len(parse_predictions(raw, 12)) == 12


def test_evidence_from_grounding_orders_by_confidence() -> None:
    def web(u: str) -> SimpleNamespace:
        return SimpleNamespace(web=SimpleNamespace(uri=u, title=u))

    meta = SimpleNamespace(
        grounding_chunks=[web("https://a.gov"), web("https://b.gov"), SimpleNamespace(web=None)],
        grounding_supports=[
            SimpleNamespace(
                segment=SimpleNamespace(text="seg one"),
                grounding_chunk_indices=[0, 1],
                confidence_scores=[0.4, 0.9],
            ),
            SimpleNamespace(
                segment=SimpleNamespace(text="seg two"),
                grounding_chunk_indices=[0],
                confidence_scores=[0.7],
            ),
        ],
    )
    resp = SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=meta)])
    ev = evidence_from_grounding(resp)
    assert [e.url for e in ev] == ["https://b.gov", "https://a.gov"]
    assert ev[1].model_snippet == "seg two"


def test_evidence_from_grounding_missing() -> None:
    assert evidence_from_grounding(SimpleNamespace(candidates=[])) == []
    none_meta = SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=None)])
    assert evidence_from_grounding(none_meta) == []


# ---------- proof ----------


def test_extract_text_skips_scripts_and_nav() -> None:
    html = b"<html><nav>menu</nav><script>evil()</script><p>Real fact here.</p></html>"
    t = extract_text(html)
    assert "Real fact here." in t
    assert "evil" not in t
    assert "menu" not in t
    assert extract_text(b"plain   text", "text/plain") == "plain text"


def test_score_requires_numbers() -> None:
    assert score_passage("India has 22 languages", "India lists 22 official languages") == 1.0
    assert score_passage("India has 24 languages", "India lists 22 official languages") <= 0.5
    assert score_passage("", "anything") == 0.0


def test_best_passage_picks_matching_window() -> None:
    text = (
        "Unrelated opening sentence about weather. "
        "The schedule now has 22 languages in total. Another filler line here ok."
    )
    passage, score = best_passage("schedule has 22 languages", text)
    assert "22 languages" in passage
    assert score > 0.9
    assert best_passage("x", "short") == ("", 0.0)


# ---------- pipeline ----------


@dataclass
class FakeModel:
    verdict: Verdict
    urls: list[str]

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[Any]:
        return []

    def assess(self, claim: str) -> Assessment:
        return Assessment(self.verdict, "why", [Evidence(url=u) for u in self.urls])


class MapFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> Fetched:
        if url not in self.pages:
            raise FetchError("nope")
        body = self.pages[url].encode()
        return Fetched(url, url, body, "text/html", datetime.now(UTC))


def test_build_card_hashes_and_snapshots() -> None:
    store = InMemoryStore()
    page = "<p>The Eighth Schedule lists 22 languages of India today.</p>"
    d = deps(
        store,
        FakeModel(Verdict.TRUE, ["https://x.gov/a", "https://bad"]),
        MapFetcher({"https://x.gov/a": page}),
    )
    card = build_card("India has 22 languages in the Eighth Schedule", d.model.assess(""), d)
    assert card is not None
    assert card.verdict is Verdict.TRUE
    src = card.sources[0]
    assert src.snapshot_sha256 == sha256_hex(page.encode())
    assert src.snapshot_sha256 in d.snapshots.blobs  # type: ignore[attr-defined]
    body = card.model_dump(mode="json")
    assert card.card_sha256 == card_fingerprint(
        {k: body[k] for k in ("claim", "verdict", "explanation", "sources", "support_score")}
    )


def test_build_card_gates_weak_evidence() -> None:
    store = InMemoryStore()
    page = "<p>The Eighth Schedule lists many languages of the Republic.</p>"
    d = deps(
        store, FakeModel(Verdict.FALSE, ["https://x.gov/a"]), MapFetcher({"https://x.gov/a": page})
    )
    card = build_card("Eighth Schedule languages of the Republic number 24", d.model.assess(""), d)
    assert card is not None
    assert card.verdict is Verdict.UNVERIFIABLE  # number missing caps support below gate


def test_build_card_no_sources_returns_none() -> None:
    d = deps(InMemoryStore(), FakeModel(Verdict.TRUE, ["https://gone"]), MapFetcher({}))
    assert build_card("claim", d.model.assess(""), d) is None


def test_verify_claim_failure_marks_failed() -> None:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    cid = store.add_claim(sid, ClaimDoc(text="unknown claim", source=ClaimSource.LIVE))
    d = deps(store, FakeModel(Verdict.TRUE, []), MapFetcher({}))
    assert verify_claim(sid, cid, d) is None
    claim = store.get_claim(sid, cid)
    assert claim is not None
    assert claim.status is ClaimStatus.FAILED
    assert verify_claim(sid, "missing-claim-id", d) is None


def test_verify_claim_model_crash_is_contained() -> None:
    class Boom(FakeModel):
        def assess(self, claim: str) -> Assessment:
            raise RuntimeError("quota")

    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    cid = store.add_claim(sid, ClaimDoc(text="c", source=ClaimSource.LIVE))
    assert verify_claim(sid, cid, deps(store, Boom(Verdict.TRUE, []))) is None


def test_run_prebunk_offline_end_to_end() -> None:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="India facts"))
    out = run_prebunk(sid, deps(store), n=4)
    assert out == {"predicted": 4, "proved": 4}
    for _, c in store.list_claims(sid):
        assert c.card_id
        card = store.get_card(c.card_id)
        assert card is not None
        assert card.verdict == c.verdict
    assert run_prebunk("nope-nope-nope", deps(store)) == {"predicted": 0, "proved": 0}


def test_card_ids_immutable() -> None:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    run_prebunk(sid, deps(store), n=1)
    cid, card = next(iter(store.cards.items()))
    with pytest.raises(ValueError, match="immutable"):
        store.put_card(cid, card)


def test_store_update_revalidates() -> None:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    with pytest.raises(ValidationError):
        store.update_session(sid, status="hacked")
    with pytest.raises(KeyError):
        store.add_claim("missing", ClaimDoc(text="c", source=ClaimSource.LIVE))


def test_inline_queue_runs_jobs() -> None:
    q = InlineQueue(workers=1)
    hits: list[int] = []
    q.enqueue_prebunk("s", lambda: hits.append(1))
    q.drain()
    assert hits == [1]


# ---------- API ----------


def test_session_view_owner_only(client: TestClient) -> None:
    sid = client.post("/api/prebunk", json={"topic": "India"}, headers=ADMIN).json()["session_id"]
    r = client.get(f"/api/sessions/{sid}", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["counts"]["proved"] == 6
    card_id = body["claims"][0]["card_id"]
    assert client.get(f"/api/cards/{card_id}").status_code == 200


def test_session_view_hides_other_users(client: TestClient, store: InMemoryStore) -> None:
    other = store.create_session(SessionDoc(owner_uid="someone-else", topic="t"))
    assert client.get(f"/api/sessions/{other}", headers=ADMIN).status_code == 404
    assert client.get("/api/sessions/bad!", headers=ADMIN).status_code == 404


def test_task_endpoint_requires_oidc(client: TestClient, store: InMemoryStore) -> None:
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    body = {"session_id": sid}
    assert client.post("/tasks/prebunk", json=body).status_code == 404
    bad = {"Authorization": "Bearer forged"}
    assert client.post("/tasks/prebunk", json=body, headers=bad).status_code == 404
    ok = client.post("/tasks/prebunk", json=body, headers={"Authorization": "Bearer task-token"})
    assert ok.status_code == 200
    assert ok.json()["proved"] == 6
