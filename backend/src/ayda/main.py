from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from ayda.api import (
    auth,
    chat,
    coop,
    days,
    devices,
    feed,
    friends,
    identities,
    ladder,
    me,
    media,
    realtime,
    reference,
    system,
)
from ayda.app.day import DayTools
from ayda.core.config import Settings, get_settings
from ayda.core.db import Database
from ayda.core.errors import init_error_tracking
from ayda.core.logging import configure_logging
from ayda.core.mail import Mailer
from ayda.core.problems import install_problem_handlers
from ayda.core.realtime import Realtime
from ayda.core.storage import Storage
from ayda.modules import assistant, events

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment != "test":
        configure_logging()
        init_error_tracking(settings, "api")
    db = Database(settings.database_url, echo=settings.database_echo)
    http = httpx.AsyncClient()
    day_tools = DayTools(
        assistant=assistant.Assistant(
            assistant.providers_from_settings(settings, http),
            sessionmaker=db.sessionmaker,
            timeout_s=settings.llm_timeout_s,
        ),
        weather=events.WeatherClient(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await day_tools.weather.aclose()
        await http.aclose()
        await db.dispose()

    app = FastAPI(title="Ayda API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.day_tools = day_tools
    app.state.storage = Storage(settings)
    app.state.realtime = Realtime(settings, http)
    app.state.mailer = Mailer(settings)
    install_problem_handlers(app)
    for router in (
        system.router,
        auth.router,
        me.router,
        identities.router,
        devices.router,
        reference.router,
        days.router,
        media.router,
        friends.router,
        feed.router,
        ladder.router,
        realtime.router,
        chat.router,
        coop.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
