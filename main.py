"""Точка входа MarketSignal: Telegram-бот + планировщик."""

import asyncio
import logging
import sys

from config.settings import settings
from core.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("marketsignal")


async def main() -> None:
    if not settings.bot_token:
        log.error("BOT_TOKEN не задан. Скопируйте config/.env.example в config/.env и заполните.")
        sys.exit(1)

    await init_db()
    log.info("Database ready")

    import bot.handlers  # noqa: F401  (регистрирует роутеры)
    from bot.services import bot, dp, notify, tracker

    tracker.set_notifier(notify)
    tracker.start()

    log.info("Starting bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await tracker.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down")
