"""E2E на уровне сервисов: матч -> голоса -> результат -> очки -> таблица."""
from __future__ import annotations

import pytest

from bot.db import repo
from bot.db.models import Choice
from bot.services import matches as matches_service
from bot.services.leaderboard import render_leaderboard
from tests.conftest import CHAT_ID


@pytest.mark.asyncio
async def test_full_flow(settings, sessionmaker, fake_bot, provider):
    # 1. Провайдер отдаёт матч, синхронизируем в БД
    fixture = provider.add_match(
        "Brazil", "Argentina", "BRA", "ARG", minutes_to_kickoff=10
    )
    async with sessionmaker() as session:
        n = await matches_service.sync_fixtures(session, provider)
    assert n == 1

    # 2. Открываем голосование — в чат уходит одно сообщение
    async with sessionmaker() as session:
        opened = await matches_service.open_votes(fake_bot, session, settings)
    assert opened == 1
    assert any(m["chat_id"] == CHAT_ID for m in fake_bot.sent)

    # 3. Три участника голосуют (двое верно — HOME, один — DRAW)
    async with sessionmaker() as session:
        match = await repo.get_match_by_provider_id(session, fixture.provider_match_id)
        for uid, choice in [(1, Choice.HOME), (2, Choice.HOME), (3, Choice.DRAW)]:
            await repo.get_or_create_user(session, uid, username=f"u{uid}")
            await repo.upsert_prediction(session, match.id, uid, choice)
        await session.commit()

    # 4. Переголосование: участник 3 меняет прогноз до старта
    async with sessionmaker() as session:
        match = await repo.get_match_by_provider_id(session, fixture.provider_match_id)
        await repo.upsert_prediction(session, match.id, 3, Choice.HOME)
        await session.commit()
        assert await repo.count_predictions(session, match.id) == 3  # не задвоилось

    # 5. «API прочитал результат»: 2:1 -> победа хозяев
    provider.set_result(fixture.provider_match_id, 2, 1)
    async with sessionmaker() as session:
        match = await repo.get_latest_unresolved_match(session)
        await matches_service.force_resolve(
            fake_bot, session, settings, match, 2, 1
        )

    # 6. Очки: все трое угадали HOME -> по 3 очка
    async with sessionmaker() as session:
        match = await repo.get_match_by_provider_id(session, fixture.provider_match_id)
        assert match.resolved is True
        preds = await repo.list_predictions_for_match(session, match.id)
        assert {p.user_tg_id: p.points_awarded for p in preds} == {1: 3, 2: 3, 3: 3}

        board = await render_leaderboard(session)
        assert "Таблица лидеров" in board

    # 7. Итоговое сообщение опубликовано в чат
    assert any("Итог матча" in m["text"] for m in fake_bot.sent)


@pytest.mark.asyncio
async def test_kickoff_is_timezone_aware_after_reload(sessionmaker, provider):
    """Регрессия: дата из SQLite должна читаться как timezone-aware, иначе
    сравнение с datetime.now(timezone.utc) падало (как в проде при голосовании)."""
    from datetime import datetime, timezone

    provider.add_match("A", "B", "AAA", "BBB", minutes_to_kickoff=30)
    async with sessionmaker() as session:
        await matches_service.sync_fixtures(session, provider)
    async with sessionmaker() as session:
        match = (await repo.list_started_unresolved(
            session, datetime.now(timezone.utc).replace(year=2100)
        ))[0]
        assert match.kickoff_utc.tzinfo is not None
        # сравнение не должно бросать TypeError
        assert match.kickoff_utc > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_vote_closes_after_kickoff(settings, sessionmaker, fake_bot, provider):
    # матч уже идёт (старт в прошлом) -> голосование должно закрыться
    provider.add_match("A", "B", "AAA", "BBB", minutes_to_kickoff=10)
    async with sessionmaker() as session:
        await matches_service.sync_fixtures(session, provider)
        await matches_service.open_votes(fake_bot, session, settings)

    # сдвигаем kickoff в прошлое напрямую в БД
    async with sessionmaker() as session:
        from datetime import datetime, timedelta, timezone

        match = (await repo.list_started_unresolved(session, datetime.now(timezone.utc)
                 + timedelta(days=1)))[0]
        match.kickoff_utc = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()

    async with sessionmaker() as session:
        closed = await matches_service.close_votes(fake_bot, session, settings)
    assert closed == 1
    assert any("закрыто" in e["text"] for e in fake_bot.edited)
