import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from musefy_backend.app import create_app
from musefy_backend.auth import FLOW_AUDIENCE, SESSION_AUDIENCE, cookie_name, decode, encode
from musefy_core.db.models import AuthSessionRow, UserRow
from musefy_core.db.session import Sessions
from musefy_core.settings import Settings
from pydantic import SecretStr
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine


def configuration(*, secure: bool = False) -> Settings:
    return Settings(
        google_client_id="test-client.apps.googleusercontent.com",
        google_redirect_uri="http://127.0.0.1:8000/auth/callback",
        auth_frontend_url="http://127.0.0.1:5173",
        google_client_secret=SecretStr("test-google-secret"),
        auth_jwt_secret=SecretStr("test-only-signing-key-at-least-32-characters"),
        auth_cookie_secure=secure,
        cors_origins=["http://127.0.0.1:5173"],
    )


@pytest.fixture(scope="module")
def google_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def mock_google(
    app: FastAPI,
    key: rsa.RSAPrivateKey,
    claims: dict[str, Any],
    flow: dict[str, Any],
    *,
    kid: str = "google-key",
) -> None:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = "google-key"

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            params = parse_qs(request.content.decode())
            assert params["code"] == ["google-one-use-code"]
            assert params["code_verifier"] == [flow["verifier"]]
            token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})
            return httpx.Response(200, json={"id_token": token})
        assert str(request.url) == "https://www.googleapis.com/oauth2/v3/certs"
        return httpx.Response(200, json={"keys": [jwk]})

    app.state.oauth_transport = httpx.MockTransport(respond)


async def begin(client: httpx.AsyncClient, config: Settings) -> tuple[str, dict[str, Any]]:
    response = await client.get("/auth/google", params={"return_to": "/?view=catalog"})
    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["scope"] == ["openid email profile"]
    flow = decode(config, client.cookies[cookie_name(config, flow=True)], FLOW_AUDIENCE)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(flow["verifier"].encode()).digest()).rstrip(b"=").decode()
    )
    assert params["code_challenge"] == [challenge]
    return params["state"][0], flow


def google_claims(config: Settings, flow: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sub": "google-stable-subject",
        "email": "tester@example.test",
        "email_verified": True,
        "name": "Tester",
        "picture": "https://example.test/avatar.png",
        "nonce": flow["nonce"],
        "iss": "https://accounts.google.com",
        "aud": config.google_client_id,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }


async def test_login_provisions_session_and_logout_revokes(
    db: tuple[AsyncEngine, Sessions],
    google_key: rsa.RSAPrivateKey,
) -> None:
    _, sessions = db
    config = configuration()
    app = create_app(sessions, settings=config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as client:
        for path in [
            "/titles",
            "/titles/1",
            "/titles/facets",
            "/search?q=story",
            "/auth/me",
            "/docs",
            "/openapi.json",
        ]:
            response = await client.get(path)
            assert response.status_code == 401, path
        assert (await client.get("/health")).status_code == 200
        state, flow = await begin(client, config)
        mock_google(app, google_key, google_claims(config, flow), flow)
        response = await client.get("/auth/callback", params={"state": state, "code": "google-one-use-code"})
        assert response.status_code == 303
        assert response.headers["location"] == "http://127.0.0.1:5173/?view=catalog"
        assert "HttpOnly" in response.headers["set-cookie"]
        token = client.cookies[cookie_name(config)]
        identity = (await client.get("/auth/me")).json()
        assert identity == {
            "id": 1,
            "email": "tester@example.test",
            "name": "Tester",
            "picture": "https://example.test/avatar.png",
        }
        assert (await client.get("/titles")).status_code == 200
        for origin in [None, "null", "https://evil.test"]:
            headers = {} if origin is None else {"Origin": origin}
            assert (await client.post("/auth/logout", headers=headers)).status_code == 403
        assert (
            await client.post("/auth/logout", headers={"Origin": config.auth_frontend_url})
        ).status_code == 204
        client.cookies.set(cookie_name(config), token)
        assert (await client.get("/auth/me")).status_code == 401
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UserRow)) == 1
            assert await session.scalar(select(func.count()).select_from(AuthSessionRow)) == 0


