"""Управляемый провайдер для тестов и дев-режима.

Позволяет программно добавить матч (с заданным временем до старта) и выставить
его результат — чтобы прогнать весь сценарий без обращения к внешнему API.
Используется тестами и дев-командами /devmatch, /devresult.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from bot.db.models import MatchDuration, MatchStatus
from bot.services.football.base import FixtureDTO, MatchProvider, ResultDTO


class MockProvider(MatchProvider):
    def __init__(self) -> None:
        self._fixtures: dict[str, FixtureDTO] = {}
        self._results: dict[str, ResultDTO] = {}

    def add_match(
        self,
        home_team: str,
        away_team: str,
        home_code: str,
        away_code: str,
        minutes_to_kickoff: float = 60,
        stage: str = "group",
    ) -> FixtureDTO:
        # Уникальный id, не зависящий от перезапусков (счётчик сбрасывался и
        # коллизировал с уже завершёнными матчами в постоянной SQLite-базе).
        pid = f"mock-{uuid.uuid4().hex[:12]}"
        kickoff = datetime.now(timezone.utc) + timedelta(minutes=minutes_to_kickoff)
        dto = FixtureDTO(
            provider_match_id=pid,
            home_team=home_team,
            away_team=away_team,
            home_code=home_code,
            away_code=away_code,
            kickoff_utc=kickoff,
            stage=stage,
        )
        self._fixtures[pid] = dto
        return dto

    def set_result(
        self,
        provider_match_id: str,
        home_score: int,
        away_score: int,
        duration: str = MatchDuration.REGULAR.value,
        pen_home: int | None = None,
        pen_away: int | None = None,
    ) -> None:
        self._results[provider_match_id] = ResultDTO(
            provider_match_id=provider_match_id,
            status=MatchStatus.FINISHED,
            home_score=home_score,
            away_score=away_score,
            duration=duration,
            pen_home=pen_home,
            pen_away=pen_away,
        )

    async def fixtures(self) -> list[FixtureDTO]:
        return list(self._fixtures.values())

    async def result(self, provider_match_id: str) -> ResultDTO | None:
        return self._results.get(provider_match_id)
