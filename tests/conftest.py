"""Общие фикстуры тестов: in-memory БД, фейковый бот, настройки, mock-провайдер."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import AppConfig, Secrets, Settings
from bot.db.models import Base
from bot.services.football.mock import MockProvider

CHAT_ID = -1001234567890
ADMIN_ID = 999


class FakeBot:
    """Минимальная замена aiogram.Bot: запоминает отправленные/изменённые сообщения."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self._mid = 0

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self._mid += 1
        self.sent.append({"chat_id": chat_id, "text": text, "message_id": self._mid})
        return SimpleNamespace(message_id=self._mid)

    async def edit_message_text(
        self, text, chat_id=None, message_id=None, reply_markup=None, **kwargs
    ):
        self.edited.append(
            {"chat_id": chat_id, "message_id": message_id, "text": text}
        )
        return True


@pytest.fixture
def settings() -> Settings:
    secrets = Secrets(
        _env_file=None,  # не читать реальный .env
        bot_token="test",
        env="dev",
    )
    app = AppConfig.model_validate(
        {
            "bot": {"vote_open_hours_before": 10, "display_timezone": "UTC"},
            "provider": {"name": "mock"},
            "roles": {"admins": [ADMIN_ID], "allowed_chats": [CHAT_ID]},
            "scoring": {"correct_outcome": 3},
        }
    )
    return Settings(secrets=secrets, app=app)


@pytest_asyncio.fixture
async def sessionmaker(tmp_path):
    db_file = tmp_path / "test.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider()
