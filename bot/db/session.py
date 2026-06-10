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


async def init_db() -> None:
    """Создаёт таблицы, если их ещё нет."""
    assert _engine is not None, "init_engine() не вызван"
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    assert _sessionmaker is not None, "init_engine() не вызван"
    return _sessionmaker
