"""Account security notices (audit V5).

A native sign-in confirmed through Telegram can be phished: someone sends a victim the
confirmation link. So after every such sign-in the bot tells the Telegram account, always by
bot and never by push (the new device may be the attacker's), and offers "sign out everywhere".
"""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.app.notifications import BOT_ONLY_KINDS, RENDERERS, Message, Renderer, app_button, notify
from ayda.core.config import Settings
from ayda.modules import auth

NEW_SIGN_IN_KIND = "auth.new_sign_in"
# Mini App launch parameter of the "it was not me" button (miniapp/src/app/launch.ts).
SIGN_OUT_START = "signout"
NEW_SIGN_IN_TEXT = (
    "В Ayda вошли через твой Telegram с другого устройства 📱\n\n"
    "Если это был ты, ничего делать не нужно. Если нет, нажми кнопку ниже: "
    "мы завершим вход на всех устройствах."
)


async def notify_new_sign_in(session: AsyncSession, user_id: uuid.UUID) -> None:
    await notify(session, user_id, NEW_SIGN_IN_KIND)


def new_sign_in_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> Message | None:
        button = app_button(settings, "Это был не я", start_param=SIGN_OUT_START)
        return Message(NEW_SIGN_IN_TEXT, button)

    return render


def register(settings: Settings) -> None:
    RENDERERS[NEW_SIGN_IN_KIND] = new_sign_in_renderer(settings)
    BOT_ONLY_KINDS.add(NEW_SIGN_IN_KIND)
