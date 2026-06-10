"""Фоновые задачи на APScheduler: синхронизация расписания, открытие/закрытие
голосований и резолв результатов.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Settings
from bot.services import matches as matches_service
from bot.services.football.base import MatchProvider

logger = logging.getLogger(__name__)


def setup_scheduler(
    bot: Bot,
    sessionmaker: async_sessionmaker,
    settings: Settings,
    provider: MatchProvider,
) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="UTC")
    sc = settings.app.scheduler

    async def job_sync() -> None:
        try:
            async with sessionmaker() as session:
                n = await matches_service.sync_fixtures(session, provider)
            logger.info("sync_fixtures: %s матчей", n)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка sync_fixtures")

    async def job_open_close() -> None:
        try:
            async with sessionmaker() as session:
                opened = await matches_service.open_votes(bot, session, settings)
            async with sessionmaker() as session:
                closed = await matches_service.close_votes(bot, session, settings)
            if opened or closed:
                logger.info("открыто=%s закрыто=%s", opened, closed)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка open/close votes")

    async def job_resolve() -> None:
        try:
            async with sessionmaker() as session:
                n = await matches_service.resolve_results(
                    bot, session, settings, provider
                )
            if n:
                logger.info("resolve_results: зарезолвлено %s", n)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка resolve_results")

    # Открытие/закрытие и резолв запускаем почти сразу после старта (а не через
    # полный интервал), чтобы голосования появлялись без задержки.
    soon = datetime.now(timezone.utc) + timedelta(seconds=10)
    sched.add_job(job_sync, "interval", hours=sc.sync_fixtures_hours, id="sync")
    sched.add_job(
        job_open_close,
        "interval",
        minutes=sc.open_votes_minutes,
        id="open_close",
        next_run_time=soon,
    )
    sched.add_job(
        job_resolve,
        "interval",
        minutes=sc.resolve_results_minutes,
        id="resolve",
        next_run_time=soon,
    )
    return sched
