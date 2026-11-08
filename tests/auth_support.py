"""Existing catalogue tests isolate business behavior from authentication."""

from fastapi import FastAPI
from musefy_backend.app import create_app as application
from musefy_backend.auth import current_user
from musefy_backend.dependencies import QueryEmbedder
from musefy_core.db.models import UserRow
from musefy_core.db.session import Sessions


def create_app(sessions: Sessions, embedder: QueryEmbedder | None = None) -> FastAPI:
    app = application(sessions, embedder)

    async def authenticated() -> UserRow:
        return UserRow(id=1, google_sub="test-catalogue-user", email="catalogue@example.test")

    app.dependency_overrides[current_user] = authenticated
    return app
