"""P3: card image, ALTERED check, share page, Telegram bot."""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pydantic import SecretStr

from app import alter
from app.card_image import font, render, wrap
from app.config import Settings
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps, run_prebunk
from app.proof import FixtureFetcher, InMemorySnapshots
from app.schemas import CardDoc, SessionDoc, TgUpdate
from app.store import InMemoryStore
from app.tasks import SyncQueue
from app.telegram import BotDeps, card_text, handle_update, result_text
from tests.conftest import WEBHOOK_SECRET, fake_oidc, fake_verifier

BASE = "https://proofcard.web.app"
BOT = "proofcard_bot"
PAPER, INK = (250, 250, 247), (17, 24, 39)


@pytest.fixture(scope="module")
def cards() -> InMemoryStore:
    store = InMemoryStore()
    sid = store.create_session(SessionDoc(owner_uid="u", topic="India"))
    run_prebunk(sid, Deps(store, StubModel(), FixtureFetcher(), InMemorySnapshots()), n=3)
    return store


def first(store: InMemoryStore) -> tuple[str, CardDoc]:
    return next(iter(store.cards.items()))


def jpeg(img: Image.Image, q: int, scale: float) -> bytes:
    small = img.resize((int(img.width * scale), int(img.height * scale)))
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=q)
    return buf.getvalue()


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def check(store: InMemoryStore, data: bytes) -> alter.CheckResult:
    return alter.check_image(data, store.get_card, BASE, BOT)


# ---------- render + ALTERED calibration ----------


def test_render_is_deterministic(cards: InMemoryStore) -> None:
    cid, card = first(cards)
    assert render(card, cid, BASE, BOT).tobytes() == render(card, cid, BASE, BOT).tobytes()


def test_wrap_truncates_with_ellipsis() -> None:
    lines = wrap("word " * 200, font(40), 500, 2)
    assert len(lines) == 2
    assert lines[-1].endswith("…")


@pytest.mark.parametrize(("q", "scale"), [(90, 1.0), (60, 0.75), (40, 0.5), (30, 0.6)])
def test_recompressed_original_is_verified(cards: InMemoryStore, q: int, scale: float) -> None:
    for cid, card in cards.cards.items():
        r = check(cards, jpeg(render(card, cid, BASE, BOT), q, scale))
        assert r.result == "VERIFIED", r.band_scores
        assert r.card_id == cid
        assert max(r.band_scores.values()) < alter.BAND_THRESHOLD


# band -> (box painted over, fill, replacement text at (x, y), font size, weight)
Edit = tuple[tuple[int, int, int, int], tuple[int, int, int], str, tuple[int, int], int, str]
EDITS: dict[str, Edit] = {
    "claim": ((300, 345, 620, 420), PAPER, "24", (300, 350), 66, "SemiBold"),
    "explanation": ((300, 790, 500, 830), PAPER, "1999", (300, 790), 34, "Regular"),
    "sources": ((90, 1100, 500, 1135), PAPER, "• fake-news.biz", (90, 1100), 28, "Medium"),
    "verdict": ((72, 160, 560, 290), (185, 28, 28), "", (0, 0), 28, "Regular"),
}


@pytest.mark.parametrize("band", list(EDITS))
def test_small_edit_is_altered(cards: InMemoryStore, band: str) -> None:
    cid, card = first(cards)
    img = render(card, cid, BASE, BOT)
    box, fill, text, xy, size, weight = EDITS[band]
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=fill)
    if text:
        d.text(xy, text, font=font(size, weight), fill=INK)
    r = check(cards, jpeg(img, 50, 0.66))
    assert r.result == "ALTERED"
    assert band in r.changed


def test_unknown_inputs(cards: InMemoryStore) -> None:
    cid, card = first(cards)
    assert check(cards, b"not an image").result == "UNKNOWN"
    assert check(cards, png(Image.new("RGB", (400, 500), PAPER))).reason.startswith("no Proof")
    cropped = render(card, cid, BASE, BOT).crop((0, 0, 1080, 1000))
    assert "cropped" in check(cards, png(cropped)).reason
    assert check(cards, b"x" * (alter.MAX_UPLOAD_BYTES + 1)).reason == "image too large"
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    assert check(cards, gif.getvalue()).reason == "unsupported image format"


