"""Telegram Bot API client (the subset we use) + update handler.

Docs: https://core.telegram.org/bots/api
- The bot token lives only in memory (Secret Manager -> env). File download URLs contain
  the token, so they are never logged.
- Bots can download files up to 20 MB (getFile) and InlineQueryResultPhoto needs a JPEG
  photo_url; both limits are enforced here.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.alter import CheckResult
from app.card_image import card_image_url, share_url
from app.logging_setup import pseudonymize
from app.schemas import CardDoc, TgUpdate

log = logging.getLogger("proofcard.telegram")

API = "https://api.telegram.org"
MAX_DOWNLOAD = 20 * 1024 * 1024
ALERT_START_RE = re.compile(r"^/start\s+(alert[A-Za-z0-9_-]{44})\s*$")
START_RE = re.compile(r"^/start(?:\s+try)?\s*$")
SAMPLE_CLAIMS = (
    "We ended eight wars in eight months.",
    "India's GDP grew 8.2 percent in 2023-24, says the statistics ministry.",
)
TRY_HINT = "Tap a sample below to see a check, or send your own."
CARD_REF_RE = re.compile(r"(?:/v/|^/start\s+|^/check\s+)([A-Za-z0-9_-]{8,64})", re.MULTILINE)

VERDICT_EMOJI = {"TRUE": "🟢", "MISLEADING": "🟠", "FALSE": "🔴", "UNVERIFIABLE": "⚪"}


class BotApi(Protocol):
    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def download(self, file_id: str) -> bytes: ...


class HttpBotApi:  # pragma: no cover - network; behaviour covered with a fake
    def __init__(self, token: str, timeout: float = 15.0) -> None:
        import httpx

        self._token = token
        self._http = httpx.Client(timeout=timeout)

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._http.post(f"{API}/bot{self._token}/{method}", json=payload)
        data: dict[str, Any] = r.json()
        if not data.get("ok"):
            log.warning(
                "tg api error", extra={"fields": {"method": method, "code": data.get("error_code")}}
            )
        return data

    def download(self, file_id: str) -> bytes:
        info = self.call("getFile", {"file_id": file_id}).get("result") or {}
        if not info.get("file_path") or int(info.get("file_size") or 0) > MAX_DOWNLOAD:
            raise ValueError("file unavailable or over 20 MB")
        r = self._http.get(f"{API}/file/bot{self._token}/{info['file_path']}")
        r.raise_for_status()
        if len(r.content) > MAX_DOWNLOAD:
            raise ValueError("file over 20 MB")
        return r.content


@dataclass
class BotDeps:
    api: BotApi
    get_card: Callable[[str], CardDoc | None]
    check_image: Callable[[bytes], CheckResult]
    base_url: str
    log_check: Callable[[CheckResult, str], None] = field(default=lambda r, ch: None)
    # "/start alert..." deep link from the live page -> session topic, None if invalid
    link_alerts: Callable[[str, int], str | None] = field(default=lambda p, c: None)
    # any other text that reads like a claim -> queued for a full check, the result is sent
    # back by send_claim_result(). Calls ack() before the job is queued (so "checking" is
    # always the first reply), returns "queued", "limit" or "off" (no checker wired).
    # The last argument is the message id the verdicts reply to.
    check_claim: Callable[[list[str], int, Callable[[], None], int], str] = field(
        default=lambda t, c, ack, mid: "off"
    )
    # a long forward -> its checkable claims (max MAX_FORWARD_CLAIMS), [] = check it whole
    split_claims: Callable[[str], list[str]] = field(default=lambda t: [])
    # a screenshot / news graphic that is not a Proof Card -> the claims written on it
    read_image: Callable[[bytes], list[str]] = field(default=lambda b: [])


def _open_button(base_url: str, card_id: str) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "Open proof", "url": share_url(base_url, card_id)}]]}


def card_text(card: CardDoc, card_id: str) -> str:
    v = card.verdict.value
    src = ", ".join(
        sorted({re.sub(r"^https?://(www\.)?", "", str(s.url)).split("/")[0] for s in card.sources})
    )
    return (
        f"{VERDICT_EMOJI.get(v, '')} <b>{html.escape(v)}</b>\n"
        f"“{html.escape(card.claim)}”\n\n"
        f"{html.escape(card.explanation)}\n\n"
        f"Sources: {html.escape(src)} · card <code>{html.escape(card_id)}</code>"
    )


def result_text(r: CheckResult) -> str:
    if r.result == "VERIFIED":
        return "✅ <b>VERIFIED</b>: this is the original Proof Card, nothing was changed."
    if r.result == "ALTERED":
        what = html.escape(", ".join(r.changed) or r.reason)
        return f"⚠️ <b>ALTERED</b>: this card was edited ({what}). Open the original below."
    return f"🤔 Can't check this one: {html.escape(r.reason)}."


HELP = (
    "<b>Proof Card: hear a claim, see its proof.</b> Every verdict comes with its source.\n\n"
    "Send me a <b>claim</b> (a line from a speech, a forward, a headline) and I'll check it "
    "against official data and trusted sources, with the exact passage as proof.\n"
    "Forward a whole message or a <b>screenshot</b> and I'll check each claim in it.\n"
    "Add me to a group: I stay quiet and check forwards, or anything you tag me in.\n"
    "Forward a <b>Proof Card</b> image and I'll tell you if it's the original or "
    "<b>ALTERED</b>.\nShare a card in any chat: <code>@ProofCardAgentBot card-id</code>."
)
CHECKING = (
    "🔎 Checking this claim against official data and trusted sources. "
    "The verdict comes here with its proof, usually within a minute."
)
STILL_CHECKING = (
    "⏳ Still checking: this one needs more sources than usual. "
    "The verdict comes here as soon as it's proven, nothing to resend."
)
STILL_CHECKING_AFTER_S = 40.0
LIMIT = "You've hit today's limit of claim checks. Try again tomorrow."
NO_PROOF = (
    "⚪ <b>UNVERIFIABLE</b>\n“{claim}”\n\nNo trusted source we could open backs or "
    "refutes this exactly, so I won't call it true or false."
)
CHECKING_MANY = (
    "🔎 Found {n} checkable claims in this {what}. Checking each against official data "
    "and trusted sources; the verdicts come here one by one."
)
MIN_CLAIM_WORDS = 4
MAX_FORWARD_CLAIMS = 3
GROUP_TYPES = ("group", "supergroup")
MENTION_RE = re.compile(r"^/check(?:@\w+)?\s*|@\w+bot\b", re.IGNORECASE)
MIN_CLAIM_CHARS = 20


def looks_like_claim(text: str) -> bool:
    t = text.strip()
    return not t.startswith("/") and len(t) >= MIN_CLAIM_CHARS and len(t.split()) >= MIN_CLAIM_WORDS


def claim_lang(text: str) -> str:
    return "hi" if re.search(r"[\u0900-\u097F]", text) else "en"


def send_claim_result(
    api: BotApi,
    chat_id: int,
    claim: str,
    card: CardDoc | None,
    card_id: str | None,
    base: str,
    reply_to: int | None = None,
    label: str = "",
) -> None:
    """Verdict for a claim sent to the bot: the card PNG + proof button, or a plain
    UNVERIFIABLE when no source could prove it either way. `reply_to` threads it under
    the message it answers; `label` ("2/3") numbers the claims of one forward."""
    head = f"<b>Claim {html.escape(label)}</b> · " if label else ""
    # https://core.telegram.org/bots/api#replyparameters - still sent if the user
    # deleted their message.
    thread: dict[str, Any] = (
        {"reply_parameters": {"message_id": reply_to, "allow_sending_without_reply": True}}
        if reply_to
        else {}
    )
    if card is None or card_id is None:
        text = head + NO_PROOF.format(claim=html.escape(claim[:300]))
        api.call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML", **thread})
        return
    caption = head + card_text(card, card_id)
    if len(caption) > 1000:  # sendPhoto caption cap is 1024
        caption = caption[:997] + "…"
    api.call(
        "sendPhoto",
        {
            "chat_id": chat_id,
            "photo": card_image_url(base, card_id),
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": _open_button(base, card_id),
            **thread,
        },
    )


def handle_update(u: TgUpdate, d: BotDeps) -> None:
    if u.inline_query is not None:
        _inline(u, d)
        return
    if u.callback_query is not None:
        d.api.call("answerCallbackQuery", {"callback_query_id": u.callback_query.id})
        return
    m = u.message
    if m is None:
        return
    chat = m.chat.id
    log.info("tg message", extra={"fields": {"chat": pseudonymize(chat)}})

    group = m.chat.type in GROUP_TYPES
    forwarded = m.forward_origin is not None
    file_id = None
    if m.photo:
        file_id = max(m.photo, key=lambda p: p.file_size or 0).file_id
    elif m.document and (m.document.mime_type or "").startswith("image/"):
        file_id = m.document.file_id

    if file_id:
        data = b""
        try:
            data = d.api.download(file_id)
            r = d.check_image(data)
        except ValueError as exc:
            r = CheckResult("UNKNOWN", str(exc))
        d.log_check(r, "telegram")
        if r.result == "UNKNOWN" and r.card_id is None and data:
            # Not a Proof Card: a screenshot of a forward or a news graphic. Read the
            # claims written on it and check them like a typed claim.
            claims = _image_claims(d, data)
            if claims and _check(d, m.message_id, chat, claims, "image"):
                return
            if group and not forwarded:
                return  # a group's ordinary photo is not ours to answer
        payload: dict[str, Any] = {"chat_id": chat, "text": result_text(r), "parse_mode": "HTML"}
        if r.card_id and r.result != "UNKNOWN" and d.get_card(r.card_id):
            payload["reply_markup"] = _open_button(d.base_url, r.card_id)
        payload["reply_parameters"] = {"message_id": m.message_id}
        d.api.call("sendMessage", payload)
        return

    text = raw = m.text or m.caption or ""
    addressed = not group or forwarded or MENTION_RE.search(text) is not None
    if group:
        text = MENTION_RE.sub(" ", text).strip()
    if (alert := ALERT_START_RE.match(text)) is not None:
        topic = d.link_alerts(alert.group(1), chat)
        msg = (
            f"Alerts on for <b>{html.escape(topic[:80])}</b>. I'll send FALSE and MISLEADING "
            "cards here the moment they're heard."
            if topic is not None
            else "That alert link has expired. Tap <b>Telegram alerts</b> on the live page again."
        )
        d.api.call("sendMessage", {"chat_id": chat, "text": msg, "parse_mode": "HTML"})
        return
    ref = CARD_REF_RE.search(raw)
    card = d.get_card(ref.group(1)) if ref else None
    if ref and card:
        d.api.call(
            "sendMessage",
            {
                "chat_id": chat,
                "text": card_text(card, ref.group(1)),
                "parse_mode": "HTML",
                "reply_markup": _open_button(d.base_url, ref.group(1)),
                "link_preview_options": {"is_disabled": True},
            },
        )
        return
    if not ref and addressed and looks_like_claim(text):
        try:
            claims = d.split_claims(text.strip())[:MAX_FORWARD_CLAIMS]
        except Exception:
            log.warning("forward split failed, checking it whole", exc_info=True)
            claims = []
        if _check(d, m.message_id, chat, claims or [text.strip()], "forward"):
            return
    if group:
        return  # never post help or errors into someone's group chat
    msg = "That card id doesn't exist." if ref else HELP
    reply: dict[str, Any] = {"chat_id": chat, "text": msg, "parse_mode": "HTML"}
    if not ref and START_RE.match(raw):
        # Opened from the site (t.me/<bot>?start=try): one tap sends a sample claim, so
        # the first check happens without typing anything.
        reply["text"] = f"{msg}\n\n{TRY_HINT}"
        reply["reply_markup"] = {
            "keyboard": [[{"text": c}] for c in SAMPLE_CLAIMS],
            "one_time_keyboard": True,
            "resize_keyboard": True,
            "input_field_placeholder": "Paste a claim or forward a message",
        }
    d.api.call("sendMessage", reply)


def _image_claims(d: BotDeps, data: bytes) -> list[str]:
    try:
        claims = [c.strip() for c in d.read_image(data) if c.strip()]
    except Exception:
        log.warning("image claim read failed", exc_info=True)
        return []
    return [c for c in claims if looks_like_claim(c)][:MAX_FORWARD_CLAIMS]


def _check(d: BotDeps, message_id: int, chat: int, claims: list[str], what: str) -> bool:
    """Queue the claims; True when the bot answered (queued or over the limit)."""

    def say(msg: str) -> None:
        d.api.call(
            "sendMessage",
            {"chat_id": chat, "text": msg, "reply_parameters": {"message_id": message_id}},
        )

    ack = CHECKING if len(claims) == 1 else CHECKING_MANY.format(n=len(claims), what=what)
    state = d.check_claim(claims, chat, lambda: say(ack), message_id)
    if state == "limit":
        say(LIMIT)
    return state != "off"


def _inline(u: TgUpdate, d: BotDeps) -> None:
    q = u.inline_query
    if q is None:
        return
    cid = q.query.strip().split("/")[-1]
    results: list[dict[str, Any]] = []
    card = d.get_card(cid) if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", cid) else None
    if card is not None:
        base = share_url(d.base_url, cid)
        results.append(
            {
                "type": "photo",
                "id": cid[:64],
                "photo_url": card_image_url(d.base_url, cid, "jpg"),
                "thumbnail_url": card_image_url(d.base_url, cid, "jpg"),
                "photo_width": 1080,
                "photo_height": 1350,
                "caption": f"{card.verdict.value}: {card.claim[:180]}\nProof: {base}",
                "reply_markup": _open_button(d.base_url, cid),
            }
        )
    d.api.call(
        "answerInlineQuery",
        {"inline_query_id": q.id, "results": results, "cache_time": 300},
    )
