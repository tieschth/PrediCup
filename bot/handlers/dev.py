"""Дев-команды для ручного прогона сценария (только ENV=dev + админ).

  /devmatch <home> <away> <минут> [home_code] [away_code]  — только provider=mock:
      вбрасывает фейковый матч и сразу открывает голосование.
  /devopen [count]            — открыть голосование по ближайшим матчам вручную
      (работает и с реальным провайдером: удобно для контрольного теста).
  /devresult <HOME|DRAW|AWAY> [счёт_вида_2:1]  — финализировать последний
      незавершённый матч: начислить очки и опубликовать итог (любой провайдер).
  /devreset                   — очистить тестовые матчи/прогнозы/голосовалки.
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


def _dev_guard(message: Message, settings: Settings) -> str | None:
    """Доступ к дев-командам: только ENV=dev и админ (без привязки к провайдеру)."""
    if not settings.secrets.is_dev:
        return "Дев-команды доступны только при ENV=dev."
    user = message.from_user
    if user is None or not is_admin(settings, user.id):
        return "⛔ Только для администраторов."
    return None


def _mock_guard(message: Message, settings: Settings, provider: MatchProvider) -> str | None:
    """Дополнительно требует mock-провайдер (для /devmatch)."""
    err = _dev_guard(message, settings)
    if err:
        return err
    if not isinstance(provider, MockProvider):
        return "Эта команда работает только с provider.name=mock."
    return None


@router.message(Command("devreset"))
async def cmd_devreset(
    message: Message,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    err = _dev_guard(message, settings)
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
    err = _mock_guard(message, settings, provider)
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


@router.message(Command("devopen"))
async def cmd_devopen(
    message: Message,
    bot: Bot,
    settings: Settings,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    err = _dev_guard(message, settings)
    if err:
        await message.reply(err)
        return
    parts = (message.text or "").split()[1:]
    count = 1
    if parts:
        try:
            count = max(1, int(parts[0]))
        except ValueError:
            await message.reply("Использование: /devopen [count]")
            return
    async with sessionmaker() as session:
        opened = await matches_service.open_next(bot, session, settings, count)
    await message.reply(f"✅ Открыто голосований: {opened}.")


@router.message(Command("devresult"))
async def cmd_devresult(
    message: Message,
    bot: Bot,
    settings: Settings,
    provider: MatchProvider,
    sessionmaker: async_sessionmaker,
    **_: object,
) -> None:
    err = _dev_guard(message, settings)
    if err:
        await message.reply(err)
        return
    parts = (message.text or "").split()[1:]
    # необязательный первый аргумент — id матча; иначе берём последний с голосовалкой
    match_id: int | None = None
    if parts and parts[0].isdigit():
        match_id = int(parts[0])
        parts = parts[1:]
    if not parts:
        await message.reply(
            "Использование: /devresult [match_id] <HOME|DRAW|AWAY> [2:1]"
        )
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
        if match_id is not None:
            match = await repo.get_match(session, match_id)
        else:
            match = await repo.get_latest_voted_unresolved_match(session)
        if match is None:
            await message.reply("Нет матча для резолва (укажи match_id из /matches).")
            return
        # для mock также положим результат в провайдер (на случай авто-резолва)
        if isinstance(provider, MockProvider):
            provider.set_result(match.provider_match_id, home_score, away_score)
        await matches_service.force_resolve(
            bot, session, settings, match, home_score, away_score, outcome
        )
    await message.reply(f"🏁 Матч #{match.id} зарезолвлен, очки начислены.")
