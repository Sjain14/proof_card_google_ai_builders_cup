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
import time
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.govsources import country_for, search_hint
from app.officialdata import PackRow, human, is_worldbank, pack_countries, pack_rows, pack_urls
from app.officialdata import render as render_official
from app.proof import Fetcher, best_match, extract_text
from app.schemas import Fact, FactBankDoc, Verdict
from app.store import Store

log = logging.getLogger("proofcard.facts")

FACTS_PROMPT_VERSION = "2026-10-16.f3"
ANGLES = 12  # 10 angles x 12 = 108 researched, 10 kept (run 5); parallel, no extra time
FACTS_PER_ANGLE = 8  # fewer per call: grounded research timed out at 12 (run 6: 10/12 empty)
MAX_FACTS = 100
# Hard wall clock budgets: a slow angle or page costs its facts, never the brief. Run 6
# (16 Oct): research 449 s (150 s timeout x 3 retries), brief 1431 s.
RESEARCH_BUDGET_S = 130.0
VERIFY_BUDGET_S = 90.0
PACK_BUDGET_S = 30.0  # official data pack: 12 API reads in parallel
MIN_REUSE = 20  # a stored bank smaller than this is researched again
MAX_AGE = timedelta(days=7)  # statistics get revised; a week old bank is rebuilt
# Passage score a source page needs to keep a fact: the card gate, plus the figure itself
# must be on the page. 0.45 kept 0 facts on prod (16 Oct): a fact sentence states the
# figure AND its period, and any number missing from a window caps it at 0.5.
FACT_SUPPORT = 0.35
SEARCH_SUPPORT = 0.35  # a search-grounded fact never outranks one read on its page
SAMPLES = 20
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


_WAYBACK = re.compile(r"^https?://web\.archive\.org/web/\d{1,14}(?:id_)?/(https?://.+)$")


def archived_original(url: str) -> str:
    """The page a Wayback Machine copy is of (web.archive.org/web/<ts>id_/<url>), else url."""
    m = _WAYBACK.match(url)
    return m.group(1) if m else url


def wayback_url(url: str, said_on: str = "") -> str:
    """Raw (id_) Wayback copy nearest the speech day; the latest copy when undated.
    Docs: https://archive.org/developers/wayback-cdx-server.html (URL form + id_ flag)."""
    stamp = said_on.replace("-", "") or "2"
    return f"https://web.archive.org/web/{stamp}id_/{url}"


def official(url: str) -> bool:
    """An official record, also when read through its Wayback Machine copy."""
    host = (urlsplit(archived_original(url)).hostname or "").lower().removeprefix("www.")
    return host.endswith(_OFFICIAL_SUFFIXES) or any(
        host == h or host.endswith("." + h) for h in _OFFICIAL_HOSTS
    )


