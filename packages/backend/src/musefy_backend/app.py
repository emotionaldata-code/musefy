from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from musefy_core.db.session import Sessions, database
from musefy_core.embeddings import Embedder
from musefy_core.settings import Settings
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from musefy_backend.auth import current_user
from musefy_backend.auth import router as auth_router
from musefy_backend.dependencies import QueryEmbedder
from musefy_backend.routes import health_router, router
from musefy_backend.search import router as search_router


class PrivateResponses(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def create_app(
    sessions: Sessions | None = None,
    embedder: QueryEmbedder | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if sessions is not None:
            app.state.sessions = sessions
            yield
            return
        engine, factory = database(config)
        app.state.sessions = factory
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Musefy", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = config
    app.add_middleware(PrivateResponses)
    app.state.embedder = embedder if embedder is not None else Embedder()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    if sessions is not None:
        app.state.sessions = sessions

    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(current_user)])
    async def openapi() -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(current_user)])
    async def docs() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url="openapi.json", title="Musefy API")

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(router)
    app.include_router(search_router)
    return app


app = create_app()
