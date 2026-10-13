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
from app.card_image import share_url
from app.logging_setup import pseudonymize
from app.schemas import CardDoc, TgUpdate

log = logging.getLogger("proofcard.telegram")

API = "https://api.telegram.org"
MAX_DOWNLOAD = 20 * 1024 * 1024
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
    "Forward me any <b>Proof Card</b> image and I'll tell you if it's the original or "
    "<b>ALTERED</b>.\nYou can also send a card link. Share a card in any chat by typing "
    "<code>@bot card-id</code>."
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

    file_id = None
    if m.photo:
        file_id = max(m.photo, key=lambda p: p.file_size or 0).file_id
    elif m.document and (m.document.mime_type or "").startswith("image/"):
        file_id = m.document.file_id

    if file_id:
        try:
            r = d.check_image(d.api.download(file_id))
        except ValueError as exc:
            r = CheckResult("UNKNOWN", str(exc))
        d.log_check(r, "telegram")
        payload: dict[str, Any] = {"chat_id": chat, "text": result_text(r), "parse_mode": "HTML"}
        if r.card_id and r.result != "UNKNOWN" and d.get_card(r.card_id):
            payload["reply_markup"] = _open_button(d.base_url, r.card_id)
        payload["reply_parameters"] = {"message_id": m.message_id}
        d.api.call("sendMessage", payload)
        return

    text = m.text or m.caption or ""
    ref = CARD_REF_RE.search(text)
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
    msg = "That card id doesn't exist." if ref else HELP
    d.api.call("sendMessage", {"chat_id": chat, "text": msg, "parse_mode": "HTML"})


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
                "photo_url": f"{base}.jpg",
                "thumbnail_url": f"{base}.jpg",
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
