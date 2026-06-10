"""Помощники для аккуратной работы с сообщениями в группе (чтобы не засорять чат)."""
from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot
from aiogram.types import Message


async def delete_later(bot: Bot, chat_id: int, message_id: int, delay: float) -> None:
    await asyncio.sleep(delay)
    with contextlib.suppress(Exception):
        await bot.delete_message(chat_id, message_id)


async def notify_temp(bot: Bot, chat_id: int, text: str, delay: float = 6) -> None:
    """Короткое самоудаляющееся уведомление."""
    with contextlib.suppress(Exception):
        msg = await bot.send_message(chat_id, text)
        asyncio.create_task(delete_later(bot, chat_id, msg.message_id, delay))


async def safe_delete(message: Message) -> None:
    """Удалить сообщение, не падая, если нет прав/уже удалено."""
    with contextlib.suppress(Exception):
        await message.delete()
