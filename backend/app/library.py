"""Proof Library: every card we have issued, listed, searchable and filterable (p75).

Cards are public proof (anyone with the link reads one) and carry no owner data, but the
Firestore rules still deny client side listing. The only way to list them is this server
index: a public safe projection, paginated, cached at the CDN.

Reads stay tiny: cards are immutable and append only, so one instance reads the
collection once on its first request and afterwards only the cards created since
(a Firestore cursor on created_at; an empty result costs one read).
Docs: https://cloud.google.com/firestore/docs/query-data/query-cursors

shortcut: in process index, comfortable to ~50k cards per instance; past that move search
to a managed index (Vertex AI Search or Firestore vector search) and keep this API shape.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from urllib.parse import urlsplit

from rapidfuzz import fuzz, process

from app.proof import FUZZY_CUTOFF, FUZZY_MIN_LEN, tokens

PAGE = 24
MAX_QUERY_CHARS = 200
MAX_QUERY_TOKENS = 12
REFRESH_S = 30.0  # how stale the index may get before a request pulls the new cards
VERDICTS = ("TRUE", "FALSE", "MISLEADING", "UNVERIFIABLE")
# The only query params /api/cards takes (frontend libraryUrl sends a subset).
LIBRARY_PARAMS = frozenset({"q", "verdict", "since", "until", "cursor"})
EXCERPT = 220


@dataclass(frozen=True)
class CardRow:
    """One card as the library shows it. Nothing here identifies who made it."""

    id: str
    claim: str
    verdict: str
    explanation: str
    support_score: float
    created_at: datetime
    domains: tuple[str, ...]
    source_count: int


class CardSource(Protocol):
    def cards_page(self, after: Any, limit: int) -> tuple[list[CardRow], Any]:
        """Oldest first, strictly after the opaque cursor `after` (None = from the start).
        Returns the rows and the cursor to pass next time (unchanged when no rows)."""
        ...


def row_from_dict(card_id: str, d: dict[str, Any]) -> CardRow | None:
    """Defensive parse of a stored card: a malformed doc is skipped, never a 500."""
    claim, verdict, created = d.get("claim"), d.get("verdict"), d.get("created_at")
    if not isinstance(claim, str) or verdict not in VERDICTS:
        return None
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created)
        except ValueError:
            return None
    if not isinstance(created, datetime) or created.tzinfo is None:
        return None
    created = created.astimezone(UTC)
    raw_sources = d.get("sources")
    sources: list[Any] = raw_sources if isinstance(raw_sources, list) else []
    domains: list[str] = []
    for s in sources:
        host = urlsplit(str(s.get("url", ""))).hostname if isinstance(s, dict) else None
        host = (host or "").removeprefix("www.")
        if host and host not in domains:
            domains.append(host)
    expl = d.get("explanation")
    score = d.get("support_score")
    return CardRow(
        id=card_id,
        claim=claim,
        verdict=str(verdict),
        explanation=expl if isinstance(expl, str) else "",
        support_score=float(score) if isinstance(score, (int, float)) else 0.0,
        created_at=created,
        domains=tuple(domains[:3]),
        source_count=len(sources),
    )


@dataclass
class _Entry:
    row: CardRow
    claim_toks: frozenset[str]
    expl_toks: frozenset[str]
    claim_lc: str


def _entry(row: CardRow) -> _Entry:
    return _Entry(
        row,
        frozenset(tokens(row.claim)),
        frozenset(tokens(row.explanation)),
        row.claim.casefold(),
    )


def _hit(t: str, toks: frozenset[str], prefix: bool) -> int:
    """2 = exact word, 1 = typo tolerant or (last typed word) prefix match, 0 = miss."""
    if t in toks:
        return 2
    if prefix and len(t) >= 2 and any(w.startswith(t) for w in toks):
        return 1
    if t.isdigit() or len(t) < FUZZY_MIN_LEN or not toks:
        return 0
    # Docs: https://rapidfuzz.github.io/RapidFuzz/Usage/process.html#extractone
    return 1 if process.extractOne(t, toks, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF) else 0


def score(entry: _Entry, q_toks: list[str], phrase: str) -> tuple[int, float]:
    """(query words matched, weight). Claim words weigh 3x the explanation's."""
    matched, weight = 0, 0.0
    for i, t in enumerate(q_toks):
        last = i == len(q_toks) - 1
        c = _hit(t, entry.claim_toks, last)
        e = 0 if c == 2 else _hit(t, entry.expl_toks, last)
        if c or e:
            matched += 1
            weight += 3.0 * c + e
    if phrase and len(q_toks) > 1 and phrase in entry.claim_lc:
        weight += 6.0
    return matched, weight


