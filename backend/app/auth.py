"""Firebase ID token verification as a FastAPI dependency.

The verifier is injectable so tests never need real Google credentials.
In prod it is firebase_admin.auth.verify_id_token with check_revoked=True.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status

Verifier = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class Principal:
    uid: str
    is_anonymous: bool


def firebase_verifier() -> Verifier:  # pragma: no cover - needs Google credentials
    import firebase_admin
    from firebase_admin import auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()  # uses the Cloud Run service account (ADC)

    def _verify(token: str) -> dict[str, Any]:
        claims: dict[str, Any] = auth.verify_id_token(token, check_revoked=True)
        return claims

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
        raise _unauthorized() from exc
    uid = claims.get("uid") or claims.get("sub")
    if not isinstance(uid, str) or not uid:
        raise _unauthorized()
    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    return Principal(uid=uid, is_anonymous=provider == "anonymous")


def admin_principal(p: Annotated[Principal, Depends(current_principal)]) -> Principal:
    """Admin actions (create session, start prebunk) need a real signed in user."""
    if p.is_anonymous:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return p
