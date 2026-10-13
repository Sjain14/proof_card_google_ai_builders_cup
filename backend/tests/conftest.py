from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.store import InMemoryStore

WEBHOOK_SECRET = "test-webhook-secret-value"

TOKENS: dict[str, dict[str, Any]] = {
    "admin-token": {"uid": "admin-1", "firebase": {"sign_in_provider": "google.com"}},
    "anon-token": {"uid": "anon-1", "firebase": {"sign_in_provider": "anonymous"}},
}


def fake_verifier(token: str) -> dict[str, Any]:
    if token not in TOKENS:
        raise ValueError("bad token")
    return TOKENS[token]


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        telegram_webhook_secret=SecretStr(WEBHOOK_SECRET),
        public_rate_per_min=3,
        max_body_bytes=5_000,
    )


@pytest.fixture
def client(settings: Settings, store: InMemoryStore) -> TestClient:
    return TestClient(create_app(settings=settings, verifier=fake_verifier, store=store))
