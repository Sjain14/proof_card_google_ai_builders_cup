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
    PredictedClaim,
    StubModel,
    evidence_from_grounding,
    parse_assessment_text,
    parse_claim_en,
    parse_predictions,
)
from app.pipeline import Deps, build_card, run_prebunk, verify_claim
from app.proof import (
    Fetched,
    FetchError,
    FixtureFetcher,
    InMemorySnapshots,
    best_contradiction,
    best_passage,
    extract_text,
    match_passage,
    score_passage,
    tokens,
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


def test_parse_claim_en() -> None:
    raw = "VERDICT: TRUE\nCLAIM_EN: The schedule has 22 languages.\nEXPLANATION: Yes."
    assert parse_claim_en(raw) == "The schedule has 22 languages."
    assert parse_assessment_text(raw)[1] == "Yes."
    assert parse_claim_en("VERDICT: TRUE") == ""


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


# Audit 14 Oct section 3: these claims failed on the real Wikipedia page.
EIGHTH = (
    "<p>The Eighth Schedule to the Constitution of India lists the official languages of "
    "the Republic of India. At the time the Constitution was enacted it had 14 languages; "
    "today the Eighth Schedule lists 22 languages.</p>"
)


def test_devanagari_tokens_keep_matras_and_digits() -> None:
    assert tokens("संविधान की आठवीं अनुसूची में २२ भाषाएँ हैं") == [
        "संविधान",
        "आठवीं",
        "अनुसूची",
        "22",
        "भाषाएँ",
    ]


def test_hindi_claim_matches_hindi_page() -> None:
    page = "भारत के संविधान की आठवीं अनुसूची में 22 भाषाएँ शामिल हैं। यह सूची 1950 से बढ़ी है।"
    assert score_passage("संविधान की आठवीं अनुसूची में २२ भाषाएँ हैं", page) >= 0.8


def test_fuzzy_tokens_absorb_spelling_variants() -> None:
    # "languages" vs "language", "schedul" typo: exact recall was 0.5 here
    assert (
        score_passage("Eighth Schedule languages 22", "the eighth schedul language list: 22") == 1
    )


def test_wrong_number_is_a_contradiction_not_a_miss() -> None:
    m = match_passage(
        "India has 25 languages in the Eighth Schedule", "The Eighth Schedule lists 22 languages."
    )
    assert m.score <= 0.5
    assert m.conflict
    assert m.topic == 0.75  # "india" absent, the rest on topic
    assert not match_passage(
        "Eighth Schedule has 25 languages", "Eighth Schedule languages"
    ).conflict
    assert best_contradiction(
        "x 5", "no numbers in this sentence at all here"
    ) == best_contradiction("", "")


# ---------- pipeline ----------


@dataclass
class FakeModel:
    verdict: Verdict
    urls: list[str]

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[Any]:
        return []

    def assess(self, claim: str, hint: str = "") -> Assessment:
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


def test_false_claim_with_wrong_number_stays_false() -> None:
    # Before: 0.5 capped support < 0.6 gate turned a debunk into UNVERIFIABLE (audit #6).
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.FALSE, ["https://w/a"]),
        MapFetcher({"https://w/a": EIGHTH}),
    )
    card = build_card("India has 25 languages in the Eighth Schedule", d.model.assess(""), d)
    assert card is not None
    assert card.verdict is Verdict.FALSE
    assert "22 languages" in card.sources[0].snippet


def test_true_claim_with_wrong_number_is_never_true() -> None:
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.TRUE, ["https://w.gov/a"]),
        MapFetcher({"https://w.gov/a": EIGHTH}),
    )
    card = build_card("India has 25 languages in the Eighth Schedule", d.model.assess(""), d)
    assert card is not None
    assert card.verdict is Verdict.UNVERIFIABLE


