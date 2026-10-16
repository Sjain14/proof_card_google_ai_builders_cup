"""Official statistics as a first source: World Bank Indicators API.

A claim about a country figure ("India's per capita GDP is higher than Japan's") gets
grounding chunks from data portals (IMF DataMapper, World Bank pages, Statista) that render
the numbers in JavaScript, so the fetched page has no figures and the card fails (prod
16 Oct 2026: the per capita line ended FAILED on 4 of 4 runs while the power plants line
proved). The World Bank API returns the official series as JSON, so we put it in front
of the grounding sources and render it as one line per country for the passage matcher.
The raw JSON is what gets snapshotted, like any other source.
Docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.model import Evidence

API = "https://api.worldbank.org/v2/country/{codes}/indicator/{indicator}?format=json&mrv=1&per_page=50"
HOST = "api.worldbank.org"

# (indicator, words that must all appear). Order matters: "gdp per capita" before "gdp".
METRICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("NY.GDP.PCAP.CD", ("gdp", "per capita")),
    ("NY.GDP.PCAP.CD", ("per capita income",)),
    ("NY.GNP.PCAP.CD", ("gni", "per capita")),
    ("NY.GDP.PCAP.CD", ("per capita",)),
    ("NY.GDP.PCAP.CD", ("प्रति व्यक्ति",)),
    ("NY.GDP.MKTP.KD.ZG", ("gdp", "growth")),
    ("NY.GDP.MKTP.CD", ("gdp",)),
    ("NY.GDP.MKTP.CD", ("जीडीपी",)),
    ("NY.GDP.MKTP.CD", ("अर्थव्यवस्था",)),
    ("NY.GDP.MKTP.CD", ("economy", "bigger")),
    ("NY.GDP.MKTP.CD", ("economy", "larger")),
    ("NY.GDP.MKTP.CD", ("economy", "badi")),
    ("FP.CPI.TOTL.ZG", ("inflation",)),
    ("FP.CPI.TOTL.ZG", ("mehngai",)),
    ("FP.CPI.TOTL.ZG", ("महंगाई",)),
    ("SL.UEM.TOTL.ZS", ("unemployment",)),
    ("SL.UEM.TOTL.ZS", ("berozgari",)),
    ("SL.UEM.TOTL.ZS", ("बेरोजगारी",)),
    ("SP.DYN.LE00.IN", ("life expectancy",)),
    ("SE.ADT.LITR.ZS", ("literacy",)),
    ("SP.DYN.TFRT.IN", ("fertility",)),
    ("SP.DYN.IMRT.IN", ("infant mortality",)),
    ("SP.POP.TOTL", ("population",)),
    ("SP.POP.TOTL", ("aabadi",)),
    ("SP.POP.TOTL", ("jansankhya",)),
    ("SP.POP.TOTL", ("आबादी",)),
    ("SP.POP.TOTL", ("जनसंख्या",)),
)

# name (lower, Latin + common Hindi spellings) -> ISO3
COUNTRIES: dict[str, str] = {
    "india": "IND", "bharat": "IND", "भारत": "IND", "japan": "JPN", "जापान": "JPN",
    "china": "CHN", "cheen": "CHN", "चीन": "CHN", "pakistan": "PAK", "पाकिस्तान": "PAK",
    "bangladesh": "BGD", "बांग्लादेश": "BGD", "nepal": "NPL", "sri lanka": "LKA",
    "srilanka": "LKA", "united states": "USA", "usa": "USA", "america": "USA",
    "amerika": "USA", "अमेरिका": "USA", "united kingdom": "GBR", "uk": "GBR",
    "britain": "GBR", "england": "GBR", "germany": "DEU", "france": "FRA", "russia": "RUS",
    "रूस": "RUS", "brazil": "BRA", "south africa": "ZAF", "indonesia": "IDN",
    "vietnam": "VNM", "thailand": "THA", "malaysia": "MYS", "singapore": "SGP",
    "south korea": "KOR", "korea": "KOR", "australia": "AUS", "canada": "CAN",
    "italy": "ITA", "spain": "ESP", "mexico": "MEX", "turkey": "TUR", "saudi arabia": "SAU",
    "uae": "ARE", "israel": "ISR", "iran": "IRN", "egypt": "EGY", "nigeria": "NGA",
    "afghanistan": "AFG", "myanmar": "MMR", "bhutan": "BTN", "maldives": "MDV",
    "philippines": "PHL", "argentina": "ARG", "switzerland": "CHE", "norway": "NOR",
    "sweden": "SWE", "netherlands": "NLD", "world": "WLD", "duniya": "WLD",
}  # fmt: skip

_WORD = re.compile(r"[\wऀ-෿]+", re.UNICODE)
MAX_COUNTRIES = 4


def _norm(s: str) -> str:
    return " " + " ".join(_WORD.findall(s.lower())) + " "


def metric_of(text: str) -> str:
    t = _norm(text)
    for indicator, need in METRICS:
        if all(f" {w} " in t or (" " not in w and w in t) for w in need):
            return indicator
    return ""


def countries_of(text: str) -> list[str]:
    t = _norm(text)
    hits: list[tuple[int, str]] = []
    for name, iso in COUNTRIES.items():
        i = t.find(f" {name} ")  # "Japan's" normalises to "japan s"
        if i >= 0 and iso not in {c for _, c in hits}:
            hits.append((i, iso))
    return [iso for _, iso in sorted(hits)][:MAX_COUNTRIES]


def official_evidence(*texts: str) -> list[Evidence]:
    """One World Bank API source when a claim names a known metric and country, else []."""
    # The text naming the most countries wins ("bharat ki aabadi" vs its English restatement).
    picks = [(metric_of(t), countries_of(t)) for t in texts if t]
    for indicator, codes in sorted(picks, key=lambda p: (bool(p[0]), len(p[1])), reverse=True):
        if indicator and codes:
            return [
                Evidence(
                    url=API.format(codes=";".join(codes), indicator=indicator),
                    title="World Bank Open Data (official statistics)",
                    model_snippet="",
                    confidence=1.0,
                )
            ]
    return []


def is_country_figure(text: str) -> bool:
    """A sentence naming an official country figure is checkable even with no number in it
    ("India's per capita income is higher than Japan's"); the live spotter returned [] for
    these on prod (16 Oct 2026, Hindi + Hinglish comparison lines skipped as not_checkable)."""
    return bool(metric_of(text)) and bool(countries_of(text))


def official_proof(url: str, text: str) -> tuple[str, float]:
    """The World Bank request is built from the claim's own metric and countries, so its
    rendered figures ARE the proof when every requested country has a value: no fuzzy
    passage matching. Prod 63929df: "भारत की जीडीपी अमेरिका से बड़ी है।" FAILED because the
    model restated it as "...the USA's" and the row says "United States" (score 0.33 < 0.35).
    A missing country -> ("", 0.0): half a comparison is not proof."""
    m = re.search(r"/country/([A-Z;]+)/indicator/", url)
    want = len(m.group(1).split(";")) if m else 1
    rows = [ln for ln in text.splitlines()[1:] if ln.strip()]
    if not rows or len(rows) < want:
        return "", 0.0
    return " ".join(rows), 1.0


def is_worldbank(url: str) -> bool:
    return url.startswith(f"https://{HOST}/")


def render(body: bytes) -> str:
    """WB JSON -> one line per country: 'India: GDP per capita (current US$), 2025: 2,702.48'.
    Unparseable or empty -> "" (the source is skipped as 'no text')."""
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return ""
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        return ""
    lines = []
    for row in data[1]:
        if not isinstance(row, dict) or row.get("value") is None:
            continue
        try:
            value = float(row["value"])
            name = str(row["country"]["value"])
            metric = str(row["indicator"]["value"])
        except (KeyError, TypeError, ValueError):
            continue
        lines.append(f"{name}: {metric}, {row.get('date', '')}: {value:,.2f}")
    if not lines:
        return ""
    return "Source: World Bank Open Data, latest official value.\n" + "\n".join(lines)


# Official data pack (p38): every fact bank also gets the headline World Bank series for
# the speaker's country and its usual comparators, around the speech date. Research kept
# 10 facts on prod (16 Oct 2026, 72 researched: 29 pages unreachable, 27 low support);
# these are read straight off the official API, so each one is a source checked figure.
PACK_INDICATORS: tuple[str, ...] = (
    "NY.GDP.MKTP.KD.ZG",  # GDP growth (annual %)
    "NY.GDP.MKTP.CD",  # GDP (current US$)
    "NY.GDP.PCAP.CD",  # GDP per capita (current US$)
    "FP.CPI.TOTL.ZG",  # inflation, consumer prices (annual %)
    "SL.UEM.TOTL.ZS",  # unemployment (% of labour force, ILO)
    "SP.POP.TOTL",  # population
    "NE.EXP.GNFS.CD",  # exports of goods and services (current US$)
    "BX.KLT.DINV.CD.WD",  # FDI, net inflows (current US$)
    "NV.IND.MANF.ZS",  # manufacturing, value added (% of GDP)
    "FI.RES.TOTL.CD",  # total reserves incl. gold (current US$)
    "EG.ELC.ACCS.ZS",  # access to electricity (% of population)
    "SP.DYN.LE00.IN",  # life expectancy at birth
)
PACK_COMPARATORS: tuple[str, ...] = ("USA", "CHN", "WLD")
PACK_YEARS = 3  # latest years with a value, per country and series
PACK_MAX_COUNTRIES = 5
SERIES_API = (
    "https://api.worldbank.org/v2/country/{codes}/indicator/{indicator}"
    "?format=json&date={start}:{end}&per_page=500"
)


@dataclass(frozen=True)
class PackRow:
    country: str
    metric: str
    year: str
    value: float
    url: str


def pack_countries(home: str, text: str) -> list[str]:
    """Home country first, then the ones the topic names, then the usual comparators."""
    codes = [c for c in [home, *countries_of(text), *PACK_COMPARATORS] if c]
    return list(dict.fromkeys(codes))[:PACK_MAX_COUNTRIES]


def pack_urls(codes: list[str], said_on: str = "", today: int | None = None) -> list[str]:
    """One request per series for all countries. A speech is checked against the figures
    published before it."""
    # annual series for year Y come out in Y+1: a speech in Y could only cite Y-1 and before
    end = int(said_on[:4]) - 1 if said_on[:4].isdigit() else (today or 2026)
    start = end - 5
    return [
        SERIES_API.format(codes=";".join(codes), indicator=ind, start=start, end=end)
        for ind in PACK_INDICATORS
    ]


def pack_rows(body: bytes, url: str) -> list[PackRow]:
    """Latest PACK_YEARS values per country from one series response; [] when unreadable."""
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return []
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        return []
    per: dict[str, list[PackRow]] = {}
    for row in data[1]:
        if not isinstance(row, dict) or row.get("value") is None:
            continue
        try:
            r = PackRow(
                country=str(row["country"]["value"]),
                metric=str(row["indicator"]["value"]),
                year=str(row["date"]),
                value=float(row["value"]),
                url=url,
            )
        except (KeyError, TypeError, ValueError):
            continue
        per.setdefault(r.country, []).append(r)
    out: list[PackRow] = []
    for rows in per.values():
        out += sorted(rows, key=lambda r: r.year, reverse=True)[:PACK_YEARS]
    return out


def human(value: float) -> str:
    """3.15e12 -> '3.15 trillion'; percentages and small figures keep 2 decimals."""
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if abs(value) >= size:
            return f"{value / size:,.2f} {word}"
    return f"{value:,.2f}"