def test_qr_for_missing_card_is_altered(cards: InMemoryStore) -> None:
    cid, card = first(cards)
    r = alter.check_image(png(render(card, cid, BASE, BOT)), lambda _: None, BASE, BOT)
    assert r.result == "ALTERED"


def test_text_similarity() -> None:
    assert alter.text_similarity("a b", "a b") == (1.0, [], [])
    sim, removed, added = alter.text_similarity("India has 22 languages", "India has 24 languages")
    assert removed == ["22"]
    assert added == ["24"]
    assert sim < 1
    assert alter.text_similarity("", "")[0] == 1.0


# ---------- HTTP: share page, images, checks ----------


class FakeBot:
    def __init__(self, image: bytes = b"") -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.image = image

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, payload))
        return {"ok": True}

    def download(self, file_id: str) -> bytes:
        if file_id == "huge":
            raise ValueError("file unavailable or over 20 MB")
        return self.image


@pytest.fixture
def http(cards: InMemoryStore) -> tuple[TestClient, FakeBot]:
    settings = Settings(
        env="test",
        telegram_webhook_secret=SecretStr(WEBHOOK_SECRET),
        telegram_bot_username=BOT,
        public_base_url=BASE,
        public_rate_per_min=100,
    )
    cid, card = first(cards)
    bot = FakeBot(png(render(card, cid, BASE, BOT)))
    deps = Deps(cards, StubModel(), FixtureFetcher(), InMemorySnapshots())
    app = create_app(
        settings=settings,
        verifier=fake_verifier,
        store=cards,
        deps=deps,
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
        bot_api=bot,
    )
    return TestClient(app), bot


def test_share_page_and_images(http: tuple[TestClient, FakeBot], cards: InMemoryStore) -> None:
    c, _ = http
    cid, card = first(cards)
    page = c.get(f"/v/{cid}")
    assert page.status_code == 200
    assert "og:image" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert card.card_sha256 in page.text
    for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg")):
        r = c.get(f"/v/{cid}.{ext}")
        assert r.headers["content-type"] == mime
        assert alter.read_card_id(Image.open(io.BytesIO(r.content))) == cid
    assert c.get("/v/nope-nope-nope").status_code == 404
    assert c.get("/v/nope-nope-nope.png").status_code == 404
    assert c.get("/v/bad!").status_code == 404


def test_share_page_escapes_html(cards: InMemoryStore) -> None:
    from app.share_page import card_page

    cid, card = first(cards)
    evil = card.model_copy(update={"claim": "<script>alert(1)</script>"})
    html = card_page(evil, cid, BASE, BOT)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_web_image_checks(http: tuple[TestClient, FakeBot], cards: InMemoryStore) -> None:
    c, bot = http
    cid, _ = first(cards)
    files = {"file": ("card.png", bot.image, "image/png")}
    r = c.post("/api/check/image", files=files)
    assert r.json()["result"] == "VERIFIED"
    page = c.post(f"/v/{cid}/check", files=files)
    assert "VERIFIED: the copy you uploaded" in page.text
    other = next(k for k in cards.cards if k != cid)
    assert "different card" in c.post(f"/v/{other}/check", files=files).text
    assert c.post("/v/nope-nope-nope/check", files=files).status_code == 404
    assert any(x.channel == "web" for x in cards.checks)


def test_web_text_check(http: tuple[TestClient, FakeBot], cards: InMemoryStore) -> None:
    c, _ = http
    cid, card = first(cards)
    ok = c.post("/api/check", json={"card_id": cid, "text": card.claim}).json()
    assert ok["result"] == "VERIFIED"
    bad = c.post("/api/check", json={"card_id": cid, "text": card.claim + " never"}).json()
    assert bad["result"] == "ALTERED"
    assert bad["added"] == ["never"]


