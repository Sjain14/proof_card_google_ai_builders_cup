"""Runtime settings.

Secrets are NEVER read from files in the repo. On Cloud Run they are injected from
Secret Manager as environment variables pinned to a version
(see context/12_Engineering_Standards.md).
Locally they come from a gitignored .env that each developer fills with their own values.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PC_", env_file=".env", extra="ignore")

    env: str = Field(default="local", pattern="^(local|test|prod)$")
    gcp_project: str = ""
    public_base_url: str = "http://localhost:8080"

    # Injected from Secret Manager on Cloud Run. Empty locally = feature disabled.
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_webhook_secret: SecretStr = SecretStr("")
    telegram_bot_username: str = ""  # public, e.g. proofcard_bot (no @)
    # Google Fact Check Tools API key (restricted to that API). Empty = lookup off.
    factcheck_api_key: SecretStr = SecretStr("")

    # Abuse limits for public endpoints (per instance; see STANDARDS.md "what we skip").
    public_rate_per_min: int = Field(default=30, ge=1, le=600)
    # Watch page polls every 2 s: its own bucket so viewers never starve card reads.
    feed_rate_per_min: int = Field(default=60, ge=1, le=600)
    # Proof Library list (/api/cards): every CDN miss is Firestore reads, own bucket.
    library_rate_per_min: int = Field(default=60, ge=1, le=600)
    # Each brief costs ~15 grounded Gemini calls: burst limit per user + durable daily cap.
    prebunk_per_min: int = Field(default=3, ge=1, le=60)
    prebunk_daily_cap: int = Field(default=20, ge=1, le=1_000)
    prebunk_anon_daily_cap: int = Field(default=100, ge=1, le=10_000)
    max_body_bytes: int = Field(default=1_000_000, ge=1_024)

    # Model + pipeline. stub = offline fixtures (tests, CI, local before GCP exists).
    model_mode: str = Field(default="stub", pattern="^(stub|vertex)$")
    gcp_region: str = "asia-south1"  # Cloud Run, Cloud Tasks, Firestore, GCS
    # Each model gets its own location: availability differs per model.
    # gemini-2.5-flash retires on Vertex 20 Oct 2026, inside the scoring window; 3.5-flash is
    # GA until at least May 2027. Docs (lifecycle + replacements):
    # https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions
    gemini_model: str = "gemini-3.5-flash"
    gemini_region: str = "global"  # global endpoint: every GA Gemini model, best availability
    # gemini-3.5-transcribe-live is served ONLY from global, us, eu (not asia-south1). Docs:
    # https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-transcribe
    live_model: str = "gemini-3.5-transcribe-live"  # Live API transcription
    live_region: str = Field(default="global", pattern="^(global|us|eu)$")
    clip_model: str = "gemini-3.5-transcribe"  # file transcription, clip upload (same regions)
    embed_model: str = "gemini-embedding-001"
    embed_region: str = ""  # empty = gcp_region (embedding-001 is regional, close to the API)
    live_origins: str = ""  # extra allowed websocket Origins, comma separated
    live_threshold: float = Field(default=0.80, ge=0.5, le=0.99)  # cosine for a PREBUNKED hit
    live_instant: float = Field(default=0.90, ge=0.5, le=1.0)  # at/above: no judge call
    prebunk_claims: int = Field(default=12, ge=1, le=20)
    proof_bucket: str = ""  # empty = in memory snapshots (local only)

    @field_validator("proof_bucket")
    @classmethod
    def _bare_bucket(cls, v: str) -> str:
        # The storage client wants the bare name; E04 prints it as gs://name, so accept both.
        return v.strip().removeprefix("gs://").rstrip("/")

    # Background jobs. inline = thread pool in process; cloudtasks = durable queue (prod).
    tasks_mode: str = Field(default="inline", pattern="^(inline|cloudtasks)$")
    tasks_queue: str = "prebunk"
    tasks_sa_email: str = ""  # api-sa email; also the only identity allowed to call /tasks/*
    service_url: str = ""  # this Cloud Run service's own URL (OIDC audience)

    # Auth: tests swap the verifier, prod always verifies Firebase ID tokens.
    auth_disabled: bool = False


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "prod" and s.auth_disabled:
        raise RuntimeError("auth_disabled is forbidden in prod")
    if s.env == "prod" and s.model_mode == "stub":
        raise RuntimeError("stub model is forbidden in prod")
    return s
