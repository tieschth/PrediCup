"""Формирование таблицы лидеров."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.services.presentation import display_name

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


async def render_leaderboard(session: AsyncSession) -> str:
    rows = await repo.leaderboard(session)  # все, кто голосовал хотя бы раз
    if not rows:
        return "🏆 <b>Таблица лидеров</b>\n\nПока нет ни одного прогноза."
    lines = ["🏆 <b>Таблица лидеров</b>", ""]
    for i, (user, pts) in enumerate(rows, start=1):
        prefix = _MEDALS.get(i, f"{i}.")
        lines.append(f"{prefix} {display_name(user)} — <b>{pts}</b>")
    return "\n".join(lines)
