import re
import uuid

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import Message as TgMessage
from aiogram.types import User as TgUser

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


LOGIN_CALLBACK = "login:"


def telegram_user(user: TgUser) -> auth.TelegramUser:
    return auth.TelegramUser(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        photo_url=None,
    )


async def login_reply(db: Database, code: str) -> tuple[str, InlineKeyboardMarkup | None]:
    """Answer to `/start login_<code>`: a confirm button, or a note that the link expired."""
    async with db.sessionmaker() as session:
        request = await auth.find_pending(session, code)
    if request is None:
        return texts.LOGIN_EXPIRED, None
    button = InlineKeyboardButton(
        text=texts.LOGIN_BUTTON, callback_data=f"{LOGIN_CALLBACK}{request.id}"
    )
    return texts.LOGIN_CONFIRM, InlineKeyboardMarkup(inline_keyboard=[[button]])


async def confirm_login(db: Database, data: str, user: TgUser) -> str:
    try:
        request_id = uuid.UUID(data.removeprefix(LOGIN_CALLBACK))
    except ValueError:
        return texts.LOGIN_EXPIRED
    async with db.sessionmaker() as session:
        approved = await auth.approve_request(session, request_id, telegram_user(user))
        await session.commit()
    return texts.LOGIN_DONE if approved else texts.LOGIN_EXPIRED


def build_router(settings: Settings, db: Database) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def on_start(message: TgMessage, command: CommandObject) -> None:  # pyright: ignore[reportUnusedFunction]
        if message.from_user is not None:
            async with db.sessionmaker() as session:
                await auth.mark_bot_reachable(session, message.from_user.id, True)
                await session.commit()
        args = command.args.strip() if command.args else ""
        if args.startswith(auth.CODE_PREFIX):
            text, markup = await login_reply(db, args.removeprefix(auth.CODE_PREFIX))
            await message.answer(text, reply_markup=markup)
            return
        reply = start_reply(settings, command.args)
        await message.answer(reply.text, reply_markup=keyboard(reply))

    @router.callback_query(F.data.startswith(LOGIN_CALLBACK))
    async def on_login_confirm(callback: CallbackQuery) -> None:  # pyright: ignore[reportUnusedFunction]
        text = await confirm_login(db, callback.data or "", callback.from_user)
        await callback.answer()
        if isinstance(callback.message, TgMessage):
            await callback.message.edit_text(text)

    return router
