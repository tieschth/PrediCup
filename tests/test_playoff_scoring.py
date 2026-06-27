from bot.config import ScoringCfg
from bot.db.models import Match, MatchDuration, PlayoffChoice
from bot.services.scoring import points_for_prediction, winning_choices

SC = ScoringCfg(correct_outcome=1, extra_time=2, penalty=2)


def _match(stage, h, a, duration="REGULAR", ph=None, pa=None):
    m = Match(
        provider_match_id="x", stage=stage, home_team="A", away_team="B",
        home_code="AAA", away_code="BBB", kickoff_utc=None,
        home_score=h, away_score=a, duration=duration, pen_home=ph, pen_away=pa,
    )
    return m


def test_playoff_regular_win():
    m = _match("LAST_16", 2, 1, "REGULAR")
    wins = winning_choices(m, SC)
    assert wins == {PlayoffChoice.R_HOME.value: 1}
    assert points_for_prediction(m, PlayoffChoice.R_HOME.value, SC) == 1
    assert points_for_prediction(m, PlayoffChoice.R_DRAW.value, SC) == 0
    assert points_for_prediction(m, PlayoffChoice.ET_HOME.value, SC) == 0


def test_playoff_extra_time_home():
    m = _match("QUARTER_FINALS", 2, 1, "EXTRA_TIME")
    wins = winning_choices(m, SC)
    # ничья в осн. время (+1) и победа хозяев в доп. время (+2)
    assert wins == {PlayoffChoice.R_DRAW.value: 1, PlayoffChoice.ET_HOME.value: 2}
    assert points_for_prediction(m, PlayoffChoice.R_DRAW.value, SC) == 1
    assert points_for_prediction(m, PlayoffChoice.ET_HOME.value, SC) == 2
    assert points_for_prediction(m, PlayoffChoice.ET_AWAY.value, SC) == 0
    assert points_for_prediction(m, PlayoffChoice.R_HOME.value, SC) == 0


def test_playoff_penalties_away():
    m = _match("FINAL", 1, 1, "PENALTY_SHOOTOUT", ph=3, pa=4)
    wins = winning_choices(m, SC)
    assert wins == {PlayoffChoice.R_DRAW.value: 1, PlayoffChoice.PEN_AWAY.value: 2}
    assert points_for_prediction(m, PlayoffChoice.PEN_AWAY.value, SC) == 2
    assert points_for_prediction(m, PlayoffChoice.PEN_HOME.value, SC) == 0


def test_group_stage_unchanged():
    m = _match("GROUP_STAGE", 1, 1, "REGULAR")
    assert winning_choices(m, SC) == {"DRAW": 1}
    m2 = _match("GROUP_STAGE", 3, 0, "REGULAR")
    assert winning_choices(m2, SC) == {"HOME": 1}
