"""Провайдер на базе openfootball/worldcup.json (статичный публичный JSON).

Без ключа и лимитов, но результаты обновляются с задержкой (репозиторий правят
вручную). Подходит как запасной источник. Формат cup.json:
rounds -> matches с team1/team2, date/time и (после матча) score.

Схема openfootball исторически слегка менялась — парсер сделан терпимым к
вариациям (team как строка или объект, разные поля счёта).
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiohttp

from bot.db.models import MatchStatus
from bot.services.football.base import FixtureDTO, MatchProvider, ResultDTO

# Готовый собранный JSON ЧМ-2026 (national teams). При необходимости переопредели.
DEFAULT_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/"
    "2026/worldcup.json"
)


class OpenFootballProvider(MatchProvider):
    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    async def _fetch(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(self._url) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    @staticmethod
    def _team(value) -> tuple[str, str]:
        """Вернуть (name, code) из строки или объекта."""
        if isinstance(value, dict):
            name = value.get("name") or value.get("team") or "TBD"
            code = value.get("code") or value.get("key") or ""
            return name, code
        return str(value), ""

    @classmethod
    def _parse_match(cls, m: dict, index: int) -> FixtureDTO | None:
        name1, code1 = cls._team(m.get("team1") or m.get("home"))
        name2, code2 = cls._team(m.get("team2") or m.get("away"))
        date = m.get("date")
        if not date:
            return None
        time = m.get("time") or "00:00"
        try:
            kickoff = datetime.fromisoformat(f"{date}T{time}").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None
        pid = str(m.get("num") or m.get("id") or index)
        s1 = m.get("score1", m.get("score", {}).get("ft", [None, None])[0]
                  if isinstance(m.get("score"), dict) else None)
        s2 = m.get("score2", m.get("score", {}).get("ft", [None, None])[1]
                  if isinstance(m.get("score"), dict) else None)
        finished = s1 is not None and s2 is not None
        return FixtureDTO(
            provider_match_id=f"of-{pid}",
            home_team=name1,
            away_team=name2,
            home_code=(code1 or "")[:8],
            away_code=(code2 or "")[:8],
            kickoff_utc=kickoff,
            stage=(m.get("group") and "group") or "group",
            status=MatchStatus.FINISHED if finished else MatchStatus.SCHEDULED,
            home_score=s1,
            away_score=s2,
        )

    async def fixtures(self) -> list[FixtureDTO]:
        data = await self._fetch()
        out: list[FixtureDTO] = []
        idx = 0
        for rnd in data.get("rounds", []):
            for m in rnd.get("matches", []):
                idx += 1
                dto = self._parse_match(m, idx)
                if dto:
                    out.append(dto)
        return out

    async def result(self, provider_match_id: str) -> ResultDTO | None:
        for dto in await self.fixtures():
            if dto.provider_match_id == provider_match_id:
                return ResultDTO(
                    provider_match_id=dto.provider_match_id,
                    status=dto.status,
                    home_score=dto.home_score,
                    away_score=dto.away_score,
                )
        return None
