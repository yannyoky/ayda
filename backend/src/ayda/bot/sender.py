from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ayda.app.notifications import Message, RateLimiter, RetryLater, Unreachable


def keyboard(message: Message) -> InlineKeyboardMarkup | None:
    button = message.button
    if button is None:
        return None
    if button.web_app:
        item = InlineKeyboardButton(text=button.text, web_app=WebAppInfo(url=button.url))
    else:
        item = InlineKeyboardButton(text=button.text, url=button.url)
    return InlineKeyboardMarkup(inline_keyboard=[[item]])


class AiogramSender:
    def __init__(self, bot: Bot, limiter: RateLimiter | None = None) -> None:
        self._bot = bot
        self._limiter = limiter or RateLimiter()

    async def send(self, chat_id: int, message: Message) -> None:
        await self._limiter.wait(chat_id)
        try:
            await self._bot.send_message(chat_id, message.text, reply_markup=keyboard(message))
        except TelegramForbiddenError:
            raise Unreachable from None
        except TelegramBadRequest as exc:
            if "chat not found" in str(exc).lower():
                raise Unreachable from None
            raise
        except (TelegramRetryAfter, TelegramNetworkError):
            raise RetryLater from None
