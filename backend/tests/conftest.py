from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.model import StubModel
from app.pipeline import Deps
from app.proof import FixtureFetcher, InMemorySnapshots
from app.store import InMemoryStore
from app.tasks import SyncQueue

WEBHOOK_SECRET = "test-webhook-secret-value"

TOKENS: dict[str, dict[str, Any]] = {
    "admin-token": {"uid": "admin-1", "firebase": {"sign_in_provider": "google.com"}},
    "anon-token": {"uid": "anon-1", "firebase": {"sign_in_provider": "anonymous"}},
}


def fake_verifier(token: str) -> dict[str, Any]:
    if token in TOKENS:
        return TOKENS[token]
    if token.startswith("anon-"):
        return {"uid": token, "firebase": {"sign_in_provider": "anonymous"}}
    if token.startswith("user-"):
        return {"uid": token, "firebase": {"sign_in_provider": "google.com"}}
    raise ValueError("bad token")


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
    deps = Deps(
        store=store, model=StubModel(), fetcher=FixtureFetcher(), snapshots=InMemorySnapshots()
    )
    app = create_app(
        settings=settings,
        verifier=fake_verifier,
        store=store,
        deps=deps,
        queue=SyncQueue(),
        oidc_verifier=fake_oidc,
    )
    return TestClient(app)


def fake_oidc(token: str) -> dict[str, Any]:
    if token != "task-token":
        raise ValueError("bad oidc")
    return {"email": "api-sa@test.iam.gserviceaccount.com", "email_verified": True}
