"""Speaker country -> that country's official sources, as a SEARCH HINT for the assess call.

Team lead flow (voice note, 16 Oct 2026): find which country the politician is from
and check that nation's government sources; India (PIB, gov.in, RBI, MoSPI) and the US
(.gov, BLS, BEA, Census, EIA) for now.

Added evidence only. The hint widens what Google Search looks at; the model's source
ORDER is never touched. Moving official domains to the front (#43) cut prod bank fill
from 11/12 to 3/12 and was reverted (#46).

PROFILES holds the politicians we see most (Team lead: Modi, the Home Minister, Trump): who
they are and which country's records apply. Matching is on lowercased name aliases.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.officialdata import countries_of


@dataclass(frozen=True)
class Profile:
    name: str
    role: str
    country: str  # ISO3, a key of GOV_SOURCES
    aliases: tuple[str, ...]


PROFILES: tuple[Profile, ...] = (
    Profile("Narendra Modi", "Prime Minister of India", "IND", ("modi", "मोदी")),
    Profile("Amit Shah", "Union Home Minister of India", "IND", ("amit shah", "अमित शाह")),
    Profile(
        "Nirmala Sitharaman",
        "Union Finance Minister of India",
        "IND",
        ("sitharaman", "सीतारमण"),
    ),
    Profile(
        "Rahul Gandhi",
        "Leader of the Opposition, Lok Sabha",
        "IND",
        ("rahul gandhi", "राहुल गांधी"),
    ),
    Profile(
        "Arvind Kejriwal",
        "AAP national convenor, former Delhi Chief Minister",
        "IND",
        ("kejriwal", "केजरीवाल"),
    ),
    Profile("Donald Trump", "President of the United States", "USA", ("trump", "ट्रंप")),
    Profile("JD Vance", "Vice President of the United States", "USA", ("vance",)),
    Profile("Kamala Harris", "former Vice President of the United States", "USA", ("harris",)),
)

GOV_SOURCES: dict[str, tuple[str, str]] = {
    "IND": (
        "India",
        "pib.gov.in, mospi.gov.in, rbi.org.in, indiabudget.gov.in, data.gov.in, "
        "censusindia.gov.in, sansad.in and the relevant ministry site (*.gov.in, *.nic.in)",
    ),
    "USA": (
        "the United States",
        "bls.gov, bea.gov, census.gov, eia.gov, cbo.gov, treasury.gov, whitehouse.gov "
        "and the relevant federal agency (*.gov)",
    ),
}


def profile_of(speaker: str) -> Profile | None:
    s = f" {speaker.lower()} "
    for p in PROFILES:
        if any(a in s for a in p.aliases):
            return p
    return None


def country_for(speaker: str, claim: str) -> str:
    """The speaker's country when we know them, else the first supported country the
    claim names, else ""."""
    p = profile_of(speaker) if speaker else None
    if p is not None:
        return p.country
    for code in countries_of(claim):
        if code in GOV_SOURCES:
            return code
    return ""


def search_hint(speaker: str, claim: str) -> str:
    """One or two sentences appended to the assess prompt, "" when no country applies."""
    code = country_for(speaker, claim)
    if not code:
        return ""
    where, sites = GOV_SOURCES[code]
    p = profile_of(speaker) if speaker else None
    who = f"The speaker is {p.name}, {p.role}. " if p else ""
    return (
        f"{who}Also search the official records of {where} ({sites}) and cite them "
        "when they hold the figure."
    )
