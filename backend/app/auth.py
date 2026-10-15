"""Firebase ID token verification as a FastAPI dependency.

The verifier is injectable so tests never need real Google credentials.
In prod it is firebase_admin.auth.verify_id_token with check_revoked=True.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, Header, HTTPException, Request, status

log = logging.getLogger("proofcard.auth")

Verifier = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class Principal:
    uid: str
    is_anonymous: bool


AUTH_TOKEN_ERROR_NAMES = {
    "RevokedIdTokenError",
    "UserDisabledError",
    "InvalidIdTokenError",
    "ExpiredIdTokenError",
}


# pragma: no cover - needs Google credentials
def firebase_verifier(project_id: str = "") -> Verifier:
    import firebase_admin
    from firebase_admin import auth

    if not firebase_admin._apps:
        options = {"projectId": project_id} if project_id else None
        firebase_admin.initialize_app(options=options)  # uses the Cloud Run service account (ADC)

    def _verify(token: str) -> dict[str, Any]:
        return cast(dict[str, Any], auth.verify_id_token(token, check_revoked=True))

    return _verify


def _unauthorized() -> HTTPException:
    # Same message for every failure: never leak why a token was rejected.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    verifier: Verifier = request.app.state.verifier
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized()
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = verifier(token)
    except Exception as exc:
        name = type(exc).__name__
        if isinstance(exc, ValueError) or name in AUTH_TOKEN_ERROR_NAMES:
            log.warning("token rejected (%s): %s", name, exc)
            raise _unauthorized() from exc
        log.exception("auth verification failed (%s): %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="auth verification failed",
        ) from exc
    uid = claims.get("uid") or claims.get("sub")
    if not isinstance(uid, str) or not uid:
        raise _unauthorized()
    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    return Principal(uid=uid, is_anonymous=provider == "anonymous")


def admin_principal(p: Annotated[Principal, Depends(current_principal)]) -> Principal:
    """Session actions (create session, start prebunk) accept signed-in and anonymous users."""
    return p
