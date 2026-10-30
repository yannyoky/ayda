"""`python -m ayda.bot`: polling locally, a webhook server when TELEGRAM_WEBHOOK_URL is set."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from ayda.bot.handlers import build_router
from ayda.core.config import Settings, get_settings
from ayda.core.db import Database
from ayda.core.errors import init_error_tracking
from ayda.core.logging import configure_logging

WEBHOOK_PATH = "/telegram/webhook"


async def run(settings: Settings) -> None:
    if settings.telegram_bot_token is None:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set")
    db = Database(settings.database_url)
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(settings, db))
    try:
        if not settings.telegram_webhook_url:
            await bot.delete_webhook(drop_pending_updates=False)
            await dispatcher.start_polling(bot)  # pyright: ignore[reportUnknownMemberType]
            return
        # Settings refuse a webhook URL without a secret (audit V1).
        assert settings.telegram_webhook_secret is not None
        secret = settings.telegram_webhook_secret.get_secret_value()
        await bot.set_webhook(settings.telegram_webhook_url, secret_token=secret)
        app = web.Application()
        SimpleRequestHandler(dispatcher=dispatcher, bot=bot, secret_token=secret).register(
            app, path=WEBHOOK_PATH
        )
        setup_application(app, dispatcher, bot=bot)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", settings.bot_port).start()
        await asyncio.Event().wait()
    finally:
        await bot.session.close()
        await db.dispose()


if __name__ == "__main__":
    configure_logging()
    settings = get_settings()
    init_error_tracking(settings, "bot")
    asyncio.run(run(settings))
