"""Research fact bank: the accuracy layer (Team lead, voice note, 16 Oct 2026).

Before any line is heard, research 50-100 facts for the topic + speaker, each with the
page that states it. A fact is KEPT only when that page was fetched and a passage on it
backs the statement (same proof scoring as a card, plus the figure must be on the page).
The bank is stored once per topic + speaker (fact_banks/{key}) and reused by later
sessions until it is MAX_AGE old.

During a check the line is ruled against the bank first: the judge picks the facts that
decide it (same measure, place and period) and the card cites those facts' pages. The
predicted CLAIM bank matched 0 of 6 spoken lines on replay 7dhIVHRKhvo because people
word a claim differently from the prediction; a fact decides a line however it is worded.
No deciding fact -> the web check runs exactly as before.

Docs: https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search
      https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.govsources import search_hint
from app.officialdata import is_worldbank
from app.officialdata import render as render_official
from app.proof import Fetcher, best_match, extract_text
from app.schemas import Fact, FactBankDoc, Verdict
from app.store import Store

log = logging.getLogger("proofcard.facts")

FACTS_PROMPT_VERSION = "2026-10-16.f1"
ANGLES = 10
FACTS_PER_ANGLE = 12
MAX_FACTS = 100
MIN_REUSE = 20  # a stored bank smaller than this is researched again
MAX_AGE = timedelta(days=7)  # statistics get revised; a week old bank is rebuilt
FACT_SUPPORT = 0.45  # passage score a source page needs to keep a fact (cards: 0.35)
URLS_PER_FACT = 3
VERIFY_WORKERS = 8
RULE_FACTS_MAX = 3

# Hosts whose figures are official records: governments, central banks, parliaments and
# the international statistical bodies. Shown as "official" in the bank export.
_OFFICIAL_SUFFIXES = (".gov", ".gov.in", ".nic.in", ".gov.uk", ".gc.ca", ".gov.au", ".int")
_OFFICIAL_HOSTS = frozenset(
    {
        "rbi.org.in",
        "sansad.in",
        "worldbank.org",
        "imf.org",
        "un.org",
        "oecd.org",
        "wto.org",
        "adb.org",
        "europa.eu",
    }
)
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def official(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return host.endswith(_OFFICIAL_SUFFIXES) or any(
        host == h or host.endswith("." + h) for h in _OFFICIAL_HOSTS
    )


def bank_key(topic: str, speaker: str) -> str:
    """Stable doc id for topic + speaker: readable slug + hash (Hindi topics: hash only)."""

    def norm(s: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", s.lower()))

    t, sp = norm(topic), norm(speaker)
    basis = f"{t}|{sp}" if t else f"{' '.join(topic.lower().split())}|{sp}"
    digest = hashlib.sha256(basis.encode()).hexdigest()[:12]
    slug = "-".join(t.split()[:8] + sp.split()[:3])[:100]
    return f"{slug}-{digest}" if slug else digest


def _numbers(text: str) -> set[str]:
    return {m.replace(",", "") for m in _NUM.findall(text)}


@dataclass(frozen=True)
class Candidate:
    """A researched fact before its source is checked."""

    statement: str
    value: str = ""
    as_of: str = ""
    angle: str = ""
    trigger: str = ""
    urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ruling:
    verdict: Verdict
    fact_ids: list[int]
    explanation: str
    claim_en: str = ""


class FactDesk(Protocol):
    def angles(self, topic: str, speaker: str, k: int) -> list[str]: ...
    def research(self, topic: str, speaker: str, angle: str, n: int) -> list[Candidate]: ...
    def rule(self, claim: str, facts: list[Fact]) -> Ruling | None: ...


# ---------- building the bank ----------


def verify_candidate(c: Candidate, fetcher: Fetcher) -> tuple[str, str, float] | None:
    """(page url, passage, score) of the first source that states the fact, else None.
    The figure itself must be in the passage: an on topic page with another number is not
    the source of this fact."""
    want = _numbers(c.value) or _numbers(c.statement)
    for url in list(dict.fromkeys(u for u in c.urls if u.startswith("http")))[:URLS_PER_FACT]:
        try:
            fetched = fetcher.fetch(url)
        except Exception as exc:  # FetchError, timeouts: try the next source
            log.info("fact source skipped", extra={"fields": {"reason": type(exc).__name__}})
            continue
        if is_worldbank(fetched.final_url):
            text = render_official(fetched.body)
        else:
            text = extract_text(fetched.body, fetched.content_type)
        if not text:
            continue
        m = best_match(c.statement, text)
        if m.score < FACT_SUPPORT or not m.passage:
            continue
        if want and not (want & _numbers(m.passage)):
            continue
        return fetched.final_url, m.passage, m.score
    return None


def _dedupe(cands: Iterable[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in cands:
        k = " ".join(re.findall(r"\w+", c.statement.lower()))
        if c.statement.strip() and k not in seen:
            seen.add(k)
            out.append(c)
    return out


def build_bank(
    topic: str, speaker: str, desk: FactDesk, fetcher: Fetcher, research_topic: str = ""
) -> FactBankDoc:
    """Plan angles, research them in parallel, keep only source verified facts.
    Official facts first, then the best supported, capped at MAX_FACTS."""
    about = research_topic or topic
    try:
        angles = desk.angles(about, speaker, ANGLES) or [topic]
    except Exception:
        log.warning("fact angles failed, researching the topic as one angle", exc_info=True)
        angles = [topic]

    def one(angle: str) -> list[Candidate]:
        try:
            return desk.research(about, speaker, angle, FACTS_PER_ANGLE)
        except Exception:
            log.warning("fact research failed for one angle", exc_info=True)
            return []

    with ThreadPoolExecutor(max_workers=max(1, len(angles)), thread_name_prefix="research") as p:
        cands = _dedupe(c for batch in p.map(one, angles) for c in batch)
    with ThreadPoolExecutor(max_workers=VERIFY_WORKERS, thread_name_prefix="factsrc") as p:
        checked = list(p.map(lambda c: verify_candidate(c, fetcher), cands))
    kept = [(c, v) for c, v in zip(cands, checked, strict=True) if v is not None]
    kept.sort(key=lambda cv: (not official(cv[1][0]), -cv[1][2]))
    facts = [
        Fact(
            id=i,
            statement=c.statement[:4_000],
            value=c.value[:200],
            as_of=c.as_of[:100],
            angle=c.angle[:200],
            trigger=c.trigger[:1_000],
            source_url=url,
            passage=passage[:4_000],
            support=min(1.0, round(score, 3)),
            official=official(url),
        )
        for i, (c, (url, passage, score)) in enumerate(kept[:MAX_FACTS])
    ]
    log.info(
        "fact bank built",
        extra={
            "fields": {
                "angles": len(angles),
                "researched": len(cands),
                "kept": len(facts),
                "official": sum(f.official for f in facts),
            }
        },
    )
    return FactBankDoc(
        key=bank_key(topic, speaker),
        topic=topic[:500],
        speaker=speaker,
        prompt_version=FACTS_PROMPT_VERSION,
        researched=len(cands),
        facts=facts,
    )


def ensure_bank(
    store: Store,
    desk: FactDesk,
    fetcher: Fetcher,
    topic: str,
    speaker: str,
    research_topic: str = "",
    now: datetime | None = None,
) -> str | None:
    """Key of a usable bank for topic + speaker: the stored one when fresh and big enough,
    else a newly researched one. None when research kept no fact at all."""
    key = bank_key(topic, speaker)
    now = now or datetime.now(UTC)
    old = store.get_fact_bank(key)
    if old is not None and len(old.facts) >= MIN_REUSE and now - old.created_at < MAX_AGE:
        log.info("fact bank reused", extra={"fields": {"facts": len(old.facts)}})
        return key
    bank = build_bank(topic, speaker, desk, fetcher, research_topic)
    if not bank.facts:
        return key if old is not None and old.facts else None
    store.put_fact_bank(bank)
    return key


def checked_ruling(r: Ruling | None, facts: list[Fact]) -> Ruling | None:
    """Drop unknown ids and UNVERIFIABLE: the bank decides a line or stays out of it."""
    if r is None or r.verdict == Verdict.UNVERIFIABLE:
        return None
    ids = {f.id for f in facts}
    keep = [i for i in dict.fromkeys(r.fact_ids) if i in ids][:RULE_FACTS_MAX]
    return Ruling(r.verdict, keep, r.explanation, r.claim_en) if keep else None


# ---------- Vertex implementation ----------

ANGLES_PROMPT = """You plan research for a fact checking newsroom before a broadcast.
Topic: {topic}
Speaker: {speaker}
List {k} distinct research angles a fact checker must have figures on file for, covering
what this speaker is most likely to cite on this topic: official statistics, rankings,
budget and scheme numbers, dates, international comparisons. Short noun phrases."""

RESEARCH_PROMPT = """You are the research desk of a fact checking newsroom.
Topic: {topic}
Speaker: {speaker}
Angle: {angle}
Using Google Search, collect {n} distinct, verifiable facts for this angle: the latest
official figure for each measure, plus the earlier figures a speaker is likely to compare
against. {hint}
For each fact return:
- statement: ONE self contained English sentence with the figure, the place and the period
  (e.g. "India's real GDP grew 8.2% in FY2023-24, per MoSPI's provisional estimates.")
