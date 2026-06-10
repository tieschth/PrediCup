"""Админские команды: таблица лидеров. Доступ — по ролям из конфига."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.access import is_admin
from bot.config import Settings
from bot.services.leaderboard import render_leaderboard

router = Router(name="admin")


@router.message(Command(commands=["leaderboard", "table"]))
async def cmd_leaderboard(
    message: Message,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    user = message.from_user
    if user is None or not is_admin(settings, user.id):
        await message.reply("⛔ Команда доступна только администраторам.")
        return
    async with sessionmaker() as session:
        text = await render_leaderboard(session)
    await message.answer(text)
