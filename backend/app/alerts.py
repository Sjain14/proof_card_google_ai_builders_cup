"""Telegram alerts (During): FALSE / MISLEADING cards land in the viewer's Telegram.

Linking is a bot deep link, the standard way to tie a Telegram chat to an account on
another service: https://core.telegram.org/bots/features#deep-linking
    t.me/<bot>?start=alert<session_id><secret>
The start payload allows [A-Za-z0-9_-], up to 64 chars: 5 + 22 + 22 = 49. The session
keeps only sha256(secret) and an expiry; the link is single use and dies in 15 minutes.
Only the session owner can mint one (the endpoint checks ownership), so a forwarded link
can't attach a stranger to someone else's feed after it was redeemed.

Alerts carry the card PNG by URL (Telegram fetches /v/<card>.png, already public and
immutable) plus an "Open proof" button. Capped per session so a long debate can't spam.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import secrets
from datetime import UTC, datetime, timedelta

from app.card_image import share_url
from app.schemas import SessionDoc
from app.store import Store
from app.telegram import BotApi

log = logging.getLogger("proofcard.alerts")

PREFIX = "alert"
SID_LEN = 22  # store.new_id(): token_urlsafe(16)
SECRET_LEN = 22
LINK_TTL = timedelta(minutes=15)
MAX_ALERTS = 10
ALERT_VERDICTS = frozenset({"FALSE", "MISLEADING"})


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def new_link(store: Store, session_id: str, bot_username: str, now: datetime | None = None) -> str:
    secret = secrets.token_urlsafe(16)
    store.update_session(
        session_id, tg_link_hash=_hash(secret), tg_link_exp=(now or _now()) + LINK_TTL
    )
    return f"https://t.me/{bot_username}?start={PREFIX}{session_id}{secret}"


def redeem(
    store: Store, payload: str, chat_id: int, now: datetime | None = None
) -> SessionDoc | None:
    """`/start alert...` from the bot: attach this chat to the session, burn the link."""
    if not payload.startswith(PREFIX) or len(payload) != len(PREFIX) + SID_LEN + SECRET_LEN:
        return None
    sid = payload[len(PREFIX) : len(PREFIX) + SID_LEN]
    secret = payload[len(PREFIX) + SID_LEN :]
    s = store.get_session(sid)
    if s is None or not s.tg_link_hash or s.tg_link_exp is None:
        return None
    if s.tg_link_exp < (now or _now()) or not hmac.compare_digest(s.tg_link_hash, _hash(secret)):
        return None
    store.update_session(
        sid, alert_chat_id=chat_id, tg_link_hash=None, tg_link_exp=None, alerts_sent=0
    )
    return s


def _verdict(v: object) -> str:
    return str(getattr(v, "value", v) or "")


class Alerter:
    def __init__(self, api: BotApi, store: Store, base_url: str) -> None:
        self.api, self.store, self.base_url = api, store, base_url

    def alert(self, session_id: str, card_id: str, verdict: object, text: str) -> bool:
        label = _verdict(verdict)
        if label not in ALERT_VERDICTS:
            return False
        s = self.store.get_session(session_id)
        if s is None or s.alert_chat_id is None or s.alerts_sent >= MAX_ALERTS:
            return False
        self.store.update_session(session_id, alerts_sent=s.alerts_sent + 1)
        caption = (
            f"⚠️ <b>{label}</b> · just heard on <i>{html.escape(s.topic[:80])}</i>\n"
            f"“{html.escape(text[:300])}”\n"
            "Forward this card anywhere: send it back to me and I'll say if it was edited."
        )
        self.api.call(
            "sendPhoto",
            {
                "chat_id": s.alert_chat_id,
                "photo": f"{self.base_url.rstrip('/')}/v/{card_id}.png",
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Open proof", "url": share_url(self.base_url, card_id)}]
                    ]
                },
            },
        )
        log.info("alert sent", extra={"fields": {"n": s.alerts_sent + 1}})
        return True
