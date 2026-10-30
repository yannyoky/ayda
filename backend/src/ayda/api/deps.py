from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.config import Settings
from ayda.core.db import get_session
from ayda.core.mail import Mailer
from ayda.core.problems import Problem
from ayda.modules import auth

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def get_mailer(request: Request) -> Mailer:
    mailer: Mailer = request.app.state.mailer
    return mailer


AppMailer = Annotated[Mailer, Depends(get_mailer)]


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
        user_id, issued_at = auth.read_token_claims(credentials.credentials, settings.token_secret)
    except auth.TokenError:
        raise _unauthorized() from None
    user = await auth.get_user(session, user_id)
    if user is None or user.deletion_requested_at is not None:
        raise _unauthorized()
    if auth.token_revoked(user, issued_at):
        raise _unauthorized()
    return user


CurrentUser = Annotated[auth.User, Depends(get_current_user)]


async def get_optional_user(
    session: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> auth.User | None:
    """No token: anonymous. A token that fails the checks is still a 401."""
    if credentials is None:
        return None
    return await get_current_user(session, settings, credentials)


OptionalUser = Annotated[auth.User | None, Depends(get_optional_user)]


async def require_consent(user: CurrentUser, session: DbSession) -> None:
    """152-FZ: no processing of personal data before the current consent is accepted.
    Clients show the consent screen when `Me.consent_required` is set."""
    if await auth.consent_required(session, user.id) is not None:
        raise Problem(409, "consent-required", detail="Сначала нужно принять согласие")


# Router or route dependency for everything except sign-in, `GET /me`, consents and deletion.
Consented = Depends(require_consent)
