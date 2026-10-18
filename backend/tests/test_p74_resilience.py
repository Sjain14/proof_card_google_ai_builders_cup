"""p74 (prod 17 Oct 2026, rev 00075): Vertex 504/429 bursts, native crash after parallel
extraction, duplicate parallel fetches. No network, no Vertex: everything is mocked."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from app.model import is_transient, with_backoff
from app.proof import Fetched, FetchError, HttpFetcher, extract_text


class _ApiError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"code {code}")
        self.code = code


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_transient_codes_retry(code: int) -> None:
    assert is_transient(_ApiError(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_client_errors_never_retry(code: int) -> None:
    assert not is_transient(_ApiError(code))


def test_timeouts_are_transient() -> None:
    assert is_transient(TimeoutError())
    assert not is_transient(ValueError("bad"))


def test_backoff_recovers_after_a_504() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fn() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise _ApiError(504)
        return "ok"

    assert with_backoff(fn, attempts=2, base_s=1.0, sleep=sleeps.append) == "ok"
    assert len(calls) == 2
    assert len(sleeps) == 1
    assert 0.5 <= sleeps[0] <= 1.5  # jittered


def test_backoff_gives_up_and_reraises() -> None:
    def fn() -> str:
        raise _ApiError(429)

    with pytest.raises(_ApiError):
        with_backoff(fn, attempts=2, base_s=0.0, sleep=lambda _s: None)


def test_backoff_never_retries_a_client_error() -> None:
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        raise _ApiError(400)

    with pytest.raises(_ApiError):
        with_backoff(fn, attempts=3, base_s=0.0, sleep=lambda _s: None)
    assert len(calls) == 1


def test_concurrency_is_capped() -> None:
    slots = threading.BoundedSemaphore(2)
    live = 0
    peak = 0
    lock = threading.Lock()

    def fn() -> int:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.02)
        with lock:
            live -= 1
        return 1

    with ThreadPoolExecutor(max_workers=8) as pool:
        out = list(pool.map(lambda _i: with_backoff(fn, slots=slots), range(8)))
    assert sum(out) == 8
    assert peak <= 2


class _CountingFetcher(HttpFetcher):
    def __init__(self, fail: bool = False) -> None:
        super().__init__()
        self.calls = 0
        self.fail = fail
        self.gate = threading.Event()

    def _fetch(self, url: str) -> Fetched:
        self.calls += 1
        self.gate.wait(2)
        if self.fail:
            raise FetchError("status 503")
        return Fetched(url, url, b"<p>hi</p>", "text/html", datetime.now(UTC))


def _parallel(f: _CountingFetcher, n: int) -> list[object]:
    out: list[object] = []

    def one() -> None:
        try:
            out.append(f.fetch("https://www.bls.gov/x"))
        except FetchError as exc:
            out.append(exc)

    threads = [threading.Thread(target=one) for _ in range(n)]
    for t in threads:
        t.start()
    time.sleep(0.1)
    f.gate.set()
    for t in threads:
        t.join(3)
    return out


def test_same_url_in_parallel_is_fetched_once() -> None:
    f = _CountingFetcher()
    out = _parallel(f, 3)
    assert f.calls == 1
    assert len(out) == 3
    assert all(isinstance(o, Fetched) for o in out)


def test_shared_fetch_error_reaches_every_caller() -> None:
    f = _CountingFetcher(fail=True)
    out = _parallel(f, 3)
    assert f.calls == 1
    assert all(isinstance(o, FetchError) for o in out)


def test_nothing_is_cached_after_the_fetch() -> None:
    f = _CountingFetcher()
    f.gate.set()
    f.fetch("https://www.bls.gov/x")
    f.fetch("https://www.bls.gov/x")
    assert f.calls == 2


def test_extraction_runs_one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    live = 0
    peak = 0
    lock = threading.Lock()

    def fake_extract(raw: str, **_kw: object) -> str:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.02)
        with lock:
            live -= 1
        return "x" * 300

    monkeypatch.setattr("app.proof.trafilatura.extract", fake_extract)
    with ThreadPoolExecutor(max_workers=4) as pool:
        out = list(pool.map(lambda _i: extract_text(b"<p>a</p>"), range(4)))
    assert all(o == "x" * 300 for o in out)
    assert peak == 1
