"""Текстовые представления матчей и исходов (используются в сообщениях и /matches)."""
from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.db.models import Choice, Match
from bot.flags import flag_for_code


def _esc(s: str) -> str:
    return html.escape(s)


def match_title(match: Match) -> str:
    hf = flag_for_code(match.home_code)
    af = flag_for_code(match.away_code)
    return f"{hf} {_esc(match.home_team)} — {_esc(match.away_team)} {af}"


def format_kickoff(match: Match, tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("UTC")
    local = match.kickoff_utc.astimezone(tz)
    return local.strftime("%d.%m.%Y %H:%M")


def choice_label(match: Match, choice: Choice | str) -> str:
    val = choice.value if isinstance(choice, Choice) else str(choice)
    if val == Choice.HOME.value:
        return f"{flag_for_code(match.home_code)} Победа: {_esc(match.home_team)}"
    if val == Choice.AWAY.value:
        return f"{flag_for_code(match.away_code)} Победа: {_esc(match.away_team)}"
    return "⚖️ Ничья"


def vote_message_text(match: Match, tz_name: str, predictions_count: int) -> str:
    return (
        "⚽ <b>Прогноз на матч</b>\n"
        f"{match_title(match)}\n"
        f"🕒 Старт: {format_kickoff(match, tz_name)}\n\n"
        "Сделай прогноз кнопкой ниже. Изменить можно до начала матча.\n"
        f"Прогнозов сделано: <b>{predictions_count}</b>"
    )


def closed_message_text(match: Match, tz_name: str, predictions_count: int) -> str:
    return (
        "🔒 <b>Голосование закрыто</b>\n"
        f"{match_title(match)}\n"
        f"🕒 Старт: {format_kickoff(match, tz_name)}\n\n"
        f"Принято прогнозов: <b>{predictions_count}</b>"
    )
