"""Приём голосов: callback от inline-кнопок голосовалки.

Голос пишется приватно (через callback_query — другие участники не видят выбор).
При успехе пользователю показывается всплывающее уведомление, при ошибке записи
— уведомление об ошибке пользователю и сообщение админам в ЛС с причиной.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Settings
from bot.db import repo
from bot.keyboards.vote import VOTE_PREFIX, parse_vote_callback
from bot.services import matches as matches_service
from bot.services import presentation
from bot.services.notifications import notify_admins

logger = logging.getLogger(__name__)
router = Router(name="predictions")


@router.callback_query(F.data.startswith(f"{VOTE_PREFIX}:"))
async def on_vote(
    callback: CallbackQuery,
    bot: Bot,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    parsed = parse_vote_callback(callback.data or "")
    if parsed is None:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    match_id, choice = parsed
    user = callback.from_user

    try:
        async with sessionmaker() as session:
            match = await repo.get_match(session, match_id)
            if match is None:
                await callback.answer("Матч не найден", show_alert=True)
                return
            if match.kickoff_utc <= datetime.now(timezone.utc):
                await callback.answer(
                    "⏱ Голосование уже закрыто — матч начался.", show_alert=True
                )
                return

            await repo.get_or_create_user(
                session, user.id, user.username, user.full_name
            )
            await repo.upsert_prediction(session, match_id, user.id, choice)
            await session.commit()

            label = presentation.choice_label(match, choice)
            await matches_service.refresh_vote_message_counts(
                bot, session, settings, match
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка записи прогноза user=%s match=%s", user.id, match_id)
        await callback.answer(
            "⚠️ Не удалось сохранить голос, попробуй ещё раз.", show_alert=True
        )
        who = f"@{user.username}" if user.username else f"{user.full_name} ({user.id})"
        await notify_admins(
            bot,
            settings.app.roles.admins,
            f"⚠️ Ошибка записи прогноза.\nКто: {who}\nМатч id={match_id}\n"
            f"Причина: {exc!r}",
        )
        return

    await callback.answer(f"✅ Голос отправлен и сохранён.\n{_plain(label)}")


def _plain(html_label: str) -> str:
    """Убрать html-теги для текста всплывашки (в toast html не рендерится)."""
    import re

    return re.sub(r"<[^>]+>", "", html_label)
