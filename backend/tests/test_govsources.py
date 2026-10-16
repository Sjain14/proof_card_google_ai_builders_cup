"""Speaker country -> official sources hint (Team lead voice note)."""

from app.govsources import country_for, profile_of, search_hint


def test_profiles() -> None:
    p = profile_of("Narendra Modi")
    assert p is not None
    assert p.country == "IND"
    shah = profile_of("Amit Shah")
    assert shah is not None
    assert "Home Minister" in shah.role
    trump = profile_of("Donald J. Trump")
    assert trump is not None
    assert trump.country == "USA"
    assert profile_of("Some Local Councillor") is None


def test_country_from_speaker_then_claim() -> None:
    assert country_for("Donald Trump", "India's GDP is bigger") == "USA"  # speaker wins
    assert country_for("", "India's unemployment is 8%") == "IND"
    assert country_for("", "Japan's GDP fell") == ""  # no supported country
    assert country_for("", "inflation is at a record high") == ""


def test_hint_names_the_country_portals() -> None:
    h = search_hint("Narendra Modi", "inflation is down")
    assert "pib.gov.in" in h
    assert "Prime Minister" in h
    us = search_hint("Donald Trump", "unemployment is the lowest ever")
    assert "bls.gov" in us
    assert search_hint("", "the weather is nice") == ""


def test_hint_never_reorders_evidence() -> None:
    # #43 front-ordered official domains and bank fill fell 11/12 -> 3/12 (reverted #46).
    import inspect

    from app import model

    src = inspect.getsource(model.evidence_from_grounding)
    assert "rank(" not in src
