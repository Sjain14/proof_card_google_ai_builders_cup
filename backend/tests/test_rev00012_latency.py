"""rev00012 prod verify (16 Oct 2026): the live "power plants" card took 120 s. Sources
were fetched one after another with no cap on the total (8 s timeout each, up to ~10
grounding chunks). Now one budget covers the whole card, still one source at a time and
best first (a parallel fetch broke the per capita comparison card on prod)."""

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


def test_budget_caps_the_whole_card() -> None:
    f = _Slow(sleep=0.3)
    urls = [f"https://s{i}.example/a" for i in range(10)]
    t0 = time.monotonic()
    got = list(fetch_all([_ev(u) for u in urls], f, budget_s=1.0))
    assert time.monotonic() - t0 < 1.6  # 10 x 0.3 s unbounded would be 3 s
    assert f.peak == 1  # one at a time, like before
    assert [ev.url for ev, _ in got] == urls[: len(got)]  # model order kept
    assert 2 <= len(got) <= 4


def test_hanging_source_and_failures_are_skipped() -> None:
    f = _Slow(sleep=0.05)
    urls = [
        "https://bad.example/a",
        "https://boom.example/a",
        "https://ok.example/a",
        "https://hang.example/a",
        "https://ok2.example/a",
    ]
    t0 = time.monotonic()
    got = list(fetch_all([_ev(u) for u in urls], f, budget_s=0.8))
    assert time.monotonic() - t0 < 1.5
    assert [ev.url for ev, _ in got] == ["https://ok.example/a"]
    assert list(fetch_all([], f)) == []


def test_card_stops_fetching_after_enough_proofs() -> None:
    f = _Slow(sleep=0.05)
    deps = Deps(InMemoryStore(), None, f, InMemorySnapshots())  # type: ignore[arg-type]
    urls = ["https://bad.example/a"] + [f"https://s{i}.example/a" for i in range(8)]
    card = build_card("Biden closed more than 100 power plants", _assessment(urls), deps)
    assert card is not None
    assert len(card.sources) == deps.max_sources
    assert str(card.sources[0].url) == "https://s0.example/a"
    assert pipeline_mod.FETCH_BUDGET_S <= 30


def test_live_classifiers_are_fast() -> None:
    import app.live as live_mod
    from app.model import _fast_thinking

    assert live_mod.SPOT_TIMEOUT_S <= 5.0  # heard -> checking took 12 s on prod
    assert str(_fast_thinking().thinking_level).endswith("MINIMAL")