def bank_key(topic: str, speaker: str, said_on: str = "") -> str:
    """Stable doc id for topic + speaker (+ the date the speech was given): readable slug +
    hash (Hindi topics: hash only). A 2022 speech gets its own bank: the 2026 figures
    decided 0 lines of the 2022 Sitharaman replay (run 5, 16 Oct)."""

    def norm(s: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", s.lower()))

    t, sp = norm(topic), norm(speaker)
    basis = f"{t}|{sp}" if t else f"{' '.join(topic.lower().split())}|{sp}"
    if said_on:
        basis += f"|{said_on}"
    digest = hashlib.sha256(basis.encode()).hexdigest()[:12]
    slug = "-".join(t.split()[:8] + sp.split()[:3])[: 90 if said_on else 100]
    if said_on and slug:
        slug += "-d" + said_on.replace("-", "")
    return f"{slug}-{digest}" if slug else digest


def _numbers(text: str) -> set[str]:
    return {m.replace(",", "") for m in _NUM.findall(text)}


# Attribution tails a source page never repeats word for word ("..., according to
# provisional estimates released by MoSPI"). They capped real matches at 0.04-0.27 on
# mospi.gov.in / rbi.org.in pages that state the figure (run 5: 35 low_support drops).
_ATTRIBUTION = re.compile(
    r"(?:[,;]\s*(?:according to|as per|per(?!\s+cent)|says|said|reported by|released by|"
    r"data from)|\s+(?:according to|as per))\b.*$",
    re.IGNORECASE,
)


def core_statement(statement: str) -> str:
    """The fact without its attribution tail; the figure and period stay."""
    core = _ATTRIBUTION.sub("", statement.strip()).rstrip(" .,;")
    return core if len(core.split()) >= 4 else statement


@dataclass(frozen=True)
class Candidate:
    """A researched fact before its source is checked."""

    statement: str
    value: str = ""
    as_of: str = ""
    angle: str = ""
    trigger: str = ""
    urls: tuple[str, ...] = ()
    # Hosts of the Google Search grounding chunks that back this statement (chunk_hosts_for).
    grounded: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ruling:
    verdict: Verdict
    fact_ids: list[int]
    explanation: str
    claim_en: str = ""


class FactDesk(Protocol):
    def angles(self, topic: str, speaker: str, k: int, said_on: str = "") -> list[str]: ...
    def research(
        self, topic: str, speaker: str, angle: str, n: int, said_on: str = ""
    ) -> list[Candidate]: ...
    def rule(self, claim: str, facts: list[Fact], said_on: str = "") -> Ruling | None: ...


# ---------- building the bank ----------


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _blocked(exc: Exception) -> bool:
    """The server refused us (WAF / geo block / rate limit), not that the page is missing."""
    msg = str(exc) or type(exc).__name__
    return any(k in msg for k in ("403", "401", "429", "Timeout", "Connect"))


def _read(c: Candidate, fetcher: Fetcher, url: str) -> tuple[str, str, float] | str:
    """(final_url, passage, score) when this page states the fact, else the drop reason.
    Raises on fetch failure."""
    want = _numbers(c.value) or _numbers(c.statement)
    fetched = fetcher.fetch(url)
    try:
        if is_worldbank(fetched.final_url):
            text = render_official(fetched.body)
        else:
            text = extract_text(fetched.body, fetched.content_type)
        queries = dict.fromkeys([c.statement, core_statement(c.statement)])
        m = max((best_match(q, text) for q in queries), key=lambda x: x.score) if text else None
    except Exception as exc:  # a broken PDF or page never sinks the whole bank
        return f"parse:{type(exc).__name__}"
    if m is None:
        return "no_text"
    if m.score < FACT_SUPPORT or not m.passage:
        return f"low_support:{m.score:.2f}"
    if want and not (want & _numbers(m.passage)):
        return "figure_missing"
    return fetched.final_url, m.passage, m.score


def verify_candidate(
    c: Candidate, fetcher: Fetcher, said_on: str = ""
) -> tuple[str, str, float, str] | str:
    """(url, passage, score, checked) of the first source that states the fact, else the
    reason the last source failed. checked="page": we fetched the page and the figure is on
    it (an on topic page with another number is not the source of this fact).
    checked="search": the official page blocks our server (pib.gov.in 403s every Cloud Run
    request), but Google Search grounding backed this exact statement from that same official
    host; the figure is still required in the statement. Anything else is dropped."""
    want = _numbers(c.value) or _numbers(c.statement)
    reason = "no_url"
    blocked: list[str] = []
    for url in list(dict.fromkeys(u for u in c.urls if u.startswith("http")))[:URLS_PER_FACT]:
        try:
            got = _read(c, fetcher, url)
        except Exception as exc:  # FetchError, timeouts: try the next source
            reason = f"fetch:{str(exc)[:40] or type(exc).__name__}"
            if official(url) and _blocked(exc):
                blocked.append(url)
            continue
        if isinstance(got, str):
            reason = got
            continue
        return got[0], got[1], got[2], "page"
    # An official page that refuses our server (pib.gov.in 403s every Cloud Run request):
    # read the same page from its Wayback Machine copy nearest the speech day. The card
    # cites the archive URL, which names the official original.
    for url in blocked:
        try:
            got = _read(c, fetcher, wayback_url(url, said_on))
        except Exception as exc:
            reason = f"fetch:archive {str(exc)[:30] or type(exc).__name__}"
            continue
        if isinstance(got, str):
            reason = got
            continue
        return got[0], got[1], got[2], "archive"
    if reason.startswith("fetch:") and want:
        grounded = {h.removeprefix("www.") for h in c.grounded}
        for url in blocked:
            if _host(url) in grounded:
                note = f"Google Search grounding, {_host(url)} (page blocks our server)"
                return url, f"{c.statement} [{note}]", SEARCH_SUPPORT, "search"
    return reason


def _dedupe(cands: Iterable[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in cands:
        k = " ".join(re.findall(r"\w+", c.statement.lower()))
        if c.statement.strip() and k not in seen:
            seen.add(k)
            out.append(c)
    return out


def official_pack(about: str, speaker: str, fetcher: Fetcher, said_on: str = "") -> list[PackRow]:
    """Headline World Bank series for the speaker's country and its comparators, up to
    the speech year. Each unreadable series costs only itself."""
    codes = pack_countries(country_for(speaker, about), f"{about} {speaker}")

    def one(url: str) -> list[PackRow]:
        try:
            return pack_rows(fetcher.fetch(url).body, url)
        except Exception:
            return []

    urls = pack_urls(codes, said_on, datetime.now(UTC).year)
    none: list[PackRow] = []
    return [
        r for rows in _within(one, urls, len(urls), PACK_BUDGET_S - 2, none, "wb") for r in rows
    ]


def pack_fact(i: int, r: PackRow) -> Fact:
    figure = human(r.value)
    line = f"{r.country}: {r.metric}, {r.year}: {figure}"
    return Fact(
        id=i,
        statement=f"{r.country}'s {r.metric} was {figure} in {r.year} (World Bank).",
        value=figure,
        as_of=r.year,
        angle="official statistics (World Bank)",
        trigger=f"a claim about {r.country}'s {r.metric.split(' (')[0].lower()} around {r.year}",
        source_url=r.url,
        passage=f"Source: World Bank Open Data, official series.\n{line}",
        support=1.0,
        official=True,
        checked="page",
    )


def _within[T, R](
    fn: Callable[[T], R], items: list[T], workers: int, budget: float, late: R, name: str
) -> list[R]:
    """fn over items in parallel; whatever hasn't finished after budget seconds counts as
    `late` and is abandoned (its thread ends on its own timeout; the result is ignored)."""
    if not items:
        return []
    pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix=name)
    try:
        futs = [pool.submit(fn, x) for x in items]
        wait(futs, timeout=budget)
        out: list[R] = []
        for f in futs:
            if f.done() and not f.cancelled() and f.exception() is None:
                out.append(f.result())
            else:
                out.append(late)
        return out
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def build_bank(
    topic: str,
    speaker: str,
    desk: FactDesk,
    fetcher: Fetcher,
    research_topic: str = "",
    said_on: str = "",
    research_budget: float = RESEARCH_BUDGET_S,
    verify_budget: float = VERIFY_BUDGET_S,
) -> FactBankDoc:
    """Plan angles, research them in parallel, keep only source verified facts.
    Official facts first, then the best supported, capped at MAX_FACTS. said_on (ISO date
    the speech was given) anchors research to the figures that were current THEN."""
    about = research_topic or topic
    t0 = time.monotonic()
    try:
        angles = desk.angles(about, speaker, ANGLES, said_on) or [topic]
    except Exception:
        log.warning("fact angles failed, researching the topic as one angle", exc_info=True)
        angles = [topic]

    def one(angle: str) -> list[Candidate]:
        try:
            return desk.research(about, speaker, angle, FACTS_PER_ANGLE, said_on)
        except Exception:
            log.warning("fact research failed for one angle", exc_info=True)
            return []

    # The official data pack is read while the angles are researched (it needs no model).
    side = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pack")
    packing = side.submit(official_pack, about, speaker, fetcher, said_on)
    side.shutdown(wait=False)
    t1 = time.monotonic()
    none: list[Candidate] = []
    batches = _within(one, angles, len(angles), research_budget, none, "research")
    cands = _dedupe(c for batch in batches for c in batch)
    t2 = time.monotonic()
    checked: list[tuple[str, str, float, str] | str] = _within(
        lambda c: verify_candidate(c, fetcher, said_on),
        cands,
        VERIFY_WORKERS,
        verify_budget,
        "timeout: verify budget",
        "factsrc",
    )
    t3 = time.monotonic()
    kept = [(c, v) for c, v in zip(cands, checked, strict=True) if not isinstance(v, str)]
    reasons = Counter(v.split(":")[0] for v in checked if isinstance(v, str))
    samples = [
        f"{v} · {urlsplit(c.urls[0]).hostname if c.urls else '-'} · {c.statement[:160]}"
        for c, v in zip(cands, checked, strict=True)
        if isinstance(v, str)
    ][:SAMPLES]
    stats: dict[str, float] = {
        "angles": len(angles),
        "angles_empty": sum(not b for b in batches),
        "angles_s": round(t1 - t0, 1),
        "research_s": round(t2 - t1, 1),
        "verify_s": round(t3 - t2, 1),
        **{f"drop_{k}": n for k, n in reasons.items()},
    }
    kept.sort(key=lambda cv: (not official(cv[1][0]), cv[1][3] == "search", -cv[1][2]))
    facts: list[Fact] = []
    stats["kept_search"] = sum(v[3] == "search" for _, v in kept)
    stats["kept_archive"] = sum(v[3] == "archive" for _, v in kept)
    for c, (url, passage, score, how) in kept:
        if len(facts) >= MAX_FACTS:
            break
        try:
            facts.append(
                Fact(
                    id=len(facts),
                    statement=c.statement[:4_000],
                    value=c.value[:200],
                    as_of=c.as_of[:100],
                    angle=c.angle[:200],
                    trigger=c.trigger[:1_000],
                    source_url=url,
                    passage=passage[:4_000],
                    support=min(1.0, round(score, 3)),
                    official=official(url),
                    checked=how,
                )
            )
        except ValueError:  # pydantic ValidationError: an odd URL or empty field
            stats["drop_invalid"] = stats.get("drop_invalid", 0) + 1
    try:
        rows = packing.result(timeout=PACK_BUDGET_S)
    except Exception:
        log.warning("official data pack failed", exc_info=True)
        rows = []
    stats["kept_pack"] = 0
    for r in rows:
        if len(facts) >= MAX_FACTS:
            break
        facts.append(pack_fact(len(facts), r))
        stats["kept_pack"] += 1
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
        key=bank_key(topic, speaker, said_on),
        topic=topic[:500],
        speaker=speaker,
        said_on=said_on,
        prompt_version=FACTS_PROMPT_VERSION,
        researched=len(cands),
        facts=facts,
        stats=stats,
        samples=samples,
    )


def ensure_bank(
    store: Store,
    desk: FactDesk,
    fetcher: Fetcher,
    topic: str,
    speaker: str,
    research_topic: str = "",
    now: datetime | None = None,
    said_on: str = "",
) -> str | None:
    """Key of a usable bank for topic + speaker: the stored one when fresh and big enough,
    else a newly researched one (stored even when empty, for its diagnostics)."""
    key = bank_key(topic, speaker, said_on)
    now = now or datetime.now(UTC)
    old = store.get_fact_bank(key)
    if old is not None and len(old.facts) >= MIN_REUSE and now - old.created_at < MAX_AGE:
        log.info("fact bank reused", extra={"fields": {"facts": len(old.facts)}})
        return key
    bank = build_bank(topic, speaker, desk, fetcher, research_topic, said_on)
    if not bank.facts and old is not None and old.facts:
        return key  # a failed rebuild never replaces facts we already verified
    # An empty bank is stored too: its stats and samples say why research kept nothing.
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
{when}
List {k} distinct research angles a fact checker must have figures on file for, covering
what this speaker is most likely to cite on this topic: official statistics, rankings,
budget and scheme numbers, dates, international comparisons. Short noun phrases."""

RESEARCH_PROMPT = """You are the research desk of a fact checking newsroom.
Topic: {topic}
Speaker: {speaker}
Angle: {angle}
{when}
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
  law firm, SEO or content farm page. pib.gov.in pages cannot be opened by our checker:
  for Indian figures cite the issuing body's own page or PDF (mospi.gov.in press release,
  rbi.org.in, dea.gov.in, indiabudget.gov.in, data.gov.in) instead of the PIB copy.
