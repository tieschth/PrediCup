"""Уведомления админам в личку.

Ограничение Telegram: бот может написать пользователю в ЛС только если тот сам
нажал Start у бота. Недоставленные адресаты логируются, рассылка не падает.
"""
from __future__ import annotations

import logging

from aiogram import Bot

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, admin_ids: list[int], text: str) -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:  # noqa: BLE001 - не валим рассылку из-за одного
            logger.warning(
                "Не удалось отправить уведомление админу %s: %s", admin_id, exc
            )
