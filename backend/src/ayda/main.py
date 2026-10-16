from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ayda.api import auth, me, system
from ayda.core.config import Settings, get_settings
from ayda.core.db import Database
from ayda.core.problems import install_problem_handlers

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url, echo=settings.database_echo)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await db.dispose()

    app = FastAPI(title="Ayda API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    install_problem_handlers(app)
    for router in (system.router, auth.router, me.router):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
