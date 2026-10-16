import re

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message as TgMessage

from ayda.app.notifications import Message, app_button
from ayda.bot import texts
from ayda.bot.sender import keyboard
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.modules import auth

# Invite codes are URL-safe tokens (social.create_invite).
INVITE_CODE = re.compile(r"^[A-Za-z0-9_-]{10,64}$")


def start_reply(settings: Settings, args: str | None) -> Message:
    code = args.strip() if args else None
    if code and INVITE_CODE.match(code):
        return Message(texts.INVITE, app_button(settings, texts.OPEN_APP, start_param=code))
    return Message(texts.GREETING, app_button(settings, texts.OPEN_APP))


def build_router(settings: Settings, db: Database) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def on_start(message: TgMessage, command: CommandObject) -> None:  # pyright: ignore[reportUnusedFunction]
        if message.from_user is not None:
            async with db.sessionmaker() as session:
                await auth.mark_bot_reachable(session, message.from_user.id, True)
                await session.commit()
        reply = start_reply(settings, command.args)
        await message.answer(reply.text, reply_markup=keyboard(reply))

    return router
