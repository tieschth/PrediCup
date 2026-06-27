"""Точка входа: настройка бота, БД, роутеров и планировщика, запуск polling."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from bot.config import load_settings
from bot.db.session import get_sessionmaker, init_db, init_engine
from bot.handlers import admin, common, dev, predictions
from bot.scheduler import setup_scheduler
from bot.services import matches as matches_service
from bot.services.football.factory import build_provider
from bot.services.labels import apply_labels_from_file, default_labels_path

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

    # Авто-импорт отображаемых имён из data/labels.csv (если файл есть).
    labels_path = default_labels_path(settings.secrets.db_path)
    if os.path.exists(labels_path):
        try:
            async with sessionmaker() as session:
                updated, missing = await apply_labels_from_file(session, labels_path)
                await session.commit()
            logger.info("Метки имён: применено %s, не найдено %s", updated, len(missing))
            if missing:
                logger.warning("Метки не найдены для: %s", ", ".join(missing))
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось применить labels.csv")

    provider = build_provider(settings)

    # Прокси только для Telegram (если api.telegram.org недоступен напрямую).
    session = None
    if settings.secrets.telegram_proxy:
        session = AiohttpSession(proxy=settings.secrets.telegram_proxy)
        logger.info("Telegram идёт через прокси")

    bot = Bot(
        token=settings.secrets.bot_token,
        session=session,
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
        logger.info(
            "ENV=dev: дев-команды включены (/devmatch, /devopen, /devresult, /devreset)"
        )

    # Стартовая синхронизация + «догоняющее» открытие/закрытие: данные доступны
    # сразу, а при рестарте в течение дня уже открытые голосования
    # восстанавливаются (повторно не постятся — есть защита), не дожидаясь крона.
    try:
        async with sessionmaker() as session:
            n = await matches_service.sync_fixtures(session, provider)
        logger.info("Стартовая синхронизация: %s матчей", n)
        async with sessionmaker() as session:
            opened = await matches_service.open_votes(bot, session, settings)
            closed = await matches_service.close_votes(bot, session, settings)
        logger.info("Догоняющее открытие=%s, закрытие=%s", opened, closed)
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
