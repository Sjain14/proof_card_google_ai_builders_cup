"""Proof Card main service (Cloud Run): API, prebunk jobs, public card reads, Telegram webhook."""

import logging
from collections.abc import Awaitable, Callable
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
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from app import alter, card_image, share_page
from app.auth import Principal, Verifier, admin_principal, firebase_verifier
from app.config import Settings, get_settings
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
    PrebunkRequest,
    SessionDoc,
    SessionView,
    TaskPrebunk,
    TgUpdate,
)
from app.security import TokenBucket, telegram_secret_ok
from app.store import FirestoreStore, Store
from app.tasks import CloudTasksQueue, InlineQueue, OidcVerifier, TaskQueue, google_oidc_verifier
from app.telegram import BotApi, BotDeps, HttpBotApi, handle_update

log = logging.getLogger("proofcard")

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
    else:
        model, fetcher = StubModel(), FixtureFetcher()
    snaps = GcsSnapshots(settings.proof_bucket) if settings.proof_bucket else InMemorySnapshots()
    return Deps(store=store, model=model, fetcher=fetcher, snapshots=snaps)


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
    app.state.verifier = verifier or firebase_verifier()
    app.state.store = store or FirestoreStore(settings.gcp_project)
    app.state.deps = deps or default_deps(settings, app.state.store)
    app.state.queue = queue or default_queue(settings)
    token = settings.telegram_bot_token.get_secret_value()
    app.state.bot_api = bot_api or (HttpBotApi(token) if token else None)
    app.state.oidc = oidc_verifier or (
        google_oidc_verifier(settings.service_url, settings.tasks_sa_email)
        if settings.tasks_mode == "cloudtasks"
        else None
    )
    app.state.limiter = TokenBucket(rate_per_min=settings.public_rate_per_min)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        upload = request.url.path == "/api/check/image" or request.url.path.endswith("/check")
        cap = alter.MAX_UPLOAD_BYTES + 64_000 if upload else settings.max_body_bytes
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

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/prebunk", status_code=status.HTTP_201_CREATED)
    def prebunk(
        body: PrebunkRequest, user: Annotated[Principal, Depends(admin_principal)]
    ) -> dict[str, str]:
        doc = SessionDoc(
            owner_uid=user.uid,
            topic=body.topic,
            speaker=body.speaker,
            youtube_url=str(body.youtube_url) if body.youtube_url else None,
            status="prebunking",
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
        )
        try:
            await run_in_threadpool(handle_update, update, bot)
        except Exception:  # never make Telegram retry a poison update
            log.exception("tg handler failed")
        return {"ok": True}

    return app