@pytest.mark.parametrize(
    "mutation",
    ["nonce", "aud", "iss", "expired", "email_verified", "missing_email", "unknown_kid", "bad_signature"],
)
async def test_google_identity_is_verified(
    db: tuple[AsyncEngine, Sessions],
    google_key: rsa.RSAPrivateKey,
    mutation: str,
) -> None:
    _, sessions = db
    config = configuration()
    app = create_app(sessions, settings=config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as client:
        state, flow = await begin(client, config)
        claims = google_claims(config, flow)
        if mutation in {"nonce", "aud", "iss"}:
            claims[mutation] = "wrong"
        elif mutation == "expired":
            claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
        elif mutation == "email_verified":
            claims["email_verified"] = False
        elif mutation == "missing_email":
            del claims["email"]
        mock_google(
            app, google_key, claims, flow, kid="unknown" if mutation == "unknown_kid" else "google-key"
        )
        if mutation == "bad_signature":
            # Keep the advertised key while signing with another private key.
            other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            bad_token = jwt.encode(claims, other, algorithm="RS256", headers={"kid": "google-key"})
            public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(google_key.public_key()))
            public_jwk["kid"] = "google-key"
            app.state.oauth_transport = httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"id_token": bad_token} if request.url.path == "/token" else {"keys": [public_jwk]},
                )
            )
        response = await client.get("/auth/callback", params={"state": state, "code": "google-one-use-code"})
        assert response.status_code == 303
        assert response.headers["location"].endswith("auth_error=login_failed")
        assert cookie_name(config) not in client.cookies
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UserRow)) == 0


async def test_relogin_uses_subject_and_sessions_require_existing_account(
    db: tuple[AsyncEngine, Sessions],
    google_key: rsa.RSAPrivateKey,
) -> None:
    _, sessions = db
    config = configuration()
    app = create_app(sessions, settings=config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as client:
        for email in ["old@example.test", "changed@example.test"]:
            state, flow = await begin(client, config)
            claims = {**google_claims(config, flow), "email": email}
            mock_google(app, google_key, claims, flow)
            assert (
                await client.get("/auth/callback", params={"state": state, "code": "google-one-use-code"})
            ).status_code == 303
            assert (await client.get("/auth/me")).json()["email"] == email
        async with sessions.begin() as session:
            assert await session.scalar(select(func.count()).select_from(UserRow)) == 1
            assert await session.scalar(select(func.count()).select_from(AuthSessionRow)) == 1
            await session.execute(
                update(AuthSessionRow).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert (await client.get("/auth/me")).status_code == 401
        async with sessions.begin() as session:
            await session.execute(delete(UserRow))
        assert (await client.get("/auth/me")).status_code == 401


async def test_invalid_state_redirects_and_forged_session(db: tuple[AsyncEngine, Sessions]) -> None:
    _, sessions = db
    config = configuration(secure=True)
    app = create_app(sessions, settings=config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://127.0.0.1:8000"
    ) as client:
        for destination in ["//evil.test", "https://evil.test", "/\\evil.test", "/\nevil"]:
            assert (await client.get("/auth/google", params={"return_to": destination})).status_code == 400
        state, flow = await begin(client, config)
        assert cookie_name(config).startswith("__Host-")
        response = await client.get("/auth/callback", params={"state": "mismatch", "code": "anything"})
        assert response.headers["location"].endswith("auth_error=login_failed")
        response = await client.get("/auth/callback", params={"state": state, "code": "anything"})
        assert response.headers["location"].endswith("auth_error=login_failed")
        for token in [
            "forged.jwt.value",
            encode(config, {"sub": "1", "jti": "bad"}, SESSION_AUDIENCE, 60),
            encode(config, {"sub": "1", "jti": "00000000-0000-0000-0000-000000000000"}, SESSION_AUDIENCE, -1),
        ]:
            client.cookies.set(cookie_name(config), token)
            assert (await client.get("/auth/me")).status_code == 401