- value: the figure exactly as the source writes it
- as_of: the period or date the figure is for
- source_url: the exact page that states this figure. Official statistics pages, central
  banks, parliaments, IMF / World Bank first, then established newsrooms. Never a blog,
  law firm, SEO or content farm page.
- trigger: one line the speaker could say on air that this fact decides (accurate,
  exaggerated or wrong)
Return ONLY a JSON array of objects with exactly those keys. No prose, no markdown."""

RULE_PROMPT = """A line was just said on air. Below is a researched fact bank; every fact was
checked against its source page. Decide whether some facts DECIDE the line: same subject,
same measure, same place and the same period (or the line names no period and the fact is
the latest figure). Same topic is NOT enough: GDP growth vs GDP size, rank vs growth rate,
state vs country, a forecast vs an actual = does not decide.
Speaker line (English, Hindi or Hinglish): "{claim}"
Facts:
{facts}
verdict: TRUE = the facts confirm the line; FALSE = they contradict its figure, ranking or
date; MISLEADING = the figure is right but the framing, period or comparison is wrong.
fact_ids: the 1 to 3 facts that decide it. explanation: two sentences, cite the figures.
claim_en: the line restated in English. decided=false when no fact decides it."""

_ANGLES_SCHEMA = {"type": "ARRAY", "items": {"type": "STRING"}}
_RULE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "decided": {"type": "BOOLEAN"},
        "verdict": {"type": "STRING", "enum": ["TRUE", "MISLEADING", "FALSE"]},
        "fact_ids": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "explanation": {"type": "STRING"},
        "claim_en": {"type": "STRING"},
    },
    "required": ["decided"],
}
RESEARCH_TIMEOUT_S = 150.0


def parse_json_list(raw: str) -> list[Any]:
    """The grounded answer is plain text (search + response schema is not relied on): take
    the outermost [...] block, tolerate ```json fences. Anything else -> []."""
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"\w+", s.lower()) if len(w) > 2}


def chunk_urls_for(statement: str, resp: Any) -> list[str]:
    """Grounding chunks whose supported segment overlaps this statement (word Jaccard
    >= 0.5), best confidence first. Backup sources when the model's own URL is wrong."""
    try:
        meta = resp.candidates[0].grounding_metadata
        chunks = list(meta.grounding_chunks or [])
        supports = list(meta.grounding_supports or [])
    except (AttributeError, IndexError, TypeError):
        return []
    want = _words(statement)
    scored: list[tuple[float, str]] = []
    for sup in supports:
        seg = _words(getattr(getattr(sup, "segment", None), "text", "") or "")
        if not seg or not want or len(seg & want) / len(seg | want) < 0.5:
            continue
        confs = list(getattr(sup, "confidence_scores", None) or [])
        for pos, idx in enumerate(getattr(sup, "grounding_chunk_indices", None) or []):
            uri = (
                getattr(getattr(chunks[idx], "web", None), "uri", None)
                if idx < len(chunks)
                else None
            )
            if uri:
                scored.append((float(confs[pos]) if pos < len(confs) else 0.0, uri))
    scored.sort(reverse=True)
    return list(dict.fromkeys(u for _, u in scored))


def candidates_from(raw: str, resp: Any, angle: str) -> list[Candidate]:
    out: list[Candidate] = []
    for item in parse_json_list(raw):
        if not isinstance(item, dict) or not str(item.get("statement", "")).strip():
            continue
        st = str(item["statement"]).strip()
        own = str(item.get("source_url", "")).strip()
        out.append(
            Candidate(
                statement=st,
                value=str(item.get("value", "")).strip(),
                as_of=str(item.get("as_of", "")).strip(),
                angle=angle,
                trigger=str(item.get("trigger", "")).strip(),
                urls=tuple(([own] if own else []) + chunk_urls_for(st, resp)),
            )
        )
    return out


def render_facts(facts: list[Fact]) -> str:
    return "\n".join(
        f"[{f.id}] {f.statement}" + (f" (as of {f.as_of})" if f.as_of else "") for f in facts
    )


class VertexFactDesk:  # pragma: no cover - needs a GCP project
    def __init__(self, project: str, location: str, model: str) -> None:
        from app.model import GENERATE_TIMEOUT_S, vertex_client

        self.client = vertex_client(project, location, GENERATE_TIMEOUT_S)
        self.research_client = vertex_client(project, location, RESEARCH_TIMEOUT_S)
        self.model = model

    def angles(self, topic: str, speaker: str, k: int) -> list[str]:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=ANGLES_PROMPT.format(topic=topic, speaker=speaker or "unknown", k=k),
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
                response_schema=_ANGLES_SCHEMA,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            ),
        )
        return [str(a)[:200] for a in json.loads(resp.text or "[]") if str(a).strip()][:k]

    def research(self, topic: str, speaker: str, angle: str, n: int) -> list[Candidate]:
        from google.genai import types

        hint = search_hint(speaker, f"{topic} {angle}")
        resp = self.research_client.models.generate_content(
            model=self.model,
            contents=RESEARCH_PROMPT.format(
                topic=topic, speaker=speaker or "unknown", angle=angle, n=n, hint=hint
            ),
            config=types.GenerateContentConfig(
                temperature=0.0, tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        return candidates_from(resp.text or "", resp, angle)

    def rule(self, claim: str, facts: list[Fact]) -> Ruling | None:
        from google.genai import types

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=RULE_PROMPT.format(claim=claim, facts=render_facts(facts)),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=_RULE_SCHEMA,
                ),
            )
            data = json.loads(resp.text or "{}")
        except Exception:
            log.warning("fact ruling failed, web check runs", exc_info=True)
            return None
        if not data.get("decided") or data.get("verdict") not in ("TRUE", "MISLEADING", "FALSE"):
            return None
        return checked_ruling(
            Ruling(
                Verdict(data["verdict"]),
                [int(i) for i in data.get("fact_ids") or [] if isinstance(i, int)],
                str(data.get("explanation", "")).strip()[:4_000] or "Decided by the fact bank.",
                str(data.get("claim_en", "")).strip(),
            ),
            facts,
        )
