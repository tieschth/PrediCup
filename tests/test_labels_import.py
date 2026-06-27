import pytest

from bot.db import repo
from bot.db.models import User
from bot.services.labels import apply_labels, parse_labels


def test_parse_labels_ignores_comments_and_blank():
    text = "# comment\n\n@vasya;Вася П.\n123;Имя По Айди\nbad_line_no_sep\n"
    pairs = parse_labels(text)
    assert pairs == [("@vasya", "Вася П."), ("123", "Имя По Айди")]


@pytest.mark.asyncio
async def test_apply_labels_by_username_and_id(sessionmaker):
    async with sessionmaker() as session:
        await repo.get_or_create_user(session, 1, username="vasya")
        await repo.get_or_create_user(session, 2, username=None,
                                      display_name="Без юзернейма")
        await session.commit()

        updated, missing = await apply_labels(
            session,
            [("@vasya", "Вася П."), ("2", "По Айди"), ("@nobody", "Никто")],
        )
        await session.commit()
        assert updated == 2
        assert missing == ["@nobody"]
        assert (await session.get(User, 1)).label == "Вася П."
        assert (await session.get(User, 2)).label == "По Айди"