def test_hinglish_claim_matches_english_page_via_claim_en() -> None:
    @dataclass
    class Translating(FakeModel):
        def assess(self, claim: str, hint: str = "") -> Assessment:
            return Assessment(
                self.verdict,
                "why",
                [Evidence(url=u) for u in self.urls],
                claim_en="The Eighth Schedule of the Constitution has 22 languages",
            )

    d = deps(
        InMemoryStore(),
        Translating(Verdict.TRUE, ["https://w/a"]),
        MapFetcher({"https://w/a": EIGHTH}),
    )
    claim = "Samvidhan ki aathvi anusuchi mein 22 bhashayein hain"
    assert score_passage(claim, EIGHTH) < 0.35  # lexical alone cannot cross scripts
    card = build_card(claim, d.model.assess(claim), d)
    assert card is not None
    assert card.verdict is Verdict.TRUE


def test_build_card_no_sources_returns_none() -> None:
    d = deps(InMemoryStore(), FakeModel(Verdict.TRUE, ["https://gone"]), MapFetcher({}))
    assert build_card("claim", d.model.assess(""), d) is None


def test_build_card_logs_why_each_source_was_dropped(caplog: pytest.LogCaptureFixture) -> None:
    # COULDN'T CHECK cards must be debuggable from Cloud Logging: host + reason per source.
    pages = {"https://w.org/off": "<p>Cricket scores from last night.</p>", "https://e.org/x": ""}
    urls = ["https://gone.org/a", "https://w.org/off", "https://w.org/off", "https://e.org/x"]
    d = deps(InMemoryStore(), FakeModel(Verdict.TRUE, urls), MapFetcher(pages))
    with caplog.at_level("INFO", logger="proofcard.pipeline"):
        assert build_card("India has 22 languages", d.model.assess(""), d) is None
    skips = [r.fields for r in caplog.records if r.msg == "source skipped"]  # type: ignore[attr-defined]
    assert [(s["host"], s["reason"]) for s in skips] == [
        ("gone.org", "nope"),
        ("w.org", "low support"),
        ("w.org", "duplicate"),
        ("e.org", "no text"),
    ]
    assert isinstance(skips[1]["score"], float)
    done = [r.fields for r in caplog.records if r.msg == "no proof"]  # type: ignore[attr-defined]
    assert done == [{"evidence": 4, "model_verdict": str(Verdict.TRUE)}]


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
        def assess(self, claim: str, hint: str = "") -> Assessment:
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


