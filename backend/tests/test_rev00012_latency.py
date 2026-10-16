"""rev00012 prod verify (16 Oct 2026): the live "power plants" card took 120 s. Sources
were fetched one after another (8 s timeout each, up to ~10 grounding chunks). Now they
are fetched in parallel under one budget per card, best source first as before."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import app.pipeline as pipeline_mod
from app.model import Assessment, Evidence
from app.pipeline import Deps, build_card, fetch_all
from app.proof import Fetched, FetchError, InMemorySnapshots
from app.schemas import Verdict
from app.store import InMemoryStore

PAGE = (
    b"<html><body><p>Biden closed more than 100 power plants, the speaker said. "
    b"Records show 98 coal power plants retired since 2021.</p></body></html>"
)


class _Slow:
    """Every fetch sleeps; one url fails, one never finishes in time."""

    def __init__(self, sleep: float) -> None:
        self.sleep = sleep
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def fetch(self, url: str) -> Fetched:
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            if "hang" in url:
                time.sleep(5)
            time.sleep(self.sleep)
            if "bad" in url:
                raise FetchError("status 403")
            if "boom" in url:
                raise ValueError("parser broke")
            return Fetched(url, url, PAGE, "text/html", datetime.now(UTC))
        finally:
            with self.lock:
                self.active -= 1


def _ev(url: str) -> Evidence:
    return Evidence(url=url, title="t", model_snippet="98 coal power plants", confidence=0.5)


def _assessment(urls: list[str]) -> Assessment:
    return Assessment(
        Verdict.FALSE,
        "Fewer than 100 plants closed.",
        [_ev(u) for u in urls],
        "Biden closed more than 100 power plants",
    )


def test_sources_fetch_in_parallel() -> None:
    f = _Slow(sleep=0.3)
    urls = [f"https://s{i}.example/a" for i in range(6)]
    t0 = time.monotonic()
    got = fetch_all([_ev(u) for u in urls], f)
    assert time.monotonic() - t0 < 1.2  # 6 x 0.3 s sequential would be 1.8 s
    assert f.peak == 6
    assert [ev.url for ev, _ in got] == urls  # model order kept


def test_budget_skips_a_hanging_source_and_failures() -> None:
    f = _Slow(sleep=0.05)
    urls = [
        "https://hang.example/a",
        "https://bad.example/a",
        "https://boom.example/a",
        "https://ok.example/a",
    ]
    t0 = time.monotonic()
    got = fetch_all([_ev(u) for u in urls], f, budget_s=0.5)
    assert time.monotonic() - t0 < 1.5
    assert [ev.url for ev, _ in got] == ["https://ok.example/a"]


def test_candidates_capped_and_empty() -> None:
    f = _Slow(sleep=0)
    many = [_ev(f"https://s{i}.example/a") for i in range(20)]
    assert len(fetch_all(many, f)) == pipeline_mod.MAX_CANDIDATES
    assert fetch_all([], f) == []


def test_card_built_from_parallel_fetch_fast() -> None:
    f = _Slow(sleep=0.3)
    deps = Deps(InMemoryStore(), None, f, InMemorySnapshots())  # type: ignore[arg-type]
    urls = ["https://bad.example/a"] + [f"https://s{i}.example/a" for i in range(5)]
    t0 = time.monotonic()
    card = build_card("Biden closed more than 100 power plants", _assessment(urls), deps)
    assert time.monotonic() - t0 < 1.2
    assert card is not None
    assert len(card.sources) == deps.max_sources
    assert str(card.sources[0].url) == "https://s0.example/a"
