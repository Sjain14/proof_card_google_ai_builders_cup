"""Proof of source: our own fetch, passage match, sha256 snapshot.

We never trust a model's quote of a page. For every evidence URL we fetch the page
ourselves (SSRF guarded on every redirect hop), extract visible text, find the passage
that best supports the claim, and store the raw bytes under their sha256 so anyone can
later prove what the page said when the card was issued.
"""

from __future__ import annotations

import contextlib
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import ClassVar, Protocol

import httpx
import trafilatura
from pypdf import PdfReader
from rapidfuzz import fuzz, process

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


HTML_TYPES = frozenset({"text/html", "text/plain", "application/xhtml+xml"})
PDF_TYPE = "application/pdf"
JSON_TYPE = "application/json"
# JSON only from official statistics APIs we render ourselves (app/officialdata.py).
JSON_HOSTS = frozenset({"api.worldbank.org"})
MAX_PDF_BYTES = 10_000_000  # official statistics (MoSPI, RBI, PIB) are mostly PDFs
MAX_PDF_PAGES = 60


class HttpFetcher:
    """Real fetcher. Redirects are followed manually so each hop is re-vetted.

    Every transport failure (timeout, DNS, TLS, proxy, protocol) becomes FetchError, so one
    slow source is skipped instead of failing the whole claim.
    Docs: https://www.python-httpx.org/exceptions/
    """

    def __init__(
        self,
        resolve: Resolver = _system_resolver,
        timeout: float = 8.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.resolve = resolve
        self.timeout = timeout
        self.transport = transport  # tests inject httpx.MockTransport

    def fetch(self, url: str) -> Fetched:
        try:
            return self._fetch(url)
        except httpx.HTTPError as exc:
            raise FetchError(f"{type(exc).__name__}") from exc

    def _fetch(self, url: str) -> Fetched:
        current = url
        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
            transport=self.transport,
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
                    if ctype in HTML_TYPES:
                        cap = MAX_BYTES
                    elif ctype == PDF_TYPE:
                        cap = MAX_PDF_BYTES
                    elif ctype == JSON_TYPE and httpx.URL(current).host in JSON_HOSTS:
                        cap = MAX_BYTES
                    else:
                        raise FetchError(f"unsupported content type {ctype}")
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > cap:
                            raise FetchError("page too large")
                    return Fetched(url, current, bytes(buf), ctype, datetime.now(UTC))
        raise FetchError("too many redirects")


# ---------- text extraction ----------


class _TextExtractor(HTMLParser):
    """Fallback when trafilatura finds no main content (tiny or unusual pages)."""

    SKIP: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "svg", "template", "nav", "footer", "header"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip += 1
        if tag in {"p", "br", "li", "div", "h1", "h2", "h3", "tr", "td"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _pdf_text(body: bytes) -> str:
    """Text layer of a PDF (pypdf, pure Python). Scanned PDFs have none: empty string.
    Docs: https://pypdf.readthedocs.io/en/stable/user/extract-text.html"""
    try:
        reader = PdfReader(io.BytesIO(body))
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((pg.extract_text() or "") for pg in pages)
    except Exception:  # hostile / broken PDFs raise many types; a bad source is just skipped
        return ""


def _html_text(raw: str) -> str:
    # Main content only (no menus, footers, "1 · 2 · 3" pagers): trafilatura, the extractor
    # picked in 08_Reuse_Map C2. Docs: https://trafilatura.readthedocs.io/en/latest/corefunctions.html
    main = trafilatura.extract(
        raw, include_comments=False, include_tables=True, favor_recall=True, deduplicate=True
    )
    if main and len(main) >= MIN_MAIN_TEXT:
        return main
    p = _TextExtractor()
    p.feed(raw)
    return "".join(p.parts)


MIN_MAIN_TEXT = 200


def extract_text(body: bytes, content_type: str = "text/html") -> str:
    if content_type == PDF_TYPE:
        text = _pdf_text(body)
    else:
        raw = body.decode("utf-8", errors="replace")
        if content_type == "text/plain":
            return re.sub(r"\s+", " ", raw).strip()
        text = _html_text(raw)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


# ---------- passage matching ----------

# \w alone drops Indic combining marks (matras, virama): "संविधान" became स, व, ध, न.
# Range covers Devanagari through Malayalam (U+0900..U+0DFF), same idea as live.py _WORD.
_TOKEN = re.compile(r"[\w\u0900-\u0DFF]+", re.UNICODE)
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")  # Devanagari digits -> ASCII
_STOP = {
    # English
    "the", "a", "an", "of", "in", "on", "and", "or", "is", "was", "are", "to", "for", "by",
    "with", "that", "this", "it", "as", "at", "be", "has", "have", "had", "from",
    # Hinglish (Latin script)
    "ki", "ka", "ke", "hai", "hain", "tha", "thi", "mein", "me", "ko", "se", "aur", "bhi", "ye",
    # Hindi (Devanagari)
    "की", "का", "के", "है", "हैं", "था", "थी", "में", "को", "से", "और", "ने", "भी", "यह", "पर",
}  # fmt: skip
FUZZY_CUTOFF = 85  # rapidfuzz ratio 0..100: inflections, transliteration spelling variants
FUZZY_MIN_LEN = 4  # short words fuzz into each other; exact match only


@dataclass(frozen=True)
class Match:
    passage: str
    score: float  # support for the claim as stated (numbers must appear)
    topic: float  # same, ignoring numbers: "the passage is about this claim"
    conflict: bool  # the claim's number is absent and the passage states other numbers


_NUM_WORDS = {
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60",
    "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100",
}  # fmt: skip
# Same fact, different word: "highest in 40 years" vs "a four-decade high" vs "largest".
_SAME = {
    "largest": "highest", "biggest": "highest", "high": "highest", "record": "highest",
    "smallest": "lowest", "low": "lowest",
    "pct": "percent", "per cent": "percent",
}  # fmt: skip
_DECADE = re.compile(r"\b(\d+)[\s-]*decades?\b")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().translate(_DIGITS)
    s = s.replace("%", " percent ").replace("per cent", "percent")
    s = re.sub(r"[a-z]+", lambda m: _NUM_WORDS.get(m.group(), m.group()), s)
    # "four-decade high" -> "40 years highest": the claim usually says "in 40 years".
    return _DECADE.sub(lambda m: f"{int(m.group(1)) * 10} years", s)


def tokens(s: str) -> list[str]:
    return [_SAME.get(t, t) for t in _TOKEN.findall(_norm(s)) if t not in _STOP]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def _hit(t: str, p: set[str]) -> bool:
    if t in p:
        return True
    if t.isdigit() or len(t) < FUZZY_MIN_LEN:
        return False
    # Docs: https://rapidfuzz.github.io/RapidFuzz/Usage/process.html#extractone
    return process.extractOne(t, p, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF) is not None


def match_passage(query: str, passage: str) -> Match:
    """Recall of the query's content words in the passage (exact or fuzzy); numbers count
    double and a number in the claim that is missing from the passage caps score at 0.5."""
    q = set(tokens(query))
    if not q:
        return Match(passage, 0.0, 0.0, False)
    p = set(tokens(passage))
    weight = hit = words = word_hits = 0.0
    missing_number = False
    for t in q:
        is_num = t.isdigit()
        w = 2.0 if is_num else 1.0
        weight += w
        found = _hit(t, p)
        if found:
            hit += w
        elif is_num:
            missing_number = True
        if not is_num:
            words += 1
            word_hits += found
    s = hit / weight
    topic = word_hits / words if words else 0.0
    conflict = missing_number and any(t.isdigit() for t in p)
    return Match(passage, min(s, 0.5) if missing_number else s, topic, conflict)


def score_passage(query: str, passage: str) -> float:
    return match_passage(query, passage).score


def best_match(query: str, text: str, window: int = 2) -> Match:
    """Best window by score, and separately the best contradicting window by topic."""
    best = Match("", 0.0, 0.0, False)
    for i, _ in enumerate(sents := _sentences(text)):
        m = match_passage(query, " ".join(sents[i : i + window]))
        if m.score > best.score:
            best = m
    return Match(best.passage[:1_500], round(best.score, 3), round(best.topic, 3), best.conflict)


def best_contradiction(query: str, text: str, window: int = 2) -> Match:
    """For FALSE claims: the on topic passage that states a different number.
    A wrong number is evidence AGAINST the claim, not missing evidence (audit #6)."""
    best = Match("", 0.0, 0.0, False)
    for i, _ in enumerate(sents := _sentences(text)):
        m = match_passage(query, " ".join(sents[i : i + window]))
        if m.conflict and m.topic > best.topic:
            best = m
    return Match(best.passage[:1_500], round(best.score, 3), round(best.topic, 3), best.conflict)


# Words that state the RELATION of a comparison, not its topic. A source proves
# "India's per capita GDP is higher than Japan's" by stating both figures; it never
# repeats "higher than" (prod 16 Oct: the model said FALSE with the IMF figures, the best
# window on worldometers scored 0.429 and the gate turned the card UNVERIFIABLE).
_RELATION = {
    "higher", "lower", "bigger", "smaller", "larger", "greater", "richer", "poorer",
    "more", "less", "fewer", "better", "worse", "than", "ahead", "behind", "exceeds",
    "exceed", "overtook", "overtaken", "surpassed", "compared", "versus", "vs",
    "zyada", "jyada", "kam", "aage", "peeche", "adhik",
    "ज़्यादा", "ज्यादा", "अधिक", "कम", "आगे", "पीछे",
}  # fmt: skip
_COMPARE = {"than", "versus", "vs", "compared", "ahead", "behind", "exceeds", "overtook",
            "surpassed", "zyada", "jyada", "aage", "peeche", "adhik",
            "ज़्यादा", "ज्यादा", "अधिक", "आगे", "पीछे",
            "\u092c\u0921\u093c\u0940", "\u092c\u0921\u093c\u093e",  # NFKC form
            "badi", "bada", "chhota", "chhoti", "छोटी", "छोटा"}  # fmt: skip


def is_comparison(query: str) -> bool:
    """A comparison with no stated figure: 'X is higher than Y', 'X ka Y se zyada'."""
    t = set(_TOKEN.findall(_norm(query)))
    return bool(t & _COMPARE) and not any(w.isdigit() for w in t)


def _figure(t: str) -> bool:
    """A number that can be one side's value; a year ("by Country (2026)") is not."""
    return t.isdigit() and not (len(t) == 4 and 1900 <= int(t) <= 2100)


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _figures(line: str) -> int:
    """Whole numbers in a line ("$35,700" is one), years left out."""
    return sum(_figure(n.replace(",", "").split(".")[0]) for n in _NUMBER.findall(_norm(line)))


def comparison_match(query: str, text: str, max_rows: int = 2) -> Match:
    """Evidence for a figure-less comparison: the lines that give each side's figure plus
    the line that names the metric, from the same page. Tables keep each country on its
    own row, far apart, so no 2 sentence window holds both sides. Score = share of the
    claim's topic words (relation words removed) covered; needs >= 2 lines with a number."""
    # len > 1 drops the possessive "s" of "Japan's"
    q = {t for t in tokens(query) if t not in _RELATION and (len(t) > 1 or t.isdigit())}
    if not q:
        return Match("", 0.0, 0.0, False)
    lines = [ln.strip() for ln in re.split(r"\n+|(?<=[.!?।])\s+", text) if ln.strip()]
    toks = [set(tokens(ln)) for ln in lines]

    def cover(i: int, need: set[str]) -> set[str]:
        return {t for t in need if _hit(t, toks[i])}

    picked: list[int] = []
    left = set(q)
    for _ in range(max_rows):  # one row per side: each must carry a figure
        best = max(
            (i for i, tk in enumerate(toks) if i not in picked and any(map(_figure, tk))),
            key=lambda i: len(cover(i, left)),
            default=None,
        )
        if best is None or not cover(best, left):
            break
        picked.append(best)
        left -= cover(best, left)
    # One line can hold both sides ("Japan's is $35,700, while India's is $2,810"): it
    # names every topic word and carries at least two figures (prod 16 Oct, English
    # wording ended `failed` when the grounded source stated the pair in one sentence).
    both = len(picked) == 1 and not left and _figures(lines[picked[0]]) >= 2
    if len(picked) < 2 and not both:
        return Match("", 0.0, 0.0, False)
    if left:  # the metric usually sits in the heading or the table caption
        ctx = max(
            (i for i in range(len(lines)) if i not in picked and len(lines[i]) > 20),
            key=lambda i: len(cover(i, left)),
            default=None,
        )
        if ctx is not None and cover(ctx, left):
            left -= cover(ctx, left)
            picked.insert(0, ctx)
    score = round(1 - len(left) / len(q), 3)
    passage = " … ".join(lines[i][:400] for i in picked)
    return Match(passage[:1_500], score, score, False)


def best_passage(query: str, text: str, window: int = 2) -> tuple[str, float]:
    m = best_match(query, text, window)
    return m.passage, m.score


# ---------- snapshot storage ----------


class SnapshotStore(Protocol):
    def put(self, sha256: str, body: bytes, content_type: str) -> str: ...
    def get(self, sha256: str) -> bytes | None: ...


class InMemorySnapshots:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, sha256: str, body: bytes, content_type: str) -> str:
        self.blobs[sha256] = body
        return f"mem://snapshots/{sha256}"

    def get(self, sha256: str) -> bytes | None:
        return self.blobs.get(sha256)


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

    def get(self, sha256: str) -> bytes | None:
        from google.api_core.exceptions import NotFound

        try:
            data: bytes = self.bucket.blob(f"snapshots/{sha256}").download_as_bytes()
        except NotFound:
            return None
        return data


def snapshot(fetched: Fetched, store: SnapshotStore) -> str:
    digest = sha256_hex(fetched.body)
    store.put(digest, fetched.body, fetched.content_type)
    return digest
