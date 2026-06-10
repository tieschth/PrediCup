"""Загрузка конфигурации: секреты из .env + настройки из config.yaml.

Секреты (токен бота, API-ключ) читаются из переменных окружения через
pydantic-settings. Всё остальное (тайминги, роли, очки, провайдер) — из
YAML-файла, путь к которому задаётся переменной CONFIG_PATH.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotCfg(BaseModel):
    vote_open_hours_before: float = 10
    display_timezone: str = "Europe/Moscow"


class ProviderCfg(BaseModel):
    name: str = "mock"  # football_data_org | openfootball | mock
    competition: str = "WC"


class SchedulerCfg(BaseModel):
    sync_fixtures_hours: float = 6
    open_votes_minutes: float = 15
    resolve_results_minutes: float = 5


class RolesCfg(BaseModel):
    admins: list[int] = Field(default_factory=list)
    allowed_chats: list[int] = Field(default_factory=list)


class ScoringCfg(BaseModel):
    correct_outcome: int = 3


class AppConfig(BaseModel):
    """Содержимое config.yaml."""

    bot: BotCfg = Field(default_factory=BotCfg)
    provider: ProviderCfg = Field(default_factory=ProviderCfg)
    scheduler: SchedulerCfg = Field(default_factory=SchedulerCfg)
    roles: RolesCfg = Field(default_factory=RolesCfg)
    scoring: ScoringCfg = Field(default_factory=ScoringCfg)


class Secrets(BaseSettings):
    """Секреты и пути из окружения (.env)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str = ""
    football_api_key: str = ""
    env: str = "dev"  # prod | dev
    config_path: str = "config/config.yaml"
    db_path: str = "data/predicup.sqlite3"

    @property
    def is_dev(self) -> bool:
        return self.env.lower() == "dev"


class Settings:
    """Объединяет секреты и YAML-конфиг в один объект."""

    def __init__(self, secrets: Secrets, app: AppConfig) -> None:
        self.secrets = secrets
        self.app = app

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.secrets.db_path}"


def load_settings() -> Settings:
    secrets = Secrets()
    cfg_path = Path(secrets.config_path)
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    else:
        data = {}
    app = AppConfig.model_validate(data)
    return Settings(secrets=secrets, app=app)
