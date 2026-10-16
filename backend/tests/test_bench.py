"""H1 gold set integrity + H2 runner mechanics (offline; real numbers need --mode vertex)."""

from datetime import UTC, datetime

from app.live import HashEmbedder, HeuristicSpotter, LiveDeps
from app.model import Assessment, Evidence, PredictedClaim
from app.pipeline import Deps
from app.proof import Fetched, InMemorySnapshots
from app.schemas import Verdict
from app.store import InMemoryStore
from bench.run import CHITCHAT, Gold, Row, load_gold, run, summarize, to_markdown


def test_gold_set_is_well_formed() -> None:
    gold = load_gold()
    assert len(gold) == 50
    assert len({g.id for g in gold}) == 50
    langs = {g.lang for g in gold}
    assert langs == {"en", "hi", "hi-Latn"}
    for lang in langs:  # every language has both labels
        assert {g.expected for g in gold if g.lang == lang} == {Verdict.TRUE, Verdict.FALSE}
    assert all(g.source.startswith("https://") for g in gold)
    assert sum(bool(g.spoken) for g in gold) >= 15
    assert len(CHITCHAT.read_text(encoding="utf-8").splitlines()) == 10


class GoldModel:
    """Answers the gold label, cites one page that states the claim."""

    def __init__(self, gold: list[Gold]) -> None:
        self.label = {g.claim: g.expected for g in gold}

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]:
        return []

    def assess(self, claim: str, hint: str = "") -> Assessment:
        if claim.startswith("crash"):
            raise RuntimeError("model down")
        return Assessment(self.label[claim], "why", [Evidence("https://src.example/" + claim)])


class EchoFetcher:
    def fetch(self, url: str) -> Fetched:
        claim = url.removeprefix("https://src.example/")
        body = f"<p>{claim} This sentence is long enough to count.</p>".encode()
        return Fetched(url, url, body, "text/html", datetime.now(UTC))


def test_runner_end_to_end_offline() -> None:
    gold = [
        Gold(
            "T1",
            "en",
            "The Lok Sabha has 543 elected seats.",
            Verdict.TRUE,
            "https://x",
            "543 seats are elected to the Lok Sabha",
        ),
        Gold("T2", "hi", "लोकसभा में 543 निर्वाचित सीटें हैं।", Verdict.TRUE, "https://x"),
        Gold("T3", "en", "GST was introduced in India on 1 July 2017.", Verdict.TRUE, "https://x"),
        Gold("T4", "en", "crash: model down for this one", Verdict.FALSE, "https://x"),
    ]
    store = InMemoryStore()
    deps = Deps(store, GoldModel(gold), EchoFetcher(), InMemorySnapshots())
    live = LiveDeps(deps, HashEmbedder(), HeuristicSpotter(), 0.5)
    rep = run("test", deps, live, gold, ["good evening and welcome"])
    assert rep.overall["n"] == 4
    assert rep.overall["accuracy"] == 0.75  # the crash is a miss, not a stop
    assert rep.overall["proof_rate"] == 0.75
    assert rep.by_lang["hi"]["accuracy"] == 1.0
    assert rep.live["spoken_n"] == 1
    assert rep.live["instant_match_rate"] == 1.0
    assert rep.live["chitchat_false_match_rate"] == 0.0
    assert rep.tamper["clean_verified_rate"] == 1.0
    assert rep.tamper["edit_caught_rate"] == 1.0
    md = to_markdown(rep)
    assert "| hi | 1 | 100% |" in md
    assert "| all | 4 | 75% |" in md


def test_summarize_percentiles() -> None:
    rows = [Row(str(i), "en", "TRUE", "TRUE", 1, ms) for i, ms in enumerate([10, 20, 30, 400])]
    s = summarize(rows)
    assert (s["latency_p50_ms"], s["latency_p95_ms"]) == (30.0, 400.0)
    assert summarize([])["accuracy"] == 0.0
