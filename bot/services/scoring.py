"""Начисление очков.

Групповой этап: совпал исход (П1/Х/П2) — даём correct_outcome очков, иначе 0.
Веса берём из конфига, чтобы их можно было менять без правки кода. Бонусы за
точный счёт / доп.время добавятся сюда же позже.
"""
from __future__ import annotations

from bot.config import ScoringCfg
from bot.db.models import Choice


def points_for(
    predicted: Choice | str, outcome: Choice | str | None, scoring: ScoringCfg
) -> int:
    """Сколько очков получает прогноз `predicted` при исходе `outcome`."""
    if outcome is None:
        return 0
    pred = predicted.value if isinstance(predicted, Choice) else str(predicted)
    out = outcome.value if isinstance(outcome, Choice) else str(outcome)
    return scoring.correct_outcome if pred == out else 0
