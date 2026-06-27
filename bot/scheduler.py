"""Фоновые задачи на APScheduler: синхронизация расписания, открытие/закрытие
голосований и резолв результатов.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Settings
from bot.services import matches as matches_service
from bot.services.backup import make_backup
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

    async def job_open() -> None:
        try:
            async with sessionmaker() as session:
                opened = await matches_service.open_votes(bot, session, settings)
            logger.info("Открытие голосований (10:05): открыто=%s", opened)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка открытия голосований")

    async def job_close() -> None:
        try:
            async with sessionmaker() as session:
                closed = await matches_service.close_votes(bot, session, settings)
            if closed:
                logger.info("Закрыто голосований: %s", closed)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка закрытия голосований")

    async def job_backup() -> None:
        try:
            # sqlite backup — блокирующий, уводим в поток, чтобы не держать loop
            await asyncio.to_thread(
                make_backup, settings.secrets.db_path, sc.backup_keep
            )
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка бэкапа БД")

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

    async def job_reverify() -> None:
        try:
            async with sessionmaker() as session:
                n = await matches_service.reverify_results(
                    bot, session, settings, provider
                )
            if n:
                logger.info("reverify_results: обновлено матчей %s", n)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка reverify_results")

    # Закрытие и резолв стартуют почти сразу после старта (а не через полный
    # интервал). Открытие — по расписанию (крон), плюс «догоняющее» открытие на
    # старте бота делает main.py (на случай рестарта в течение дня).
    soon = datetime.now(timezone.utc) + timedelta(seconds=10)
    hour, minute = _parse_hhmm(sc.open_at_local)
    tz = settings.app.bot.display_timezone

    sched.add_job(job_sync, "interval", hours=sc.sync_fixtures_hours, id="sync")
    sched.add_job(
        job_open, "cron", hour=hour, minute=minute, timezone=tz, id="open_daily"
    )
    sched.add_job(
        job_close,
        "interval",
        minutes=sc.close_votes_minutes,
        id="close",
        next_run_time=soon,
    )
    sched.add_job(
        job_resolve,
        "interval",
        minutes=sc.resolve_results_minutes,
        id="resolve",
        next_run_time=soon,
    )
    sched.add_job(
        job_reverify,
        "interval",
        minutes=sc.reverify_minutes,
        id="reverify",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    if sc.backup_keep > 0:
        bh, bm = _parse_hhmm(sc.backup_at_local)
        sched.add_job(
            job_backup, "cron", hour=bh, minute=bm, timezone=tz, id="backup"
        )
    return sched


def _parse_hhmm(value: str) -> tuple[int, int]:
    """'10:05' -> (10, 5)."""
    h, m = value.split(":")
    return int(h), int(m)
