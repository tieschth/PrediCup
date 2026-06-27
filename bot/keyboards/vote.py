"""Inline-клавиатура голосовалки с флагами.

callback_data: "vote:<match_id>:<КОД>".
Групповой этап — 3 кнопки (HOME/DRAW/AWAY). Плей-офф — 7 кнопок (R_*, ET_*, PEN_*).
Парсинг выбора — parse_vote_callback() (возвращает код-строку, валидный для стадии).
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Choice, Match, PlayoffChoice
from bot.flags import flag_for_code

VOTE_PREFIX = "vote"

_GROUP_CODES = {c.value for c in Choice}
_PLAYOFF_CODES = {c.value for c in PlayoffChoice}


def _btn(match: Match, text: str, code: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=f"{VOTE_PREFIX}:{match.id}:{code}"
    )


def build_vote_keyboard(match: Match) -> InlineKeyboardMarkup:
    hf = flag_for_code(match.home_code)
    af = flag_for_code(match.away_code)
    menu = [InlineKeyboardButton(text="📋 Мои голосования", callback_data="mymatches")]

    if not match.is_playoff:
        rows = [
            [
                _btn(match, f"{hf} П1", Choice.HOME.value),
                _btn(match, "⚖️ Ничья", Choice.DRAW.value),
                _btn(match, f"{af} П2", Choice.AWAY.value),
            ],
            menu,
        ]
        return InlineKeyboardMarkup(inline_keyboard=rows)

    # Плей-офф: основное время / доп. время / пенальти
    rows = [
        [
            _btn(match, f"{hf} П1 (осн.)", PlayoffChoice.R_HOME.value),
            _btn(match, "⚖️ Ничья (осн.)", PlayoffChoice.R_DRAW.value),
            _btn(match, f"{af} П2 (осн.)", PlayoffChoice.R_AWAY.value),
        ],
        [
            _btn(match, f"{hf} П1 (доп.)", PlayoffChoice.ET_HOME.value),
            _btn(match, f"{af} П2 (доп.)", PlayoffChoice.ET_AWAY.value),
        ],
        [
            _btn(match, f"{hf} П1 (пен.)", PlayoffChoice.PEN_HOME.value),
            _btn(match, f"{af} П2 (пен.)", PlayoffChoice.PEN_AWAY.value),
        ],
        menu,
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_vote_callback(data: str) -> tuple[int, str] | None:
    """Вернуть (match_id, код_выбора). Код валидируется на этапе обработки
    относительно стадии матча, здесь — лишь принадлежность известным наборам."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != VOTE_PREFIX:
        return None
    try:
        match_id = int(parts[1])
    except ValueError:
        return None
    code = parts[2]
    if code not in _GROUP_CODES and code not in _PLAYOFF_CODES:
        return None
    return match_id, code
