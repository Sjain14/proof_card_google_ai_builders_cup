"""Proof Card main service (Cloud Run): API, prebunk jobs, public card reads, Telegram webhook."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.auth import Principal, Verifier, admin_principal, firebase_verifier
from app.config import Settings, get_settings
from app.logging_setup import configure_logging, pseudonymize
from app.model import ModelClient, StubModel, VertexModel
from app.pipeline import Deps, run_prebunk
from app.proof import FixtureFetcher, GcsSnapshots, HttpFetcher, InMemorySnapshots
from app.schemas import (
    CardDoc,
    CheckTextRequest,
    PrebunkRequest,
    SessionDoc,
    SessionView,
    TaskPrebunk,
    TgUpdate,
)
from app.security import TokenBucket, telegram_secret_ok
from app.store import FirestoreStore, Store
from app.tasks import CloudTasksQueue, InlineQueue, OidcVerifier, TaskQueue, google_oidc_verifier

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
        if length is not None and (not length.isdigit() or int(length) > settings.max_body_bytes):
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

    @app.post("/api/check", dependencies=[Depends(rate_limited)])
    def check_text(body: CheckTextRequest) -> dict[str, str]:
        card: CardDoc | None = app.state.store.get_card(body.card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="not found")
        # Phase 4 replaces this exact compare with Gemini extraction + text diff + pHash.
        result = "VERIFIED" if body.text.strip() == card.claim.strip() else "ALTERED"
        return {"result": result}

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
        if update.message is not None:
            log.info(
                "tg update",
                extra={"fields": {"chat": pseudonymize(update.message.chat.id)}},
            )
        # Phase 4: QR / id lookup, compare, reply with inline "Open proof" button.
        return {"ok": True}

    return app
