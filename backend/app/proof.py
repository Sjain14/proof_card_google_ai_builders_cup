"""Proof of source: our own fetch, passage match, sha256 snapshot.

We never trust a model's quote of a page. For every evidence URL we fetch the page
ourselves (SSRF guarded on every redirect hop), extract visible text, find the passage
that best supports the claim, and store the raw bytes under their sha256 so anyone can
later prove what the page said when the card was issued.
"""

from __future__ import annotations

import contextlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import ClassVar, Protocol

from app.security import (
    Resolver,
    UnsafeURLError,
    _system_resolver,
    assert_public_https_url,
    sha256_hex,
)

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 4
USER_AGENT = "ProofCardBot/0.2 (+fact check snapshot)"


@dataclass(frozen=True)
class Fetched:
    url: str
    final_url: str
    body: bytes
    content_type: str
    fetched_at: datetime


class FetchError(RuntimeError):
    pass


class Fetcher(Protocol):
    def fetch(self, url: str) -> Fetched: ...


class FixtureFetcher:
    """Offline fetcher for stub mode: serves fixtures.page_for()."""

    def fetch(self, url: str) -> Fetched:
        from app.fixtures import page_for

        body = page_for(url)
        if body is None:
            raise FetchError("not in fixtures")
        return Fetched(url, url, body, "text/html", datetime.now(UTC))


class HttpFetcher:
    """Real fetcher. Redirects are followed manually so each hop is re-vetted."""

    def __init__(self, resolve: Resolver = _system_resolver, timeout: float = 8.0) -> None:
        self.resolve = resolve
        self.timeout = timeout

    def fetch(self, url: str) -> Fetched:  # pragma: no cover - network; logic covered via fakes
        import httpx

        current = url
        with httpx.Client(
            timeout=self.timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT}
        ) as c:
            for _ in range(MAX_REDIRECTS + 1):
                try:
                    assert_public_https_url(current, self.resolve)
                except UnsafeURLError as exc:
                    raise FetchError(str(exc)) from exc
                with c.stream("GET", current) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location", "")
                        current = str(httpx.URL(current).join(loc))
                        continue
                    if r.status_code != 200:
                        raise FetchError(f"status {r.status_code}")
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in {"text/html", "text/plain", "application/xhtml+xml"}:
                        raise FetchError(f"unsupported content type {ctype}")
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > MAX_BYTES:
                            raise FetchError("page too large")
                    return Fetched(url, current, bytes(buf), ctype, datetime.now(UTC))
        raise FetchError("too many redirects")


# ---------- text extraction ----------


class _TextExtractor(HTMLParser):
    SKIP: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "svg", "template", "nav", "footer", "header"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "li", "div", "h1", "h2", "h3", "tr", "td"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def extract_text(body: bytes, content_type: str = "text/html") -> str:
    raw = body.decode("utf-8", errors="replace")
    if content_type == "text/plain":
        return re.sub(r"\s+", " ", raw).strip()
    p = _TextExtractor()
    p.feed(raw)
    text = "".join(p.parts)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


# ---------- passage matching ----------

_TOKEN = re.compile(r"[\w]+", re.UNICODE)
_STOP = {
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "and",
    "or",
    "is",
    "was",
    "are",
    "to",
    "for",
    "by",
    "with",
    "that",
    "this",
    "it",
    "as",
    "at",
    "be",
    "has",
    "have",
    "had",
    "from",
    "ki",
    "ka",
    "ke",
    "hai",
    "tha",
    "thi",
    "mein",
    "ko",
    "se",
    "aur",
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def tokens(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(_norm(s)) if t not in _STOP]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def score_passage(query: str, passage: str) -> float:
    """Recall of the query's content words in the passage; numbers count double and
    a number in the claim that is missing from the passage caps the score at 0.5."""
    q = tokens(query)
    if not q:
        return 0.0
    p = set(tokens(passage))
    weight = hit = 0.0
    missing_number = False
    for t in set(q):
        w = 2.0 if t.isdigit() else 1.0
        weight += w
        if t in p:
            hit += w
        elif t.isdigit():
            missing_number = True
    s = hit / weight
    return min(s, 0.5) if missing_number else s


def best_passage(query: str, text: str, window: int = 2) -> tuple[str, float]:
    sents = _sentences(text)
    if not sents:
        return "", 0.0
    best = ("", 0.0)
    for i in range(len(sents)):
        cand = " ".join(sents[i : i + window])
        s = score_passage(query, cand)
        if s > best[1]:
            best = (cand, s)
    return best[0][:1_500], round(best[1], 3)


# ---------- snapshot storage ----------


class SnapshotStore(Protocol):
    def put(self, sha256: str, body: bytes, content_type: str) -> str: ...


class InMemorySnapshots:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, sha256: str, body: bytes, content_type: str) -> str:
        self.blobs[sha256] = body
        return f"mem://snapshots/{sha256}"


class GcsSnapshots:  # pragma: no cover - needs GCP
    """Content addressed: snapshots/<sha256>. if_generation_match=0 makes writes create only."""

    def __init__(self, bucket: str) -> None:
        import google.cloud.storage as storage

        self.bucket = storage.Client().bucket(bucket)

    def put(self, sha256: str, body: bytes, content_type: str) -> str:
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(f"snapshots/{sha256}")
        with contextlib.suppress(PreconditionFailed):  # same bytes already stored
            blob.upload_from_string(body, content_type=content_type, if_generation_match=0)
        return f"gs://{self.bucket.name}/snapshots/{sha256}"


def snapshot(fetched: Fetched, store: SnapshotStore) -> str:
    digest = sha256_hex(fetched.body)
    store.put(digest, fetched.body, fetched.content_type)
    return digest
