"""Inline-клавиатура голосовалки с флагами.

callback_data: "vote:<match_id>:<HOME|DRAW|AWAY>".
Парсинг — parse_vote_callback().
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Choice, Match
from bot.flags import flag_for_code

VOTE_PREFIX = "vote"


def build_vote_keyboard(match: Match) -> InlineKeyboardMarkup:
    home_flag = flag_for_code(match.home_code)
    away_flag = flag_for_code(match.away_code)
    buttons = [
        InlineKeyboardButton(
            text=f"{home_flag} П1",
            callback_data=f"{VOTE_PREFIX}:{match.id}:{Choice.HOME.value}",
        ),
        InlineKeyboardButton(
            text="⚖️ Ничья",
            callback_data=f"{VOTE_PREFIX}:{match.id}:{Choice.DRAW.value}",
        ),
        InlineKeyboardButton(
            text=f"{away_flag} П2",
            callback_data=f"{VOTE_PREFIX}:{match.id}:{Choice.AWAY.value}",
        ),
    ]
    menu = [
        InlineKeyboardButton(
            text="📋 Мои голосования", callback_data="mymatches"
        )
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons, menu])


def parse_vote_callback(data: str) -> tuple[int, Choice] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != VOTE_PREFIX:
        return None
    try:
        match_id = int(parts[1])
        choice = Choice(parts[2])
    except (ValueError, KeyError):
        return None
    return match_id, choice
