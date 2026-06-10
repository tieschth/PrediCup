"""Выбор провайдера по конфигу."""
from __future__ import annotations

from bot.config import Settings
from bot.services.football.base import MatchProvider
from bot.services.football.mock import MockProvider


def build_provider(settings: Settings) -> MatchProvider:
    name = settings.app.provider.name.lower()
    if name == "mock":
        return MockProvider()
    if name == "football_data_org":
        from bot.services.football.football_data_org import FootballDataOrgProvider

        return FootballDataOrgProvider(
            api_key=settings.secrets.football_api_key,
            competition=settings.app.provider.competition,
        )
    if name == "openfootball":
        from bot.services.football.openfootball import OpenFootballProvider

        return OpenFootballProvider()
    raise ValueError(f"Неизвестный провайдер: {settings.app.provider.name}")
