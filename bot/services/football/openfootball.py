"""Провайдер на базе openfootball/worldcup.json (статичный публичный JSON).

Без ключа и лимитов, но результаты обновляются с задержкой (репозиторий правят
вручную). Реальный формат файла 2026:
    {"name": "...", "matches": [
        {"date": "2026-06-11", "time": "13:00 UTC-6",
         "team1": "Mexico", "team2": "South Africa", "group": "Group A"}, ...]}

Команды приходят строками без кода — код и русское название проставляются через
каноническую таблицу bot/teams.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiohttp

from bot.db.models import MatchStatus
from bot.services.football.base import FixtureDTO, MatchProvider, ResultDTO
from bot.teams import _normalize, canonical

DEFAULT_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/"
    "2026/worldcup.json"
)


def _parse_time(date: str, time_str: str) -> datetime | None:
    """'2026-06-11' + '13:00 UTC-6' -> aware UTC datetime."""
    parts = time_str.split()
    hhmm = parts[0]
    offset_hours = 0.0
    if len(parts) > 1 and parts[1].upper().startswith("UTC"):
        rest = parts[1][3:]  # '-6', '+0', '-3:30'
        if rest:
            sign = -1 if rest[0] == "-" else 1
            body = rest.lstrip("+-")
            if ":" in body:
                h, m = body.split(":")
                offset_hours = sign * (int(h) + int(m) / 60)
            else:
                offset_hours = sign * int(body)
    try:
        local = datetime.fromisoformat(f"{date}T{hhmm}")
    except ValueError:
        return None
    return (local - timedelta(hours=offset_hours)).replace(tzinfo=timezone.utc)


def _scores(m: dict) -> tuple[int | None, int | None]:
    if m.get("score1") is not None and m.get("score2") is not None:
        return m["score1"], m["score2"]
    score = m.get("score")
    if isinstance(score, dict):
        ft = score.get("ft")
        if isinstance(ft, (list, tuple)) and len(ft) == 2:
            return ft[0], ft[1]
    return None, None


def _parse_match(m: dict) -> FixtureDTO | None:
    name1, name2 = m.get("team1"), m.get("team2")
    date = m.get("date")
    if not (name1 and name2 and date):
        return None
    kickoff = _parse_time(date, m.get("time") or "00:00 UTC+0")
    if kickoff is None:
        return None
    home_team, home_code = canonical(str(name1))
    away_team, away_code = canonical(str(name2))
    s1, s2 = _scores(m)
    finished = s1 is not None and s2 is not None
    pid = f"of-{date}-{_normalize(str(name1))}-{_normalize(str(name2))}"
    group = (m.get("group") or "").lower()
    stage = "group" if group.startswith("group") else (group or "group")
    return FixtureDTO(
        provider_match_id=pid,
        home_team=home_team,
        away_team=away_team,
        home_code=home_code,
        away_code=away_code,
        kickoff_utc=kickoff,
        stage=stage,
        status=MatchStatus.FINISHED if finished else MatchStatus.SCHEDULED,
        home_score=s1,
        away_score=s2,
    )


class OpenFootballProvider(MatchProvider):
    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    async def _fetch(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(self._url) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    async def fixtures(self) -> list[FixtureDTO]:
        data = await self._fetch()
        out: list[FixtureDTO] = []
        for m in data.get("matches", []):
            dto = _parse_match(m)
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
