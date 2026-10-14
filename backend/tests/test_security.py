import json
import logging

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings, get_settings
from app.logging_setup import JsonFormatter, pseudonymize, redact
from app.schemas import ClaimDoc, ClaimSource, Verdict, gate_verdict
from app.security import (
    TokenBucket,
    UnsafeURLError,
    assert_public_https_url,
    card_fingerprint,
    telegram_secret_ok,
)
from app.store import InMemoryStore


def _resolver(ips: list[str]):  # type: ignore[no-untyped-def]
    return lambda _host: ips


def test_telegram_secret_compare() -> None:
    assert telegram_secret_ok("s3cret", "s3cret")
    assert not telegram_secret_ok("s3cre", "s3cret")
    assert not telegram_secret_ok(None, "s3cret")
    assert not telegram_secret_ok("", "")  # unconfigured bot rejects everything


@pytest.mark.parametrize(
    ("url", "ips"),
    [
        ("http://example.org/", ["93.184.216.34"]),
        ("https://user:pw@example.org/", ["93.184.216.34"]),
        ("https://example.org:8443/", ["93.184.216.34"]),
        ("https://metadata.google.internal/", ["169.254.169.254"]),
        ("https://localhost/", ["127.0.0.1"]),
        ("https://intranet/", ["10.0.0.5"]),
        ("https://v6local/", ["::1"]),
        ("https://mixed.example/", ["93.184.216.34", "192.168.1.1"]),
        ("https://nowhere.example/", []),
        ("https:///nohost", ["93.184.216.34"]),
    ],
)
def test_ssrf_guard_blocks(url: str, ips: list[str]) -> None:
    with pytest.raises(UnsafeURLError):
        assert_public_https_url(url, resolve=_resolver(ips))


def test_ssrf_guard_allows_public() -> None:
    url = "https://example.org/a?b=1"
    assert assert_public_https_url(url, resolve=_resolver(["93.184.216.34"])) == url


def test_card_fingerprint_is_order_independent_and_ignores_hash_fields() -> None:
    a = card_fingerprint({"claim": "x", "verdict": "TRUE", "card_sha256": "1"})
    b = card_fingerprint({"verdict": "TRUE", "claim": "x", "png_phash": "2"})
    assert a == b
    assert a != card_fingerprint({"claim": "y", "verdict": "TRUE"})


def test_verdict_gate() -> None:
    assert gate_verdict(Verdict.FALSE, 0.3) is Verdict.UNVERIFIABLE
    assert gate_verdict(Verdict.FALSE, 0.8) is Verdict.FALSE
    assert gate_verdict(Verdict.UNVERIFIABLE, 0.0) is Verdict.UNVERIFIABLE


def test_token_bucket_refills() -> None:
    now = [0.0]
    tb = TokenBucket(rate_per_min=2, clock=lambda: now[0])
    assert tb.allow("a")
    assert tb.allow("a")
    assert not tb.allow("a")
    assert tb.allow("b")  # per key
    now[0] = 30.0
    assert tb.allow("a")


def test_redaction_and_pseudonyms() -> None:
    token = "123456789:" + "A" * 35
    assert "[REDACTED]" in redact(f"token {token}")
    assert "[REDACTED]" in redact("Authorization: Bearer " + "x" * 40)
    assert pseudonymize(42) == pseudonymize("42")
    assert "42" not in pseudonymize(42)


def test_json_formatter_redacts_fields() -> None:
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hi", None, None)
    rec.fields = {"auth": "Bearer " + "y" * 40}
    out = json.loads(JsonFormatter().format(rec))
    assert out["severity"] == "INFO"
    assert out["auth"] == "[REDACTED]"


def test_prod_refuses_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("PC_ENV", "prod")
    monkeypatch.setenv("PC_AUTH_DISABLED", "true")
    with pytest.raises(RuntimeError):
        get_settings()
    get_settings.cache_clear()


def test_settings_reject_bad_env() -> None:
    with pytest.raises(ValidationError):
        Settings(env="staging")
    assert Settings(telegram_bot_token=SecretStr("x")).telegram_bot_token.get_secret_value()


def test_model_defaults_survive_the_scoring_window() -> None:
    # gemini-2.5-flash retires on Vertex 20 Oct 2026; transcribe-live is global/us/eu only.
    s = Settings(_env_file=None)
    assert s.gemini_model == "gemini-3.5-flash"
    assert s.gemini_region == "global"
    assert s.live_region == "global"
    with pytest.raises(ValidationError):
        Settings(live_region="asia-south1")


def test_claim_doc_validation_and_store() -> None:
    with pytest.raises(ValidationError):
        ClaimDoc(text="x", source=ClaimSource.LIVE, lang="fr")
    s = InMemoryStore()
    with pytest.raises(KeyError):
        s.add_claim("missing", ClaimDoc(text="x", source=ClaimSource.LIVE))
