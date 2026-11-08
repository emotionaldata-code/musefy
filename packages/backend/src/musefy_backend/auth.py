"""Google OIDC and local, revocable cookie sessions."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from musefy_core.db.models import AuthSessionRow, UserRow
from musefy_core.settings import Settings
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from musefy_backend.dependencies import Session

router = APIRouter(prefix="/auth", tags=["authentication"])
ISSUER = "musefy"
SESSION_AUDIENCE = "musefy-session"
FLOW_AUDIENCE = "musefy-google-flow"
FLOW_TTL = 600


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str | None
    picture: str | None


class Flow(BaseModel):
    state: str
    nonce: str
    verifier: str
    return_to: str


class GoogleIdentity(BaseModel):
    sub: str
    email: str
    email_verified: bool
    name: str | None = None
    picture: str | None = None
    nonce: str
    azp: str | None = None


def settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def signing_key(config: Settings) -> str:
    if config.auth_jwt_secret is None:
        raise HTTPException(503, "Authentication is not configured")
    key = config.auth_jwt_secret.get_secret_value()
    if len(key) < 32:
        raise HTTPException(503, "Authentication is not configured")
    return key


def cookie_name(config: Settings, *, flow: bool = False) -> str:
    prefix = "__Host-" if config.auth_cookie_secure else ""
    return prefix + ("musefy_oauth" if flow else "musefy_session")


def encode(config: Settings, payload: dict[str, object], audience: str, ttl: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {**payload, "iss": ISSUER, "aud": audience, "iat": now, "exp": now + timedelta(seconds=ttl)},
        signing_key(config),
        algorithm="HS256",
    )


def decode(config: Settings, token: str, audience: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        signing_key(config),
        algorithms=["HS256"],
        issuer=ISSUER,
        audience=audience,
        options={"require": ["exp", "iat", "iss", "aud"]},
    )


def set_cookie(response: Response, config: Settings, token: str, *, flow: bool = False) -> None:
    response.set_cookie(
        cookie_name(config, flow=flow),
        token,
        max_age=FLOW_TTL if flow else config.auth_session_ttl_seconds,
        httponly=True,
        secure=config.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_cookie(response: Response, config: Settings, *, flow: bool = False) -> None:
    response.delete_cookie(
        cookie_name(config, flow=flow),
        path="/",
        httponly=True,
        secure=config.auth_cookie_secure,
        samesite="lax",
    )


def relative_destination(value: str) -> str:
    # Never let an OAuth callback become an open redirect, including browser backslash normalization.
    parts = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Invalid return path")
    if parts.scheme or parts.netloc or len(value) > 2048:
        raise ValueError("Invalid return path")
    return value


async def current_user(request: Request, session: Session) -> UserRow:
    config = settings(request)
    token = request.cookies.get(cookie_name(config))
    if not token:
        raise HTTPException(401, "Authentication required")
    try:
        claims = decode(config, token, SESSION_AUDIENCE)
        session_id = UUID(claims["jti"])
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Invalid or expired session") from None
    user = await session.scalar(
        select(UserRow)
        .join(AuthSessionRow)
        .where(
            AuthSessionRow.id == session_id,
            AuthSessionRow.user_id == user_id,
            AuthSessionRow.expires_at > datetime.now(UTC),
        )
    )
    if user is None:
        raise HTTPException(401, "Invalid or expired session")
    request.state.auth_session_id = session_id
    return user


CurrentUser = Annotated[UserRow, Depends(current_user)]


@router.get("/google")
async def google_login(
    request: Request, return_to: Annotated[str, Query(max_length=2048)] = "/"
) -> RedirectResponse:
    config = settings(request)
    signing_key(config)
    if not config.google_client_id or config.google_client_secret is None:
        raise HTTPException(503, "Google login is not configured")
    try:
        destination = relative_destination(return_to)
    except ValueError:
        raise HTTPException(400, "Invalid return path") from None
    flow = Flow(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(64),
        return_to=destination,
    )
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).rstrip(b"=").decode()
    )
    params = {
        "client_id": config.google_client_id,
        "redirect_uri": config.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": flow.state,
        "nonce": flow.nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), 302)
    set_cookie(response, config, encode(config, flow.model_dump(), FLOW_AUDIENCE, FLOW_TTL), flow=True)
    return response


async def google_identity(request: Request, code: str, flow: Flow) -> GoogleIdentity:
    config = settings(request)
    if not config.google_client_id or config.google_client_secret is None:
        raise ValueError("Google login is not configured")
    transport = cast(httpx.AsyncBaseTransport | None, getattr(request.app.state, "oauth_transport", None))
    async with httpx.AsyncClient(timeout=15, transport=transport) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": config.google_client_id,
                "client_secret": config.google_client_secret.get_secret_value(),
                "redirect_uri": config.google_redirect_uri,
                "code_verifier": flow.verifier,
            },
        )
        token_response.raise_for_status()
        token = token_response.json()["id_token"]
        # Only Google's pinned JWKS endpoint supplies verification keys. No token-controlled URLs.
        key_response = await client.get("https://www.googleapis.com/oauth2/v3/certs")
        key_response.raise_for_status()
        header = jwt.get_unverified_header(token)
        key_data = next(
            (key for key in key_response.json()["keys"] if key.get("kid") == header.get("kid")), None
        )
        if key_data is None:
            raise ValueError("Unknown Google signing key")
        key = jwt.PyJWK.from_dict(key_data, algorithm="RS256")
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=config.google_client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce", "email", "email_verified"]},
        )
    identity = GoogleIdentity.model_validate(claims)
    if not secrets.compare_digest(identity.nonce, flow.nonce) or not identity.email_verified:
        raise ValueError("Invalid identity")
    if identity.azp is not None and identity.azp != config.google_client_id:
        raise ValueError("Invalid authorized party")
    if not identity.sub or len(identity.sub) > 255 or not identity.email or len(identity.email) > 320:
        raise ValueError("Invalid identity")
    # Avatar is displayed by the browser; never persist an executable URL.
    if identity.picture and urlsplit(identity.picture).scheme != "https":
        identity.picture = None
    return identity


@router.get("/callback")
async def google_callback(
    request: Request,
    session: Session,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    config = settings(request)
    failure = RedirectResponse(config.auth_frontend_url.rstrip("/") + "/?auth_error=login_failed", 303)
    clear_cookie(failure, config, flow=True)
    try:
        if error or not code or not state:
            return failure
        flow_token = request.cookies.get(cookie_name(config, flow=True), "")
        flow = Flow.model_validate(decode(config, flow_token, FLOW_AUDIENCE))
        if not secrets.compare_digest(flow.state, state):
            return failure
        destination = relative_destination(flow.return_to)
        identity = await google_identity(request, code, flow)
    except (
        jwt.InvalidTokenError,
        ValidationError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
        httpx.HTTPError,
    ):
        return failure
    now = datetime.now(UTC)
    await session.execute(delete(AuthSessionRow).where(AuthSessionRow.expires_at <= now))
    statement = insert(UserRow).values(
        google_sub=identity.sub,
        email=identity.email,
        name=identity.name,
        picture=identity.picture,
        created_at=now,
        last_login_at=now,
    )
    upsert = statement.on_conflict_do_update(
        index_elements=[UserRow.google_sub],
        set_={
            "email": identity.email,
            "name": identity.name,
            "picture": identity.picture,
            "last_login_at": now,
        },
    ).returning(UserRow.id)
    user_id = await session.scalar(upsert)
    assert user_id is not None
    session_id = uuid4()
    session.add(
        AuthSessionRow(
            id=session_id,
            user_id=user_id,
            expires_at=now + timedelta(seconds=config.auth_session_ttl_seconds),
        )
    )
    # A successful login replaces the browser's old local session.
    old_token = request.cookies.get(cookie_name(config))
    if old_token:
        try:
            old_id = UUID(decode(config, old_token, SESSION_AUDIENCE)["jti"])
            await session.execute(delete(AuthSessionRow).where(AuthSessionRow.id == old_id))
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            pass
    await session.commit()
    response = RedirectResponse(config.auth_frontend_url.rstrip("/") + destination, 303)
    clear_cookie(response, config, flow=True)
    set_cookie(
        response,
        config,
        encode(
            config,
            {"sub": str(user_id), "jti": str(session_id)},
            SESSION_AUDIENCE,
            config.auth_session_ttl_seconds,
        ),
    )
    return response


@router.get("/me", response_model=User)
async def me(user: CurrentUser) -> User:
    return User.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, session: Session, user: CurrentUser) -> Response:
    require_origin(request)
    config = settings(request)
    await session.execute(delete(AuthSessionRow).where(AuthSessionRow.id == request.state.auth_session_id))
    await session.commit()
    response = Response(status_code=204)
    clear_cookie(response, config)
    return response


def require_origin(request: Request) -> None:
    """Cookie-authenticated writes must originate from the configured frontend."""
    config = settings(request)
    allowed = {config.auth_frontend_url.rstrip("/"), *config.cors_origins}
    if request.headers.get("origin") not in allowed:
        raise HTTPException(403, "Invalid request origin")
