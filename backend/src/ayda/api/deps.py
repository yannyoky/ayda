from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.config import Settings
from ayda.core.db import get_session
from ayda.core.problems import Problem
from ayda.modules import auth

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def _unauthorized() -> Problem:
    return Problem(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    session: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> auth.User:
    if credentials is None:
        raise _unauthorized()
    try:
        user_id = auth.read_token(credentials.credentials, settings.token_secret)
    except auth.TokenError:
        raise _unauthorized() from None
    user = await auth.get_user(session, user_id)
    if user is None or user.deletion_requested_at is not None:
        raise _unauthorized()
    return user


CurrentUser = Annotated[auth.User, Depends(get_current_user)]
