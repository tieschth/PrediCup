"""Провайдер на базе football-data.org (v4).

Бесплатный тариф покрывает ЧМ-2026 (код турнира "WC"). Авторизация — заголовок
X-Auth-Token. Документация: https://www.football-data.org/documentation/quickstart
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiohttp

from bot.db.models import MatchStatus
from bot.services.football.base import FixtureDTO, MatchProvider, ResultDTO

BASE_URL = "https://api.football-data.org/v4"

# Маппинг статусов football-data.org -> наши
_STATUS_MAP = {
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.LIVE,
    "PAUSED": MatchStatus.LIVE,
    "SUSPENDED": MatchStatus.LIVE,
    "FINISHED": MatchStatus.FINISHED,
    "AWARDED": MatchStatus.FINISHED,
}


class FootballDataOrgProvider(MatchProvider):
    def __init__(self, api_key: str, competition: str = "WC") -> None:
        self._key = api_key
        self._competition = competition
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Auth-Token": self._key}
            )
        return self._session

    async def _fetch_matches(self) -> list[dict]:
        session = await self._get_session()
        url = f"{BASE_URL}/competitions/{self._competition}/matches"
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data.get("matches", [])

    @staticmethod
    def _parse(m: dict) -> FixtureDTO:
        home = m.get("homeTeam", {})
        away = m.get("awayTeam", {})
        score = m.get("score", {}).get("fullTime", {})
        kickoff = datetime.fromisoformat(
            m["utcDate"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        status = _STATUS_MAP.get(m.get("status", ""), MatchStatus.SCHEDULED)
        return FixtureDTO(
            provider_match_id=str(m["id"]),
            home_team=home.get("name") or home.get("shortName") or "TBD",
            away_team=away.get("name") or away.get("shortName") or "TBD",
            home_code=(home.get("tla") or "")[:8],
            away_code=(away.get("tla") or "")[:8],
            kickoff_utc=kickoff,
            stage=(m.get("stage") or "group").lower(),
            status=status,
            home_score=score.get("home"),
            away_score=score.get("away"),
        )

    async def fixtures(self) -> list[FixtureDTO]:
        matches = await self._fetch_matches()
        return [self._parse(m) for m in matches]

    async def result(self, provider_match_id: str) -> ResultDTO | None:
        session = await self._get_session()
        url = f"{BASE_URL}/matches/{provider_match_id}"
        async with session.get(url) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            m = await resp.json()
        score = m.get("score", {}).get("fullTime", {})
        status = _STATUS_MAP.get(m.get("status", ""), MatchStatus.SCHEDULED)
        return ResultDTO(
            provider_match_id=str(m["id"]),
            status=status,
            home_score=score.get("home"),
            away_score=score.get("away"),
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