- trigger: one line the speaker could say on air that this fact decides (accurate,
  exaggerated or wrong)
Return ONLY a JSON array of objects with exactly those keys. No prose, no markdown."""

RULE_PROMPT = """A line was just said on air. Below is a researched fact bank; every fact was
checked against its source page (or, marked [search], backed by Google Search on an official
page that blocks our checker). Decide whether some facts DECIDE the line: same subject,
same measure, same place and the same period (or the line names no period and the fact is
the latest figure). Same topic is NOT enough: GDP growth vs GDP size, rank vs growth rate,
state vs country, a forecast vs an actual = does not decide.
Speaker line (English, Hindi or Hinglish): "{claim}"
{when}
Facts:
{facts}
verdict: TRUE = the facts confirm the line; FALSE = they contradict its figure, ranking or
date; MISLEADING = the figure is right but the framing, period or comparison is wrong.
fact_ids: the 1 to 3 facts that decide it. explanation: two sentences, cite the figures.
claim_en: the line restated in English. decided=false when no fact decides it."""


def when_line(said_on: str) -> str:
    """Research anchor: the figures a speaker could cite on the day of the speech."""
    if not said_on:
        return "The speech is current: use the latest figures."
    return (
        f"The speech was given on {said_on}. Collect the figures that were the latest "
        f"published ones ON THAT DATE (what the speaker could cite then) and the earlier "
        f"figures they compare against. Never use a figure published after {said_on}."
    )


def said_line(said_on: str) -> str:
    return (
        f"The line was said on {said_on}: 'latest figure' means latest on that date."
        if said_on
        else ""
    )


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
RESEARCH_TIMEOUT_S = 100.0


def parse_json_list(raw: str) -> list[Any]:
    """The grounded answer is plain text (search + response schema is not relied on): the
    first JSON array of objects in it, ignoring prose, ```json fences and trailing text or
    citation marks like [1]. Anything else -> []."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\[", raw):
        try:
            data, _ = dec.raw_decode(raw, m.start())
        except ValueError:
            continue
        if isinstance(data, list) and any(isinstance(d, dict) for d in data):
            return data
    return []


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"\w+", s.lower()) if len(w) > 2}


def chunk_urls_for(statement: str, resp: Any) -> list[str]:
    """Grounding chunk URIs that back this statement, best confidence first. Backup sources
    when the model's own URL is wrong."""
    return list(dict.fromkeys(u for _, u, _ in _support_chunks(statement, resp) if u))


def chunk_hosts_for(statement: str, resp: Any) -> list[str]:
    """Source hosts (chunk web.domain, else web.title when it is a hostname) of the grounding
    chunks that back this statement. The URIs are search redirects, the host is the page."""
    out = []
    for _, _, host in _support_chunks(statement, resp):
        h = host.strip().lower()
        if h and " " not in h and "." in h:
            out.append(h.removeprefix("www."))
    return list(dict.fromkeys(out))


def _support_chunks(statement: str, resp: Any) -> list[tuple[float, str, str]]:
    """(confidence, uri, host) of grounding chunks whose supported segment covers most of
    this statement (>= 60% of its words; a JSON segment also holds keys and other fields,
    so not Jaccard), best confidence first."""
    try:
        meta = resp.candidates[0].grounding_metadata
        chunks = list(meta.grounding_chunks or [])
        supports = list(meta.grounding_supports or [])
    except (AttributeError, IndexError, TypeError):
        return []
    want = _words(statement)
    scored: list[tuple[float, str, str]] = []
    for sup in supports:
        seg = _words(getattr(getattr(sup, "segment", None), "text", "") or "")
        if not seg or not want or len(seg & want) / len(want) < 0.6:
            continue
        confs = list(getattr(sup, "confidence_scores", None) or [])
        for pos, idx in enumerate(getattr(sup, "grounding_chunk_indices", None) or []):
            web = getattr(chunks[idx], "web", None) if idx < len(chunks) else None
            uri = getattr(web, "uri", None) or ""
            host = getattr(web, "domain", None) or getattr(web, "title", None) or ""
            if uri or host:
                conf = float(confs[pos]) if pos < len(confs) else 0.0
                scored.append((conf, str(uri), str(host)))
    scored.sort(reverse=True)
    return scored


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
                grounded=tuple(chunk_hosts_for(st, resp)),
            )
        )
    return out


def render_facts(facts: list[Fact]) -> str:
    return "\n".join(
        f"[{f.id}] {f.statement}"
        + (f" (as of {f.as_of})" if f.as_of else "")
        + (" [search]" if f.checked == "search" else "")
        for f in facts
    )


class VertexFactDesk:  # pragma: no cover - needs a GCP project
    def __init__(self, project: str, location: str, model: str) -> None:
        from app.model import GENERATE_TIMEOUT_S, vertex_client

        self.client = vertex_client(project, location, GENERATE_TIMEOUT_S)
        # one attempt: a grounded call that timed out once times out again (run 6: 3 x 150 s)
        self.research_client = vertex_client(project, location, RESEARCH_TIMEOUT_S, attempts=1)
        self.model = model

    def angles(self, topic: str, speaker: str, k: int, said_on: str = "") -> list[str]:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=ANGLES_PROMPT.format(
                topic=topic, speaker=speaker or "unknown", k=k, when=when_line(said_on)
            ),
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
                response_schema=_ANGLES_SCHEMA,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            ),
        )
        return [str(a)[:200] for a in json.loads(resp.text or "[]") if str(a).strip()][:k]

    def research(
        self, topic: str, speaker: str, angle: str, n: int, said_on: str = ""
    ) -> list[Candidate]:
        from google.genai import types

        hint = search_hint(speaker, f"{topic} {angle}")
        resp = self.research_client.models.generate_content(
            model=self.model,
            contents=RESEARCH_PROMPT.format(
                topic=topic,
                speaker=speaker or "unknown",
                angle=angle,
                n=n,
                hint=hint,
                when=when_line(said_on),
            ),
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            ),
        )
        return candidates_from(resp.text or "", resp, angle)

    def rule(self, claim: str, facts: list[Fact], said_on: str = "") -> Ruling | None:
        from google.genai import types

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=RULE_PROMPT.format(
                    claim=claim, facts=render_facts(facts), when=said_line(said_on)
                ),
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
