"""Proof Card main service (Cloud Run). Phase 1: skeleton, auth, schemas, webhook guard."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.auth import Principal, Verifier, admin_principal, firebase_verifier
from app.config import Settings, get_settings
from app.logging_setup import configure_logging, pseudonymize
from app.schemas import CardDoc, CheckTextRequest, PrebunkRequest, SessionDoc, TgUpdate
from app.security import TokenBucket, telegram_secret_ok
from app.store import FirestoreStore, Store

log = logging.getLogger("proofcard")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def create_app(
    settings: Settings | None = None,
    verifier: Verifier | None = None,
    store: Store | None = None,
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
        # Phase 2 enqueues Cloud Tasks verify_claim jobs here.
        return {"session_id": sid}

    @app.get("/api/cards/{card_id}")
    def get_card(card_id: str) -> CardDoc:
        if not (8 <= len(card_id) <= 64) or not card_id.replace("-", "").replace("_", "").isalnum():
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
