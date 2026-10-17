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
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from app.card_image import card_image_url, share_url
from app.schemas import ClaimSource, SessionDoc
from app.store import Store
from app.telegram import BotApi, send_photo

log = logging.getLogger("proofcard.alerts")

PREFIX = "alert"
SID_LEN = 22  # store.new_id(): token_urlsafe(16)
SECRET_LEN = 22
LINK_TTL = timedelta(minutes=15)
MAX_ALERTS = 10
ALERT_VERDICTS = frozenset({"FALSE", "MISLEADING"})
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_moment(url: str | None, t: float | None) -> str | None:
    """https://youtu.be/<id>?t=<s> for the speech video at the moment the claim was said.
    None when there is no YouTube link or the id can't be read. No t: the video start."""
    if not url:
        return None
    u = urlsplit(url)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = ""
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host == "youtube.com":
        parts = [p for p in u.path.split("/") if p]
        if parts[:1] == ["watch"]:
            vid = (parse_qs(u.query).get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "live", "embed"):
            vid = parts[1]
    if not _YT_ID.match(vid):
        return None
    if t is None or t < 0:
        return f"https://youtu.be/{vid}"
    return f"https://youtu.be/{vid}?t={int(t)}"


def _clock(t: float) -> str:
    s = int(t)
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


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
        sid,
        alert_chat_id=chat_id,
        tg_link_hash=None,
        tg_link_exp=None,
        alerts_sent=0,
        tg_run_open=s.status == "live",  # linked mid run: its summary still comes
    )
    # Linked once: every later live run or clip of this user alerts this chat with no tap
    # (a bot may message a chat only after the person pressed Start, so the first link
    # stays a tap: https://core.telegram.org/bots/features#deep-linking).
    store.put_tg_chat(s.owner_uid, chat_id)
    return s


def _verdict(v: object) -> str:
    return str(getattr(v, "value", v) or "")


SUMMARY_ICONS = (("FALSE", "🔴"), ("MISLEADING", "🟠"), ("TRUE", "🟢"), ("UNVERIFIABLE", "⚪"))


class Alerter:
    def __init__(self, api: BotApi, store: Store, base_url: str) -> None:
        self.api, self.store, self.base_url = api, store, base_url

    def _live_button(self, session_id: str) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}/s/{session_id}/live"
        return {"inline_keyboard": [[{"text": "Open live page", "url": url}]]}

    def attach(self, session_id: str) -> SessionDoc | None:
        """A run is starting: link the owner's Telegram if they linked it once before."""
        s = self.store.get_session(session_id)
        if s is None or s.alert_chat_id is not None:
            return s
        chat = self.store.get_tg_chat(s.owner_uid)
        if chat is None:
            return s
        self.store.update_session(session_id, alert_chat_id=chat)
        return s.model_copy(update={"alert_chat_id": chat})

    def started(self, session_id: str, what: str) -> bool:
        """One "checking now" line per run, so the chat knows the feed is on."""
        s = self.attach(session_id)
        if s is None or s.alert_chat_id is None or s.tg_run_open:
            return False
        self.store.update_session(session_id, tg_run_open=True, alerts_sent=0)
        self.api.call(
            "sendMessage",
            {
                "chat_id": s.alert_chat_id,
                "text": (
                    f"🔴 <b>Checking {html.escape(what)}</b> · <i>{html.escape(s.topic[:80])}</i>\n"
                    "FALSE and MISLEADING claims land here the moment they're heard, with "
                    "the proof. A summary of every verdict follows when it ends."
                ),
                "parse_mode": "HTML",
                "reply_markup": self._live_button(session_id),
            },
        )
        return True

    def summary(self, session_id: str) -> bool:
        """The run ended: every verdict it produced, counted, once."""
        s = self.store.get_session(session_id)
        if s is None or s.alert_chat_id is None or not s.tg_run_open:
            return False
        self.store.update_session(session_id, tg_run_open=False)
        seen = [
            _verdict(c.verdict)
            for _, c in self.store.list_claims(session_id)
            if c.verdict is not None and c.source == ClaimSource.LIVE
        ]
        if seen:
            counts = " · ".join(
                f"{icon} {seen.count(v)} {v}" for v, icon in SUMMARY_ICONS if seen.count(v)
            )
            body = f"{len(seen)} claims checked: {counts}"
        else:
            body = "No checkable claim was heard."
        self.api.call(
            "sendMessage",
            {
                "chat_id": s.alert_chat_id,
                "text": f"✅ <b>Done</b> · <i>{html.escape(s.topic[:80])}</i>\n{body}",
                "parse_mode": "HTML",
                "reply_markup": self._live_button(session_id),
            },
        )
        return True

    def alert(
        self, session_id: str, card_id: str, verdict: object, text: str, t: float | None = None
    ) -> bool:
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
        buttons = [{"text": "Open proof", "url": share_url(self.base_url, card_id)}]
        moment = youtube_moment(s.youtube_url, t)
        if moment:
            label_t = f"Watch at {_clock(t)}" if t is not None and t >= 0 else "Watch speech"
            buttons.append({"text": label_t, "url": moment})
        send_photo(
            self.api,
            {
                "chat_id": s.alert_chat_id,
                "photo": card_image_url(self.base_url, card_id),
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": [buttons]},
            },
        )
        log.info("alert sent", extra={"fields": {"n": s.alerts_sent + 1}})
        return True
