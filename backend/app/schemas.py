"""Boundary schemas. Every request body and every Firestore document goes through one of these.

extra="forbid" rejects unknown fields; max lengths cap abuse and prompt size.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

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
    status: Annotated[str, Field(pattern="^(draft|prebunking|ready|live|closed|failed)$")] = "draft"
    is_anonymous: bool = False
    public_view: bool = False  # owner opted in to the read only /watch/:id link
    created_at: datetime = Field(default_factory=_now)
    # Telegram alerts (app/alerts.py): pending deep link (hash only) + linked chat
    tg_link_hash: str | None = None
    tg_link_exp: datetime | None = None
    alert_chat_id: int | None = None
    alerts_sent: int = 0
    fact_bank_key: str | None = (
        None  # fact_banks/{key}: researched facts this session checks against
    )
    # Last progress of the prebunk job: a revision swap can kill it mid run; a session read
    # that finds it silent for PREBUNK_STALE re-queues it (pipeline.prebunk_stalled).
    prebunk_beat: datetime | None = None


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
    t_offset_s: Annotated[float, Field(ge=0)] | None = None  # replay: second in the video
    fact_ids: Annotated[list[int], Field(max_length=8)] = []  # fact bank facts that decided it
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime | None = None  # set by the store on every update (feed cursor)


class Fact(Strict):
    """One researched fact, kept only after its source page was fetched and a passage on it
    backed the statement (app/facts.py). trigger = a line a speaker could say that this fact
    decides (true, exaggerated or wrong), so the bank reads like a fact checker's desk."""

    id: Annotated[int, Field(ge=0)]
    statement: LongText
    value: Annotated[str, Field(max_length=200)] = ""
    as_of: Annotated[str, Field(max_length=100)] = ""
    angle: Annotated[str, Field(max_length=200)] = ""
    trigger: Annotated[str, Field(max_length=1_000)] = ""
    source_url: AnyHttpUrl
    passage: LongText
    support: Annotated[float, Field(ge=0.0, le=1.0)]
    official: bool = False
    # page = passage read on the fetched page; search = official page blocks our server,
    # the statement was backed by Google Search grounding on that same official host;
    # archive = official page blocks our server, read on its Wayback Machine copy.
    checked: Literal["page", "search", "archive"] = "page"


class FactBankDoc(Strict):
    """fact_banks/{key}, key = topic + speaker. Reused by every later session on the same
    topic and speaker until it is older than facts.MAX_AGE (Team lead VN, 16 Oct 2026)."""

    schema_version: int = SCHEMA_VERSION
    key: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,120}$")]
    topic: ShortText
    speaker: str = ""
    # ISO date the speech was given (YouTube publish date); "" = current. Anchors research.
    said_on: Annotated[str, Field(pattern=r"^(\d{4}-\d{2}-\d{2})?$")] = ""
    prompt_version: str
    researched: Annotated[int, Field(ge=0)] = 0  # candidates before source verification
    facts: Annotated[list[Fact], Field(max_length=200)] = []
    # Diagnostics: stage seconds + drop counts by reason, and a sample of dropped facts.
    stats: dict[str, float] = {}
    samples: Annotated[list[str], Field(max_length=20)] = []
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
    matched_claim_id: str | None = None
    t_offset_s: float | None = None
    matched: bool = False  # live claim answered by a prebunked card
    fact_ids: list[int] = []  # fact bank facts that decided it (app/facts.py)


class SessionView(BaseModel):
    id: str
    topic: str
    speaker: str
    status: str
    youtube_url: str | None = None
    public_view: bool = False
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
                matched_claim_id=c.matched_claim_id,
                t_offset_s=c.t_offset_s,
                matched=c.matched_claim_id is not None,
                fact_ids=c.fact_ids,
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
            public_view=s.public_view,
            claims=views,
            counts=counts,
        )


class ShareRequest(Strict):
    public_view: bool


class FeedClaim(BaseModel):
    """One heard claim as a public viewer sees it: no owner data, no prebunk bank."""

    id: str
    text: str
    status: ClaimStatus
    card_id: str | None
    verdict: Verdict | None
    matched: bool  # answered instantly by a prebunked card (PREBUNKED badge), else LIVE
    latency_ms: int | None
    created_at: datetime


class FeedView(BaseModel):
    id: str
    topic: str
    speaker: str
    status: str
    claims: list[FeedClaim]
    cursor: datetime  # pass back as ?since= on the next poll

    @classmethod
    def build(
        cls,
        sid: str,
        s: SessionDoc,
        claims: list[tuple[str, ClaimDoc]],
        since: datetime | None,
        now: datetime,
    ) -> "FeedView":
        views = [
            FeedClaim(
                id=cid,
                text=c.text,
                status=c.status,
                card_id=c.card_id,
                verdict=c.verdict,
                matched=c.matched_claim_id is not None,
                latency_ms=c.latency_ms,
                created_at=c.created_at,
            )
            for cid, c in claims
            if c.source == ClaimSource.LIVE
            and (since is None or (c.updated_at or c.created_at) > since)
        ]
        return cls(
            id=sid, topic=s.topic, speaker=s.speaker, status=s.status, claims=views, cursor=now
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
