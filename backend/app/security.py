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
