from fastapi import APIRouter

from ayda.api.deps import AppSettings, DbSession
from ayda.api.schemas import Session, TelegramSignIn
from ayda.app.profile import build_me
from ayda.app.reminders import reminder_opened
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
