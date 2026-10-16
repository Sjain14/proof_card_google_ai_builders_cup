"""Official records first: ranking of grounding sources (Team lead flow step 3)."""

from __future__ import annotations

from types import SimpleNamespace

from app.model import Evidence, evidence_from_grounding
from app.trusted import FACT_CHECKER, OFFICIAL, OTHER, domain_of, is_official, rank, tier

R = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"


def test_domain_from_redirect_title() -> None:
    assert domain_of(R, "pib.gov.in") == "pib.gov.in"
    assert domain_of("https://www.rbi.org.in/x", "") == "rbi.org.in"


def test_tiers() -> None:
    assert tier(R, "mospi.gov.in") == OFFICIAL
    assert tier(R, "eci.gov.in") == OFFICIAL
    assert tier("https://sansad.in/ls/debates", "") == OFFICIAL
    assert tier(R, "data.worldbank.org") == OFFICIAL
    assert tier(R, "boomlive.in") == FACT_CHECKER
    assert tier(R, "factcheck.pib.gov.in") == FACT_CHECKER
    assert tier(R, "ndtv.com") == OTHER
    assert tier(R, "") == OTHER


def test_lookalike_domains_are_not_official() -> None:
    assert not is_official("https://fakegov.in/x")
    assert not is_official("https://gov.in.evil.com/x")
    assert not is_official(R, "notrbi.org.in.example.com")


def test_rank_is_stable_inside_tiers() -> None:
    ev = [
        Evidence(url=R, title="ndtv.com", confidence=0.9),
        Evidence(url=R, title="altnews.in", confidence=0.8),
        Evidence(url=R, title="mospi.gov.in", confidence=0.5),
        Evidence(url=R, title="thehindu.com", confidence=0.4),
        Evidence(url=R, title="rbi.org.in", confidence=0.3),
    ]
    assert [e.title for e in rank(ev)] == [
        "mospi.gov.in",
        "rbi.org.in",
        "altnews.in",
        "ndtv.com",
        "thehindu.com",
    ]


def test_grounding_puts_official_first() -> None:
    def chunk(title: str) -> SimpleNamespace:
        return SimpleNamespace(web=SimpleNamespace(uri=R + title, title=title))

    sup = SimpleNamespace(
        segment=SimpleNamespace(text="s"),
        confidence_scores=[0.95, 0.4],
        grounding_chunk_indices=[0, 1],
    )
    meta = SimpleNamespace(
        grounding_chunks=[chunk("timesofindia.com"), chunk("pib.gov.in")],
        grounding_supports=[sup],
    )
    resp = SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=meta)])
    out = evidence_from_grounding(resp)
    assert [e.title for e in out] == ["pib.gov.in", "timesofindia.com"]
