"""Формирование таблицы лидеров."""
from __future__ import annotations

import html

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import User

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _display(user: User) -> str:
    name = user.display_name or (f"@{user.username}" if user.username else None)
    return html.escape(name or str(user.tg_id))


async def render_leaderboard(session: AsyncSession) -> str:
    rows = await repo.leaderboard(session)
    rows = [(u, p) for u, p in rows if p > 0] or rows  # покажем всех, если очков нет
    if not rows:
        return "🏆 <b>Таблица лидеров</b>\n\nПока нет ни одного прогноза."
    lines = ["🏆 <b>Таблица лидеров</b>", ""]
    for i, (user, pts) in enumerate(rows, start=1):
        prefix = _MEDALS.get(i, f"{i}.")
        lines.append(f"{prefix} {_display(user)} — <b>{pts}</b>")
    return "\n".join(lines)
