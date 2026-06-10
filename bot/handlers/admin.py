"""Админские команды: таблица лидеров. Доступ — по ролям из конфига."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.access import is_admin
from bot.config import Settings
from bot.handlers.chat_utils import notify_temp, safe_delete
from bot.services.leaderboard import render_leaderboard

router = Router(name="admin")


@router.message(Command(commands=["leaderboard", "table"]))
async def cmd_leaderboard(
    message: Message,
    bot: Bot,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    user = message.from_user
    chat_id = message.chat.id
    # Команду убираем в любом случае, чтобы не засорять чат.
    await safe_delete(message)
    if user is None or not is_admin(settings, user.id):
        await notify_temp(bot, chat_id, "⛔ Таблица доступна только администраторам.")
        return
    async with sessionmaker() as session:
        text = await render_leaderboard(session)
    await bot.send_message(chat_id, text)
