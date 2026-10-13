"""Structured JSON logs for Cloud Logging, with PII and secret redaction.

Cloud Logging parses one JSON object per line on stdout and maps "severity" and
"message". We never log raw tokens, Telegram chat ids or user text bodies.
"""

import hashlib
import json
import logging
import re
import sys
from typing import Any

_REDACT_PATTERNS = [
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),  # Telegram bot token shape
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),  # bearer / ID tokens
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),  # Google API key shape
]


def redact(text: str) -> str:
    for p in _REDACT_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


def pseudonymize(value: int | str) -> str:
    """Stable, non reversible id for correlating logs without storing the raw id."""
    return hashlib.sha256(f"pc:{value}".encode()).hexdigest()[:16]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": redact(record.getMessage()),
            "logger": record.name,
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update({k: redact(str(v)) for k, v in extra.items()})
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