class _SpeakerHangs:
    """predict_claims fails for a named speaker (prod: Trump timed out 90 s x 3)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[Any]:
        self.calls.append(speaker)
        if speaker:
            raise TimeoutError("deadline")
        return [PredictedClaim(text=f"claim number {i} about {topic}", lang="en") for i in range(n)]

    def assess(self, claim: str, hint: str = "") -> Assessment:
        return Assessment(Verdict.UNVERIFIABLE, "why", [])


def test_speaker_prediction_failure_falls_back_to_topic() -> None:
    from app.pipeline import _predict

    m = _SpeakerHangs()
    d = deps(InMemoryStore(), m, MapFetcher({}))
    out = _predict(d, "economy", "Donald Trump", 3)
    assert len(out) == 3
    assert m.calls == ["Donald Trump", ""]


def test_no_speaker_prediction_failure_still_raises() -> None:
    import pytest

    from app.pipeline import _predict

    class _Down(_SpeakerHangs):
        def predict_claims(self, topic: str, speaker: str, n: int) -> list[Any]:
            raise TimeoutError("deadline")

    d = deps(InMemoryStore(), _Down(), MapFetcher({}))
    with pytest.raises(TimeoutError):
        _predict(d, "economy", "", 3)


# ---------- weak sources, hint race, video title (replay 7dhIVHRKhvo) ----------


def test_unverifiable_card_cites_reputable_sources_only() -> None:
    from app.pipeline import Trace, reputable

    assert reputable("https://www.pib.gov.in/x")
    assert reputable("https://data.imf.org/a")
    assert not reputable("https://www.legal500.com/c/india")
    page = "<p>The Eighth Schedule lists many languages of the Republic.</p>"
    d = deps(
        InMemoryStore(),
        FakeModel(Verdict.FALSE, ["https://www.legal500.com/a"]),
        MapFetcher({"https://www.legal500.com/a": page}),
    )
    t = Trace()
    claim = "Eighth Schedule languages of the Republic number 24"
    assert build_card(claim, d.model.assess(""), d, t) is None
    assert t.reason == "weak_sources_only"


def test_live_race_keeps_plain_card_and_records_stages() -> None:
    from app.pipeline import Trace

    class Hinted(FakeModel):
        def __init__(self) -> None:
            super().__init__(Verdict.TRUE, ["https://x.gov/a"])
            self.hints: list[str] = []

        def assess(self, claim: str, hint: str = "") -> Assessment:
            self.hints.append(hint)
            return super().assess(claim, hint)

    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t", speaker="Narendra Modi"))
    cid = store.add_claim(
        sid, ClaimDoc(text="India has 22 languages in the Eighth Schedule", source=ClaimSource.LIVE)
    )
    m = Hinted()
    d = deps(store, m, MapFetcher({"https://x.gov/a": EIGHTH}))
    t = Trace()
    assert verify_claim(sid, cid, d, t, True) is not None
    assert "plain_assess" in t.stages
    assert "" in m.hints


def test_bank_prediction_sees_the_video_title() -> None:
    seen: list[str] = []

    class Rec(FakeModel):
        def predict_claims(self, topic: str, speaker: str, n: int) -> list[Any]:
            seen.append(topic)
            return []

    store = InMemoryStore()
    sid = store.create_session(
        SessionDoc(owner_uid="u", topic="economy", youtube_url="https://youtu.be/abc")
    )
    d = Deps(
        store,
        Rec(Verdict.TRUE, []),
        MapFetcher({}),
        InMemorySnapshots(),
        video_title=lambda url: "FM reply in Lok Sabha",
    )
    run_prebunk(sid, d, 3)
    assert seen
    assert "FM reply in Lok Sabha" in seen[0]


def test_prediction_drops_the_video_title_before_the_speaker() -> None:
    from app.pipeline import _predict

    calls: list[tuple[str, str]] = []

    class TitleHangs(_SpeakerHangs):
        def predict_claims(self, topic: str, speaker: str, n: int) -> list[Any]:
            calls.append((topic, speaker))
            if "Video" in topic:
                raise TimeoutError("deadline")
            return [PredictedClaim(text="x", lang="en")]

    d = deps(InMemoryStore(), TitleHangs(), MapFetcher({}))
    assert _predict(d, "economy. Video: FM", "Sitharaman", 3, "economy")
    assert calls == [("economy. Video: FM", "Sitharaman"), ("economy", "Sitharaman")]


def test_published_date_reads_watch_page_formats() -> None:
    from app.pipeline import published_date

    assert published_date('"publishDate":{"simpleText":"1 Aug 2022"}') == "2022-08-01"
    assert published_date('<meta itemprop="datePublished" content="2022-08-01T03:00">') == (
        "2022-08-01"
    )
    assert published_date('"uploadDate":"2021-02-03T00:00:00-08:00"') == "2021-02-03"
    assert published_date("<html>no date</html>") == ""


def test_prebunk_stalled_reads_the_beat() -> None:
    from datetime import UTC, datetime, timedelta

    from app.pipeline import PREBUNK_STALE, prebunk_stalled

    now = datetime.now(UTC)
    s = SessionDoc(owner_uid="u", topic="t", status="prebunking", prebunk_beat=now)
    assert not prebunk_stalled(s, now + PREBUNK_STALE - timedelta(seconds=1))
    assert prebunk_stalled(s, now + PREBUNK_STALE + timedelta(seconds=1))
    assert not prebunk_stalled(s.model_copy(update={"status": "ready"}), now + 2 * PREBUNK_STALE)


def test_pulse_beats_while_a_long_step_runs() -> None:
    import time as _t

    from app.pipeline import _pulse

    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t", status="prebunking"))
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    with _pulse(sid, deps, every=0.02):
        _t.sleep(0.15)
    first = store.sessions[sid].prebunk_beat
    assert first is not None
    _t.sleep(0.06)
    assert store.sessions[sid].prebunk_beat == first  # stopped with the step


# ---------- claim -> card cache ----------


def test_same_claim_reuses_the_proved_card() -> None:
    from datetime import timedelta

    from app.pipeline import Trace, claim_key

    class Counting(FakeModel):
        calls = 0

        def assess(self, claim: str, hint: str = "") -> Assessment:
            Counting.calls += 1
            return super().assess(claim, hint)

    store = InMemoryStore()
    d = deps(
        store, Counting(Verdict.TRUE, ["https://x.gov/a"]), MapFetcher({"https://x.gov/a": EIGHTH})
    )

    def check(text: str, url: str | None = None) -> tuple[str | None, Trace]:
        sid = store.create_session(SessionDoc(owner_uid="u", topic="t", youtube_url=url))
        cid = store.add_claim(sid, ClaimDoc(text=text, source=ClaimSource.LIVE))
        t = Trace()
        return verify_claim(sid, cid, d, t), t

    first, _ = check("India has 22 languages in the Eighth Schedule")
    assert first is not None
    n = Counting.calls
    again, t = check("  india has 22 languages, in the Eighth Schedule!  ")
    assert again == first
    assert t.reason == "cache"
    assert Counting.calls == n  # no model call for a repeat
    # another speech is its own context; a week old entry is checked again
    other, _ = check("India has 22 languages in the Eighth Schedule", "https://youtu.be/x")
    assert other not in (None, first)
    key = claim_key("India has 22 languages in the Eighth Schedule")
    store.claim_cards[key] = (first, datetime.now(UTC) - timedelta(days=8))
    stale, t = check("India has 22 languages in the Eighth Schedule")
    assert stale is not None
    assert t.reason != "cache"
    # an index row pointing at a missing card is ignored
    store.claim_cards[key] = ("gone", datetime.now(UTC))
    assert check("India has 22 languages in the Eighth Schedule")[0] not in (None, "gone")


def test_unverifiable_card_is_not_cached() -> None:
    from app.pipeline import claim_key

    store = InMemoryStore()
    d = deps(
        store,
        FakeModel(Verdict.UNVERIFIABLE, ["https://x.gov/a"]),
        MapFetcher({"https://x.gov/a": EIGHTH}),
    )
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    cid = store.add_claim(sid, ClaimDoc(text="India has 22 languages", source=ClaimSource.LIVE))
    verify_claim(sid, cid, d)
    assert claim_key("India has 22 languages") not in store.claim_cards


# ---------- brief budget (p39) ----------


def test_brief_turns_ready_while_a_slow_claim_keeps_checking() -> None:
    import threading
    import time
    from dataclasses import replace

    gate = threading.Event()

    class Slow(FakeModel):
        def assess(self, claim: str, hint: str = "") -> Assessment:
            if "slow" in claim:
                gate.wait(5)
            return super().assess(claim, hint)

    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    for text in ["India has 22 languages in the Eighth Schedule", "slow: 22 languages"]:
        store.add_claim(sid, ClaimDoc(text=text, source=ClaimSource.PREDICTED))
    d = replace(
        deps(
            store, Slow(Verdict.TRUE, ["https://x.gov/a"]), MapFetcher({"https://x.gov/a": EIGHTH})
        ),
        brief_budget_s=0.3,
        brief_hard_cap_s=5.0,
    )
    seen: list[str] = []
    t = threading.Thread(target=lambda: seen.append(str(run_prebunk(sid, d))))
    t.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        s = store.get_session(sid)
        if s is not None and s.status == "ready":
            break
        time.sleep(0.05)
    s = store.get_session(sid)
    assert s is not None
    assert s.status == "ready"
    assert not seen  # still running: the straggler is still being checked
    gate.set()
    t.join(5)
    statuses = {c.text: c.status for _, c in store.list_claims(sid)}
    assert statuses["slow: 22 languages"] in (ClaimStatus.PROVED, ClaimStatus.FAILED)


def test_brief_never_pulls_a_live_session_back_to_ready() -> None:
    from app.pipeline import _ready_if_prebunking

    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    store.update_session(sid, status="live")
    _ready_if_prebunking(sid, deps(store))
    s = store.get_session(sid)
    assert s is not None
    assert s.status == "live"
