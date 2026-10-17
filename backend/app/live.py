"""Live bridge (During): heard sentence -> claim spotting -> instant match or cold check.

Flow per final transcript sentence (03_Architecture §2 steps 10 to 13):
  1. spot_claims(): which spans are checkable factual claims (model; stub = heuristic).
  2. embed each claim, cosine against this session's PROVED prebunked claims.
  3. similarity >= threshold -> the existing Proof Card is pushed at once (PREBUNKED hit).
  4. miss -> a LIVE claim is stored as `checking` and pipeline.verify_claim() runs cold,
     the exact same path as Before, so the card is identical in shape and proof.

Embeddings: gemini-embedding-001, task_type SEMANTIC_SIMILARITY, 768 dims.
Docs: https://ai.google.dev/gemini-api/docs/embeddings
Live transcription: Gemini Live API, raw PCM16 16 kHz mono, 10 minute session cap (we
reconnect). Docs: https://ai.google.dev/gemini-api/docs/live-api/live-transcribe
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.model import FAST_TIMEOUT_S, _fast_thinking, vertex_client
from app.officialdata import is_country_figure
from app.pipeline import Deps, Trace, verify_claim
from app.schemas import ClaimDoc, ClaimSource, ClaimStatus

log = logging.getLogger("proofcard.live")

MATCH_THRESHOLD = 0.80  # cosine; calibrated in tests/test_live.py, re-check on the demo clip
INSTANT_THRESHOLD = 0.90  # at or above (same numbers): card at once, no judge call
# Recall floor, judge only. Replay 7dhIVHRKhvo (16 Oct): 0 of 6 spoken lines matched a
# 9 card bank. "we remain at the highest" vs bank "8.2%, fastest growing major economy"
# never reached the judge: different stated numbers (none vs 8.2) and cosine under 0.80.
# Below MATCH_THRESHOLD, or with numbers that only overlap, a candidate needs the judge's
# yes ("one fact check decides both"), so wider retrieval can't show a wrong card.
RECALL_THRESHOLD = 0.65
JUDGE_TOP_K = 3  # judge calls per claim, best cosine first (~1 s each, minimal thinking)
# Cold checks get their own threads. asyncio.to_thread shares the loop's default pool,
# min(32, cpus + 4) = 5 threads on a 1 vCPU Cloud Run instance: a replay's 6 cold checks
# (~40 s each, blocking) held every thread, so spotter, match and Firestore calls queued
# behind them and a card took 108 to 145 s from the moment the line was heard.
_COLD_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="cold")
MAX_SENTENCE_CHARS = 600
# Past this the heuristic decides (check the whole line). 12 s used to eat most of a live
# card's budget when the spotter stalled (rev00012: heard -> checking took 12 s).
SPOT_TIMEOUT_S = 4.0
EMBED_DIMS = 768


# ---------- embeddings ----------


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # inputs are unit vectors


_WORD = re.compile(r"[\wऀ-ॿ]+")


class HashEmbedder:
    """Offline embedder for tests and local dev only: hashed word + character trigrams.

    shortcut: lexical, not semantic; prod uses VertexEmbedder (model_mode=vertex).
    """

    dims = 512

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dims
            words = _WORD.findall(t.lower())
            grams = words + [w[i : i + 3] for w in words for i in range(max(1, len(w) - 2))]
            for g in grams:
                h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=4).digest(), "big")
                v[h % self.dims] += 1.0
            out.append(_unit(v))
        return out


class VertexEmbedder:  # pragma: no cover - needs a GCP project
    def __init__(self, project: str, location: str, model: str = "gemini-embedding-001") -> None:
        self.client = vertex_client(project, location, FAST_TIMEOUT_S)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        from google.genai import types

        contents: list[Any] = list(texts)
        resp = self.client.models.embed_content(
            model=self.model,
            contents=contents,
            config=types.EmbedContentConfig(
                task_type="SEMANTIC_SIMILARITY", output_dimensionality=EMBED_DIMS
            ),
        )
        return [_unit(list(e.values or [])) for e in resp.embeddings or []]


# ---------- claim spotting ----------

_NUMBERISH = re.compile(
    r"\d|percent|%|crore|lakh|million|billion|first|largest|highest|lowest|"
    # comparatives (prod check 16 Oct: "per capita GDP is higher than Japan" never reached
    # the spotter) and rate/record words that carry a checkable figure without a digit
    r"\b(?:higher|lower|bigger|smaller|richer|poorer|more|less|fewer|worst|best|record|"
    r"doubled|tripled|halved|per capita|ahead of|behind)\b|"
    # done deeds and absolutes: "I got all the hostages back", "we ended eight wars" (no
    # digit, skipped as not_checkable on the Trump demo, 16 Oct); the model decides.
    r"\b(?:all the|all of (?:the|them|our|my)|every single|none of|never|nobody|no one|"
    r"ended|stopped|released|freed|"
    r"signed|passed|built|banned|abolished|eliminated|destroyed|obliterated|got back|"
    r"brought back|returned)\b|"
    r"sabhi|sab ke sab|kabhi nahi|kabhi bhi|khatam|band kar|"
    r"सभी|सबको|कभी नहीं|ख़त्म|खत्म|"
    r"pratishat|karod|sabse|pehla|pehli|zyada|jyada|kam|aage|peeche|"
    r"प्रतिशत|करोड़|लाख|सबसे|ज़्यादा|ज्यादा|कम|आगे|पीछे",
    re.IGNORECASE,
)


def heuristic_spot(sentence: str) -> list[str]:
    """Cheap pre filter: a checkable claim almost always carries a number or a superlative."""
    s = sentence.strip()
    if len(_WORD.findall(s)) < 4 or s.endswith("?"):
        return []
    return [s] if _NUMBERISH.search(s) else []


class Spotter(Protocol):
    def spot_claims(self, sentence: str) -> list[str]: ...


class HeuristicSpotter:
    def spot_claims(self, sentence: str) -> list[str]:
        return heuristic_spot(sentence)


SPOT_PROMPT = """You are a live fact-check desk. From this sentence heard on air, return the
factual claims a fact checker can verify against public records (numbers, dates, rankings,
official statistics). Copy each claim as said, keep its language (English, Hindi or
Hinglish). Comparisons of countries or states on official figures (bigger economy,
higher per capita income, more populous) are claims even without a number. So are
statements of what already happened ("I got all the hostages back", "we ended eight
wars", "Iran's nuclear sites were destroyed") and absolutes about the present or past
("no country has ever...", "every hostage is home").
Return [] for opinions, questions, greetings and pure promises about the future ("Iran
will never have a nuclear weapon" is a pledge: nothing on record can prove it yet).
Keep who said it: a claim put in a named person's mouth ("Modi said India is the third
largest economy") is copied WITH the name and "said", never as the bare statement. Did
they say it is the first thing to check.
Sentence: "{sentence}"
"""


IMAGE_PROMPT = """This image was sent to a fact checking bot: a forwarded WhatsApp message,
a screenshot of a post or a news graphic. Return the factual claims written on it that a
fact checker can verify against public records (numbers, dates, rankings, official
statistics, things said to have already happened). Copy each claim as written as one full
sentence, keep its language (English, Hindi or Hinglish), most important first, at most 3.
Return [] for a photo with no such claim, opinions, jokes and promises about the future.
A quote card (a person's photo or name with words in their mouth) is copied WITH the name:
"Modi said: <the words>", never the bare words.
"""


def image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class VertexImageReader:  # pragma: no cover - needs a GCP project
    """Claims written on a forwarded image (the bot's screenshot path)."""

    def __init__(self, project: str, location: str, model: str) -> None:
        self.client = vertex_client(project, location, FAST_TIMEOUT_S * 2)
        self.model = model

    def __call__(self, data: bytes) -> list[str]:
        import json

        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=[types.Part.from_bytes(data=data, mime_type=image_mime(data)), IMAGE_PROMPT],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema={"type": "ARRAY", "items": {"type": "STRING"}},
                thinking_config=_fast_thinking(),
            ),
        )
        try:
            items = json.loads(resp.text or "[]")
        except ValueError:
            return []
        return [str(c).strip() for c in items if str(c).strip()][:3]


class VertexSpotter:  # pragma: no cover - needs a GCP project
    """Model spotting behind the heuristic pre filter, so chit chat never costs a call."""

    def __init__(self, project: str, location: str, model: str) -> None:
        self.client = vertex_client(project, location, FAST_TIMEOUT_S)
        self.model = model

    def spot_claims(self, sentence: str) -> list[str]:
        import json

        from google.genai import types

        if not heuristic_spot(sentence):
            return []
        resp = self.client.models.generate_content(
            model=self.model,
            contents=SPOT_PROMPT.format(sentence=sentence),
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema={"type": "ARRAY", "items": {"type": "STRING"}},
                thinking_config=_fast_thinking(),
            ),
        )
        try:
            items = json.loads(resp.text or "[]")
        except ValueError:
            return []
        return [str(c).strip() for c in items if str(c).strip()][:3]


# ---------- match judge ----------


class Judge(Protocol):
    def same_claim(self, heard: str, checked: str) -> bool: ...


JUDGE_PROMPT = """Two claims. A was just heard on air. B was already fact checked.
Answer same=true only if B's fact check fully decides whether A is true: same subject,
same measure or quantity, same place and same time period. Same topic is NOT enough
(GDP rank vs GDP per capita, population vs economy, repo rate vs growth rate = false).
Claims can be English, Hindi or Hinglish.
A: "{heard}"
B: "{checked}"
"""


class VertexJudge:  # pragma: no cover - needs a GCP project
    """Gray zone check (threshold <= cosine < instant): retrieve by embedding, then verify,
    like Full Fact's claim matching: one fact check must apply to both claims.
    https://fullfact.org/blog/2021/oct/towards-common-definition-claim-matching/
    Any model error = not the same claim, so the cold check runs: never a wrong card."""

    def __init__(self, project: str, location: str, model: str) -> None:
        self.client = vertex_client(project, location, FAST_TIMEOUT_S)
        self.model = model

    def same_claim(self, heard: str, checked: str) -> bool:
        import json

        from google.genai import types

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=JUDGE_PROMPT.format(heard=heard, checked=checked),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    thinking_config=_fast_thinking(),
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {"same": {"type": "BOOLEAN"}},
                        "required": ["same"],
                    },
                ),
            )
            return bool(json.loads(resp.text or "{}").get("same", False))
        except Exception:
            log.warning("match judge failed, treating as a miss", exc_info=True)
            return False


