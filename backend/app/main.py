"""Proof Card main service (Cloud Run): API, prebunk jobs, public card reads, Telegram webhook."""

import asyncio
import contextlib
import json
import logging
import re
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from app import alerts, alter, card_image, share_page
from app.auth import Principal, Verifier, admin_principal, firebase_verifier
from app.clip import (
    CLIP_BATCH,
    MAX_CLIP_BYTES,
    ClipTranscriber,
    GeminiClipTranscriber,
    clip_mime,
    clip_stalled,
)
from app.clip import sentences as clip_sentences
from app.config import Settings, get_settings
from app.factcheck import FactCheckClient, FactCheckedModel
from app.facts import VertexFactDesk
from app.library import LIBRARY_PARAMS, VERDICTS, Library
from app.live import (
    Alert,
    GeminiLiveTranscriber,
    HashEmbedder,
    HeuristicSpotter,
    LiveDeps,
    LiveEngine,
    Spotter,
    Transcriber,
    VertexEmbedder,
    VertexImageReader,
    VertexJudge,
    VertexSpotter,
    vocabulary_for,
)
from app.logging_setup import configure_logging, pseudonymize
from app.model import ModelClient, StubModel, VertexModel
from app.pipeline import (
    Deps,
    Trace,
    prebunk_stalled,
    run_prebunk,
    verify_claim,
    youtube_published,
    youtube_title,
)
from app.proof import FixtureFetcher, GcsSnapshots, HttpFetcher, InMemorySnapshots
from app.reuse import SimilarCards
from app.schemas import (
    CardDoc,
    CheckDoc,
    CheckImageResponse,
    CheckTextRequest,
    CheckTextResponse,
    ClaimDoc,
    ClaimSource,
    ClipJob,
    ClipJobView,
    ClipLine,
    FactBankDoc,
    FeedView,
    PrebunkRequest,
    ReportDoc,
    SessionDoc,
    SessionView,
    ShareRequest,
    TaskPrebunk,
    TgUpdate,
    VideoRequest,
)
from app.security import TokenBucket, is_cdn_hop, sha256_hex, telegram_secret_ok
from app.store import FirestoreStore, InMemoryStore, Store
from app.tasks import CloudTasksQueue, InlineQueue, OidcVerifier, TaskQueue, google_oidc_verifier
from app.telegram import (
    MAX_FORWARD_CLAIMS,
    STILL_CHECKING,
    STILL_CHECKING_AFTER_S,
    BotApi,
    BotDeps,
    HttpBotApi,
    claim_lang,
    handle_update,
    looks_like_claim,
    send_claim_result,
)

REPORTS_PER_MIN = 5

log = logging.getLogger("proofcard")
BOT_DAILY_CHECKS = 40  # claim checks per Telegram chat per UTC day (Vertex cost guard;
# 10 was hit by one demo run of 4 claims + a 3-claim forward + retries, 16 Oct)
CLIP_TRIES = 3  # transcription attempts per clip (transient Gemini 429/503)
CLIP_BACKOFF_S = 8.0
FORWARD_SENTENCES = 8  # sentences of a forward read by the spotter, at most
FORWARD_SPLIT_CHARS = 240  # longer bot texts are forwards: split into their claims
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


def several_claims(text: str) -> bool:
    """A short forward with 2+ claim-like sentences ("India is 4th. Petrol is cheapest.
    Every village got power.", 199 chars, checked whole -> UNVERIFIABLE, 16 Oct)."""
    parts = [p for p in _SENTENCE_END.split(text.strip()) if looks_like_claim(p)]
    return len(parts) >= 2


def _statement(sentence: str) -> bool:
    """A plain statement ("The Earth has two moons."), not a question or a call to action
    ("Share before they delete!!")."""
    s = sentence.strip()
    return looks_like_claim(s) and not s.endswith(("?", "!"))


LIVE_AUTH_TIMEOUT_S = 5.0
LIVE_MAX_FRAME = 64_000  # 2 s of PCM16 16 kHz mono; the client sends ~100 ms frames
LIVE_AUDIO_QUEUE = 200

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def default_deps(settings: Settings, store: Store) -> Deps:  # pragma: no cover - prod wiring
    model: ModelClient
    if settings.model_mode == "vertex":
        model = VertexModel(
            settings.gcp_project,
            settings.gemini_region or settings.gcp_region,
            settings.gemini_model,
        )
        fetcher: FixtureFetcher | HttpFetcher = HttpFetcher()
        if key := settings.factcheck_api_key.get_secret_value():
            model = FactCheckedModel(model, FactCheckClient(key))
    else:
        model, fetcher = StubModel(), FixtureFetcher()
    snaps = GcsSnapshots(settings.proof_bucket) if settings.proof_bucket else InMemorySnapshots()
    title = youtube_title if settings.model_mode == "vertex" else None
    published = youtube_published if settings.model_mode == "vertex" else None
    facts = (
        VertexFactDesk(
            settings.gcp_project,
            settings.gemini_region or settings.gcp_region,
            settings.gemini_model,
        )
        if settings.model_mode == "vertex"
        else None
    )
    similar = (
        SimilarCards(
            store,
            VertexEmbedder(
                settings.gcp_project,
                settings.embed_region or settings.gcp_region,
                settings.embed_model,
            ),
            VertexJudge(
                settings.gcp_project,
                settings.gemini_region or settings.gcp_region,
                settings.gemini_model,
            ),
        )
        if settings.model_mode == "vertex"
        else None
    )
    return Deps(
        store=store,
        model=model,
        fetcher=fetcher,
        snapshots=snaps,
        video_title=title,
        video_date=published,
        facts=facts,
        similar=similar,
    )


