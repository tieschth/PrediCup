from bot.config import ScoringCfg
from bot.db.models import Choice
from bot.services.scoring import points_for

SC = ScoringCfg(correct_outcome=3)


def test_correct_outcome_awards_points():
    assert points_for(Choice.HOME, Choice.HOME, SC) == 3
    assert points_for(Choice.DRAW, Choice.DRAW, SC) == 3
    assert points_for(Choice.AWAY, Choice.AWAY, SC) == 3


def test_wrong_outcome_zero():
    assert points_for(Choice.HOME, Choice.AWAY, SC) == 0
    assert points_for(Choice.DRAW, Choice.HOME, SC) == 0


def test_unknown_outcome_zero():
    assert points_for(Choice.HOME, None, SC) == 0


def test_accepts_plain_strings():
    assert points_for("HOME", "HOME", SC) == 3
    assert points_for("HOME", "DRAW", SC) == 0
