"""Начисление очков.

Групповой этап: совпал исход (П1/Х/П2) — даём correct_outcome очков, иначе 0.

Плей-офф (7 вариантов, по согласованным правилам):
  R_HOME / R_AWAY  — победа в основное время  → correct_outcome (1)
  R_DRAW           — ничья после 90 мин (матч ушёл в доп.время/пенальти) → 1
  ET_HOME / ET_AWAY— победа в доп. время       → extra_time (2)
  PEN_HOME/PEN_AWAY— победа по пенальти         → penalty (2)

Каждый участник выбирает один вариант. Несколько вариантов могут «выиграть»
одновременно для разных участников: напр. матч ушёл в доп.время и победила 1-я
команда → побеждают и R_DRAW (+1, у тех кто ставил на ничью в осн.), и ET_HOME
(+2, у тех кто ставил на победу в доп.время).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from bot.config import ScoringCfg
from bot.db.models import Choice, MatchDuration, PlayoffChoice

if TYPE_CHECKING:
    from bot.db.models import Match


def points_for(
    predicted: Choice | str, outcome: Choice | str | None, scoring: ScoringCfg
) -> int:
    """Очки за прогноз на групповой этап (П1/Х/П2)."""
    if outcome is None:
        return 0
    pred = predicted.value if isinstance(predicted, Choice) else str(predicted)
    out = outcome.value if isinstance(outcome, Choice) else str(outcome)
    return scoring.correct_outcome if pred == out else 0


def group_outcome(home: int | None, away: int | None) -> Choice | None:
    if home is None or away is None:
        return None
    if home > away:
        return Choice.HOME
    if home < away:
        return Choice.AWAY
    return Choice.DRAW


def winning_choices(match: "Match", scoring: ScoringCfg) -> dict[str, int]:
    """Какие варианты голосования выигрывают на этом матче и сколько дают очков.

    Возвращает {код_варианта: очки}. Пусто, если результат ещё не известен.
    """
    h, a = match.home_score, match.away_score
    if not match.is_playoff:
        out = group_outcome(h, a)
        return {out.value: scoring.correct_outcome} if out else {}

    if h is None or a is None:
        return {}
    duration = (match.duration or MatchDuration.REGULAR.value).upper()

    if duration == MatchDuration.REGULAR.value:
        if h > a:
            return {PlayoffChoice.R_HOME.value: scoring.correct_outcome}
        if a > h:
            return {PlayoffChoice.R_AWAY.value: scoring.correct_outcome}
        return {}  # в плей-офф основное время не может закончиться вничью

    # дальше — ничья в основное время всегда «выиграла»
    result: dict[str, int] = {PlayoffChoice.R_DRAW.value: scoring.correct_outcome}

    if duration == MatchDuration.EXTRA_TIME.value:
        if h > a:
            result[PlayoffChoice.ET_HOME.value] = scoring.extra_time
        elif a > h:
            result[PlayoffChoice.ET_AWAY.value] = scoring.extra_time
    elif duration == MatchDuration.PENALTY_SHOOTOUT.value:
        ph, pa = match.pen_home, match.pen_away
        if ph is not None and pa is not None:
            if ph > pa:
                result[PlayoffChoice.PEN_HOME.value] = scoring.penalty
            elif pa > ph:
                result[PlayoffChoice.PEN_AWAY.value] = scoring.penalty
    return result


def points_for_prediction(match: "Match", choice: str, scoring: ScoringCfg) -> int:
    """Сколько очков получает конкретный выбор на этом матче."""
    code = choice.value if isinstance(choice, (Choice, PlayoffChoice)) else str(choice)
    return winning_choices(match, scoring).get(code, 0)
