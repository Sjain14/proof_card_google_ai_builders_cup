"""Boundary schemas. Every request body and every Firestore document goes through one of these.

extra="forbid" rejects unknown fields; max lengths cap abuse and prompt size.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1

ShortText = Annotated[str, Field(min_length=1, max_length=500)]
LongText = Annotated[str, Field(min_length=1, max_length=4_000)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
DocId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class Verdict(StrEnum):
    TRUE = "TRUE"
    MISLEADING = "MISLEADING"
    FALSE = "FALSE"
    UNVERIFIABLE = "UNVERIFIABLE"


class ClaimStatus(StrEnum):
    QUEUED = "queued"
    CHECKING = "checking"
    PROVED = "proved"
    FAILED = "failed"


class ClaimSource(StrEnum):
    PREDICTED = "predicted"
    LIVE = "live"


# ---------- API requests ----------


class PrebunkRequest(Strict):
    topic: ShortText
    speaker: Annotated[str, Field(max_length=200)] = ""
    youtube_url: AnyHttpUrl | None = None
    context_links: Annotated[list[AnyHttpUrl], Field(max_length=5)] = []

    @field_validator("youtube_url")
    @classmethod
    def _youtube_only(cls, v: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if v is None:
            return v
        allowed = {"www.youtube.com", "youtube.com", "youtu.be", "m.youtube.com"}
        if v.scheme != "https" or v.host not in allowed:
            raise ValueError("youtube_url must be an https YouTube link")
        return v


class CheckTextRequest(Strict):
    card_id: DocId
    text: LongText


# ---------- Firestore documents ----------


def _now() -> datetime:
    return datetime.now(UTC)


class SourceProof(Strict):
    url: AnyHttpUrl
    snippet: LongText
    snapshot_sha256: Sha256Hex
    fetched_at: datetime


class SessionDoc(Strict):
    schema_version: int = SCHEMA_VERSION
    owner_uid: Annotated[str, Field(min_length=1, max_length=128)]
    topic: ShortText
    speaker: str = ""
    youtube_url: str | None = None
    status: Annotated[str, Field(pattern="^(draft|prebunking|ready|live|closed)$")] = "draft"
    created_at: datetime = Field(default_factory=_now)


class ClaimDoc(Strict):
    schema_version: int = SCHEMA_VERSION
    text: LongText
    lang: Annotated[str, Field(pattern="^(en|hi|hi-Latn)$")] = "en"
    source: ClaimSource
    status: ClaimStatus = ClaimStatus.QUEUED
    card_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class CardDoc(Strict):
    schema_version: int = SCHEMA_VERSION
    claim: LongText
    verdict: Verdict
    explanation: LongText
    sources: Annotated[list[SourceProof], Field(min_length=1, max_length=8)]
    support_score: Annotated[float, Field(ge=0.0, le=1.0)]
    card_sha256: Sha256Hex
    png_phash: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")] | None = None
    created_at: datetime = Field(default_factory=_now)


def gate_verdict(verdict: Verdict, support_score: float, threshold: float = 0.6) -> Verdict:
    """Never show a hard verdict the sources don't back (faithfulness gate)."""
    if verdict in (Verdict.TRUE, Verdict.FALSE, Verdict.MISLEADING) and support_score < threshold:
        return Verdict.UNVERIFIABLE
    return verdict


# ---------- Telegram (subset we actually read) ----------


class TgUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int


class TgChat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    type: str


class TgPhotoSize(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file_id: Annotated[str, Field(max_length=256)]
    file_size: int | None = None


class TgMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: int
    chat: TgChat
    from_: TgUser | None = Field(default=None, alias="from")
    text: Annotated[str, Field(max_length=4_096)] | None = None
    photo: list[TgPhotoSize] | None = None


class TgUpdate(BaseModel):
    """Telegram may add fields any time, so unknown fields are ignored (not forbidden)."""

    model_config = ConfigDict(extra="ignore")
    update_id: int
    message: TgMessage | None = None