# ---------- matching engine ----------


@dataclass
class _Index:
    count: int = -1
    ids: list[str] = field(default_factory=list)
    vecs: list[list[float]] = field(default_factory=list)
    nums: list[frozenset[str]] = field(default_factory=list)


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text: str) -> frozenset[str]:
    """Digits a claim states ("4 percent", "2025", "12.5 crore"), commas dropped.
    Two claims that state different numbers are different claims, however close their
    embeddings: "repo rate 4% in 2025" must never borrow the "4th largest economy by 2025"
    card (live run 15 Oct, cosine 0.806). A miss is safe: it falls through to a cold check."""
    return frozenset(m.replace(",", "") for m in _NUM.findall(text))


def numbers_compatible(a: frozenset[str], b: frozenset[str]) -> bool:
    """Loose number check for judge-gated candidates: one side states no number, or the
    two share one ("8.2% se ab 7.4%" vs a bank "8.2%" claim). Disjoint numbers never match."""
    return not a or not b or bool(a & b)


@dataclass
class LiveDeps:
    deps: Deps
    embedder: Embedder
    spotter: Spotter
    threshold: float = MATCH_THRESHOLD
    judge: Judge | None = None  # None = trust the cosine (tests, stub mode)
    instant: float = INSTANT_THRESHOLD


