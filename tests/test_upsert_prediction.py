from datetime import datetime, timezone

import pytest

from bot.db import repo
from bot.db.models import Choice


@pytest.mark.asyncio
async def test_upsert_is_idempotent_no_unique_error(sessionmaker):
    async with sessionmaker() as session:
        match = await repo.upsert_match(
            session,
            provider_match_id="m23",
            home_team="A",
            away_team="B",
            home_code="AAA",
            away_code="BBB",
            kickoff_utc=datetime(2026, 6, 17, 19, 0, tzinfo=timezone.utc),
        )
        await repo.get_or_create_user(session, 544535357, username="andrey")

        # первый голос
        await repo.upsert_prediction(session, match.id, 544535357, Choice.HOME)
        # повторный голос на тот же матч — не должен падать с UNIQUE, должен обновить
        await repo.upsert_prediction(session, match.id, 544535357, Choice.AWAY)
        await session.commit()

        assert await repo.count_predictions(session, match.id) == 1
        pred = await repo.get_prediction(session, match.id, 544535357)
        assert pred.choice == Choice.AWAY.value
