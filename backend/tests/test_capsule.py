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
    assert "Send me a <b>claim</b>" in bot.calls[-1][1]["text"]


def test_tg_claim_text_is_checked_and_answered(
    http: tuple[TestClient, FakeBot], cards: InMemoryStore
) -> None:
    c, bot = http
    claim = "India's GDP grew 8.2 percent in 2023-24 says the statistics ministry"
    tg(c, {"message": {**MSG, "text": claim}})
    sent = [m for m, _ in bot.calls]
    assert sent[-2] == "sendMessage"
    assert "Checking this claim" in bot.calls[-2][1]["text"]
    assert bot.calls[-2][1]["reply_parameters"] == {"message_id": 7}
    method, payload = bot.calls[-1]
    assert payload["chat_id"] == 42
    if method == "sendPhoto":
        assert payload["photo"].endswith(".png")
        assert payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "Open proof"
    else:
        assert "UNVERIFIABLE" in payload["text"]


def test_tg_claim_daily_limit(http: tuple[TestClient, FakeBot]) -> None:
    from app import main as main_mod

    c, bot = http
    for _ in range(main_mod.BOT_DAILY_CHECKS):
        tg(c, {"message": {**MSG, "text": "Petrol costs 50 rupees a litre in Delhi today"}})
    tg(c, {"message": {**MSG, "text": "Petrol costs 50 rupees a litre in Delhi today"}})
    assert "today's limit" in bot.calls[-1][1]["text"]


def test_tg_claim_result_helpers(cards: InMemoryStore) -> None:
    from app.telegram import claim_lang, looks_like_claim, send_claim_result

    assert claim_lang("भारत की जीडीपी बड़ी है") == "hi"
    assert claim_lang("GDP grew") == "en"
    assert not looks_like_claim("/start abc def ghi jkl mno")
    assert not looks_like_claim("too short")
    bot = FakeBot()
    send_claim_result(bot, 1, "<x> claim", None, None, BASE)
    assert "UNVERIFIABLE" in bot.calls[-1][1]["text"]
    assert "&lt;x&gt;" in bot.calls[-1][1]["text"]
    cid, card = first(cards)
    long = card.model_copy(update={"explanation": "y" * 2000})
    send_claim_result(bot, 1, "c", long, cid, BASE)
    assert bot.calls[-1][0] == "sendPhoto"
    assert len(bot.calls[-1][1]["caption"]) <= 1000


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


# ---------- bot automation (p40) ----------


def _bot(**kw: Any) -> tuple[FakeBot, BotDeps, list[list[str]]]:
    seen: list[list[str]] = []

    def check(claims: list[str], chat: int, ack: Any) -> str:
        seen.append(claims)
        ack()
        return "queued"

    bot = FakeBot(b"\x89PNG not a card")
    deps = BotDeps(
        bot,
        lambda cid: None,
        lambda b: alter.CheckResult("UNKNOWN", "no QR"),
        BASE,
        check_claim=check,
        **kw,
    )
    return bot, deps, seen


def _msg(chat_type: str = "private", **kw: Any) -> TgUpdate:
    m = {"message_id": 7, "chat": {"id": 42, "type": chat_type}, **kw}
    return TgUpdate.model_validate({"update_id": 1, "message": m})


GDP = "India's GDP grew 8.2 percent in 2023-24 says the statistics ministry"
CPI = "Retail inflation in India fell to 4.8 percent in May 2024"


def test_tg_long_forward_is_split_into_its_claims() -> None:
    bot, deps, seen = _bot(split_claims=lambda t: [GDP, CPI, "hi"])
    handle_update(_msg(text=f"{GDP}. {CPI}. Forward to everyone!"), deps)
    assert seen == [[GDP, CPI, "hi"]]
    assert "Found 3 checkable claims in this forward" in bot.calls[-1][1]["text"]


def test_tg_split_failure_checks_the_forward_whole() -> None:
    def boom(t: str) -> list[str]:
        raise RuntimeError("model down")

    _, deps, seen = _bot(split_claims=boom)
    handle_update(_msg(text=GDP), deps)
    assert seen == [[GDP]]


