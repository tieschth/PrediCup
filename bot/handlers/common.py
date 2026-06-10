"""Базовые команды: /start, /help, /matches."""
from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Settings
from bot.db import repo
from bot.handlers.chat_utils import notify_temp, safe_delete
from bot.services import presentation

router = Router(name="common")

_START_TEXT = (
    "👋 Привет! Я <b>PrediCup</b> — бот предсказаний на ЧМ-2026.\n\n"
    "Перед матчами в чате появляется голосовалка с флагами — жми кнопку и делай "
    "прогноз (П1 / Ничья / П2). Менять можно до начала матча. После матча я "
    "начисляю очки и веду таблицу лидеров.\n\n"
    "Команда /matches пришлёт сюда, в личку, список открытых голосований со "
    "ссылками — чтобы не искать их в чате."
)


def _vote_link(chat_id: int, message_id: int) -> str | None:
    """Ссылка на сообщение в супергруппе: t.me/c/<internal>/<message_id>."""
    s = str(chat_id)
    if s.startswith("-100"):
        return f"https://t.me/c/{s[4:]}/{message_id}"
    return None


@router.message(Command("start"))
async def cmd_start(
    message: Message, sessionmaker: async_sessionmaker, **_: object
) -> None:
    user = message.from_user
    if user is not None:
        async with sessionmaker() as session:
            await repo.get_or_create_user(
                session, user.id, user.username, user.full_name
            )
            await session.commit()
    await message.answer(_START_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message, **_: object) -> None:
    await message.answer(
        "Команды:\n"
        "/matches — список открытых голосований (в личку)\n"
        "/id — показать id этого чата и твой tg_id (для настройки)\n"
        "/help — эта справка\n\n"
        "Прогнозы делаются кнопками под сообщением-голосовалкой в чате."
    )


@router.message(Command("id"))
async def cmd_id(message: Message, **_: object) -> None:
    """Показать id чата и пользователя — нужно для заполнения config.yaml."""
    user = message.from_user
    chat = message.chat
    lines = [
        f"🆔 <b>chat_id</b>: <code>{chat.id}</code> ({chat.type})",
    ]
    if user is not None:
        lines.append(f"👤 <b>твой tg_id</b>: <code>{user.id}</code>")
    await message.reply("\n".join(lines))


async def _build_open_matches_text(
    sessionmaker: async_sessionmaker, settings: Settings, user_id: int,
    username: str | None, full_name: str | None,
) -> str:
    """Текст со списком открытых голосований и прогнозом пользователя."""
    now = datetime.now(timezone.utc)
    tz = settings.app.bot.display_timezone
    async with sessionmaker() as session:
        await repo.get_or_create_user(session, user_id, username, full_name)
        await session.commit()
        rows = await repo.list_open_matches_with_messages(session, now)
        if not rows:
            return "Сейчас нет открытых голосований. Загляни позже 🙌"
        lines = ["🗳 <b>Открытые голосования</b>", ""]
        for match, vm in rows:
            pred = await repo.get_prediction(session, match.id, user_id)
            title = presentation.match_title(match)
            when = presentation.format_kickoff(match, tz)
            link = _vote_link(vm.chat_id, vm.message_id)
            head = f"<a href='{link}'>{title}</a>" if link else title
            status = (
                f"твой прогноз: {presentation.choice_label(match, pred.choice)}"
                if pred
                else "ты ещё не голосовал"
            )
            lines.append(f"• {head}\n  🕒 {when} — {status}")
        return "\n".join(lines)


_DM_HINT = (
    "Сначала напиши мне в личку команду /start — тогда смогу прислать список "
    "(бот не может написать первым)."
)


@router.message(Command("matches"))
async def cmd_matches(
    message: Message,
    bot: Bot,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    user = message.from_user
    if user is None:
        return
    text = await _build_open_matches_text(
        sessionmaker, settings, user.id, user.username, user.full_name
    )
    # В личке просто отвечаем списком — чистить нечего.
    if message.chat.type == "private":
        await message.answer(text, disable_web_page_preview=True)
        return
    # В группе: убираем команду и шлём в ЛС, чтобы не засорять чат.
    await safe_delete(message)
    try:
        await bot.send_message(user.id, text, disable_web_page_preview=True)
        await notify_temp(
            bot, message.chat.id, f"📬 {user.full_name}, список — у тебя в личке."
        )
    except TelegramForbiddenError:
        await notify_temp(bot, message.chat.id, f"{user.full_name}, {_DM_HINT}", 12)


@router.callback_query(F.data == "mymatches")
async def on_my_matches(
    callback: CallbackQuery,
    bot: Bot,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    """Кнопка «Мои голосования»: список — в ЛС, подтверждение — всплывашкой."""
    user = callback.from_user
    text = await _build_open_matches_text(
        sessionmaker, settings, user.id, user.username, user.full_name
    )
    try:
        await bot.send_message(user.id, text, disable_web_page_preview=True)
        await callback.answer("📬 Список открытых голосований — у тебя в личке.")
    except TelegramForbiddenError:
        await callback.answer(_DM_HINT, show_alert=True)
