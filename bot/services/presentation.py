"""Текстовые представления матчей и исходов (используются в сообщениях и /matches)."""
from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.db.models import Choice, Match, PlayoffChoice, User
from bot.flags import flag_for_code


def _esc(s: str) -> str:
    return html.escape(s)


def display_name(user: User) -> str:
    """Имя для показа: заданная метка (label) > имя из ТГ > @username > id."""
    if user.label:
        return _esc(user.label)
    if user.display_name:
        return _esc(user.display_name)
    if user.username:
        return f"@{_esc(user.username)}"
    return str(user.tg_id)


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


def choice_label(match: Match, choice: Choice | PlayoffChoice | str) -> str:
    val = choice.value if isinstance(choice, (Choice, PlayoffChoice)) else str(choice)
    hf, af = flag_for_code(match.home_code), flag_for_code(match.away_code)
    home, away = _esc(match.home_team), _esc(match.away_team)
    labels = {
        Choice.HOME.value: f"{hf} Победа: {home}",
        Choice.AWAY.value: f"{af} Победа: {away}",
        Choice.DRAW.value: "⚖️ Ничья",
        PlayoffChoice.R_HOME.value: f"{hf} {home} — победа в осн. время",
        PlayoffChoice.R_AWAY.value: f"{af} {away} — победа в осн. время",
        PlayoffChoice.R_DRAW.value: "⚖️ Ничья в осн. время (доп.время/пенальти)",
        PlayoffChoice.ET_HOME.value: f"{hf} {home} — победа в доп. время",
        PlayoffChoice.ET_AWAY.value: f"{af} {away} — победа в доп. время",
        PlayoffChoice.PEN_HOME.value: f"{hf} {home} — победа по пенальти",
        PlayoffChoice.PEN_AWAY.value: f"{af} {away} — победа по пенальти",
    }
    return labels.get(val, val)


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
