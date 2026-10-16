from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.model import Assessment, Evidence, StubModel
from app.pipeline import Deps, Trace, check_quote, verify_claim
from app.proof import Fetched, FetchError, InMemorySnapshots
from app.quotes import attribution, surname
from app.schemas import ClaimDoc, ClaimSource, ClaimStatus, SessionDoc, Verdict
from app.store import InMemoryStore

SPEECH = "https://pib.gov.in/speech"
Q10 = 'Modi said: "India will become a 10 trillion dollar economy by 2030"'
PAGE = (
    "<html><body><p>Prime Minister Narendra Modi addressed the nation today.</p>"
    "<p>He said India will become a 10 trillion dollar economy by 2030, and that every "
    "village now has electricity.</p></body></html>"
)
NO_NAME = PAGE.replace("Prime Minister Narendra Modi", "The speaker")


@dataclass
class Model:
    urls: list[str]
    calls: int = 0

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[object]:
        return []

    def assess(self, claim: str, hint: str = "") -> Assessment:
        self.calls += 1
        return Assessment(Verdict.TRUE, "why", [Evidence(url=u) for u in self.urls])


class Pages:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> Fetched:
        if url not in self.pages:
            raise FetchError("nope")
        return Fetched(url, url, self.pages[url].encode(), "text/html", datetime.now(UTC))


def deps(model: object, pages: dict[str, str]) -> Deps:
    return Deps(InMemoryStore(), model, Pages(pages), InMemorySnapshots())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "who", "quote"),
    [
        (
            'Modi said: "India will become a 10 trillion dollar economy"',
            "Modi",
            "India will become a 10 trillion dollar economy",
        ),
        (
            "Rahul Gandhi ne kaha ki 40 percent youth berozgar hain",
            "Rahul Gandhi",
            "40 percent youth berozgar hain",
        ),
        ("मोदी ने कहा कि भारत तीसरी सबसे बड़ी अर्थव्यवस्था है", "मोदी", "भारत तीसरी सबसे बड़ी अर्थव्यवस्था है"),
        (
            '"We ended eight wars in eight months" - Donald Trump',
            "Donald Trump",
            "We ended eight wars in eight months",
        ),
        (
            'Sitharaman: "India is the fastest growing major economy"',
            "Sitharaman",
            "India is the fastest growing major economy",
        ),
    ],
)
def test_attribution_forms(text: str, who: str, quote: str) -> None:
    a = attribution(text)
    assert a is not None
    assert a.speaker == who
    assert a.quote == quote


@pytest.mark.parametrize(
    "text",
    [
        "India has 22 languages in the Eighth Schedule",
        "The report said that inflation fell to 4 percent",
        'Modi said: "yes"',
        "the data released by the ministry last week said that exports rose 5 percent",
    ],
)
def test_not_an_attribution(text: str) -> None:
    assert attribution(text) is None


def test_surname() -> None:
    assert surname("PM Narendra Modi") == "modi"
    assert surname("") == ""


def test_quote_on_record_is_true_and_says_what_it_proves() -> None:
    d = deps(Model([SPEECH]), {SPEECH: PAGE})
    card = check_quote(Q10, d, Trace())
    assert card is not None
    assert card.verdict == Verdict.TRUE
    assert "proves the quote, not the statement" in card.explanation
    assert "10 trillion" in card.sources[0].snippet


def test_page_not_naming_the_speaker_is_no_record() -> None:
    d = deps(Model([SPEECH]), {SPEECH: NO_NAME})
    t = Trace()
    assert check_quote(Q10, d, t) is None
    assert t.skips.get("quote_not_found")


def test_twisted_quote_is_misleading(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.pipeline as pl

    monkeypatch.setattr(pl, "QUOTE_SAID", 1.01)  # on record, but not these exact words
    d = deps(Model([SPEECH]), {SPEECH: PAGE})
    card = check_quote(Q10, d, Trace())
    assert card is not None
    assert card.verdict == Verdict.MISLEADING
    assert "Twisted quote" in card.explanation


def test_plain_claim_never_calls_the_quote_search() -> None:
    m = Model([SPEECH])
    assert (
        check_quote("India has 22 languages in the Eighth Schedule", deps(m, {}), Trace()) is None
    )
    assert m.calls == 0


def test_verify_claim_uses_the_quote_check_first() -> None:
    d = deps(Model([SPEECH]), {SPEECH: PAGE})
    store = d.store
    sid = store.create_session(SessionDoc(owner_uid="u", topic="t"))
    cid = store.add_claim(
        sid,
        ClaimDoc(
            text='Modi said: "India will become a 10 trillion dollar economy by 2030"',
            source=ClaimSource.LIVE,
        ),
    )
    t = Trace()
    card_id = verify_claim(sid, cid, d, t)
    assert card_id is not None
    claim = store.get_claim(sid, cid)
    assert claim is not None
    assert claim.status == ClaimStatus.PROVED
    assert claim.verdict == Verdict.TRUE
    assert t.reason == "quote"


def test_stub_model_still_works_for_quotes() -> None:
    # no evidence -> no record -> falls through to the normal check, no crash
    assert (
        check_quote(
            'Modi said: "every village now has electricity"', deps(StubModel(), {}), Trace()
        )
        is None
    )


def test_words_said_by_someone_else_are_no_record() -> None:
    # prod 16 Oct: Mukesh Ambani said it, Modi was only named elsewhere on the page
    page = (
        "<html><body><p>PM Narendra Modi has set a 5 trillion dollar target.</p>"
        + "<p>Unrelated filler about markets and sectors. </p>" * 12
        + "<p>RIL chief Mukesh Ambani said India will become a 10 trillion dollar economy "
        "by 2030.</p></body></html>"
    )
    t = Trace()
    assert check_quote(Q10, deps(Model([SPEECH]), {SPEECH: page}), t) is None
    assert t.skips.get("quote_other_speaker")


def test_speaker_named_just_before_the_passage_counts() -> None:
    from app.pipeline import speaker_near

    page = "Prime Minister Modi spoke in Delhi. He said every village now has electricity."
    assert speaker_near("modi", "every village now has electricity", page)
    assert not speaker_near(
        "modi", "every village", "x" * 900 + "Modi" + "y" * 900 + "every village"
    )
    assert not speaker_near("", "a", "a")


def test_quote_with_another_figure_is_no_record() -> None:
    # prod 16 Oct: '10 trillion by 2030' went TRUE on a passage about '$7 trillion by 2030'
    page = (
        "<html><body><p>Ten years of the Narendra Modi government: India can aspire to become "
        "a $7 trillion economy by 2030, the finance ministry said.</p></body></html>"
    )
    t = Trace()
    assert check_quote(Q10, deps(Model([SPEECH]), {SPEECH: page}), t) is None
