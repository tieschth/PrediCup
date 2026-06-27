"""Сценарий Иран-Египет: матч зарезолвлен как победа гостей, позже API
исправил счёт на ничью — бот должен пересчитать очки и опубликовать поправку."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.db import repo
from bot.db.models import Choice
from bot.services import matches as matches_service


@pytest.mark.asyncio
async def test_reverify_recomputes_points_on_corrected_result(
    settings, sessionmaker, fake_bot, provider
):
    f = provider.add_match("Egypt", "Iran", "EGY", "IRN", minutes_to_kickoff=-120)
    async with sessionmaker() as session:
        await matches_service.sync_fixtures(session, provider)
        match = await repo.get_match_by_provider_id(session, f.provider_match_id)
        # голоса: один за победу Ирана (AWAY), один за ничью (DRAW)
        await repo.get_or_create_user(session, 1, username="iran_fan")
        await repo.get_or_create_user(session, 2, username="draw_fan")
        await repo.upsert_prediction(session, match.id, 1, Choice.AWAY)
        await repo.upsert_prediction(session, match.id, 2, Choice.DRAW)
        await session.commit()

    # API сначала отдал победу Ирана 1:2
    provider.set_result(f.provider_match_id, 1, 2)
    async with sessionmaker() as session:
        n = await matches_service.resolve_results(fake_bot, session, settings, provider)
        assert n == 1
        match = await repo.get_match_by_provider_id(session, f.provider_match_id)
        preds = {p.user_tg_id: p.points_awarded
                 for p in await repo.list_predictions_for_match(session, match.id)}
        assert preds == {1: settings.app.scoring.correct_outcome, 2: 0}

    # API исправил на ничью 1:1 — перепроверка должна пересчитать
    provider.set_result(f.provider_match_id, 1, 1)
    async with sessionmaker() as session:
        changed = await matches_service.reverify_results(
            fake_bot, session, settings, provider
        )
        assert changed == 1
        match = await repo.get_match_by_provider_id(session, f.provider_match_id)
        assert match.home_score == 1 and match.away_score == 1
        preds = {p.user_tg_id: p.points_awarded
                 for p in await repo.list_predictions_for_match(session, match.id)}
        # теперь очко у того, кто ставил на ничью; у «фаната Ирана» — 0
        assert preds == {1: 0, 2: settings.app.scoring.correct_outcome}

    # в чат опубликована поправка
    assert any("уточнён" in m["text"] for m in fake_bot.sent)
