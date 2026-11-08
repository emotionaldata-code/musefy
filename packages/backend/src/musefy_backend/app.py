from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from musefy_core.db.session import Sessions, database
from musefy_core.settings import Settings

from musefy_backend.routes import router


def create_app(sessions: Sessions | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if sessions is not None:
            app.state.sessions = sessions
            yield
            return
        engine, factory = database(Settings())
        app.state.sessions = factory
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Musefy", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings().cors_origins,
        allow_methods=["GET"],
        allow_headers=["Accept"],
    )
    if sessions is not None:
        app.state.sessions = sessions
    app.include_router(router)
    return app


app = create_app()