def test_upload_size_cap(http: tuple[TestClient, FakeBot]) -> None:
    c, _ = http
    big = {"file": ("x.png", b"0" * (alter.MAX_UPLOAD_BYTES + 1), "image/png")}
    assert c.post("/api/check/image", files=big).status_code == 413


# ---------- Telegram ----------


def tg(c: TestClient, update: dict[str, Any]) -> None:
    hdr = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
    assert c.post("/tg/webhook", json={"update_id": 1, **update}, headers=hdr).json() == {
        "ok": True
    }


MSG = {"message_id": 7, "chat": {"id": 42, "type": "private"}}


def test_tg_photo_verified_with_button(http: tuple[TestClient, FakeBot]) -> None:
    c, bot = http
    tg(
        c,
        {
            "message": {
                **MSG,
                "photo": [{"file_id": "a", "file_unique_id": "u", "width": 1, "height": 1}],
            }
        },
    )
    method, payload = bot.calls[-1]
    assert method == "sendMessage"
    assert "VERIFIED" in payload["text"]
    assert payload["reply_markup"]["inline_keyboard"][0][0]["url"].startswith(f"{BASE}/v/")


def test_tg_document_too_big(http: tuple[TestClient, FakeBot]) -> None:
    c, bot = http
    doc = {"file_id": "huge", "mime_type": "image/png"}
    tg(c, {"message": {**MSG, "document": doc}})
    assert "over 20 MB" in bot.calls[-1][1]["text"]


def test_tg_text_lookup_and_help(http: tuple[TestClient, FakeBot], cards: InMemoryStore) -> None:
    c, bot = http
    cid, _ = first(cards)
    tg(c, {"message": {**MSG, "text": f"see {BASE}/v/{cid}"}})
    assert cid in bot.calls[-1][1]["text"]
    tg(c, {"message": {**MSG, "text": "/start nope-nope-nope"}})
    assert "doesn't exist" in bot.calls[-1][1]["text"]
    tg(c, {"message": {**MSG, "text": "hi"}})
    assert "Forward me" in bot.calls[-1][1]["text"]


def test_tg_inline_and_callback(http: tuple[TestClient, FakeBot], cards: InMemoryStore) -> None:
    c, bot = http
    cid, _ = first(cards)
    tg(c, {"inline_query": {"id": "q1", "query": cid}})
    method, payload = bot.calls[-1]
    assert method == "answerInlineQuery"
    assert payload["results"][0]["photo_url"] == f"{BASE}/v/{cid}.jpg"
    tg(c, {"inline_query": {"id": "q2", "query": "bad"}})
    assert bot.calls[-1][1]["results"] == []
    tg(c, {"callback_query": {"id": "cb"}})
    assert bot.calls[-1][0] == "answerCallbackQuery"


def test_tg_handler_crash_is_contained(http: tuple[TestClient, FakeBot]) -> None:
    c, bot = http

    def boom(method: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("telegram down")

    bot.call = boom  # type: ignore[method-assign]
    tg(c, {"message": {**MSG, "text": "hi"}})


def test_tg_text_helpers_escape(cards: InMemoryStore) -> None:
    cid, card = first(cards)
    evil = card.model_copy(update={"claim": "<b>x</b>"})
    assert "&lt;b&gt;x&lt;/b&gt;" in card_text(evil, cid)
    r = alter.CheckResult("ALTERED", "<i>", changed=[])
    assert "&lt;i&gt;" in result_text(r)
    assert "Can't check" in result_text(alter.CheckResult("UNKNOWN", "x"))


def test_tg_no_message_is_noop(cards: InMemoryStore) -> None:
    bot = FakeBot()
    deps = BotDeps(bot, cards.get_card, lambda b: alter.CheckResult("UNKNOWN", ""), BASE)
    handle_update(TgUpdate(update_id=1), deps)
    assert bot.calls == []
