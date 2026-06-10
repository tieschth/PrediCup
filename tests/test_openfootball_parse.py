from datetime import datetime, timezone

from bot.db.models import MatchStatus
from bot.services.football.openfootball import _parse_match, _parse_time


def test_parse_time_utc_offset():
    # 13:00 в UTC-6 -> 19:00 UTC
    dt = _parse_time("2026-06-11", "13:00 UTC-6")
    assert dt == datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)


def test_parse_match_localizes_and_codes():
    m = {
        "date": "2026-06-11",
        "time": "13:00 UTC-6",
        "team1": "Mexico",
        "team2": "South Africa",
        "group": "Group A",
    }
    dto = _parse_match(m)
    assert dto.home_team == "Мексика"
    assert dto.home_code == "MEX"
    assert dto.away_team == "ЮАР"
    assert dto.away_code == "RSA"
    assert dto.status == MatchStatus.SCHEDULED
    assert dto.kickoff_utc == datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)


def test_parse_match_with_score_is_finished():
    m = {
        "date": "2026-06-11",
        "time": "13:00 UTC-6",
        "team1": "Brazil",
        "team2": "Haiti",
        "score": {"ft": [2, 0]},
    }
    dto = _parse_match(m)
    assert dto.status == MatchStatus.FINISHED
    assert dto.home_score == 2 and dto.away_score == 0