Emit = Callable[[dict[str, Any]], Awaitable[None]]


class Alert(Protocol):
    """(session, card, verdict, text, t) -> sent. t = seconds into the speech video, when
    known, so the alert can link the exact moment. Implementation: app/alerts.py."""

    def __call__(
        self,
        session_id: str,
        card_id: str,
        verdict: Any,
        text: str,
        t: float | None = None,
        /,
    ) -> bool: ...


class LiveEngine:
    """One per websocket. Sync core (match) + async cold checks pushed via emit()."""

    def __init__(
        self, session_id: str, live: LiveDeps, emit: Emit, alert: Alert | None = None
    ) -> None:
        self.sid = session_id
        self.live = live
        self.emit = emit
        self.alert = alert
        self._index = _Index()
        self._seen: set[str] = set()
        self._shown: set[str] = set()  # prebunked claim ids already pushed this session
        self._cards: set[str] = set()  # card ids on screen: one tile per card, ever
        # live claims sent to a cold check: (text, vector, numbers). A second wording of
        # the same claim ("worst inflation in 48 years" / "inflation is the worst in 48
        # years") used to start a second check and put two identical cards on screen
        # (Team lead, Trump demo 16 Oct 2026).
        self._cold_seen: list[tuple[str, list[float], Any]] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = threading.Lock()  # match() runs in worker threads, two at a time

    def _refresh(self) -> _Index:
        """Index of prebunked claims that already have a card; rebuilt only when it grew.

        shortcut: in process cosine over one session's claims (<= 20, sub millisecond);
        switch to Firestore find_nearest if a session ever holds hundreds.
        """
        with self._lock:
            return self._refresh_locked()

    def _refresh_locked(self) -> _Index:
        claims = [
            (cid, c)
            for cid, c in self.live.deps.store.list_claims(self.sid)
            if c.source == ClaimSource.PREDICTED and c.status == ClaimStatus.PROVED and c.card_id
        ]
        if len(claims) != self._index.count:
            vecs = self.live.embedder.embed([c.text for _, c in claims]) if claims else []
            nums = [numbers(c.text) for _, c in claims]
            self._index = _Index(len(claims), [cid for cid, _ in claims], vecs, nums)
        return self._index

    def match(self, text: str) -> tuple[str | None, float]:
        """Best strict candidate: same stated numbers and cosine >= threshold."""
        for cid, sim, exact in self.candidates(text):
            if exact and sim >= self.live.threshold:
                return cid, sim
        return None, 0.0

    def candidates(self, text: str) -> list[tuple[str, float, bool]]:
        """(claim id, cosine, same numbers) best first. Strict ones (same numbers, cosine >=
        threshold) always; with a judge also loose ones (compatible numbers, cosine >=
        RECALL_THRESHOLD), which only ever count after the judge says yes."""
        idx = self._refresh()
        if not idx.ids:
            return []
        [q] = self.live.embedder.embed([text])
        heard = numbers(text)
        out: list[tuple[str, float, bool]] = []
        for cid, v, n in zip(idx.ids, idx.vecs, idx.nums, strict=True):
            sim = cosine(q, v)
            exact = n == heard  # same stated numbers, or none on both sides
            if exact and sim >= self.live.threshold:
                out.append((cid, sim, True))
            elif (
                self.live.judge is not None
                and sim >= RECALL_THRESHOLD
                and (exact or numbers_compatible(n, heard))
            ):
                out.append((cid, sim, exact))
        out.sort(key=lambda p: p[1], reverse=True)
        return out

    async def warm(self) -> None:
        """Embed the prebunked claims before the first sentence, not during it."""
        try:
            await asyncio.to_thread(self._refresh)
        except Exception:
            log.warning("live index warm up failed", exc_info=True)

    async def on_sentence(
        self, sentence: str, heard_at: float | None = None, t_offset: float | None = None
    ) -> None:
        """Every heard line ends in exactly one outcome the user sees: a match, a check
        (checking -> proved/failed) or `skipped` with the reason. Never silence (rev00012
        bug 2: a checkable line got `heard` and then nothing).
        t_offset: second in the source video (replay clips), stored on every live claim
        so the Live page can pop the card at that exact moment of the YouTube player."""
        t0 = heard_at or time.monotonic()
        sentence = sentence.strip()[:MAX_SENTENCE_CHARS]
        if not sentence:
            return
        await self.emit({"type": "heard", "text": sentence})
        try:
            reason = await self._route(sentence, t0, t_offset)
        except Exception:  # one bad line never kills the socket
            log.exception("live line failed")
            reason = "error"
        if reason:
            await self.emit({"type": "skipped", "text": sentence, "reason": reason})

    async def _route(self, sentence: str, t0: float, t_offset: float | None = None) -> str | None:
        """None when the line reached the user, else why it didn't."""
        # Fast path in parallel with the spotter model call: a sentence that is itself a
        # strong match (same numbers, cosine >= instant) shows its card without waiting.
        spot = asyncio.create_task(self._spot(sentence))
        shown = False
        if heuristic_spot(sentence):
            hit, sim = await asyncio.to_thread(self.match, sentence)
            if hit and sim >= self.live.instant and hit not in self._shown:
                shown = bool(await self._push_match(sentence, hit, sim, t0, t_offset))
        claims = await spot
        if not claims and is_country_figure(sentence):
            claims = [sentence]  # deterministic floor under the model spotter
        for text in claims:
            key = text.lower()
            if key in self._seen:  # the speaker repeated it: one card is enough
                continue
            self._seen.add(key)
            shown = await self._handle_claim(text, t0, t_offset) or shown
        if shown:
            return None
        return "repeat" if claims else "not_checkable"

    async def _spot(self, sentence: str) -> list[str]:
        """Model spotting, bounded. A model error or timeout falls back to the heuristic
        (check the whole line), so an outage costs precision, never a dropped claim."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.live.spotter.spot_claims, sentence), SPOT_TIMEOUT_S
            )
        except Exception:
            log.warning("spotter failed, heuristic fallback", exc_info=True)
            return heuristic_spot(sentence)

    async def _handle_claim(self, text: str, t0: float, t_offset: float | None = None) -> bool:
        """True when a card was pushed or a check started; False for a card already shown."""
        store = self.live.deps.store
        hit, sim, repeat = await self._find_match(text)
        if repeat:  # same prebunked claim, already on screen
            return False
        if hit:
            pushed = await self._push_match(text, hit, sim, t0, t_offset)
            if pushed is not None:
                return pushed
        if await self._cold_repeat(text):
            return False
        doc = ClaimDoc(text=text, source=ClaimSource.LIVE, t_offset_s=t_offset)
        cid = await asyncio.to_thread(store.add_claim, self.sid, doc)
        await self.emit({"type": "checking", "claim_id": cid, "text": text, "t": t_offset})
        task = asyncio.create_task(self._cold(cid, text, t0))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _cold_repeat(self, text: str) -> bool:
        """True when this claim, in other words, is already being checked or shown."""
        try:
            [vec] = await asyncio.to_thread(self.live.embedder.embed, [text])
        except Exception:
            log.warning("repeat check embed failed", exc_info=True)
            return False
        heard = numbers(text)
        for prev, pvec, pnum in self._cold_seen:
            sim = cosine(vec, pvec)
            if pnum == heard and sim >= self.live.instant:
                return True
            judge = self.live.judge
            if (
                judge is not None
                and sim >= RECALL_THRESHOLD
                and (pnum == heard or numbers_compatible(pnum, heard))
                and await asyncio.to_thread(judge.same_claim, text, prev)
            ):
                return True
        self._cold_seen.append((text, vec, heard))
        return False

    async def _find_match(self, text: str) -> tuple[str | None, float, bool]:
        """(hit, cosine, already shown). Strong (same numbers, cosine >= instant) wins at
        once; anything else needs the judge, top JUDGE_TOP_K by cosine, first yes wins.
        No judge (tests, stub): the strict cosine decides, as before."""
        store, judge = self.live.deps.store, self.live.judge
        cands = await asyncio.to_thread(self.candidates, text)
        for cid, sim, exact in cands[:JUDGE_TOP_K]:
            if not (exact and sim >= self.live.instant) and judge is not None:
                pre = await asyncio.to_thread(store.get_claim, self.sid, cid)
                same = pre is not None and await asyncio.to_thread(judge.same_claim, text, pre.text)
                log.info(
                    "judge",
                    extra={"fields": {"sim": round(sim, 3), "exact": exact, "same": same}},
                )
                if not same:
                    continue
            return (None, sim, True) if cid in self._shown else (cid, sim, False)
        return None, 0.0, False

    async def _push_match(
        self, text: str, hit: str, sim: float, t0: float, t_offset: float | None = None
    ) -> bool | None:
        """Store a LIVE claim pointing at the prebunked card and push it. True = pushed,
        False = that card is already on screen (another prebunked claim shares it),
        None = the prebunked claim has no card (cannot happen for indexed claims)."""
        # Firestore calls run off the event loop: a slow write must never stall the
        # socket (prod 16 Oct: keepalive ping timeout while a brief was prebunking).
        store = self.live.deps.store
        pre = await asyncio.to_thread(store.get_claim, self.sid, hit)
        if pre is None or not pre.card_id:
            return None
        self._shown.add(hit)
        if pre.card_id in self._cards:
            return False
        self._cards.add(pre.card_id)
        latency = int((time.monotonic() - t0) * 1000)
        doc = ClaimDoc(
            text=text,
            source=ClaimSource.LIVE,
            status=ClaimStatus.PROVED,
            card_id=pre.card_id,
            verdict=pre.verdict,
            matched_claim_id=hit,
            latency_ms=latency,
            t_offset_s=t_offset,
        )
        cid = await asyncio.to_thread(store.add_claim, self.sid, doc)
        await self.emit(
            {
                "type": "match",
                "claim_id": cid,
                "text": text,
                "card_id": pre.card_id,
                "verdict": pre.verdict,
                "similarity": round(sim, 3),
                "latency_ms": latency,
                "t": t_offset,
            }
        )
        self._notify(pre.card_id, pre.verdict, text, t_offset)
        return True

    async def _cold(self, cid: str, text: str, t0: float) -> None:
        trace = Trace()
        loop = asyncio.get_running_loop()
        try:
            card_id = await loop.run_in_executor(
                _COLD_POOL, lambda: verify_claim(self.sid, cid, self.live.deps, trace, True)
            )
        except Exception:  # a "checking" tile must always resolve
            log.exception("live cold check failed")
            card_id = None
            trace.reason = trace.reason or "error"
        latency = int((time.monotonic() - t0) * 1000)
        if card_id is None:
            await self.emit(
                {
                    "type": "failed",
                    "claim_id": cid,
                    "text": text,
                    "reason": trace.reason or "no_proof",
                    "stages": trace.stages,
                    "latency_ms": latency,
                }
            )
            return
        store = self.live.deps.store
        claim = await asyncio.to_thread(store.get_claim, self.sid, cid)
        await asyncio.to_thread(store.update_claim, self.sid, cid, latency_ms=latency)
        repeat = card_id in self._cards  # the claim cache gave back a card already shown
        self._cards.add(card_id)
        await self.emit(
            {
                "type": "proved",
                "claim_id": cid,
                "text": text,
                "card_id": card_id,
                "verdict": claim.verdict if claim else None,
                "latency_ms": latency,
                "stages": trace.stages,
                "facts": claim.fact_ids if claim else [],
                "repeat": repeat,
            }
        )
        if claim is not None and not repeat:
            self._notify(card_id, claim.verdict, text, claim.t_offset_s)

    def _notify(self, card_id: str, verdict: Any, text: str, t: float | None = None) -> None:
        """Telegram alert off the hot path: the feed never waits on the Bot API."""
        if self.alert is None:
            return
        alert = self.alert

        async def run() -> None:
            try:
                await asyncio.to_thread(alert, self.sid, card_id, verdict, text, t)
            except Exception:
                log.warning("telegram alert failed", exc_info=True)

        task = asyncio.create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


# ---------- transcription ----------


class Transcriber(Protocol):
    async def run(
        self,
        audio: asyncio.Queue[bytes | None],
        on_final: Callable[[str], Awaitable[None]],
        vocabulary: Sequence[str] = (),
    ) -> None: ...


MAX_VOCABULARY = 100  # docs: up to 1,000 phrases, best results with up to 100
_PROPER = re.compile(r"\b[A-Z][\w-]{2,}|[\u0900-\u0DFF]{4,}")  # 4+: skips में, हैं


def vocabulary_for(claims: Sequence[str]) -> list[str]:
    """Speech biasing terms from the prebunked claims: names, acronyms, Indic words.
    Sentence initial capitals are kept too; a few common words cost nothing here."""
    seen: dict[str, None] = {}
    for c in claims:
        for w in _PROPER.findall(c):
            seen.setdefault(w, None)
    return list(seen)[:MAX_VOCABULARY]


def final_text(server_content: Any) -> str:
    """input_transcription is already the finalized segment (emitted on pause / turn end);
    interim_input_transcription is speculative and never checked. Docs:
    https://ai.google.dev/gemini-api/docs/live-api/live-transcribe"""
    tr = getattr(server_content, "input_transcription", None)
    return (getattr(tr, "text", None) or "").strip()


