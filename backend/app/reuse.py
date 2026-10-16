"""Database first: a claim said in other words reuses a card already proved this week.

claim_key() only catches the same words. Here every proved claim (claim_cards: text, card,
context, time) is embedded into a small in-process index; a new claim with the same
numbers, the same negation and the same meaning (cosine >= DIRECT, or the judge says yes
from GRAY up) gets that card instead of a fresh check. Wrong reuse is worse than a slow
check, so the bar is higher than the live screen's: numbers must be identical, not only
compatible, and "is" vs "is not" never match.

shortcut: in-process cosine over the last week's cards (<= MAX_ENTRIES); move to Firestore
find_nearest with a vector index once the week holds tens of thousands.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.live import Embedder, Judge, cosine, numbers
from app.pipeline import claim_key
from app.store import Store

log = logging.getLogger(__name__)

DIRECT = 0.97  # same numbers + negation, at/above: reuse without asking the judge
GRAY = 0.80  # from here the judge decides; below: a different claim
JUDGE_TOP_K = 2
MAX_ENTRIES = 500
REFRESH_S = 300.0
AGE = timedelta(days=7)
EMBED_BATCH = 50

_NEG = re.compile(
    r"\b(?:not|never|no|none|nobody|nothing|didn't|isn't|wasn't|won't|nahi|nahin|mat)\b"
    r"|नहीं"
)


# "third largest" vs "fourth largest": numbers() reads digits only, so ranks in words are
# compared here (English + Hindi), alongside the digits.
_RANKS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "top": 1, "largest": 0,
    "पहली": 1, "पहला": 1, "दूसरी": 2, "दूसरा": 2, "तीसरी": 3, "तीसरा": 3,
    "चौथी": 4, "चौथा": 4, "पांचवीं": 5, "पांचवां": 5,
}  # fmt: skip
_RANK_RE = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b")


def ranks(text: str) -> frozenset[int]:
    low = text.lower()
    out = {int(m) for m in _RANK_RE.findall(low)}
    out |= {v for w in re.findall(r"[\w\u0900-\u097f]+", low) if (v := _RANKS.get(w, -1)) > 0}
    return frozenset(out)


def negated(text: str) -> bool:
    return len(_NEG.findall(text.lower())) % 2 == 1


@dataclass
class _Entry:
    key: str
    card_id: str
    text: str
    context: str
    vec: list[float]
    nums: frozenset[str]
    neg: bool
    ranks: frozenset[int]


class SimilarCards:
    """Pipeline's `Similar`: lookup() before a cold check, add() after a card is proved."""

    def __init__(self, store: Store, embedder: Embedder, judge: Judge | None = None) -> None:
        self.store, self.embedder, self.judge = store, embedder, judge
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._loading = False

    # ---------- index ----------

    def refresh(self) -> None:
        """Load the week's claim_cards and embed the ones not yet indexed."""
        since = datetime.now(UTC) - AGE
        rows = self.store.recent_claim_cards(since, MAX_ENTRIES)
        with self._lock:
            # a key from an older CACHE_VERSION is a verdict a later fix may have changed
            new = [
                r
                for r in rows
                if r.key not in self._entries and r.text and r.key == claim_key(r.text, r.context)
            ]
        for i in range(0, len(new), EMBED_BATCH):
            chunk = new[i : i + EMBED_BATCH]
            vecs = self.embedder.embed([r.text for r in chunk])
            with self._lock:
                for r, v in zip(chunk, vecs, strict=True):
                    self._entries[r.key] = _Entry(
                        r.key,
                        r.card_id,
                        r.text,
                        r.context,
                        v,
                        numbers(r.text),
                        negated(r.text),
                        ranks(r.text),
                    )
        with self._lock:
            self._loaded_at = time.monotonic()
            if len(self._entries) > MAX_ENTRIES:  # keep the newest keys
                keep = {r.key for r in rows}
                self._entries = {k: e for k, e in self._entries.items() if k in keep}

    def _maybe_refresh(self) -> None:
        """Never blocks a check: the first lookups after start run on what is loaded."""
        with self._lock:
            due = time.monotonic() - self._loaded_at > REFRESH_S and not self._loading
            if due:
                self._loading = True

        def run() -> None:
            try:
                self.refresh()
            except Exception:
                log.warning("similar index refresh failed", exc_info=True)
            finally:
                with self._lock:
                    self._loading = False

        if due:
            threading.Thread(target=run, daemon=True).start()

    def add(self, key: str, text: str, context: str, card_id: str) -> None:
        try:
            [vec] = self.embedder.embed([text])
        except Exception:
            log.warning("similar index add failed", exc_info=True)
            return
        with self._lock:
            self._entries[key] = _Entry(
                key, card_id, text, context, vec, numbers(text), negated(text), ranks(text)
            )

    # ---------- lookup ----------

    def lookup(self, text: str, context: str) -> tuple[str, float] | None:
        """(card id, cosine) of the same claim proved this week, else None. A speech
        (context = its link) reuses cards of the same speech or of the bot (no context);
        the bot reuses any."""
        self._maybe_refresh()
        with self._lock:
            pool = [e for e in self._entries.values() if not context or e.context in ("", context)]
        if not pool:
            return None
        try:
            [q] = self.embedder.embed([text])
        except Exception:
            log.warning("similar lookup embed failed", exc_info=True)
            return None
        heard, neg, rk = numbers(text), negated(text), ranks(text)
        cands = sorted(
            (
                (cosine(q, e.vec), e)
                for e in pool
                if e.nums == heard and e.neg == neg and e.ranks == rk
            ),
            key=lambda p: p[0],
            reverse=True,
        )
        asked = 0
        for sim, e in cands:
            if sim >= DIRECT:
                return e.card_id, sim
            if sim < GRAY or self.judge is None or asked >= JUDGE_TOP_K:
                break
            asked += 1  # noqa: SIM113 - counts judge calls, not loop steps
            if self.judge.same_claim(text, e.text):
                return e.card_id, sim
        return None

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
