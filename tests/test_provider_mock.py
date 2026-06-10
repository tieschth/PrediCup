import pytest

from bot.db.models import Choice, MatchStatus
from bot.services.football.mock import MockProvider


@pytest.mark.asyncio
async def test_add_and_list_fixtures():
    p = MockProvider()
    p.add_match("Brazil", "Argentina", "BRA", "ARG", minutes_to_kickoff=30)
    fixtures = await p.fixtures()
    assert len(fixtures) == 1
    assert fixtures[0].home_team == "Brazil"
    assert fixtures[0].status == MatchStatus.SCHEDULED


@pytest.mark.asyncio
async def test_result_and_outcome():
    p = MockProvider()
    f = p.add_match("Brazil", "Argentina", "BRA", "ARG")
    assert await p.result(f.provider_match_id) is None
    p.set_result(f.provider_match_id, 2, 1)
    res = await p.result(f.provider_match_id)
    assert res is not None
    assert res.status == MatchStatus.FINISHED
    assert res.outcome == Choice.HOME

    p.set_result(f.provider_match_id, 1, 1)
    assert (await p.result(f.provider_match_id)).outcome == Choice.DRAW
