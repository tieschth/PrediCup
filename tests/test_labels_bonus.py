from datetime import datetime, timezone

import pytest

from bot.db import repo
from bot.db.models import Choice
from bot.services.leaderboard import render_leaderboard


@pytest.mark.asyncio
async def test_label_priority_and_bonus(sessionmaker):
    async with sessionmaker() as session:
        match = await repo.upsert_match(
            session, provider_match_id="m1", home_team="A", away_team="B",
            home_code="AAA", away_code="BBB",
            kickoff_utc=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        )
        # двое с одинаковым именем в ТГ, различаем меткой
        await repo.get_or_create_user(session, 1, username="vaskaaaak",
                                      display_name="Александр")
        await repo.get_or_create_user(session, 2, username="other",
                                      display_name="Александр")
        await repo.upsert_prediction(session, match.id, 1, Choice.HOME)
        await repo.upsert_prediction(session, match.id, 2, Choice.AWAY)
        await session.commit()

        # метка перекрывает имя из ТГ
        await repo.set_label(session, 1, "Вася П.")
        # ручной бонус +1
        assert await repo.adjust_bonus(session, 1, 1) == 1
        await session.commit()

        board = await render_leaderboard(session)
        assert "Вася П." in board       # показывается метка, а не «Александр»
        rows = await repo.leaderboard(session)
        pts = {u.tg_id: p for u, p in rows}
        # user1: бонус 1 (+0 за прогноз пока матч не сыгран) = 1; user2: 0
        assert pts[1] == 1 and pts[2] == 0


@pytest.mark.asyncio
async def test_adjust_bonus_unknown_user(sessionmaker):
    async with sessionmaker() as session:
        assert await repo.adjust_bonus(session, 999999, 5) is None