class GeminiLiveTranscriber:  # pragma: no cover - needs a GCP project and live audio
    """Relays PCM16 16 kHz chunks to the Gemini Live API; final transcripts -> on_final.

    Keys never reach the browser: the websocket ends here and the service account talks
    to Vertex. A Live session is capped at 10 minutes, so we reconnect transparently.
    """

    def __init__(self, project: str, location: str, model: str) -> None:
        from google import genai

        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.model = model

    async def run(
        self,
        audio: asyncio.Queue[bytes | None],
        on_final: Callable[[str], Awaitable[None]],
        vocabulary: Sequence[str] = (),
    ) -> None:
        from google.genai import types

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            # [] = auto language detection incl. mid sentence Hindi / English code mixing.
            input_audio_transcription=types.AudioTranscriptionConfig(
                language_codes=[], custom_vocabulary=list(vocabulary) or None
            ),
        )
        done = False
        while not done:
            async with self.client.aio.live.connect(model=self.model, config=config) as s:

                async def pump() -> bool:
                    while True:
                        chunk = await audio.get()
                        if chunk is None:
                            await s.send_realtime_input(audio_stream_end=True)
                            return True
                        await s.send_realtime_input(
                            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                        )

                async def recv() -> None:
                    async for r in s.receive():
                        if text := final_text(r.server_content):
                            await on_final(text)

                pump_t = asyncio.create_task(pump())
                recv_t = asyncio.create_task(recv())
                finished, _ = await asyncio.wait(
                    {pump_t, recv_t}, return_when=asyncio.FIRST_COMPLETED
                )
                if pump_t in finished:
                    done = pump_t.result()
                    await asyncio.wait_for(recv_t, timeout=10)
                else:  # server closed (10 min cap or error): reconnect, keep the queue
                    pump_t.cancel()
                    log.info("live session closed by server, reconnecting")
