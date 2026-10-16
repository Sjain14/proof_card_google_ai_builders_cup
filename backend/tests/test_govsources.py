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


class _Spy:
    def __init__(self, prove_on_hint: bool) -> None:
        self.hints: list[str] = []
        self.prove_on_hint = prove_on_hint

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[object]:
        return []

    def assess(self, claim: str, hint: str = "") -> object:
        from app.model import Assessment, Evidence
        from app.schemas import Verdict

        self.hints.append(hint)
        ev = [Evidence(url="https://x/1", title="t", model_snippet=claim, confidence=1.0)]
        good = bool(hint) == self.prove_on_hint
        return Assessment(verdict=Verdict.TRUE, explanation="x", evidence=ev if good else [])


def _run(spy: _Spy) -> str | None:
    from app.pipeline import Deps, verify_claim
    from app.proof import InMemorySnapshots
    from app.schemas import ClaimDoc, ClaimSource, SessionDoc
    from app.store import InMemoryStore

    class _F:
        def fetch(self, url: str) -> object:
            from app.proof import FetchError

            raise FetchError("offline")

    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t", speaker="Donald Trump"))
    cid = store.add_claim(sid, ClaimDoc(text="unemployment is 4%", source=ClaimSource.LIVE))
    return verify_claim(sid, cid, Deps(store, spy, _F(), InMemorySnapshots()))  # type: ignore[arg-type]


def test_hint_is_second_try_only() -> None:
    spy = _Spy(prove_on_hint=True)
    _run(spy)
    assert spy.hints[0] == ""  # plain check first, unchanged from before #50
    assert len(spy.hints) == 2
    assert "bls.gov" in spy.hints[1]


def test_no_second_call_when_plain_check_proves_or_no_country() -> None:
    spy = _Spy(prove_on_hint=False)  # plain arm has evidence; fetch fails -> still None
    _run(spy)
    assert spy.hints[0] == ""