def default_live(
    settings: Settings, deps: Deps
) -> tuple[LiveDeps, Transcriber | None]:  # pragma: no cover - prod wiring
    if settings.model_mode == "vertex":
        gen_loc = settings.gemini_region or settings.gcp_region
        embed_loc = settings.embed_region or settings.gcp_region
        live = LiveDeps(
            deps,
            VertexEmbedder(settings.gcp_project, embed_loc, settings.embed_model),
            VertexSpotter(settings.gcp_project, gen_loc, settings.gemini_model),
            settings.live_threshold,
            judge=VertexJudge(settings.gcp_project, gen_loc, settings.gemini_model),
            instant=settings.live_instant,
        )
        transcriber = GeminiLiveTranscriber(
            settings.gcp_project, settings.live_region, settings.live_model
        )
        return live, transcriber
    return LiveDeps(deps, HashEmbedder(), HeuristicSpotter(), settings.live_threshold), None


def default_queue(settings: Settings) -> TaskQueue:  # pragma: no cover - prod wiring
    if settings.tasks_mode == "cloudtasks":
        return CloudTasksQueue(
            settings.gcp_project,
            settings.gcp_region,
            settings.tasks_queue,
            settings.service_url,
            settings.tasks_sa_email,
        )
    return InlineQueue()


def dev_verifier(token: str) -> dict[str, object]:
    """PC_AUTH_DISABLED=true locally: every caller is one signed in dev user."""
    return {"uid": "local-dev", "firebase": {"sign_in_provider": "google.com"}}


def _valid_id(v: str) -> bool:
    return 8 <= len(v) <= 64 and v.replace("-", "").replace("_", "").isalnum()


