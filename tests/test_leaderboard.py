from datetime import datetime, timezone

import pytest

from bot.db import repo
from bot.db.models import Choice
from bot.services.leaderboard import render_leaderboard


@pytest.mark.asyncio
async def test_leaderboard_includes_zero_point_voters_excludes_non_voters(sessionmaker):
    async with sessionmaker() as session:
        match = await repo.upsert_match(
            session,
            provider_match_id="x1",
            home_team="A",
            away_team="B",
            home_code="AAA",
            away_code="BBB",
            kickoff_utc=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        )
        # проголосовавший (по умолчанию 0 очков, пока матч не зарезолвлен)
        await repo.get_or_create_user(session, 1, username="voter")
        await repo.upsert_prediction(session, match.id, 1, Choice.HOME)
        # просто нажал /start, но не голосовал
        await repo.get_or_create_user(session, 2, username="lurker")
        await session.commit()

        rows = await repo.leaderboard(session)
        ids = {u.tg_id for u, _ in rows}
        assert 1 in ids  # проголосовавший с 0 очков — показан
        assert 2 not in ids  # не голосовал — не показан

        board = await render_leaderboard(session)
        assert "voter" in board
        assert "lurker" not in board
