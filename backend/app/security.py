"""Security primitives: webhook secret check, SSRF guard, canonical hashing, rate limiting."""

import hashlib
import hmac
import ipaddress
import json
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

# ---------- Telegram webhook ----------


def telegram_secret_ok(header_value: str | None, expected: str) -> bool:
    """Constant time compare of X-Telegram-Bot-Api-Secret-Token.

    An empty expected secret means the bot is not configured: reject everything.
    """
    if not expected or header_value is None:
        return False
    return hmac.compare_digest(header_value.encode(), expected.encode())


# ---------- SSRF guard for the fetcher ----------

Resolver = Callable[[str], Iterable[str]]


def _system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return [str(i[4][0]) for i in infos]


class UnsafeURLError(ValueError):
    pass


def assert_public_https_url(url: str, resolve: Resolver = _system_resolver) -> str:
    """Allow only https URLs whose host resolves exclusively to public addresses.

    Blocks loopback, private, link local (incl. 169.254.169.254 metadata), multicast,
    reserved and unspecified ranges. The fetcher must call this again on every redirect
    hop and connect to the vetted IP, otherwise DNS rebinding can bypass it.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeURLError("only https is allowed")
    if parts.username or parts.password:
        raise UnsafeURLError("credentials in URL are not allowed")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("missing host")
    if parts.port not in (None, 443):
        raise UnsafeURLError("only port 443 is allowed")
    addrs = list(resolve(host))
    if not addrs:
        raise UnsafeURLError("host does not resolve")
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURLError(f"non public address for {host}")
    return url


# ---------- Canonical hashing ----------


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


FINGERPRINT_EXCLUDED = {"card_sha256", "png_phash", "search_suggestion_html"}


def card_fingerprint(card_fields: dict[str, Any]) -> str:
    """sha256 over the canonical card record (excluding the hash itself and image fields)."""
    body = {k: v for k, v in card_fields.items() if k not in FINGERPRINT_EXCLUDED}
    return sha256_hex(canonical_json(body))


# ---------- Trusted proxy hops (Firebase Hosting -> Cloud Run) ----------

# Measured on prod 2026-10-18 (p77): behind a Hosting rewrite X-Forwarded-For is exactly
# "<client>, <Google proxy>" (Hosting overwrites any caller supplied value) and the proxy
# rotates per request (66.249.82.x, 192.178.14.x). These are Google front end ranges
# from https://www.gstatic.com/ipranges/goog.json that are NOT in cloud.json, so no
# Cloud customer can originate from them. Direct Cloud Run hits never end in one.
GOOGLE_PROXY_NETS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "64.233.160.0/19",
        "66.102.0.0/20",
        "66.249.64.0/19",
        "72.14.192.0/18",
        "74.125.0.0/16",
        "108.177.0.0/17",
        "142.250.0.0/15",
        "172.217.0.0/16",
        "172.253.0.0/16",
        "173.194.0.0/16",
        "192.178.0.0/15",
        "209.85.128.0/17",
        "216.58.192.0/19",
        "216.239.32.0/19",
        "2001:4860::/32",
        "2404:6800::/32",
        "2607:f8b0::/32",
        "2800:3f0::/32",
        "2a00:1450::/32",
    )
)


def is_cdn_hop(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr.version == n.version and addr in n for n in GOOGLE_PROXY_NETS)


# ---------- Rate limiting (per instance token bucket) ----------


@dataclass
class TokenBucket:
    rate_per_min: int
    clock: Callable[[], float] = time.monotonic
    _state: dict[str, tuple[float, float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def allow(self, key: str) -> bool:
        cap = float(self.rate_per_min)
        refill = cap / 60.0
        now = self.clock()
        with self._lock:
            tokens, last = self._state.get(key, (cap, now))
            tokens = min(cap, tokens + (now - last) * refill)
            if tokens < 1.0:
                self._state[key] = (tokens, now)
                return False
            self._state[key] = (tokens - 1.0, now)
            return True
