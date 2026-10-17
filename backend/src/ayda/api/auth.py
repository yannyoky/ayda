from datetime import datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.deps import AppMailer, AppSettings, DbSession
from ayda.api.schemas import EmailStart, EmailVerify, RefreshTokenInput, Session, TelegramSignIn
from ayda.app.profile import build_me
from ayda.app.reminders import reminder_opened
from ayda.core.config import Settings
from ayda.core.mail import MailError
from ayda.core.problems import Problem
from ayda.modules import analytics, auth
from ayda.modules.analytics import EventType

router = APIRouter(tags=["auth"])


@router.post("/auth/telegram", operation_id="signInWithTelegram")
async def sign_in_with_telegram(
    body: TelegramSignIn, session: DbSession, settings: AppSettings
) -> Session:
    if settings.telegram_bot_token is None:
        raise Problem(401, "telegram-not-configured", detail="Вход через Telegram не настроен")
    try:
        init_data = auth.validate_init_data(
            body.init_data, settings.telegram_bot_token.get_secret_value()
        )
    except auth.InitDataError:
        raise Problem(401, "invalid-init-data", detail="Не удалось проверить вход") from None

    user, _ = await auth.upsert_telegram_user(session, init_data.user)
    if user.deletion_requested_at is not None:
        await session.rollback()
        raise Problem(401, "account-deleted", detail="Аккаунт удаляется")
    opened = reminder_opened(init_data.start_param)
    if opened:
        await analytics.record(session, EventType.REMINDER_OPENED, user.id, {"kind": opened})
    me = await build_me(session, user)
    await session.commit()
    token, expires_at = auth.issue_token(user.id, settings.token_secret)
    return Session(access_token=token, expires_at=expires_at, user=me)


_EMAIL_SUBJECT = "Код входа в Ayda"
_EMAIL_BODY = (
    "Твой код для входа в Ayda: {code}\n\n"
    "Он действует 10 минут. Если ты не входил в Ayda, просто проигнорируй это письмо."
)


def _email(raw: str) -> str:
    try:
        return auth.normalize_email(raw)
    except auth.EmailError:
        raise Problem(422, "invalid-email", detail="Проверьте адрес почты") from None


@router.post("/auth/email/start", operation_id="startEmailSignIn", status_code=202)
async def start_email_sign_in(
    body: EmailStart,
    request: Request,
    session: DbSession,
    settings: AppSettings,
    mailer: AppMailer,
) -> Response:
    email = _email(body.email)
    if not mailer.enabled:
        raise Problem(503, "email-not-configured", detail="Вход по почте пока недоступен")
    client = request.client.host if request.client else "unknown"
    try:
        issued = await auth.issue_code(session, email, client, settings.token_secret)
    except auth.EmailError:
        raise Problem(
            429, "too-many-codes", detail="Слишком много кодов, попробуйте чуть позже"
        ) from None
    try:
        await mailer.send(email, _EMAIL_SUBJECT, _EMAIL_BODY.format(code=issued.code))
    except MailError:
        await session.rollback()
        raise Problem(503, "email-failed", detail="Не удалось отправить письмо") from None
    await session.commit()
    return Response(status_code=202)


async def _native_session(
    session: AsyncSession,
    settings: Settings,
    user: auth.User,
    refresh_token: str,
    refresh_expires_at: datetime,
) -> Session:
    me = await build_me(session, user)
    await session.commit()
    access, expires_at = auth.issue_token(user.id, settings.token_secret)
    return Session(
        access_token=access,
        expires_at=expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
        user=me,
    )


def _invalid_code() -> Problem:
    return Problem(401, "invalid-code", detail="Неверный или устаревший код")


@router.post("/auth/email/verify", operation_id="verifyEmailSignIn")
async def verify_email_sign_in(
    body: EmailVerify, session: DbSession, settings: AppSettings
) -> Session:
    email = _email(body.email)
    try:
        await auth.check_code(session, email, body.code, settings.token_secret)
    except auth.EmailError:
        await session.commit()  # keep the wrong-attempt count
        raise _invalid_code() from None
    user, created = await auth.find_or_create_email_user(session, email)
    if user.deletion_requested_at is not None:
        await session.rollback()
        raise Problem(401, "account-deleted", detail="Аккаунт удаляется")
    await analytics.record(
        session, EventType.SIGNED_IN, user.id, {"provider": "email", "new": created}
    )
    token, refresh_expires_at = await auth.issue_refresh_token(session, user.id)
    return await _native_session(session, settings, user, token, refresh_expires_at)


def _invalid_refresh() -> Problem:
    return Problem(401, "invalid-refresh-token", detail="Войдите заново")


@router.post("/auth/refresh", operation_id="refreshSession")
async def refresh_session(
    body: RefreshTokenInput, session: DbSession, settings: AppSettings
) -> Session:
    try:
        user_id, token, refresh_expires_at = await auth.rotate_refresh_token(
            session, body.refresh_token
        )
    except auth.RefreshError:
        await session.commit()  # a reused token revokes its family
        raise _invalid_refresh() from None
    user = await auth.get_user(session, user_id)
    if user is None or user.deletion_requested_at is not None:
        await session.rollback()
        raise _invalid_refresh()
    return await _native_session(session, settings, user, token, refresh_expires_at)


@router.post("/auth/logout", operation_id="signOut", status_code=204)
async def sign_out(body: RefreshTokenInput, session: DbSession) -> Response:
    await auth.revoke_refresh_token(session, body.refresh_token)
    await session.commit()
    return Response(status_code=204)
