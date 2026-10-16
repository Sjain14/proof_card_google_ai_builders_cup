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