def test_tg_screenshot_claims_are_read_and_checked() -> None:
    photo = [{"file_id": "a", "file_unique_id": "u", "width": 1, "height": 1}]
    bot, deps, seen = _bot(read_image=lambda b: [GDP, "lol"])
    handle_update(_msg(photo=photo), deps)
    assert seen == [[GDP]]  # "lol" is not a claim
    assert "Checking this claim" in bot.calls[-1][1]["text"]
    # nothing readable -> the old answer
    bot, deps, seen = _bot(read_image=lambda b: [])
    handle_update(_msg(photo=photo), deps)
    assert not seen
    assert "Can't check" in bot.calls[-1][1]["text"]
    # reader crash -> the old answer, never a crash
    bot, deps, seen = _bot(read_image=lambda b: 1 / 0)
    handle_update(_msg(photo=photo), deps)
    assert "Can't check" in bot.calls[-1][1]["text"]


def test_tg_group_stays_quiet_unless_addressed(cards: InMemoryStore) -> None:
    photo = [{"file_id": "a", "file_unique_id": "u", "width": 1, "height": 1}]
    bot, deps, seen = _bot()
    handle_update(_msg("group", text="hi all"), deps)
    handle_update(_msg("group", text=GDP), deps)
    handle_update(_msg("supergroup", photo=photo), deps)
    assert bot.calls == []
    assert seen == []
    handle_update(_msg("group", text=f"@ProofCardAgentBot {GDP}"), deps)
    handle_update(_msg("group", text=f"/check@ProofCardAgentBot {CPI}"), deps)
    handle_update(_msg("group", text=GDP, forward_origin={"type": "user"}), deps)
    assert seen == [[GDP], [CPI], [GDP]]
    cid, _ = first(cards)
    bot2, deps2, _ = _bot()
    deps2.get_card = cards.get_card
    handle_update(_msg("group", text=f"/check {cid}"), deps2)
    assert cid in bot2.calls[-1][1]["text"]


def test_tg_forward_through_the_app_sends_one_verdict_per_claim(
    http: tuple[TestClient, FakeBot],
) -> None:
    c, bot = http
    a = "India has 22 languages in the Eighth Schedule of the Constitution"
    b = "India's GDP grew 8.2 percent in 2023-24 says the statistics ministry"
    long = f"{a}. {b}. " + "Share this with every family group before it gets deleted. " * 3
    c.app.state.live.spotter.spot_claims = lambda t: [a, b]  # type: ignore[attr-defined]
    n = len(bot.calls)
    tg(c, {"message": {**MSG, "chat": {"id": 4242, "type": "private"}, "text": long}})
    out = bot.calls[n:]
    assert "Found 2 checkable claims" in out[0][1]["text"]
    assert len(out) == 3  # ack + one verdict per claim


# ---------- how-to pass (p42): card page actions, bot opened from the site ----------


def test_share_page_says_what_it_is_and_every_share_is_prefilled(cards: InMemoryStore) -> None:
    from app.share_page import card_page

    cid, card = first(cards)
    page = card_page(card, cid, BASE, BOT)
    assert "This is a <b>Proof Card</b>" in page
    assert "https://wa.me/?text=" in page
    assert "https://t.me/share/url?url=" in page
    assert f"https://t.me/{BOT}?start={cid}" in page  # bot opens with this card, no typing
    # the card image repeats the page: offered as a download, never shown twice
    assert "<img" not in page
    assert f"/v/{cid}.png" in page


def test_bot_opened_from_the_site_offers_one_tap_samples(cards: InMemoryStore) -> None:
    from app.telegram import SAMPLE_CLAIMS, looks_like_claim

    bot = FakeBot()
    deps = BotDeps(bot, cards.get_card, lambda b: alter.CheckResult("UNKNOWN", "x"), BASE)
    for text in ("/start try", "/start"):
        handle_update(
            TgUpdate.model_validate({"update_id": 1, "message": {**MSG, "text": text}}), deps
        )
        payload = bot.calls[-1][1]
        assert "Send me a <b>claim</b>" in payload["text"]
        assert [r[0]["text"] for r in payload["reply_markup"]["keyboard"]] == list(SAMPLE_CLAIMS)
    assert all(looks_like_claim(c) for c in SAMPLE_CLAIMS)  # a tap is checked like typing
    handle_update(_msg(text="hi"), deps)
    assert "reply_markup" not in bot.calls[-1][1]
