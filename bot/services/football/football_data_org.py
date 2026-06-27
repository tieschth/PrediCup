"""Провайдер на базе football-data.org (v4).

Бесплатный тариф покрывает ЧМ-2026 (код турнира "WC"). Авторизация — заголовок
X-Auth-Token. Документация: https://www.football-data.org/documentation/quickstart
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import aiohttp

from bot.db.models import MatchStatus
from bot.services.football.base import FixtureDTO, MatchProvider, ResultDTO
from bot.teams import canonical

BASE_URL = "https://api.football-data.org/v4"

# Один запрос к /competitions/WC/matches отдаёт все 104 матча со статусами и
# счётом. Кэшируем его на короткое время, чтобы пачка проверок результатов в
# одном цикле резолва стоила 1 запрос, а не N (лимит — 10 запросов/мин).
_CACHE_TTL = 90.0

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
        self._cache: dict[str, dict] = {}  # id -> сырой матч
        self._cache_ts: float = 0.0

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
        matches = data.get("matches", [])
        self._cache = {str(m["id"]): m for m in matches}
        self._cache_ts = time.monotonic()
        return matches

    async def _cached_matches(self) -> dict[str, dict]:
        if not self._cache or (time.monotonic() - self._cache_ts) > _CACHE_TTL:
            await self._fetch_matches()
        return self._cache

    @staticmethod
    def _score_parts(m: dict) -> tuple[str, int | None, int | None, int | None, int | None]:
        """(duration, full_home, full_away, pen_home, pen_away)."""
        score = m.get("score", {})
        full = score.get("fullTime", {}) or {}
        pens = score.get("penalties", {}) or {}
        duration = score.get("duration") or "REGULAR"
        return (
            duration,
            full.get("home"),
            full.get("away"),
            pens.get("home"),
            pens.get("away"),
        )

    @classmethod
    def _parse(cls, m: dict) -> FixtureDTO:
        home = m.get("homeTeam", {})
        away = m.get("awayTeam", {})
        kickoff = datetime.fromisoformat(
            m["utcDate"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        status = _STATUS_MAP.get(m.get("status", ""), MatchStatus.SCHEDULED)
        home_name = home.get("name") or home.get("shortName") or "TBD"
        away_name = away.get("name") or away.get("shortName") or "TBD"
        home_team, home_code = canonical(home_name, (home.get("tla") or ""))
        away_team, away_code = canonical(away_name, (away.get("tla") or ""))
        duration, fh, fa, ph, pa = cls._score_parts(m)
        return FixtureDTO(
            provider_match_id=str(m["id"]),
            home_team=home_team,
            away_team=away_team,
            home_code=home_code[:8],
            away_code=away_code[:8],
            kickoff_utc=kickoff,
            stage=(m.get("stage") or "group").lower(),
            status=status,
            home_score=fh,
            away_score=fa,
            duration=duration,
            pen_home=ph,
            pen_away=pa,
        )

    async def fixtures(self) -> list[FixtureDTO]:
        matches = await self._fetch_matches()
        return [self._parse(m) for m in matches]

    async def result(self, provider_match_id: str) -> ResultDTO | None:
        # Берём из кэша всего турнира — не делаем отдельный запрос на каждый матч.
        matches = await self._cached_matches()
        m = matches.get(str(provider_match_id))
        if m is None:
            return None
        status = _STATUS_MAP.get(m.get("status", ""), MatchStatus.SCHEDULED)
        duration, fh, fa, ph, pa = self._score_parts(m)
        return ResultDTO(
            provider_match_id=str(m["id"]),
            status=status,
            home_score=fh,
            away_score=fa,
            duration=duration,
            pen_home=ph,
            pen_away=pa,
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
