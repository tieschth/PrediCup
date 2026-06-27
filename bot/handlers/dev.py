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
from bot.db.models import Choice, MatchDuration
from bot.services import matches as matches_service
from bot.services.football.base import MatchProvider
from bot.services.football.mock import MockProvider

router = Router(name="dev")


@router.message(Command("id"))
async def cmd_id(message: Message, **_: object) -> None:
    """Показать id чата и пользователя — для заполнения config.yaml (только dev)."""
    chat = message.chat
    lines = [f"🆔 <b>chat_id</b>: <code>{chat.id}</code> ({chat.type})"]
    if message.from_user is not None:
        lines.append(f"👤 <b>твой tg_id</b>: <code>{message.from_user.id}</code>")
    await message.reply("\n".join(lines))

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


_USAGE = (
    "Использование: /devresult [match_id] <счёт|HOME|DRAW|AWAY> [ET|PEN] [пен.счёт]\n"
    "Примеры:\n"
    "  /devresult 5 2:1            — основное время\n"
    "  /devresult HOME             — основное (счёт по умолчанию)\n"
    "  /devresult 73 1:1 ET        — победа в доп. время\n"
    "  /devresult 73 1:1 PEN 4:3   — победа по пенальти"
)
_DUR = {
    "ET": MatchDuration.EXTRA_TIME.value, "EXTRA": MatchDuration.EXTRA_TIME.value,
    "PEN": MatchDuration.PENALTY_SHOOTOUT.value,
    "PENALTY": MatchDuration.PENALTY_SHOOTOUT.value,
}


def _parse_score(token: str) -> tuple[int, int] | None:
    if ":" not in token:
        return None
    try:
        h, a = token.split(":", 1)
        return int(h), int(a)
    except ValueError:
        return None


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
    match_id: int | None = None
    if parts and parts[0].isdigit():
        match_id = int(parts[0])
        parts = parts[1:]
    if not parts:
        await message.reply(_USAGE)
        return

    # первый токен — счёт «h:a» или ключевое слово HOME/DRAW/AWAY
    score = _parse_score(parts[0])
    if score is None:
        try:
            score = _DEFAULT_SCORES[Choice(parts[0].upper())]
        except ValueError:
            await message.reply(_USAGE)
            return
    home_score, away_score = score

    duration = MatchDuration.REGULAR.value
    pen_home = pen_away = None
    for tok in parts[1:]:
        if tok.upper() in _DUR:
            duration = _DUR[tok.upper()]
        elif _parse_score(tok):
            pen_home, pen_away = _parse_score(tok)

    async with sessionmaker() as session:
        if match_id is not None:
            match = await repo.get_match(session, match_id)
        else:
            match = await repo.get_latest_voted_unresolved_match(session)
        if match is None:
            await message.reply("Нет матча для резолва (укажи match_id из /matches).")
            return
        if isinstance(provider, MockProvider):
            provider.set_result(
                match.provider_match_id, home_score, away_score,
                duration, pen_home, pen_away,
            )
        await matches_service.force_resolve(
            bot, session, settings, match,
            home_score, away_score, duration, pen_home, pen_away,
        )
    await message.reply(f"🏁 Матч #{match.id} зарезолвлен, очки начислены.")
