"""Админские команды: таблица лидеров, ручная корректировка очков.
Доступ — по ролям из конфига."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.access import is_admin
from bot.config import Settings
from bot.db import repo
from bot.handlers.chat_utils import notify_temp, safe_delete
from bot.services.leaderboard import render_leaderboard
from bot.services.presentation import display_name

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


_BONUS_USAGE = (
    "Использование: /bonus <@username|tg_id> <±N>\n"
    "Примеры: /bonus @vaskaaaak +1   |   /bonus 475130843 -2\n"
    "Это ручная добавка/штраф к очкам (не трогает баллы за прогнозы)."
)


@router.message(Command(commands=["bonus", "addpoints"]))
async def cmd_bonus(
    message: Message,
    bot: Bot,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    user = message.from_user
    chat_id = message.chat.id
    await safe_delete(message)
    if user is None or not is_admin(settings, user.id):
        await notify_temp(bot, chat_id, "⛔ Команда только для администраторов.")
        return

    parts = (message.text or "").split()[1:]
    if len(parts) < 2:
        await notify_temp(bot, chat_id, _BONUS_USAGE, delay=15)
        return
    ident, delta_raw = parts[0], parts[1]
    try:
        delta = int(delta_raw)
    except ValueError:
        await notify_temp(bot, chat_id, "Δ должно быть целым: +1 или -2", delay=12)
        return

    async with sessionmaker() as session:
        if ident.lstrip("@").isdigit():
            target = await repo.get_or_create_user(session, int(ident.lstrip("@")))
        else:
            target = await repo.find_user_by_username(session, ident)
        if target is None:
            await notify_temp(
                bot, chat_id,
                f"Пользователь {ident} не найден (он должен был хоть раз "
                "проголосовать или нажать /start).", delay=12,
            )
            return
        new_bonus = await repo.adjust_bonus(session, target.tg_id, delta)
        await session.commit()

    await bot.send_message(
        chat_id,
        f"✏️ Очки скорректированы: {display_name(target)} "
        f"(бонус теперь {new_bonus:+d}).",
    )
