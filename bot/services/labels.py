"""Импорт отображаемых имён (label) из файла.

Файл — по строке на участника: «идентификатор;имя», где идентификатор это
@username, username или tg_id. Разделитель «;», «,» или табуляция. Строки с # и
пустые игнорируются. Применяется автоматически при старте бота (если файл есть)
и вручную скриптом scripts/set_labels.py.
"""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import User


def parse_labels(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for sep in (";", "\t", ","):
            if sep in line:
                ident, label = (s.strip() for s in line.split(sep, 1))
                if ident and label:
                    out.append((ident, label))
                break
    return out


async def apply_labels(session: AsyncSession, pairs: list[tuple[str, str]]):
    """Проставить метки. Возвращает (обновлено, [не найденные идентификаторы])."""
    updated = 0
    missing: list[str] = []
    for ident, label in pairs:
        bare = ident.lstrip("@")
        if bare.isdigit():
            user = await session.get(User, int(bare))
        else:
            user = await repo.find_user_by_username(session, bare)
        if user is None:
            missing.append(ident)
            continue
        user.label = label
        updated += 1
    await session.flush()
    return updated, missing


def default_labels_path(db_path: str) -> str:
    """labels.csv рядом с файлом БД (в той же папке data/)."""
    return os.path.join(os.path.dirname(db_path) or ".", "labels.csv")


async def apply_labels_from_file(session: AsyncSession, path: str):
    with open(path, encoding="utf-8-sig") as f:
        pairs = parse_labels(f.read())
    return await apply_labels(session, pairs)
