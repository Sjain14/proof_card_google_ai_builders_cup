"""Runtime settings.

Secrets are NEVER read from files in the repo. On Cloud Run they are injected from
Secret Manager as environment variables pinned to a version (see docs/STANDARDS.md).
Locally they come from a gitignored .env that each developer fills with their own values.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PC_", env_file=".env", extra="ignore")

    env: str = Field(default="local", pattern="^(local|test|prod)$")
    gcp_project: str = ""
    public_base_url: str = "http://localhost:8080"

    # Injected from Secret Manager on Cloud Run. Empty locally = feature disabled.
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_webhook_secret: SecretStr = SecretStr("")

    # Abuse limits for public endpoints (per instance; see STANDARDS.md "what we skip").
    public_rate_per_min: int = Field(default=30, ge=1, le=600)
    max_body_bytes: int = Field(default=1_000_000, ge=1_024)

    # Auth: tests swap the verifier, prod always verifies Firebase ID tokens.
    auth_disabled: bool = False


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "prod" and s.auth_disabled:
        raise RuntimeError("auth_disabled is forbidden in prod")
    return s
