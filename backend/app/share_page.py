"""Server rendered /v/<card_id> share page (the Proof Capsule).

Server side so link previews (Telegram, WhatsApp, X) read Open Graph tags without JS,
and the page works on any phone with zero JS. Every dynamic value is html escaped.
OG tags: https://ogp.me/
"""

from __future__ import annotations

from html import escape

from app.alter import CheckResult
from app.card_image import share_url
from app.schemas import CardDoc, Verdict

LABEL = {
    Verdict.TRUE: ("True", "सही", "#15803D"),
    Verdict.MISLEADING: ("Misleading", "भ्रामक", "#B45309"),
    Verdict.FALSE: ("False", "गलत", "#B91C1C"),
    Verdict.UNVERIFIABLE: ("Not enough proof", "पुख्ता सबूत नहीं", "#6B7280"),
}

CSP = (
    "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
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
a{color:#1F4FFF;word-break:break-all}blockquote{margin:10px 0;padding-left:12px;
border-left:3px solid #1F4FFF}code{font-size:12px;word-break:break-all;color:#6B7280}
img{width:100%;border-radius:16px;border:1px solid #E5E7EB}
button{background:#1F4FFF;color:#fff;border:0;border-radius:10px;padding:10px 16px;font-weight:700}
.r{border-radius:14px;padding:18px;margin:0 0 20px;font-weight:700}
.VERIFIED{background:#ECFDF3;color:#15803D}.ALTERED{background:#FEF2F2;color:#B91C1C}
.UNKNOWN{background:#F3F4F6;color:#374151}
"""


def _page(title: str, desc: str, url: str, body: str) -> str:
    t, d, u = escape(title), escape(desc), escape(url)
    og = (
        f'<meta property="og:title" content="{t}"><meta property="og:description" content="{d}">'
        f'<meta property="og:url" content="{u}"><meta property="og:image" content="{u}.jpg">'
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


def card_page(
    card: CardDoc, card_id: str, base_url: str, bot: str = "", check: CheckResult | None = None
) -> str:
    url = share_url(base_url, card_id)
    en, hi, colour = LABEL[card.verdict]
    parts = [_check_banner(check)] if check else []
    parts.append(
        f'<span class="pill" style="background:{colour}">{escape(en)}</span>'
        f'<span class="hi" style="color:{colour}">{escape(hi)}</span>'
        f'<h1>“{escape(card.claim)}”</h1><p class="why">{escape(card.explanation)}</p>'
        f'<p class="meta">card {escape(card_id)} · support {card.support_score:.2f} · '
        f"issued {card.created_at:%d %b %Y %H:%M} UTC</p><section><h2>Proof</h2>"
    )
    for s in card.sources:
        u = escape(str(s.url))
        parts.append(
            f'<div class="src"><a href="{u}" rel="noopener nofollow">{u}</a>'
            f"<blockquote>{escape(s.snippet)}</blockquote><code>page sha256 "
            f'<a href="/api/snapshots/{escape(s.snapshot_sha256)}" rel="nofollow">'
            f"{escape(s.snapshot_sha256)}</a> · fetched {s.fetched_at:%d %b %Y %H:%M} UTC"
            "</code></div>"
        )
    parts.append(
        f'<p class="meta">Card fingerprint <code>{escape(card.card_sha256)}</code>. We fetched '
        "each page ourselves and stored its exact bytes under that hash: download any page "
        "hash above and run <code>sha256sum</code> on it to check.</p></section>"
        "<section><h2>Got this card forwarded?</h2>"
        f'<form method="post" action="/v/{escape(card_id)}/check" enctype="multipart/form-data">'
        '<input type="file" name="file" accept="image/png,image/jpeg,image/webp" required '
        'aria-label="card image"> <button>Check it</button></form>'
    )
    if bot:
        b = escape(bot)
        parts.append(f'<p class="meta">Or forward it to <a href="https://t.me/{b}">@{b}</a>.</p>')
    parts.append(
        f'</section><section><img src="{escape(url)}.png" alt="Proof Card image"></section>'
    )
    return _page(f"{en}: {card.claim[:90]}", card.explanation[:200], url, "".join(parts))


def not_found_page() -> str:
    return _page(
        "Card not found",
        "This Proof Card does not exist.",
        "",
        '<h1>No such card.</h1><p class="why">If someone sent you this, the card may be made '
        "up. Real Proof Cards always open here.</p>",
    )
