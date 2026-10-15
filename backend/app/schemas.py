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
    is_anonymous: bool = False
    created_at: datetime = Field(default_factory=_now)


class ClaimDoc(Strict):
    schema_version: int = SCHEMA_VERSION
    text: LongText
    lang: Annotated[str, Field(pattern="^(en|hi|hi-Latn)$")] = "en"
    source: ClaimSource
    status: ClaimStatus = ClaimStatus.QUEUED
    card_id: str | None = None
    verdict: Verdict | None = None  # copied from the card so list views need no join
    matched_claim_id: str | None = None  # live claim answered instantly by a prebunked one
    latency_ms: Annotated[int, Field(ge=0)] | None = None  # live: heard to card shown
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
    # Google's Search suggestion HTML for the grounded explanation. Presentation, not proof:
    # outside the fingerprint, served only inside a sandboxed frame.
    search_suggestion_html: Annotated[str, Field(max_length=50_000)] | None = None
    created_at: datetime = Field(default_factory=_now)


class CheckDoc(Strict):
    """One ALTERED / VERIFIED check. Deliberately no chat id, user id or image stored."""

    schema_version: int = SCHEMA_VERSION
    card_id: str | None = None
    channel: Annotated[str, Field(pattern="^(telegram|web)$")]
    result: Annotated[str, Field(pattern="^(VERIFIED|ALTERED|UNKNOWN)$")]
    changed: list[str] = []
    text_similarity: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    phash_distance: int | None = None
    created_at: datetime = Field(default_factory=_now)


class CheckImageResponse(BaseModel):
    result: str
    reason: str
    card_id: str | None
    changed: list[str]


class CheckTextResponse(BaseModel):
    result: str
    similarity: float
    removed: list[str]
    added: list[str]


def gate_verdict(verdict: Verdict, support_score: float, threshold: float = 0.6) -> Verdict:
    """Never show a hard verdict the sources don't back (faithfulness gate)."""
    if verdict in (Verdict.TRUE, Verdict.FALSE, Verdict.MISLEADING) and support_score < threshold:
        return Verdict.UNVERIFIABLE
    return verdict


# ---------- API responses / internal task bodies ----------


class TaskPrebunk(Strict):
    session_id: DocId


class ClaimView(BaseModel):
    id: str
    text: str
    lang: str
    source: ClaimSource
    status: ClaimStatus
    card_id: str | None
    verdict: Verdict | None


class SessionView(BaseModel):
    id: str
    topic: str
    speaker: str
    status: str
    youtube_url: str | None = None
    claims: list[ClaimView]
    counts: dict[str, int]

    @classmethod
    def build(cls, sid: str, s: SessionDoc, claims: list[tuple[str, ClaimDoc]]) -> "SessionView":
        views = [
            ClaimView(
                id=cid,
                text=c.text,
                lang=c.lang,
                source=c.source,
                status=c.status,
                card_id=c.card_id,
                verdict=c.verdict,
            )
            for cid, c in claims
        ]
        counts = {st.value: sum(1 for v in views if v.status == st) for st in ClaimStatus}
        return cls(
            id=sid,
            topic=s.topic,
            speaker=s.speaker,
            status=s.status,
            youtube_url=s.youtube_url,
            claims=views,
            counts=counts,
        )


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


class TgDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file_id: Annotated[str, Field(max_length=256)]
    mime_type: str | None = None
    file_size: int | None = None


class TgMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: int
    chat: TgChat
    from_: TgUser | None = Field(default=None, alias="from")
    text: Annotated[str, Field(max_length=4_096)] | None = None
    caption: Annotated[str, Field(max_length=4_096)] | None = None
    photo: list[TgPhotoSize] | None = None
    document: TgDocument | None = None


class TgInlineQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Annotated[str, Field(max_length=128)]
    query: Annotated[str, Field(max_length=256)] = ""


class TgCallbackQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Annotated[str, Field(max_length=128)]
    data: Annotated[str, Field(max_length=64)] | None = None


class TgUpdate(BaseModel):
    """Telegram may add fields any time, so unknown fields are ignored (not forbidden)."""

    model_config = ConfigDict(extra="ignore")
    update_id: int
    message: TgMessage | None = None
    inline_query: TgInlineQuery | None = None
    callback_query: TgCallbackQuery | None = None
