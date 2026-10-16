"""Proof Card main service (Cloud Run): API, prebunk jobs, public card reads, Telegram webhook."""

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
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
    MAX_CLIP_BYTES,
    ClipTranscriber,
    GeminiClipTranscriber,
    clip_mime,
)
from app.clip import sentences as clip_sentences
from app.config import Settings, get_settings
from app.factcheck import FactCheckClient, FactCheckedModel
from app.live import (
    Alert,
    GeminiLiveTranscriber,
    HashEmbedder,
    HeuristicSpotter,
    LiveDeps,
    LiveEngine,
    Transcriber,
    VertexEmbedder,
    VertexJudge,
    VertexSpotter,
    vocabulary_for,
)
from app.logging_setup import configure_logging
from app.model import ModelClient, StubModel, VertexModel
from app.pipeline import Deps, run_prebunk
from app.proof import FixtureFetcher, GcsSnapshots, HttpFetcher, InMemorySnapshots
from app.schemas import (
    CardDoc,
    CheckDoc,
    CheckImageResponse,
    CheckTextRequest,
    CheckTextResponse,
    ClaimSource,
    PrebunkRequest,
    SessionDoc,
    SessionView,
    TaskPrebunk,
    TgUpdate,
)
from app.security import TokenBucket, sha256_hex, telegram_secret_ok
from app.store import FirestoreStore, InMemoryStore, Store
from app.tasks import CloudTasksQueue, InlineQueue, OidcVerifier, TaskQueue, google_oidc_verifier
from app.telegram import BotApi, BotDeps, HttpBotApi, handle_update

log = logging.getLogger("proofcard")

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
    return Deps(store=store, model=model, fetcher=fetcher, snapshots=snaps)


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
    app.state.deps = deps or default_deps(settings, app.state.store)
    app.state.queue = queue or default_queue(settings)
    if live is None:
        live, transcriber = default_live(settings, app.state.deps)
    app.state.live, app.state.transcriber = live, transcriber
    if clip_transcriber is None and settings.model_mode == "vertex":  # pragma: no cover
        clip_transcriber = GeminiClipTranscriber(
            settings.gcp_project,
            settings.live_region,
            settings.clip_model,
            settings.gemini_model,
            settings.gemini_region or settings.gcp_region,
        )
    app.state.clip = clip_transcriber
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

    def rate_limited(request: Request) -> None:
        # The Google front end APPENDS the real client IP to X-Forwarded-For, so the
        # rightmost entry is trustworthy; leftmost entries can be spoofed by the caller.
        fwd = request.headers.get("x-forwarded-for", "")
        client = fwd.split(",")[-1].strip() or (request.client.host if request.client else "?")
        if not app.state.limiter.allow(client):
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
        doc = SessionDoc(
            owner_uid=user.uid,
            topic=body.topic,
            speaker=body.speaker,
            youtube_url=str(body.youtube_url) if body.youtube_url else None,
            status="prebunking",
            is_anonymous=user.is_anonymous,
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
        claims = app.state.store.list_claims(session_id)
        return SessionView.build(session_id, s, claims)

    @app.post("/api/sessions/{session_id}/clip")
    async def upload_clip(
        session_id: str,
        user: Annotated[Principal, Depends(admin_principal)],
        file: Annotated[UploadFile, File()],
        timed: bool = False,
    ) -> dict[str, object]:
        """?timed=true (replay): sentences carry their second in the clip, stored on each live
        claim, so the Live page pops each card at that moment of the YouTube video.

        Fallback when live audio isn't possible: a recorded clip, transcribed in one
        call, every sentence through the same live engine. Returns the same events the
        websocket would have pushed, in order."""
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
        if not app.state.prebunk_limiter.allow(user.uid):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow down")
        vocab = vocabulary_for(
            [
                c.text
                for _, c in app.state.store.list_claims(session_id)
                if c.source == ClaimSource.PREDICTED
            ]
        )
        try:
            timed_fn = getattr(app.state.clip, "transcribe_timed", None) if timed else None
            if timed_fn is not None:
                timed_lines: list[tuple[float | None, str]] = list(
                    await run_in_threadpool(timed_fn, data, mime, vocab)
                )
            else:
                transcript = await run_in_threadpool(app.state.clip.transcribe, data, mime, vocab)
                timed_lines = [(None, line) for line in clip_sentences(transcript)]
        except Exception:
            log.exception("clip transcription failed")
            raise HTTPException(status_code=502, detail="transcription failed, try again") from None
        events: list[dict[str, object]] = []

        async def collect(ev: dict[str, object]) -> None:
            events.append(ev)

        app.state.store.update_session(session_id, status="live")
        try:
            engine = LiveEngine(session_id, app.state.live, collect, _alert_fn())
            await engine.warm()
            for t_off, line in timed_lines:
                await engine.on_sentence(line, t_offset=t_off)
            await engine.drain()
        finally:
            app.state.store.update_session(session_id, status="ready")
        return {"sentences": len(timed_lines), "timed": timed_fn is not None, "events": events}

    def _alert_fn() -> Alert | None:
        return app.state.alerter.alert if app.state.alerter is not None else None

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
        )
        try:
            await run_in_threadpool(handle_update, update, bot)
        except Exception:  # never make Telegram retry a poison update
            log.exception("tg handler failed")
        return {"ok": True}

    return app
