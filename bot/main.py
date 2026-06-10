"""Точка входа: настройка бота, БД, роутеров и планировщика, запуск polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_settings
from bot.db.session import get_sessionmaker, init_db, init_engine
from bot.handlers import admin, common, dev, predictions
from bot.scheduler import setup_scheduler
from bot.services import matches as matches_service
from bot.services.football.factory import build_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("predicup")


async def main() -> None:
    settings = load_settings()
    if not settings.secrets.bot_token:
        raise RuntimeError("BOT_TOKEN не задан (см. .env).")

    init_engine(settings.db_url, settings.secrets.db_path)
    await init_db()
    sessionmaker = get_sessionmaker()

    provider = build_provider(settings)

    bot = Bot(
        token=settings.secrets.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Зависимости, доступные хендлерам по имени параметра
    dp["settings"] = settings
    dp["sessionmaker"] = sessionmaker
    dp["provider"] = provider

    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(predictions.router)
    if settings.secrets.is_dev:
        dp.include_router(dev.router)
        logger.info("ENV=dev: дев-команды /devmatch, /devresult включены")

    # Стартовая синхронизация расписания, чтобы данные были сразу (не ждать
    # первого тика планировщика — у sync интервал в часах).
    try:
        async with sessionmaker() as session:
            n = await matches_service.sync_fixtures(session, provider)
        logger.info("Стартовая синхронизация: %s матчей", n)
    except Exception:  # noqa: BLE001
        logger.exception("Стартовая синхронизация не удалась")

    scheduler = setup_scheduler(bot, sessionmaker, settings, provider)
    scheduler.start()
    logger.info("Бот запущен. Провайдер: %s", settings.app.provider.name)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await provider.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановлено.")
