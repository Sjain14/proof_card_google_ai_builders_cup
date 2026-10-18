"""p81: "Report this card" on /v/<id>: issue required, email + source optional, stored."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps, run_prebunk
from app.proof import FixtureFetcher, InMemorySnapshots
from app.schemas import CardDoc, SessionDoc
from app.share_page import ReportState, card_page, report_error
from app.store import InMemoryStore
from app.tasks import SyncQueue
from tests.conftest import fake_oidc, fake_verifier

BASE = "https://proofcard.web.app"


@pytest.fixture
def store() -> InMemoryStore:
    s = InMemoryStore()
    sid = s.create_session(SessionDoc(owner_uid="u", topic="India"))
    run_prebunk(sid, Deps(s, StubModel(), FixtureFetcher(), InMemorySnapshots()), n=2)
    return s


@pytest.fixture
def client(store: InMemoryStore) -> TestClient:
    settings = Settings(env="test", public_base_url=BASE, public_rate_per_min=100)
    deps = Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots())
    app = create_app(
        settings=settings,
        verifier=fake_verifier,
        store=store,
        deps=deps,
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
    )
    return TestClient(app)


def first(store: InMemoryStore) -> tuple[str, CardDoc]:
    return next(iter(store.cards.items()))


def test_card_page_has_prefilled_report_form(client: TestClient, store: InMemoryStore) -> None:
    cid, _card = first(store)
    html = client.get(f"/v/{cid}").text
    assert "Report it</summary>" in html
    assert f'action="/v/{cid}/report#report"' in html
    assert "You are reporting" in html
    assert cid in html
    assert 'name="issue" rows="4" required' in html
    assert 'name="email" type="email"' in html
    assert 'name="source_url" type="url"' in html
    assert "<details open" not in html.split('id="report"')[1]  # folded until used


def test_report_with_issue_only_is_stored(client: TestClient, store: InMemoryStore) -> None:
    cid, card = first(store)
    r = client.post(f"/v/{cid}/report", data={"issue": "  the year is wrong  "})
    assert r.status_code == 200
    assert "your report is in" in r.text
    assert r.headers["cache-control"] == "no-store"
    doc = store.reports[-1]
    assert (doc.card_id, doc.issue, doc.email, doc.source_url) == (
        cid,
        "the year is wrong",
        None,
        None,
    )
    assert doc.claim == card.claim
    assert doc.verdict == card.verdict


def test_report_with_all_fields(client: TestClient, store: InMemoryStore) -> None:
    cid, _ = first(store)
    data = {"issue": "x", "email": "a@b.co", "source_url": "https://rbi.org.in/x"}
    assert client.post(f"/v/{cid}/report", data=data).status_code == 200
    doc = store.reports[-1]
    assert doc.email == "a@b.co"
    assert str(doc.source_url) == "https://rbi.org.in/x"


@pytest.mark.parametrize(
    ("data", "words"),
    [
        ({"issue": "   "}, "required"),
        ({"issue": "x" * 2001}, "under 2000"),
        ({"issue": "x", "email": "not-an-email"}, "email does not look right"),
        ({"issue": "x", "source_url": "javascript:alert(1)"}, "full web address"),
        ({"issue": "x", "source_url": "ftp://a.b/c"}, "full web address"),
    ],
)
def test_bad_report_is_400_and_keeps_input(
    client: TestClient, store: InMemoryStore, data: dict[str, str], words: str
) -> None:
    cid, _ = first(store)
    before = len(store.reports)
    r = client.post(f"/v/{cid}/report", data=data)
    assert r.status_code == 400
    assert words in r.text
    assert "<details open" in r.text  # the form opens again with what they typed
    assert len(store.reports) == before


def test_report_unknown_card_is_404(client: TestClient, store: InMemoryStore) -> None:
    assert client.post("/v/nope-nope-nope/report", data={"issue": "x"}).status_code == 404
    assert client.post("/v/bad!/report", data={"issue": "x"}).status_code == 404
    assert store.reports == []


def test_report_rate_limited_per_ip(client: TestClient, store: InMemoryStore) -> None:
    cid, _ = first(store)
    codes = [client.post(f"/v/{cid}/report", data={"issue": "x"}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5:] == [429, 429]
    assert len(store.reports) == 5


def test_report_form_escapes_input(store: InMemoryStore) -> None:
    cid, card = first(store)
    evil = {"issue": "</textarea><script>x</script>", "email": '"><b>', "source_url": ""}
    html = card_page(card, cid, BASE, report=ReportState("fix it", False, evil))
    assert "<script>x</script>" not in html
    assert '"><b>' not in html
    assert "&lt;/textarea&gt;&lt;script&gt;" in html


def test_report_error_accepts_good_input() -> None:
    ok = {"issue": "wrong", "email": "a@b.in", "source_url": "http://pib.gov.in/a"}
    assert report_error(ok) == ""


# p82: general "Report an issue" from the home footer (/v/report, no card).


def test_general_report_page_renders(client: TestClient) -> None:
    r = client.get("/v/report")
    assert r.status_code == 200
    assert "<h1>Report an issue</h1>" in r.text
    assert 'action="/v/report#report"' in r.text
    assert 'name="issue" rows="5" required' in r.text
    assert "You are reporting" not in r.text  # nothing prefilled
    assert r.headers["cache-control"] == "no-store"


def test_general_report_is_stored_without_card(client: TestClient, store: InMemoryStore) -> None:
    data = {"issue": " add a share button ", "email": "a@b.co", "source_url": "https://x.in/a"}
    r = client.post("/v/report", data=data)
    assert r.status_code == 200
    assert "your report is in" in r.text
    doc = store.reports[-1]
    assert (doc.card_id, doc.claim, doc.verdict) == (None, None, None)
    assert doc.issue == "add a share button"
    assert doc.email == "a@b.co"


@pytest.mark.parametrize(
    ("data", "words"),
    [
        ({"issue": ""}, "required"),
        ({"issue": "x", "email": "nope"}, "email does not look right"),
        ({"issue": "x", "source_url": "javascript:alert(1)"}, "full web address"),
    ],
)
def test_general_report_bad_input_is_400(
    client: TestClient, store: InMemoryStore, data: dict[str, str], words: str
) -> None:
    r = client.post("/v/report", data=data)
    assert r.status_code == 400
    assert words in r.text
    assert store.reports == []


def test_general_report_shares_the_rate_limit(client: TestClient, store: InMemoryStore) -> None:
    codes = [client.post("/v/report", data={"issue": "x"}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_general_report_escapes_input(client: TestClient) -> None:
    r = client.post("/v/report", data={"issue": "</textarea><script>x</script>", "email": "bad"})
    assert "<script>x</script>" not in r.text
    assert "&lt;/textarea&gt;" in r.text


def test_server_pages_carry_the_favicon(client: TestClient, store: InMemoryStore) -> None:
    """p83: card, report and 404 pages show the Proof Card icon, not the browser globe."""
    cid, _card = first(store)
    icon = '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
    for path in (f"/v/{cid}", "/v/report", "/v/zzzzzzzzzzzz"):
        assert icon in client.get(path).text, path
