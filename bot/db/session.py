"""Async-движок и фабрика сессий SQLAlchemy."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.db.models import Base

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(db_url: str, db_path: str | None = None) -> None:
    """Создаёт движок и фабрику сессий. Вызывается один раз при старте."""
    global _engine, _sessionmaker
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_async_engine(db_url, future=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


# Колонки, добавленные после первого релиза. ALTER ADD COLUMN безопасен и
# аддитивен — нужен, чтобы обновить уже существующую боевую БД без потери данных.
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "users": [
        ("label", "VARCHAR(128)"),
        ("bonus_points", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "matches": [
        ("duration", "VARCHAR(20) NOT NULL DEFAULT 'REGULAR'"),
        ("pen_home", "INTEGER"),
        ("pen_away", "INTEGER"),
    ],
}


def _ensure_schema(conn) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {
            row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
        }
        for name, ddl in columns:
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


async def init_db() -> None:
    """Создаёт таблицы, если их ещё нет, и доливает недостающие колонки."""
    assert _engine is not None, "init_engine() не вызван"
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_schema)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    assert _sessionmaker is not None, "init_engine() не вызван"
    return _sessionmaker