def create_app(
    settings: Settings | None = None,
    verifier: Verifier | None = None,
    store: Store | None = None,
    deps: Deps | None = None,
    queue: TaskQueue | None = None,
    oidc_verifier: OidcVerifier | None = None,
    bot_api: BotApi | None = None,
    live: LiveDeps | None = None,
    transcriber: Transcriber | None = None,
    clip_transcriber: ClipTranscriber | None = None,
    clip_store: InMemorySnapshots | GcsSnapshots | None = None,
    image_reader: Callable[[bytes], list[str]] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    docs_on = settings.env != "prod"
    app = FastAPI(
        title="Proof Card API",
        docs_url="/docs" if docs_on else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_on else None,
    )
    app.state.settings = settings
    if verifier is None and settings.auth_disabled:  # local dev only (prod refuses, config.py)
        verifier = dev_verifier
    app.state.verifier = verifier or firebase_verifier(settings.gcp_project)
    allowed_origins = {
        o.strip().rstrip("/")
        for o in [settings.public_base_url, *settings.live_origins.split(",")]
        if o.strip()
    }
    if store is None and settings.model_mode == "stub" and not settings.gcp_project:
        # Local demo without GCP (README "Run locally"): nothing to connect to, keep it in
        # memory. Prod can't hit this: stub mode is refused there (config.py).
        log.warning("no PC_GCP_PROJECT in stub mode: in memory store, data is not kept")
        store = InMemoryStore()
    app.state.store = store or FirestoreStore(settings.gcp_project)
    app.state.library = Library(app.state.store)
    app.state.deps = deps or default_deps(settings, app.state.store)
    app.state.queue = queue or default_queue(settings)
    if live is None:
        live, transcriber = default_live(settings, app.state.deps)
    app.state.live, app.state.transcriber = live, transcriber
    if image_reader is None and settings.model_mode == "vertex":  # pragma: no cover
        image_reader = VertexImageReader(
            settings.gcp_project,
            settings.gemini_region or settings.gcp_region,
            settings.gemini_model,
        )
    app.state.image_reader = image_reader
    if clip_transcriber is None and settings.model_mode == "vertex":  # pragma: no cover
        clip_transcriber = GeminiClipTranscriber(
            settings.gcp_project,
            settings.live_region,
            settings.clip_model,
            settings.gemini_model,
            settings.gemini_region or settings.gcp_region,
        )
    app.state.clip = clip_transcriber
    # Uploaded clips wait here for their job: GCS clips/ (never served), else in memory.
    app.state.clips = clip_store or (
        GcsSnapshots(settings.proof_bucket, prefix="clips")
        if settings.proof_bucket
        else InMemorySnapshots()
    )
    token = settings.telegram_bot_token.get_secret_value()
    app.state.bot_api = bot_api or (HttpBotApi(token) if token else None)
    app.state.alerter = (
        alerts.Alerter(app.state.bot_api, app.state.store, settings.public_base_url)
        if app.state.bot_api is not None
        else None
    )
    app.state.oidc = oidc_verifier or (
        google_oidc_verifier(settings.service_url, settings.tasks_sa_email)
        if settings.tasks_mode == "cloudtasks"
        else None
    )
    app.state.limiter = TokenBucket(rate_per_min=settings.public_rate_per_min)
    app.state.prebunk_limiter = TokenBucket(rate_per_min=settings.prebunk_per_min)
    app.state.feed_limiter = TokenBucket(rate_per_min=settings.feed_rate_per_min)
    app.state.library_limiter = TokenBucket(rate_per_min=settings.library_rate_per_min)
    # Reports are typed by people: a handful a minute per IP is plenty, spam stops here.
    app.state.report_limiter = TokenBucket(rate_per_min=REPORTS_PER_MIN)

    # Clip uploads go straight to the Cloud Run URL (VITE_LIVE_ORIGIN) from our own pages:
    # only our configured origins, POST + Authorization, no cookies.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_methods=["POST"],
        allow_headers=["Authorization"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        upload = request.url.path == "/api/check/image" or request.url.path.endswith("/check")
        cap = alter.MAX_UPLOAD_BYTES + 64_000 if upload else settings.max_body_bytes
        if request.url.path.endswith("/clip"):
            cap = MAX_CLIP_BYTES + 64_000
        if length is not None and (not length.isdigit() or int(length) > cap):
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    def client_ip(request: Request) -> str:
        # The Google front end APPENDS the peer IP to X-Forwarded-For, so the rightmost
        # entry is trustworthy; leftmost entries can be spoofed by the caller. Behind
        # Firebase Hosting that peer is a Google proxy (a different one per request), so
        # skip trusted proxy hops from the right: the next entry is the real client.
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",")]
        hops = [h for h in hops if h]
        while len(hops) > 1 and is_cdn_hop(hops[-1]):
            hops.pop()
        return hops[-1] if hops else (request.client.host if request.client else "?")

    def rate_limited(request: Request) -> None:
        if not app.state.limiter.allow(client_ip(request)):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow down")

    # /api/health is the one to probe: Cloud Run reserves some paths ending in "z" and
    # recommends avoiding them all (https://docs.cloud.google.com/run/docs/known-issues),
    # and Hosting only rewrites /api/** to us. /healthz stays for local runs.
    @app.get("/api/health")
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/prebunk", status_code=status.HTTP_201_CREATED)
    def prebunk(
        body: PrebunkRequest,
        user: Annotated[Principal, Depends(admin_principal)],
    ) -> dict[str, str]:
        today = datetime.now(UTC).date().isoformat()
        if not app.state.prebunk_limiter.allow(user.uid):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow down")
        if (
            user.is_anonymous
            and app.state.store.count_anon_sessions_today(today) >= settings.prebunk_anon_daily_cap
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="daily anonymous brief limit reached",
            )
        cap = 5 if user.is_anonymous else settings.prebunk_daily_cap
        if app.state.store.count_sessions_since(user.uid, today) >= cap:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="daily brief limit reached"
            )
        topic = body.topic.strip()
        if not topic and body.youtube_url is not None:
            title_of = app.state.deps.video_title
            topic = (title_of(str(body.youtube_url)) if title_of else "").strip()[:500]
            if not topic:
                raise HTTPException(
                    status_code=422, detail="couldn't read that video's title: add a topic"
                )
        doc = SessionDoc(
            owner_uid=user.uid,
            topic=topic,
            speaker=body.speaker,
            youtube_url=str(body.youtube_url) if body.youtube_url else None,
            status="prebunking",
            is_anonymous=user.is_anonymous,
            alert_chat_id=app.state.store.get_tg_chat(user.uid),  # linked once, alerts on
        )
        sid = app.state.store.create_session(doc)
        log.info("session created", extra={"fields": {"session": sid}})
        n = settings.prebunk_claims
        app.state.queue.enqueue_prebunk(sid, lambda: run_prebunk(sid, app.state.deps, n))
        return {"session_id": sid}

    @app.get("/api/sessions/{session_id}")
    def get_session(
        session_id: str, user: Annotated[Principal, Depends(admin_principal)]
    ) -> SessionView:
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        # 404 for "not yours" too: never confirm another user's session exists.
        if s is None or s.owner_uid != user.uid:
            raise HTTPException(status_code=404, detail="not found")
        if prebunk_stalled(s):
            # Take the lease first (fresh beat) so the next poll doesn't queue it again;
            # run_prebunk is idempotent, so a late duplicate only finishes the same bank.
            app.state.store.update_session(session_id, prebunk_beat=datetime.now(UTC))
            n = settings.prebunk_claims
            app.state.queue.enqueue_prebunk(
                session_id, lambda: run_prebunk(session_id, app.state.deps, n)
            )
            log.warning("stalled prebunk re-queued", extra={"fields": {"session": session_id}})
        claims = app.state.store.list_claims(session_id)
        return SessionView.build(session_id, s, claims)

    @app.get("/api/sessions/{session_id}/facts")
    def session_facts(
        session_id: str, user: Annotated[Principal, Depends(admin_principal)]
    ) -> FactBankDoc:
        """The researched fact bank this session checks against, as JSON (export / reuse)."""
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if s is None or s.owner_uid != user.uid or not s.fact_bank_key:
            raise HTTPException(status_code=404, detail="not found")
        bank: FactBankDoc | None = app.state.store.get_fact_bank(s.fact_bank_key)
        if bank is None:
            raise HTTPException(status_code=404, detail="not found")
        return bank

    @app.post("/api/sessions/{session_id}/share")
    def share_session(
        session_id: str,
        body: ShareRequest,
        user: Annotated[Principal, Depends(admin_principal)],
    ) -> dict[str, bool]:
        """Owner turns the read only viewer link (/watch/:id) on or off."""
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if s is None or s.owner_uid != user.uid:
            raise HTTPException(status_code=404, detail="not found")
        app.state.store.update_session(session_id, public_view=body.public_view)
        return {"public_view": body.public_view}

    @app.post("/api/sessions/{session_id}/video")
    def set_video(
        session_id: str,
        body: VideoRequest,
        user: Annotated[Principal, Depends(admin_principal)],
    ) -> dict[str, str]:
        """Owner adds the live link after the brief was built. Claims, cards and the fact
        bank are untouched, so the live page matches speech against the same prebunks."""
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if s is None or s.owner_uid != user.uid:
            raise HTTPException(status_code=404, detail="not found")
        if not app.state.prebunk_limiter.allow(user.uid):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow down")
        url = str(body.youtube_url)
        app.state.store.update_session(session_id, youtube_url=url)
        return {"youtube_url": url}

    @app.get("/api/sessions/{session_id}/feed")
    def session_feed(session_id: str, request: Request, since: datetime | None = None) -> FeedView:
        """Public, read only card stream for /watch/:id (polled every 2 s). Served by us,
        not a Firestore listener: rules can't hide fields, so a client read of the session
        doc would expose owner_uid. Only opted in sessions; 404 otherwise, never "private"."""
        if not app.state.feed_limiter.allow(client_ip(request)):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow down")
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if s is None or not s.public_view:
            raise HTTPException(status_code=404, detail="not found")
        if since is not None and since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
        # 2 s overlap: an update stamped just before this read may commit just after it.
        # The client keys claims by id, so repeats are harmless.
        now = datetime.now(UTC)
        claims = app.state.store.list_claims(session_id)
        return FeedView.build(session_id, s, claims, since, now - timedelta(seconds=2))

    @app.post("/api/sessions/{session_id}/clip", status_code=status.HTTP_202_ACCEPTED)
    async def upload_clip(
        session_id: str,
        user: Annotated[Principal, Depends(admin_principal)],
        file: Annotated[UploadFile, File()],
        timed: bool = False,
    ) -> ClipJobView:
        """?timed=true (replay): sentences carry their second in the clip, stored on each live
        claim, so the Live page pops each card at that moment of the YouTube video.

        Fallback when live audio isn't possible: a recorded clip, transcribed in one call,
        every sentence through the same live engine. Answers at once (202) and works in the
        background; the browser polls GET /clip for progress and the events the websocket
        would have pushed. A 9 min clip outlived the request (demo, 16 Oct 2026)."""
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if s is None or s.owner_uid != user.uid:
            raise HTTPException(status_code=404, detail="not found")
        mime = clip_mime(file.content_type)
        if mime is None:
            raise HTTPException(
                status_code=415, detail="audio only: mp3, m4a, wav, ogg, webm, flac"
            )
        data = await file.read(MAX_CLIP_BYTES + 1)
        if len(data) > MAX_CLIP_BYTES:
            raise HTTPException(status_code=413, detail="clip over 20 MB, trim it")
        if app.state.clip is None:
            raise HTTPException(status_code=503, detail="clip transcription needs the cloud model")
        job_ = s.clip_job
        if job_ is not None and job_.state in ("queued", "running") and not clip_stalled(job_):
            raise HTTPException(status_code=409, detail="a clip is already being checked")
        if not app.state.prebunk_limiter.allow(user.uid):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow down")
        digest = sha256_hex(data)
        await run_in_threadpool(app.state.clips.put, digest, data, mime)
        job = ClipJob(digest=digest, mime=mime, timed=timed)
        app.state.store.update_session(session_id, clip_job=job)
        await run_in_threadpool(_enqueue_clip, session_id)
        return ClipJobView.build(job)

    @app.get("/api/sessions/{session_id}/clip")
    def clip_status(
        session_id: str, user: Annotated[Principal, Depends(admin_principal)]
    ) -> ClipJobView:
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if s is None or s.owner_uid != user.uid or s.clip_job is None:
            raise HTTPException(status_code=404, detail="not found")
        job = s.clip_job
        if clip_stalled(job):
            # Its instance died (revision swap): take the lease, then resume from job.done.
            job = job.model_copy(update={"beat": datetime.now(UTC)})
            app.state.store.update_session(session_id, clip_job=job)
            _enqueue_clip(session_id)
            log.warning("stalled clip job re-queued", extra={"fields": {"session": session_id}})
        return ClipJobView.build(job)

    def _enqueue_clip(session_id: str) -> None:
        app.state.queue.enqueue_clip(session_id, lambda: asyncio.run(_run_clip(session_id)))

    def _save_job(session_id: str, **changes: object) -> ClipJob | None:
        s = app.state.store.get_session(session_id)
        if s is None or s.clip_job is None:
            return None
        job: ClipJob = ClipJob.model_validate(
            {**s.clip_job.model_dump(), **changes, "beat": datetime.now(UTC)}
        )
        app.state.store.update_session(session_id, clip_job=job)
        return job

    async def _transcribe(audio: bytes, job: ClipJob, vocab: list[str]) -> list[Any]:
        timed_fn = getattr(app.state.clip, "transcribe_timed", None) if job.timed else None
        if timed_fn is not None:
            return list(await run_in_threadpool(timed_fn, audio, job.mime, vocab))
        text = await run_in_threadpool(app.state.clip.transcribe, audio, job.mime, vocab)
        return [(None, line) for line in clip_sentences(text)]

    async def _run_clip(session_id: str) -> None:
        """Transcribe once (lines stored), then feed the live engine CLIP_BATCH lines at a
        time, saving progress and events after each batch. A retry or re-queue resumes at
        job.done; only a batch cut off mid way runs again."""
        s = app.state.store.get_session(session_id)
        if s is None or s.clip_job is None or s.clip_job.state in ("done", "failed"):
            return
        job = _save_job(session_id, state="running") or s.clip_job
        audio = await run_in_threadpool(app.state.clips.get, job.digest)
        if job.lines is None:
            if audio is None:
                _save_job(session_id, state="failed", error="clip expired, upload it again")
                return
            vocab = vocabulary_for(
                [
                    c.text
                    for _, c in app.state.store.list_claims(session_id)
                    if c.source == ClaimSource.PREDICTED
                ]
            )
            # Gemini under load answers 429/503 in seconds (prod e2e 16 Oct 21:5x: two clips
            # at once both failed in 11 s). Retry with backoff before telling the user.
            pairs = None
            for attempt in range(CLIP_TRIES):
                try:
                    pairs = await _transcribe(audio, job, vocab)
                    break
                except Exception:
                    log.warning("clip transcription attempt failed", exc_info=True)
                    if attempt + 1 < CLIP_TRIES:
                        await asyncio.sleep(CLIP_BACKOFF_S * (attempt + 1))
            if pairs is None:
                log.error("clip transcription failed")
                _save_job(session_id, state="failed", error="transcription failed, try again")
                await run_in_threadpool(app.state.clips.delete, job.digest)
                return
            lines = [ClipLine(t=t, text=line[:2_000]) for t, line in pairs][:2_000]
            job = (
                _save_job(
                    session_id,
                    lines=lines,
                    timed=job.timed and hasattr(app.state.clip, "transcribe_timed"),
                )
                or job
            )
        events: list[dict[str, object]] = list(job.events)

        async def collect(ev: dict[str, object]) -> None:
            events.append(ev)

        app.state.store.update_session(session_id, status="live")
        lines = job.lines or []
        await run_in_threadpool(_tg_run, session_id, "the recorded clip")
        try:
            engine = LiveEngine(session_id, app.state.live, collect, _alert_fn())
            await engine.warm()
            for start in range(job.done, len(lines), CLIP_BATCH):
                for line in lines[start : start + CLIP_BATCH]:
                    await engine.on_sentence(line.text, t_offset=line.t)
                await engine.drain()
                _save_job(
                    session_id, done=min(len(lines), start + CLIP_BATCH), events=events[-2_000:]
                )
            _save_job(session_id, state="done", done=len(lines), events=events[-2_000:])
            await run_in_threadpool(_tg_run, session_id, None)
        finally:
            app.state.store.update_session(session_id, status="ready")
        await run_in_threadpool(app.state.clips.delete, job.digest)

    def _alert_fn() -> Alert | None:
        return app.state.alerter.alert if app.state.alerter is not None else None

    def _tg_run(session_id: str, starting: str | None) -> None:
        """Telegram, automatic: a run start ("checking now") or end (verdict summary) for a
        chat the owner linked once. Off the result path: a Bot API failure is logged only."""
        alerter = app.state.alerter
        if alerter is None:
            return
        try:
            if starting is not None:
                alerter.started(session_id, starting)
            else:
                alerter.summary(session_id)
        except Exception:
            log.warning("telegram run message failed", exc_info=True)

    @app.post("/api/sessions/{session_id}/telegram-link")
    def telegram_link(
        session_id: str, user: Annotated[Principal, Depends(admin_principal)]
    ) -> dict[str, str]:
        """During: deep link that attaches the owner's Telegram to this session's alerts."""
        s = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if s is None or s.owner_uid != user.uid:
            raise HTTPException(status_code=404, detail="not found")
        if app.state.alerter is None or not settings.telegram_bot_username:
            raise HTTPException(status_code=503, detail="telegram alerts are not configured")
        if not app.state.prebunk_limiter.allow(user.uid):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow down")
        url = alerts.new_link(app.state.store, session_id, settings.telegram_bot_username)
        return {"url": url}

    @app.websocket("/api/live/{session_id}")
    async def live_ws(ws: WebSocket, session_id: str) -> None:
        """During: browser streams tab audio (PCM16 16 kHz binary frames) or transcript
        lines ({"type": "text"}); we push heard / match / checking / proved events.

        Auth is the FIRST message ({"type": "auth", "token": <Firebase ID token>}), never
        the URL, so tokens stay out of access logs. Cloud Run websockets:
        https://cloud.google.com/run/docs/triggering/websockets
        """
        origin = (ws.headers.get("origin") or "").rstrip("/")
        if settings.env == "prod" and origin not in allowed_origins:
            await ws.close(code=4403)  # cross site websocket hijacking guard
            return
        await ws.accept()
        try:
            first = await asyncio.wait_for(ws.receive_json(), timeout=LIVE_AUTH_TIMEOUT_S)
            claims = (
                app.state.verifier(str(first.get("token", "")))
                if (isinstance(first, dict) and first.get("type") == "auth")
                else {}
            )
        except Exception:
            claims = {}
        uid = claims.get("uid") or claims.get("sub")
        sess = app.state.store.get_session(session_id) if _valid_id(session_id) else None
        if not uid or sess is None or sess.owner_uid != uid:
            await ws.close(code=4401)  # one code for every failure, like the HTTP 401/404
            return
        app.state.store.update_session(session_id, status="live")
        lock = asyncio.Lock()

        async def emit(ev: dict[str, object]) -> None:
            try:
                async with lock:
                    await ws.send_json(ev)
            except Exception:  # socket gone: the card is stored, the feed reloads it
                log.debug("live emit dropped, socket closed")

        engine = LiveEngine(session_id, app.state.live, emit, _alert_fn())
        warm = asyncio.create_task(engine.warm())  # index ready before the first sentence
        await run_in_threadpool(_tg_run, session_id, "live")
        audio: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=LIVE_AUDIO_QUEUE)
        stt: asyncio.Task[None] | None = None
        await emit({"type": "ready", "audio": app.state.transcriber is not None})
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if (data := msg.get("bytes")) is not None:
                    if app.state.transcriber is None or len(data) > LIVE_MAX_FRAME:
                        await emit({"type": "error", "code": "audio_unavailable"})
                        continue
                    if stt is None:
                        vocab = vocabulary_for(
                            [
                                c.text
                                for _, c in app.state.store.list_claims(session_id)
                                if c.source == ClaimSource.PREDICTED
                            ]
                        )
                        stt = asyncio.create_task(
                            app.state.transcriber.run(audio, engine.on_sentence, vocab)
                        )
                    if audio.full():  # never let a slow upstream grow memory: drop oldest
                        audio.get_nowait()
                    audio.put_nowait(data)
                    continue
                try:
                    body = json.loads(msg.get("text") or "")
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    continue
                if body.get("type") == "text" and isinstance(body.get("text"), str):
                    await engine.on_sentence(body["text"])
                elif body.get("type") == "stop":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            if stt is not None:
                if audio.full():
                    audio.get_nowait()
                audio.put_nowait(None)
                try:
                    await asyncio.wait_for(stt, timeout=15)
                except Exception:
                    stt.cancel()
            warm.cancel()
            await engine.drain()
            app.state.store.update_session(session_id, status="ready")
            await run_in_threadpool(_tg_run, session_id, None)
            with contextlib.suppress(Exception):  # already closed by the client
                await ws.close()

    @app.post("/tasks/prebunk", include_in_schema=False)
    def task_prebunk(
        body: TaskPrebunk, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, int]:
        verify = app.state.oidc
        token = (authorization or "").removeprefix("Bearer ").strip()
        try:
            if verify is None or not token:
                raise ValueError("no task auth")
            verify(token)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="not found") from exc
        result: dict[str, int] = run_prebunk(
            body.session_id, app.state.deps, settings.prebunk_claims
        )
        return result

    @app.post("/tasks/clip", include_in_schema=False)
    async def task_clip(
        body: TaskPrebunk, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, str]:
        verify = app.state.oidc
        token = (authorization or "").removeprefix("Bearer ").strip()
        try:
            if verify is None or not token:
                raise ValueError("no task auth")
            verify(token)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="not found") from exc
        await _run_clip(body.session_id)
        return {"ok": "done"}

    @app.get("/api/cards")
    def list_cards(
        request: Request,
        response: Response,
        q: Annotated[str, Query(max_length=200)] = "",
        verdict: Annotated[str, Query(max_length=60)] = "",
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> dict[str, Any]:
        """Proof Library (/cards): every issued card, public safe fields only, 24 a page.
        Search ranks claim words first, typo tolerant, Hindi and English. Cached at the
        Hosting CDN for 60 s (https://firebase.google.com/docs/hosting/manage-cache)."""
        # Only known params, once each: a cache buster (?cb=1) would make every hit a CDN
        # miss and so fresh Firestore reads. 400 is not cached (no Cache-Control).
        keys = [k for k, _ in request.query_params.multi_items()]
        if set(keys) - LIBRARY_PARAMS or len(keys) != len(set(keys)):
            raise HTTPException(status_code=400, detail="unknown or repeated parameter")
        if not app.state.library_limiter.allow(client_ip(request)):
            retry = max(1, -(-60 // app.state.library_limiter.rate_per_min))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="slow down",
                headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
            )
        wanted = frozenset(v for v in verdict.upper().split(",") if v)
        if not wanted <= set(VERDICTS):
            raise HTTPException(status_code=422, detail="unknown verdict")
        since, until = (
            (t.replace(tzinfo=UTC) if t is not None and t.tzinfo is None else t)
            for t in (since, until)
        )
        try:
            out: dict[str, Any] = app.state.library.search(q, wanted, since, until, cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="bad cursor") from exc
        response.headers["Cache-Control"] = "public, max-age=30, s-maxage=60"
        return out

    @app.get("/api/cards/{card_id}")
    def get_card(card_id: str) -> CardDoc:
        if not _valid_id(card_id):
            raise HTTPException(status_code=404, detail="not found")
        card: CardDoc | None = app.state.store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="not found")
        return card

    @app.get("/api/cards/{card_id}/search-suggestion", include_in_schema=False)
    def search_suggestion(card_id: str) -> HTMLResponse:
        """Google's Search suggestion for a card, framed by the share page and the brief."""
        card = app.state.store.get_card(card_id) if _valid_id(card_id) else None
        if card is None or not card.search_suggestion_html:
            raise HTTPException(status_code=404, detail="not found")
        return HTMLResponse(
            share_page.suggestion_doc(card.search_suggestion_html),
            headers={
                "Content-Security-Policy": share_page.SUGGESTION_CSP,
                "X-Frame-Options": "SAMEORIGIN",
                "Cache-Control": "public, max-age=3600",
            },
        )

    @app.get("/api/snapshots/{digest}")
    def get_snapshot(digest: str, request: Request) -> Response:
        """The exact bytes behind a proof, so anyone can recompute the sha256 on a card.
        Always a download: a stored third party page must never render on our origin."""
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(status_code=404, detail="not found")
        rate_limited(request)
        body = app.state.deps.snapshots.get(digest)
        if body is None or sha256_hex(body) != digest:  # never serve bytes that don't match
            raise HTTPException(status_code=404, detail="not found")
        return Response(
            body,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{digest}.snapshot"',
                "Cache-Control": "public, max-age=31536000, immutable",  # content addressed
            },
        )

    def log_check(r: alter.CheckResult, channel: str, similarity: float | None = None) -> None:
        doc = CheckDoc(
            card_id=r.card_id,
            channel=channel,
            result=r.result,
            changed=r.changed,
            text_similarity=similarity,
            phash_distance=r.phash_distance,
        )
        try:
            app.state.store.add_check(doc)
        except Exception:  # analytics only, never fail the user's check
            log.exception("check log failed")

    def check_bytes(data: bytes) -> alter.CheckResult:
        return alter.check_image(
            data, app.state.store.get_card, settings.public_base_url, settings.telegram_bot_username
        )

    @lru_cache(maxsize=256)  # cards are immutable, so the rendered bytes are too
    def card_bytes(card_id: str, fmt: str) -> bytes | None:
        card = app.state.store.get_card(card_id)
        if card is None:
            return None
        img = card_image.render(
            card, card_id, settings.public_base_url, settings.telegram_bot_username
        )
        return card_image.encode(img, "JPEG" if fmt == "jpg" else "PNG")

    async def read_upload(file: UploadFile) -> bytes:
        data = await file.read(alter.MAX_UPLOAD_BYTES + 1)
        if len(data) > alter.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="image too large")
        return data

    @app.post("/api/check", dependencies=[Depends(rate_limited)])
    def check_text(body: CheckTextRequest) -> CheckTextResponse:
        card: CardDoc | None = app.state.store.get_card(body.card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="not found")
        sim, removed, added = alter.text_similarity(card.claim, body.text)
        result: alter.Result = "VERIFIED" if not removed and not added else "ALTERED"
        log_check(alter.CheckResult(result, "text", body.card_id), "web", sim)
        return CheckTextResponse(result=result, similarity=sim, removed=removed, added=added)

    @app.post("/api/check/image", dependencies=[Depends(rate_limited)])
    async def check_image(file: Annotated[UploadFile, File()]) -> CheckImageResponse:
        r = await run_in_threadpool(check_bytes, await read_upload(file))
        log_check(r, "web")
        return CheckImageResponse(
            result=r.result, reason=r.reason, card_id=r.card_id, changed=r.changed
        )

    @app.get("/v/{name}", include_in_schema=False)
    async def share(name: str) -> Response:
        card_id, _, ext = name.partition(".")
        if ext in ("png", "jpg") and _valid_id(card_id):
            data = await run_in_threadpool(card_bytes, card_id, ext)
            if data is not None:
                media = "image/jpeg" if ext == "jpg" else "image/png"
                cache = {"Cache-Control": "public, max-age=31536000, immutable"}
                return Response(data, media_type=media, headers=cache)
        elif not ext and _valid_id(card_id):
            card = app.state.store.get_card(card_id)
            if card is not None:
                html = share_page.card_page(
                    card, card_id, settings.public_base_url, settings.telegram_bot_username
                )
                return HTMLResponse(html, headers={"Content-Security-Policy": share_page.CSP})
        return HTMLResponse(
            share_page.not_found_page(),
            status_code=404,
            headers={"Content-Security-Policy": share_page.CSP},
        )

    @app.post("/v/{card_id}/check", include_in_schema=False, dependencies=[Depends(rate_limited)])
    async def share_check(card_id: str, file: Annotated[UploadFile, File()]) -> HTMLResponse:
        card = app.state.store.get_card(card_id) if _valid_id(card_id) else None
        if card is None:
            return HTMLResponse(
                share_page.not_found_page(),
                status_code=404,
                headers={"Content-Security-Policy": share_page.CSP},
            )
        r = await run_in_threadpool(check_bytes, await read_upload(file))
        log_check(r, "web")
        if r.card_id and r.card_id != card_id:  # a different card's image uploaded here
            r = alter.CheckResult("UNKNOWN", "that image belongs to a different card", r.card_id)
        html = share_page.card_page(
            card, card_id, settings.public_base_url, settings.telegram_bot_username, r
        )
        return HTMLResponse(html, headers={"Content-Security-Policy": share_page.CSP})

    @app.post("/v/{card_id}/report", include_in_schema=False)
    def share_report(
        card_id: str,
        request: Request,
        issue: Annotated[str, Form()] = "",
        email: Annotated[str, Form()] = "",
        source_url: Annotated[str, Form()] = "",
    ) -> HTMLResponse:
        """ "Report this card" on /v/<id> (Team lead VN, 18 Oct): the issue is required,
        email and a source link are optional. Stored in Firestore `reports`, server only.
        Zero JS, plain form post like /v/<id>/check. No model calls."""
        csp = {"Content-Security-Policy": share_page.CSP, "Cache-Control": "no-store"}
        card = app.state.store.get_card(card_id) if _valid_id(card_id) else None
        if card is None:
            return HTMLResponse(share_page.not_found_page(), status_code=404, headers=csp)
        form = {"issue": issue.strip(), "email": email.strip(), "source_url": source_url.strip()}

        def page(msg: str, code: int, ok: bool = False) -> HTMLResponse:
            html = share_page.card_page(
                card,
                card_id,
                settings.public_base_url,
                settings.telegram_bot_username,
                report=share_page.ReportState(msg, ok, {} if ok else form),
            )
            return HTMLResponse(html, status_code=code, headers=csp)

        if not app.state.report_limiter.allow(client_ip(request)):
            return page("Too many reports from here. Try again in a minute.", 429)
        error = share_page.report_error(form)
        if error:
            return page(error, 400)
        try:
            doc = ReportDoc(
                card_id=card_id,
                claim=card.claim,
                verdict=card.verdict,
                issue=form["issue"],
                email=form["email"] or None,
                source_url=form["source_url"] or None,
            )
        except ValidationError:
            return page("Please check the fields and try again.", 400)
        app.state.store.add_report(doc)
        return page("Thanks, your report is in. We review every report.", 200, ok=True)

    def run_bot_check(session_id: str) -> None:
        """Telegram claim check job: verify the one claim, send the verdict to the chat."""
        store = app.state.store
        s = store.get_session(session_id)
        if s is None or s.alert_chat_id is None or app.state.bot_api is None:
            return
        if s.status == "closed":  # a Cloud Tasks retry after the verdict went out
            return
        claims = store.list_claims(session_id)
        if not claims:
            return

        def one(item: tuple[str, ClaimDoc]) -> str | None:
            cid, claim = item
            try:
                return claim.card_id or verify_claim(
                    session_id, cid, app.state.deps, Trace(), race_hint=True
                )
            except Exception:  # one failed claim answers UNVERIFIABLE, never sinks the rest
                log.warning("bot claim check failed", exc_info=True)
                return None

        # A forward with several claims: all checked at once. Each verdict goes out the
        # moment it is ready, as a reply to the message it answers ("2/3" when there are
        # several), so a late verdict can't read as the answer to the next message the
        # person sent (prod 17 Oct: "water boils" landed under the Modi quote).
        n = len(claims)
        # A slow check never sits silent: if no verdict is out after STILL_CHECKING_AFTER_S,
        # one "still checking" line goes to the chat (judges must never think it's stuck).
        first_sent = threading.Event()

        def still_checking() -> None:
            if first_sent.is_set():
                return
            with contextlib.suppress(Exception):
                app.state.bot_api.call(
                    "sendMessage",
                    {
                        "chat_id": s.alert_chat_id,
                        "text": STILL_CHECKING,
                        **(
                            {
                                "reply_parameters": {
                                    "message_id": s.tg_reply_to,
                                    "allow_sending_without_reply": True,
                                }
                            }
                            if s.tg_reply_to
                            else {}
                        ),
                    },
                )

        timer = threading.Timer(STILL_CHECKING_AFTER_S, still_checking)
        timer.daemon = True
        timer.start()
        with ThreadPoolExecutor(max_workers=n, thread_name_prefix="botcheck") as pool:
            futures = {pool.submit(one, item): i for i, item in enumerate(claims)}
            for fut in as_completed(futures):
                first_sent.set()
                timer.cancel()
                i = futures[fut]
                card_id = fut.result()
                card = store.get_card(card_id) if card_id else None
                try:
                    send_claim_result(
                        app.state.bot_api,
                        s.alert_chat_id,
                        claims[i][1].text,
                        card,
                        card_id,
                        settings.public_base_url,
                        reply_to=s.tg_reply_to,
                        label=f"{i + 1}/{n}" if n > 1 else "",
                    )
                except Exception:
                    # One failed send (network blip to Telegram) must not drop the other
                    # verdicts of the forward, nor make a Cloud Tasks retry re-send the
                    # ones already delivered.
                    log.warning("bot verdict send failed", exc_info=True)
        # shortcut: a Cloud Tasks retry after a crash mid-loop re-sends verdicts already
        # out; per-claim sent flags if that ever shows up in prod.
        store.update_session(session_id, status="closed")

    def split_claims(text: str) -> list[str]:
        """A short line is one claim; a long forward is split into its checkable claims."""
        if len(text) <= FORWARD_SPLIT_CHARS and not several_claims(text):
            return []
        spotter: Spotter = app.state.live.spotter
        # The spotter reads one sentence heard on air; handed a whole forward it returns it
        # as one claim (prod e2e 16 Oct, 3 claims -> 1 MISLEADING). Spot sentence by sentence.
        sentences = [p for p in _SENTENCE_END.split(text[:3_000].strip()) if looks_like_claim(p)]
        if len(sentences) < 2:
            return spotter.spot_claims(text[:3_000])
        out: list[str] = []
        for sentence in sentences[:FORWARD_SENTENCES]:
            # The spotter's cheap pre filter wants a number ("Water boils at 100 C" passed,
            # "The capital of Australia is Sydney" and "The Earth has two moons" were
            # dropped, so a 3-claim message got 1 verdict, prod 17 Oct 00:1x). A sentence a
            # person sent the bot is theirs to check: a plain statement is kept as written.
            spotted = spotter.spot_claims(sentence) or ([sentence] if _statement(sentence) else [])
            out += [c for c in spotted if c not in out]
            if len(out) >= MAX_FORWARD_CLAIMS:
                break
        return out

    def check_claim(
        claims: list[str], chat_id: int, ack: Callable[[], None], message_id: int | None = None
    ) -> str:
        text = claims[0]
        today = datetime.now(UTC).date().isoformat()
        owner = f"tg:{pseudonymize(chat_id)}"
        if app.state.store.count_sessions_since(owner, today) >= BOT_DAILY_CHECKS:
            return "limit"
        sid = app.state.store.create_session(
            SessionDoc(
                owner_uid=owner,
                topic=text[:500],
                status="live",
                alert_chat_id=chat_id,
                tg_reply_to=message_id,
            )
        )
        for c in claims:
            app.state.store.add_claim(
                sid, ClaimDoc(text=c[:4_000], lang=claim_lang(c), source=ClaimSource.LIVE)
            )
        log.info("bot claim queued", extra={"fields": {"session": sid}})
        try:
            ack()
        except Exception:
            # The "checking" line is a courtesy: if it fails the check must still be
            # queued, or the person waits for a verdict that never comes.
            log.warning("bot ack failed, checking anyway", exc_info=True)
        app.state.queue.enqueue_check(sid, lambda: run_bot_check(sid))
        return "queued"

    @app.post("/tasks/check", include_in_schema=False)
    def task_check(
        body: TaskPrebunk, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, str]:
        verify = app.state.oidc
        token = (authorization or "").removeprefix("Bearer ").strip()
        try:
            if verify is None or not token:
                raise ValueError("no task auth")
            verify(token)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="not found") from exc
        run_bot_check(body.session_id)
        return {"ok": "done"}

    def link_alerts(payload: str, chat_id: int) -> str | None:
        s = alerts.redeem(app.state.store, payload, chat_id)
        return s.topic if s is not None else None

    @app.post("/tg/webhook")
    async def tg_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        expected = settings.telegram_webhook_secret.get_secret_value()
        if not telegram_secret_ok(x_telegram_bot_api_secret_token, expected):
            # 404 not 401: don't confirm the endpoint exists to scanners.
            raise HTTPException(status_code=404, detail="not found")
        try:
            update = TgUpdate.model_validate(await request.json())
        except (ValidationError, ValueError):
            return {"ok": True}  # ack junk so Telegram doesn't retry it forever
        api = app.state.bot_api
        if api is None:
            return {"ok": True}
        bot = BotDeps(
            api=api,
            get_card=app.state.store.get_card,
            check_image=check_bytes,
            base_url=settings.public_base_url,
            log_check=log_check,
            link_alerts=link_alerts,
            check_claim=check_claim,
            split_claims=split_claims,
            read_image=app.state.image_reader or (lambda b: []),
        )
        try:
            await run_in_threadpool(handle_update, update, bot)
        except Exception:  # never make Telegram retry a poison update
            log.exception("tg handler failed")
        return {"ok": True}

    return app
