"""HttpFetcher on httpx.MockTransport: no network, real redirect / error / size logic."""

from collections.abc import Callable

import httpx
import pytest

from app.proof import MAX_BYTES, FetchError, HttpFetcher, extract_text

PUBLIC = ["93.184.216.34"]


def fetcher(handler: Callable[[httpx.Request], httpx.Response]) -> HttpFetcher:
    return HttpFetcher(resolve=lambda _h: PUBLIC, transport=httpx.MockTransport(handler))


def _pdf(text: str) -> bytes:
    """Smallest valid one page PDF with a text layer (offsets computed, not hardcoded)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def test_follows_redirect_and_returns_final_url() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/a":
            return httpx.Response(301, headers={"location": "/b"})
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="ok")

    got = fetcher(h).fetch("https://example.org/a")
    assert got.final_url == "https://example.org/b"
    assert got.body == b"ok"
    assert got.content_type == "text/html"


@pytest.mark.parametrize(
    ("resp", "reason"),
    [
        (httpx.Response(404), "status 404"),
        (httpx.Response(200, headers={"content-type": "image/png"}), "unsupported"),
        (
            httpx.Response(
                200, headers={"content-type": "text/html"}, content=b"x" * (MAX_BYTES + 1)
            ),
            "too large",
        ),
        (httpx.Response(302, headers={"location": "http://example.org/"}), "https"),
    ],
)
def test_rejections_are_fetch_errors(resp: httpx.Response, reason: str) -> None:
    with pytest.raises(FetchError, match=reason):
        fetcher(lambda _r: resp).fetch("https://example.org/")


def test_redirect_loop_stops() -> None:
    f = fetcher(lambda _r: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(FetchError, match="too many redirects"):
        f.fetch("https://example.org/")


def test_transport_errors_become_fetch_error() -> None:
    # Before: a timeout / proxy / TLS error escaped and failed the whole claim (audit #7).
    def h(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=req)

    with pytest.raises(FetchError, match="ConnectTimeout"):
        fetcher(h).fetch("https://example.org/")


def test_private_address_is_refused() -> None:
    never = httpx.MockTransport(lambda _r: httpx.Response(200))
    f = HttpFetcher(resolve=lambda _h: ["10.0.0.1"], transport=never)
    with pytest.raises(FetchError):
        f.fetch("https://internal.example/")


def test_pdf_source_is_fetched_and_read() -> None:
    body = _pdf("UPI processed 20 billion transactions in August")
    got = fetcher(
        lambda _r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=body)
    ).fetch("https://example.org/report.pdf")
    assert got.content_type == "application/pdf"
    assert "20 billion transactions" in extract_text(got.body, got.content_type)
    assert extract_text(b"%PDF-1.4 broken", "application/pdf") == ""


def test_main_content_beats_boilerplate() -> None:
    article = " ".join(["The Eighth Schedule of the Constitution lists 22 languages."] * 8)
    html = (
        "<html><body><div class='menu'>Home · About · 1 · 2 · 3 · Login</div>"
        f"<article><h1>Languages</h1><p>{article}</p></article>"
        "<div class='footer'>Copyright · Terms · Privacy</div></body></html>"
    ).encode()
    text = extract_text(html)
    assert "22 languages" in text
    assert "Login" not in text
