"""Дев-команды для ручного прогона сценария (только ENV=dev + админ).

Работают с MockProvider:
  /devmatch <home> <away> <минут_до_старта> [home_code] [away_code]
      — вбрасывает фейковый матч и сразу открывает по нему голосование.
  /devresult <HOME|DRAW|AWAY> [счёт_вида_2:1]
      — «как будто API прочитал результат»: резолвит последний матч, начисляет
        очки и публикует итог.
"""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.access import is_admin
from bot.config import Settings
from bot.db import repo
from bot.db.models import Choice
from bot.services import matches as matches_service
from bot.services.football.base import MatchProvider
from bot.services.football.mock import MockProvider

router = Router(name="dev")

_DEFAULT_SCORES = {Choice.HOME: (1, 0), Choice.DRAW: (1, 1), Choice.AWAY: (0, 1)}


def _guard(message: Message, settings: Settings, provider: MatchProvider) -> str | None:
    if not settings.secrets.is_dev:
        return "Дев-команды доступны только при ENV=dev."
    user = message.from_user
    if user is None or not is_admin(settings, user.id):
        return "⛔ Только для администраторов."
    if not isinstance(provider, MockProvider):
        return "Дев-команды работают только с provider.name=mock."
    return None


@router.message(Command("devreset"))
async def cmd_devreset(
    message: Message,
    settings: Settings,
    provider: MatchProvider,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    err = _guard(message, settings, provider)
    if err:
        await message.reply(err)
        return
    async with sessionmaker() as session:
        await repo.clear_matches_and_predictions(session)
        await session.commit()
    await message.reply("🧹 Тестовые данные очищены: матчи, прогнозы, голосовалки.")


@router.message(Command("devmatch"))
async def cmd_devmatch(
    message: Message,
    bot: Bot,
    settings: Settings,
    provider: MatchProvider,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    err = _guard(message, settings, provider)
    if err:
        await message.reply(err)
        return
    parts = (message.text or "").split()[1:]
    if len(parts) < 3:
        await message.reply(
            "Использование: /devmatch <home> <away> <минут_до_старта> "
            "[home_code] [away_code]\nПример: /devmatch Бразилия Аргентина 10 BRA ARG"
        )
        return
    home, away, minutes_raw = parts[0], parts[1], parts[2]
    try:
        minutes = float(minutes_raw)
    except ValueError:
        await message.reply("Минуты должны быть числом.")
        return
    home_code = parts[3] if len(parts) > 3 else home[:3].upper()
    away_code = parts[4] if len(parts) > 4 else away[:3].upper()

    assert isinstance(provider, MockProvider)
    provider.add_match(home, away, home_code, away_code, minutes_to_kickoff=minutes)

    async with sessionmaker() as session:
        await matches_service.sync_fixtures(session, provider)
        opened = await matches_service.open_votes(bot, session, settings)
    await message.reply(f"✅ Матч добавлен, открыто голосований: {opened}.")


@router.message(Command("devresult"))
async def cmd_devresult(
    message: Message,
    bot: Bot,
    settings: Settings,
    provider: MatchProvider,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    err = _guard(message, settings, provider)
    if err:
        await message.reply(err)
        return
    parts = (message.text or "").split()[1:]
    if not parts:
        await message.reply("Использование: /devresult <HOME|DRAW|AWAY> [2:1]")
        return
    try:
        outcome = Choice(parts[0].upper())
    except ValueError:
        await message.reply("Исход: HOME, DRAW или AWAY.")
        return
    if len(parts) > 1 and ":" in parts[1]:
        try:
            h_str, a_str = parts[1].split(":", 1)
            home_score, away_score = int(h_str), int(a_str)
        except ValueError:
            await message.reply("Счёт в формате 2:1.")
            return
    else:
        home_score, away_score = _DEFAULT_SCORES[outcome]

    async with sessionmaker() as session:
        match = await repo.get_latest_unresolved_match(session)
        if match is None:
            await message.reply("Нет незавершённого матча для резолва.")
            return
        assert isinstance(provider, MockProvider)
        provider.set_result(match.provider_match_id, home_score, away_score)
        await matches_service.force_resolve(
            bot, session, settings, match, home_score, away_score, outcome
        )
    await message.reply("🏁 Матч зарезолвлен, очки начислены.")