def _encode(cursor: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(cursor, separators=(",", ":")).encode()).decode()


def decode_cursor(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    if len(raw) > 200:
        raise ValueError("bad cursor")
    try:
        got = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("bad cursor") from exc
    if not isinstance(got, dict):
        raise ValueError("bad cursor")
    return got


@dataclass
class Library:
    source: CardSource
    clock: Callable[[], float] = time.monotonic
    refresh_s: float = REFRESH_S
    _entries: list[_Entry] = field(default_factory=list)  # newest first
    _ids: set[str] = field(default_factory=set)
    _cursor: Any = None
    _loaded_at: float | None = None
    _lock: Lock = field(default_factory=Lock)

    def _refresh(self) -> None:
        now = self.clock()
        if self._loaded_at is not None and now - self._loaded_at < self.refresh_s:
            return
        with self._lock:  # one request refreshes, the rest wait and reuse it
            if self._loaded_at is not None and now - self._loaded_at < self.refresh_s:
                return
            fresh: list[_Entry] = []
            while True:  # until a page comes back empty (cursor unchanged)
                rows, nxt = self.source.cards_page(self._cursor, 500)
                fresh.extend(_entry(r) for r in rows if r.id not in self._ids)
                self._ids.update(r.id for r in rows)
                if nxt is self._cursor or nxt == self._cursor:
                    break
                self._cursor = nxt
            if fresh:
                merged = fresh + self._entries
                merged.sort(key=lambda e: (e.row.created_at, e.row.id), reverse=True)
                self._entries = merged
            self._loaded_at = self.clock()

    def total(self) -> int:
        self._refresh()
        return len(self._entries)

    def search(
        self,
        q: str = "",
        verdicts: frozenset[str] = frozenset(),
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: str | None = None,
        limit: int = PAGE,
    ) -> dict[str, Any]:
        self._refresh()
        entries = self._entries
        q_toks = list(dict.fromkeys(tokens(q[:MAX_QUERY_CHARS])))[:MAX_QUERY_TOKENS]
        phrase = " ".join(q[:MAX_QUERY_CHARS].casefold().split())

        def in_time(e: _Entry) -> bool:
            at = e.row.created_at
            return (since is None or at >= since) and (until is None or at <= until)

        pool = [e for e in entries if in_time(e)]
        if q_toks:
            need = max(1, math.ceil(len(q_toks) / 2))  # a long query may miss a word or two
            scored = [(score(e, q_toks, phrase), e) for e in pool]
            ranked = [
                (s, e)
                for s, e in scored
                if s[0] >= need and (s[0] == len(q_toks) or any(t in e.claim_toks for t in q_toks))
            ]
            # Most query words first, then weight, then newest: list stays stable per index.
            ranked.sort(key=lambda se: (se[0][0], se[0][1], se[1].row.created_at), reverse=True)
            pool = [e for _, e in ranked]
        counts = {v: 0 for v in VERDICTS}
        for e in pool:
            counts[e.row.verdict] += 1
        hits = [e for e in pool if not verdicts or e.row.verdict in verdicts]

        cur = decode_cursor(cursor)
        start = 0
        if cur is not None:
            if q_toks:
                start = int(cur.get("o", 0)) if isinstance(cur.get("o"), int) else 0
            else:  # keyset: a card created meanwhile never shifts the next page
                try:
                    key = (datetime.fromisoformat(str(cur.get("t"))), str(cur.get("i", "")))
                except ValueError as exc:
                    raise ValueError("bad cursor") from exc
                if key[0].tzinfo is None:
                    raise ValueError("bad cursor")
                start = next(
                    (n for n, e in enumerate(hits) if (e.row.created_at, e.row.id) < key),
                    len(hits),
                )
        start = max(0, start)
        page = hits[start : start + limit]
        nxt = None
        if start + limit < len(hits):
            last = page[-1].row
            nxt = _encode(
                {"o": start + limit} if q_toks else {"t": last.created_at.isoformat(), "i": last.id}
            )
        return {
            "items": [view(e.row) for e in page],
            "next_cursor": nxt,
            "matched": len(hits),
            "total": len(entries),
            "counts": counts,
        }


def view(row: CardRow) -> dict[str, Any]:
    expl = row.explanation
    if len(expl) > EXCERPT:
        expl = expl[: EXCERPT - 1].rsplit(" ", 1)[0] + "…"
    return {
        "id": row.id,
        "claim": row.claim,
        "verdict": row.verdict,
        "excerpt": expl,
        "support_score": round(row.support_score, 2),
        "created_at": row.created_at.isoformat(),
        "domains": list(row.domains),
        "source_count": row.source_count,
    }
