"""Абстракция источника данных о матчах.

Любой провайдер (football-data.org, openfootball, mock) реализует интерфейс
MatchProvider, отдавая данные в едином DTO. Это позволяет менять источник одним
параметром конфига и подменять его моком в тестах.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from bot.db.models import Choice, MatchStatus


@dataclass(slots=True)
class FixtureDTO:
    """Один матч в расписании."""

    provider_match_id: str
    home_team: str
    away_team: str
    home_code: str
    away_code: str
    kickoff_utc: datetime
    stage: str = "group"
    status: MatchStatus = MatchStatus.SCHEDULED
    home_score: int | None = None
    away_score: int | None = None


@dataclass(slots=True)
class ResultDTO:
    """Итог завершённого матча."""

    provider_match_id: str
    status: MatchStatus
    home_score: int | None
    away_score: int | None

    @property
    def outcome(self) -> Choice | None:
        if self.home_score is None or self.away_score is None:
            return None
        if self.home_score > self.away_score:
            return Choice.HOME
        if self.home_score < self.away_score:
            return Choice.AWAY
        return Choice.DRAW


class MatchProvider(ABC):
    """Контракт источника данных о матчах."""

    @abstractmethod
    async def fixtures(self) -> list[FixtureDTO]:
        """Вернуть расписание матчей турнира."""

    @abstractmethod
    async def result(self, provider_match_id: str) -> ResultDTO | None:
        """Вернуть результат конкретного матча (None, если ещё неизвестен)."""

    async def close(self) -> None:
        """Освободить ресурсы (HTTP-сессию и т.п.). По умолчанию ничего."""
