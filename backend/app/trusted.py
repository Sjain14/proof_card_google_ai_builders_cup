"""Trusted source ranking: official records first, then recognised fact checkers.

Grounding returns sources in the model's confidence order, and build_card fetches them
one at a time under one budget. So the ORDER decides which sources a card can use. We move
government and primary statistical sources (gov.in, nic.in, RBI, Parliament, ECI, World
Bank, IMF ...) to the front, recognised fact checkers next, everything else after, keeping
the model's order inside each tier.

Grounding chunk URLs are vertexaisearch redirect links; the real domain is in the chunk
title (e.g. "pib.gov.in"), so we read the domain from the title when the URL is a redirect.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

OFFICIAL = 0
FACT_CHECKER = 1
OTHER = 2

REDIRECT_HOSTS = ("vertexaisearch.cloud.google.com",)

# Suffix match on the registrable domain. Keep it short and boring: only bodies that
# publish the primary record (statistics, budgets, laws, election results, debates).
OFFICIAL_SUFFIXES = (
    ".gov.in",
    ".nic.in",
    ".gov",
    ".gov.uk",
    "rbi.org.in",
    "sansad.in",
    "indiabudget.gov.in",
    "data.gov.in",
    "censusindia.gov.in",
    "eci.gov.in",
    "sebi.gov.in",
    "nhm.gov.in",
    "niti.gov.in",
    "worldbank.org",
    "imf.org",
    "un.org",
    "who.int",
    "oecd.org",
    "wto.org",
    "undp.org",
    "unicef.org",
)

FACT_CHECKER_SUFFIXES = (
    "boomlive.in",
    "altnews.in",
    "factly.in",
    "factchecker.in",
    "newschecker.in",
    "vishvasnews.com",
    "thequint.com",
    "indiatoday.in",
    "afp.com",
    "reuters.com",
    "fullfact.org",
    "politifact.com",
)


def domain_of(url: str, title: str = "") -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host in REDIRECT_HOSTS or not host:
        t = (title or "").strip().lower()
        # titles are a bare domain for grounding chunks; fall back to the first token
        host = t.split()[0] if t else host
    return host.removeprefix("www.")


def _ends(host: str, suffixes: Sequence[str]) -> bool:
    for s in suffixes:
        base = s.lstrip(".")
        if host == base or host.endswith("." + base):
            return True
    return False


def tier(url: str, title: str = "") -> int:
    host = domain_of(url, title)
    if not host:
        return OTHER
    if host == "factcheck.pib.gov.in":
        return FACT_CHECKER
    if _ends(host, OFFICIAL_SUFFIXES):
        return OFFICIAL
    if _ends(host, FACT_CHECKER_SUFFIXES):
        return FACT_CHECKER
    return OTHER


def is_official(url: str, title: str = "") -> bool:
    return tier(url, title) == OFFICIAL


def rank[T](evidence: Sequence[T]) -> list[T]:
    """Stable sort by tier; the model's order is kept inside a tier."""
    return sorted(
        evidence,
        key=lambda e: tier(getattr(e, "url", ""), getattr(e, "title", "")),
    )
