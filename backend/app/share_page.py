"""Server rendered /v/<card_id> share page (the Proof Capsule).

Server side so link previews (Telegram, WhatsApp, X) read Open Graph tags without JS,
and the page works on any phone with zero JS. Every dynamic value is html escaped.
OG tags: https://ogp.me/
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from urllib.parse import quote, urlsplit

from app.alter import CheckResult
from app.card_image import RENDER_REV, share_url
from app.schemas import CardDoc, Verdict

LABEL = {
    Verdict.TRUE: ("True", "सही", "#15803D"),
    Verdict.MISLEADING: ("Misleading", "भ्रामक", "#B45309"),
    Verdict.FALSE: ("False", "गलत", "#B91C1C"),
    Verdict.UNVERIFIABLE: ("Not enough proof", "पुख्ता सबूत नहीं", "#6B7280"),
}

CSP = (
    "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
    "frame-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)

CSS = """
body{margin:0;background:#FAFAF7;color:#111827;font:16px/1.55 system-ui,"Noto Sans",
"Noto Sans Devanagari",sans-serif}main{max-width:720px;margin:0 auto;padding:28px 20px 64px}
.top{display:flex;justify-content:space-between;margin-bottom:24px;color:#6B7280;font-size:13px}
.brand{font-weight:800;letter-spacing:.08em;color:#1F4FFF;text-decoration:none}
.pill{display:inline-block;padding:8px 18px;border-radius:999px;color:#fff;font-weight:800;
text-transform:uppercase;letter-spacing:.04em}.hi{margin-left:10px;font-weight:600}
h1{font-size:clamp(24px,5vw,34px);line-height:1.25;margin:18px 0 12px}.why{font-size:18px}
.meta{color:#6B7280;font-size:14px}section{border-top:1px solid #E5E7EB;margin-top:28px}
.src{background:#fff;border:1px solid #E5E7EB;border-radius:14px;padding:16px;margin:12px 0}
a{color:#1F4FFF;overflow-wrap:anywhere}blockquote{margin:10px 0;padding-left:12px;
border-left:3px solid #1F4FFF}code{font-size:12px;word-break:break-all;color:#6B7280}
img{width:100%;border-radius:16px;border:1px solid #E5E7EB}
button{background:#1F4FFF;color:#fff;border:0;border-radius:10px;padding:10px 16px;font-weight:700}
.r{border-radius:14px;padding:18px;margin:0 0 20px;font-weight:700}
.VERIFIED{background:#ECFDF3;color:#15803D}.ALTERED{background:#FEF2F2;color:#B91C1C}
.UNKNOWN{background:#F3F4F6;color:#374151}
.gsugg{display:block;width:100%;height:76px;border:0;margin:4px 0 16px}
ul{padding-left:18px}.up{display:inline-block;border:1.5px dashed #1F4FFF;border-radius:10px;
padding:9px 14px;color:#1F4FFF;font-weight:650;cursor:pointer}.up input{display:block;
font-size:13px;margin-top:6px;color:#6B7280;max-width:100%}
@media(max-width:560px){.acts a{flex:1 1 calc(50% - 8px);text-align:center}}
.upr{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start}
.what{background:#EEF2FF;border-radius:12px;padding:12px 14px;font-size:14px;margin:0 0 18px}
.acts{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 4px}.acts a{display:inline-block;
padding:9px 14px;border-radius:10px;border:1.5px solid #E5E7EB;color:#111827;font-weight:650;
font-size:14px;text-decoration:none;word-break:normal}.acts a.main{background:#1F4FFF;
color:#fff;border-color:#1F4FFF}details summary{cursor:pointer;font-weight:650;margin:14px 0}
.rep summary{color:#6B7280;font-size:14px}.rep label{display:block;font-weight:650;font-size:14px;
margin:14px 0 0}.rep label span{color:#6B7280;font-weight:400}.rep textarea,.rep input{
display:block;width:100%;box-sizing:border-box;font:inherit;font-size:15px;
border:1.5px solid #E5E7EB;border-radius:10px;padding:10px 12px;margin-top:6px;background:#fff}
.rep textarea{resize:vertical}.rep button{margin-top:16px}.rep .src{margin:4px 0 0}
.err{background:#FEF2F2;color:#B91C1C}
.ok{background:#ECFDF3;color:#15803D}
"""

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ISSUE_MAX = 2000


@dataclass(frozen=True)
class ReportState:
    """What the report form shows after a post: a message, and the fields to refill."""

    msg: str = ""
    ok: bool = False
    form: dict[str, str] = field(default_factory=dict)


def report_error(form: dict[str, str]) -> str:
    """The first problem with a report, in words a reader understands; "" when fine."""
    issue, email, src = form.get("issue", ""), form.get("email", ""), form.get("source_url", "")
    if not issue:
        return "Tell us what is wrong with this card. That field is required."
    if len(issue) > ISSUE_MAX:
        return f"Please keep it under {ISSUE_MAX} characters."
    if email and (len(email) > 254 or not EMAIL_RE.match(email)):
        return "That email does not look right. Fix it or leave it empty."
    if src and (
        len(src) > 2000
        or urlsplit(src).scheme not in ("http", "https")
        or not urlsplit(src).hostname
    ):
        return "The source link should be a full web address (https://...), or leave it empty."
    return ""


def _page(title: str, desc: str, url: str, body: str) -> str:
    t, d, u = escape(title), escape(desc), escape(url)
    og = (
        f'<meta property="og:title" content="{t}"><meta property="og:description" content="{d}">'
        f'<meta property="og:url" content="{u}">'
        f'<meta property="og:image" content="{u}.jpg?r={RENDER_REV}">'
        '<meta name="twitter:card" content="summary_large_image">'
        if url
        else ""
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{t}</title><meta name="description" content="{d}">{og}'
        f'<meta name="robots" content="noindex"><style>{CSS}</style></head><body><main>'
        '<div class="top"><a class="brand" href="/">PROOF CARD</a></div>'
        f"{body}</main></body></html>"
    )


def _check_banner(c: CheckResult) -> str:
    msg = {
        "VERIFIED": "VERIFIED: the copy you uploaded is the original card.",
        "ALTERED": f"ALTERED: the copy you uploaded was edited ({', '.join(c.changed)}). "
        "The real card is below.",
    }.get(c.result, f"Couldn't check: {c.reason}.")
    return f'<div class="r {c.result}" role="status">{escape(msg)}</div>'


# The suggestion frame: Google's HTML runs on its own document (own CSP, no scripts,
# sandboxed), never inline on our page. Popups escape the sandbox so a tap opens the
# Google results page directly, as the grounding display rules require.
SUGGESTION_SANDBOX = "allow-popups allow-popups-to-escape-sandbox"
SUGGESTION_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data: https:; "
    "font-src https: data:; frame-ancestors 'self'"
)


def suggestion_frame(card: CardDoc, card_id: str) -> str:
    if not card.search_suggestion_html:
        return ""
    return (
        f'<iframe class="gsugg" src="/api/cards/{escape(card_id)}/search-suggestion" '
        f'sandbox="{SUGGESTION_SANDBOX}" title="Google Search suggestions" '
        'referrerpolicy="no-referrer" loading="lazy"></iframe>'
    )


def suggestion_doc(html: str) -> str:
    """Wrapper only: the suggestion markup itself goes in byte for byte."""
    return (
        '<!doctype html><html><head><meta charset="utf-8"><base target="_blank">'
        "<style>html,body{margin:0;padding:0;background:transparent}</style></head>"
        f"<body>{html}</body></html>"
    )


def card_page(
    card: CardDoc,
    card_id: str,
    base_url: str,
    bot: str = "",
    check: CheckResult | None = None,
    report: ReportState | None = None,
) -> str:
    url = share_url(base_url, card_id)
    en, hi, colour = LABEL[card.verdict]
    parts = [_check_banner(check)] if check else []
    if not check:
        # Team lead (VN): "what is the user supposed to do with this link?"
        parts.append(
            '<p class="what">This is a <b>Proof Card</b>: a claim, its verdict and the exact '
            "source passage that decides it. Share this link; anyone who opens it sees the "
            "same proof, and an edited copy of the card is caught.</p>"
        )
    parts.append(
        f'<span class="pill" style="background:{colour}">{escape(en)}</span>'
        f'<span class="hi" style="color:{colour}">{escape(hi)}</span>'
        f'<h1>“{escape(card.claim)}”</h1><p class="why">{escape(card.explanation)}</p>'
        + suggestion_frame(card, card_id)
        + _actions(card, card_id, url, bot)
        + f'<p class="meta">Issued {card.created_at:%d %b %Y %H:%M} UTC</p>'
        "<section><h2>Proof: the passage that decides it</h2>"
    )
    hashes = []
    b = escape(bot)
    for s in card.sources:
        u = escape(str(s.url))
        parts.append(
            f'<div class="src"><a href="{u}" rel="noopener nofollow">{escape(_short(s.url))}</a>'
            f"<blockquote>{escape(s.snippet)}</blockquote>"
            f'<span class="meta">fetched {s.fetched_at:%d %b %Y %H:%M} UTC</span></div>'
        )
        hashes.append(
            f'<li><a href="/api/snapshots/{escape(s.snapshot_sha256)}" rel="nofollow">'
            f"<code>{escape(s.snapshot_sha256)}</code></a></li>"
        )
    # The hashes are for verifiers, not readers: folded, one place, never repeated.
    parts.append(
        "<details><summary>Check the proof yourself</summary>"
        '<p class="meta">We fetched each page ourselves and stored its exact bytes. Download '
        "a stored page and run <code>sha256sum</code>: it must match.</p>"
        f"<ul>{''.join(hashes)}</ul>"
        f'<p class="meta">Card fingerprint <code>{escape(card.card_sha256)}</code> · '
        f"source match {card.support_score:.2f}</p></details></section>"
        "<section><h2>Got this card forwarded?</h2>"
        '<p class="meta">Upload the image you received'
        + (f' (or forward it to <a href="https://t.me/{b}">@{b}</a>)' if bot else "")
        + ": we tell you if it is this card or an edited copy.</p>"
        f'<form method="post" action="/v/{escape(card_id)}/check" enctype="multipart/form-data">'
        '<div class="upr"><label class="up">Choose the card image<input type="file" name="file" '
        'accept="image/png,image/jpeg,image/webp" required aria-label="card image"></label> '
        "<button>Check it</button></div></form>"
    )
    # No card image on the page: it repeats everything above (Team lead, VN).
    # "Download image" and the link preview (og:image) carry it.
    parts.append("</section>")
    parts.append(_report_form(card, card_id, report))
    return _page(f"{en}: {card.claim[:90]}", card.explanation[:200], url, "".join(parts))


def _report_form(card: CardDoc, card_id: str, state: ReportState | None) -> str:
    """Folded at the very bottom: "Report this card", prefilled with the card it is about.
    Opens by itself after a post, so the reader sees the result or what to fix."""
    st = state or ReportState()
    en, _, _ = LABEL[card.verdict]
    cid = escape(card_id)
    msg = f'<div class="r {"ok" if st.ok else "err"}" role="status">{escape(st.msg)}</div>'
    if st.ok:
        return f'<section class="rep" id="report"><h2>Report this card</h2>{msg}</section>'
    v = {k: escape(st.form.get(k, "")) for k in ("issue", "email", "source_url")}
    return (
        f'<section class="rep" id="report"><details{" open" if st.msg else ""}>'
        "<summary>Something wrong with this card? Report it</summary>"
        + (msg if st.msg else "")
        + '<p class="meta">AI can get things wrong. Tell us what is off and we will look at '
        "this card again.</p>"
        f'<div class="src"><span class="meta">You are reporting</span><br><b>{escape(en)}</b>: '
        f"“{escape(card.claim)}”<br><code>{cid}</code></div>"
        f'<form method="post" action="/v/{cid}/report#report">'
        '<label for="r-issue">What is wrong? <span>(required)</span></label>'
        f'<textarea id="r-issue" name="issue" rows="4" required maxlength="{ISSUE_MAX}" '
        f'placeholder="e.g. the source says 2023, not 2024">{v["issue"]}</textarea>'
        '<label for="r-src">Source that shows it <span>(optional)</span></label>'
        f'<input id="r-src" name="source_url" type="url" maxlength="2000" '
        f'placeholder="https://..." value="{v["source_url"]}">'
        '<label for="r-email">Your email, to hear back when it is fixed <span>(optional)</span>'
        "</label>"
        f'<input id="r-email" name="email" type="email" maxlength="254" autocomplete="email" '
        f'placeholder="you@example.com" value="{v["email"]}">'
        "<button>Send report</button></form></details></section>"
    )


def _short(url: object) -> str:
    """en.wikipedia.org/wiki/Chandrayaan-3 instead of the full https URL."""
    p = urlsplit(str(url))
    path = p.path.rstrip("/")
    tail = path if len(path) <= 48 else "…" + path[-46:]
    return f"{p.hostname or ''}{tail}"


def share_text(card: CardDoc) -> str:
    en, _, _ = LABEL[card.verdict]
    claim = card.claim if len(card.claim) <= 140 else card.claim[:137] + "…"
    return f"{en.upper()}: “{claim}” · Proof Card"


def _actions(card: CardDoc, card_id: str, url: str, bot: str) -> str:
    """One row: every way to pass the card on, each with its message already written."""
    text = share_text(card)
    links = [
        ("main", f"https://wa.me/?text={quote(text + ' ' + url)}", "Share on WhatsApp"),
        ("", f"https://t.me/share/url?url={quote(url)}&text={quote(text)}", "Share on Telegram"),
        ("", f"{url}.png", "Download image"),
    ]
    if bot:
        # Opens the bot with this card already loaded: nobody types a card id.
        links.append(("", f"https://t.me/{bot}?start={card_id}", "Open in the Telegram bot"))
    return (
        '<div class="acts">'
        + "".join(
            f'<a class="{c}" href="{escape(h)}" rel="noopener" target="_blank">{escape(label)}</a>'
            for c, h, label in links
        )
        + "</div>"
    )


def not_found_page() -> str:
    return _page(
        "Card not found",
        "This Proof Card does not exist.",
        "",
        '<h1>No such card.</h1><p class="why">If someone sent you this, the card may be made '
        "up. Real Proof Cards always open here.</p>",
    )
