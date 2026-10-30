import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.deps import AppMailer, AppSettings, CurrentUser, DbSession, OptionalUser
from ayda.api.schemas import (
    EmailStart,
    EmailVerify,
    RefreshTokenInput,
    Session,
    TelegramLoginApprove,
    TelegramLoginExchange,
    TelegramLoginRequestOut,
    TelegramSignIn,
)
from ayda.app import security
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


@router.post("/auth/sign-out-everywhere", operation_id="signOutEverywhere", status_code=204)
async def sign_out_everywhere(user: CurrentUser, session: DbSession) -> Response:
    await auth.end_all_sessions(session, user)
    await session.commit()
    return Response(status_code=204)


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post(
    "/auth/telegram/login-requests", operation_id="createTelegramLoginRequest", status_code=201
)
async def create_telegram_login_request(
    request: Request, session: DbSession, settings: AppSettings, user: OptionalUser
) -> TelegramLoginRequestOut:
    if settings.telegram_bot_token is None:
        raise Problem(503, "telegram-not-configured", detail="Вход через Telegram не настроен")
    try:
        created = await auth.create_request(
            session, _client(request), settings.token_secret, user.id if user else None
        )
    except auth.LoginRequestError:
        raise Problem(
            429, "too-many-requests", detail="Слишком много попыток, попробуйте чуть позже"
        ) from None
    await session.commit()
    # The Mini App confirms it (approveTelegramLoginRequest), so the bot need not get updates
    start = f"{auth.CODE_PREFIX}{created.code}"
    return TelegramLoginRequestOut(
        id=created.id,
        poll_secret=created.poll_secret,
        bot_url=f"https://t.me/{settings.telegram_bot_username}?startapp={start}",
        expires_at=created.expires_at,
    )


@router.post(
    "/auth/telegram/login-requests/approve",
    operation_id="approveTelegramLoginRequest",
    status_code=204,
)
async def approve_telegram_login_request(
    body: TelegramLoginApprove, session: DbSession, settings: AppSettings
) -> Response:
    if settings.telegram_bot_token is None:
        raise Problem(401, "telegram-not-configured", detail="Вход через Telegram не настроен")
    try:
        init_data = auth.validate_init_data(
            body.init_data, settings.telegram_bot_token.get_secret_value()
        )
    except auth.InitDataError:
        raise Problem(401, "invalid-init-data", detail="Не удалось проверить вход") from None
    request = await auth.find_pending(session, body.code.removeprefix(auth.CODE_PREFIX))
    approved = request is not None and await auth.approve_request(
        session, request.id, init_data.user
    )
    if not approved:
        await session.rollback()
        raise Problem(
            404, "login-request-expired", detail="Ссылка для входа устарела, начните вход заново"
        )
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/auth/telegram/login-requests/{request_id}/exchange",
    operation_id="exchangeTelegramLoginRequest",
    responses={202: {"description": "Not confirmed yet"}},
)
async def exchange_telegram_login_request(
    request_id: uuid.UUID, body: TelegramLoginExchange, session: DbSession, settings: AppSettings
) -> Response:
    try:
        approved = await auth.exchange_request(session, request_id, body.poll_secret)
    except auth.LoginRequestError as exc:
        if exc.code == "pending":
            return Response(status_code=202)
        raise Problem(
            401, "invalid-login-request", detail="Вход не подтверждён, попробуйте ещё раз"
        ) from None

    if approved.link_user_id is not None:
        user = await auth.get_user(session, approved.link_user_id)
        if user is None or user.deletion_requested_at is not None:
            await session.rollback()
            raise _invalid_refresh()
        try:
            await auth.link_telegram(session, user, approved.telegram_user)
        except auth.IdentityError:
            await session.commit()  # the request stays used
            raise Problem(
                409, "identity-taken", detail="Этот Telegram уже привязан к другому аккаунту"
            ) from None
        created = False
    else:
        user, created = await auth.upsert_telegram_user(session, approved.telegram_user)
        if user.deletion_requested_at is not None:
            await session.rollback()
            raise Problem(401, "account-deleted", detail="Аккаунт удаляется")
    await analytics.record(
        session, EventType.SIGNED_IN, user.id, {"provider": "telegram", "new": created}
    )
    if not created:
        # The confirmation link can be phished: tell the Telegram account (audit V5).
        await security.notify_new_sign_in(session, user.id)
    token, refresh_expires_at = await auth.issue_refresh_token(session, user.id)
    result = await _native_session(session, settings, user, token, refresh_expires_at)
    return Response(
        content=result.model_dump_json(), media_type="application/json", status_code=200
    )
