"""CRUD-хелперы. Каждая функция принимает активную AsyncSession.

Коммит делает вызывающая сторона (или контекст-менеджер сессии), чтобы можно
было собирать несколько операций в одну транзакцию.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Choice,
    Match,
    MatchStatus,
    Prediction,
    User,
    VoteMessage,
    VoteStatus,
    utcnow,
)


# ----------------------------- Users -----------------------------------------
async def get_or_create_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None = None,
    display_name: str | None = None,
) -> User:
    user = await session.get(User, tg_id)
    if user is None:
        user = User(tg_id=tg_id, username=username, display_name=display_name)
        session.add(user)
        await session.flush()
    else:
        # держим профиль в актуальном состоянии
        if username is not None:
            user.username = username
        if display_name is not None:
            user.display_name = display_name
    return user


# ----------------------------- Matches ---------------------------------------
async def get_match(session: AsyncSession, match_id: int) -> Match | None:
    return await session.get(Match, match_id)


async def get_match_by_provider_id(
    session: AsyncSession, provider_match_id: str
) -> Match | None:
    res = await session.execute(
        select(Match).where(Match.provider_match_id == provider_match_id)
    )
    return res.scalar_one_or_none()


async def upsert_match(
    session: AsyncSession,
    *,
    provider_match_id: str,
    home_team: str,
    away_team: str,
    home_code: str,
    away_code: str,
    kickoff_utc: datetime,
    stage: str = "group",
    status: MatchStatus = MatchStatus.SCHEDULED,
    home_score: int | None = None,
    away_score: int | None = None,
) -> Match:
    match = await get_match_by_provider_id(session, provider_match_id)
    if match is None:
        match = Match(provider_match_id=provider_match_id)
        session.add(match)
    match.home_team = home_team
    match.away_team = away_team
    match.home_code = home_code
    match.away_code = away_code
    match.kickoff_utc = kickoff_utc
    match.stage = stage
    # не перетираем статус/счёт уже завершённого, если провайдер вернул меньше данных
    if not match.resolved:
        match.status = status
        if home_score is not None:
            match.home_score = home_score
        if away_score is not None:
            match.away_score = away_score
    await session.flush()
    return match


async def list_matches_for_vote_opening(
    session: AsyncSession, now: datetime, open_before_seconds: float
) -> list[Match]:
    """Матчи, для которых пора открыть голосование: kickoff в окне [now, now+window],
    ещё не стартовали и не имеют активной голосовалки."""
    horizon = _add_seconds(now, open_before_seconds)
    res = await session.execute(
        select(Match)
        .where(
            Match.status == MatchStatus.SCHEDULED,
            Match.kickoff_utc > now,
            Match.kickoff_utc <= horizon,
        )
        .order_by(Match.kickoff_utc)
    )
    matches = list(res.scalars().all())
    out: list[Match] = []
    for m in matches:
        if not await has_open_vote_message(session, m.id):
            out.append(m)
    return out


async def list_matches_to_close(session: AsyncSession, now: datetime) -> list[Match]:
    """Матчи, которые уже стартовали, но всё ещё имеют открытую голосовалку."""
    res = await session.execute(
        select(Match)
        .join(VoteMessage, VoteMessage.match_id == Match.id)
        .where(Match.kickoff_utc <= now, VoteMessage.status == VoteStatus.OPEN)
        .distinct()
    )
    return list(res.scalars().all())


async def list_finished_unresolved(session: AsyncSession) -> list[Match]:
    res = await session.execute(
        select(Match).where(
            Match.status == MatchStatus.FINISHED, Match.resolved.is_(False)
        )
    )
    return list(res.scalars().all())


async def get_latest_unresolved_match(session: AsyncSession) -> Match | None:
    """Последний добавленный незавершённый матч — удобно для дев-команд."""
    res = await session.execute(
        select(Match).where(Match.resolved.is_(False)).order_by(Match.id.desc())
    )
    return res.scalars().first()


async def get_latest_voted_unresolved_match(session: AsyncSession) -> Match | None:
    """Незавершённый матч с самой свежей голосовалкой — то, что сейчас тестируют.
    Если таких нет, откатываемся к последнему незавершённому матчу."""
    res = await session.execute(
        select(Match)
        .join(VoteMessage, VoteMessage.match_id == Match.id)
        .where(Match.resolved.is_(False))
        .order_by(VoteMessage.id.desc())
    )
    match = res.scalars().first()
    if match is not None:
        return match
    return await get_latest_unresolved_match(session)


async def list_started_unresolved(session: AsyncSession, now: datetime) -> list[Match]:
    """Матчи, которые уже должны были начаться, но ещё не зарезолвлены —
    кандидаты на проверку результата у провайдера."""
    res = await session.execute(
        select(Match)
        .where(Match.kickoff_utc <= now, Match.resolved.is_(False))
        .order_by(Match.kickoff_utc)
    )
    return list(res.scalars().all())


async def list_open_matches_with_messages(
    session: AsyncSession, now: datetime
) -> list[tuple[Match, VoteMessage]]:
    """Матчи с открытым голосованием (kickoff ещё не наступил) + их сообщение.
    Используется командой /matches."""
    res = await session.execute(
        select(Match, VoteMessage)
        .join(VoteMessage, VoteMessage.match_id == Match.id)
        .where(VoteMessage.status == VoteStatus.OPEN, Match.kickoff_utc > now)
        .order_by(Match.kickoff_utc)
    )
    return [(row[0], row[1]) for row in res.all()]


# ----------------------------- Predictions -----------------------------------
async def get_prediction(
    session: AsyncSession, match_id: int, user_tg_id: int
) -> Prediction | None:
    res = await session.execute(
        select(Prediction).where(
            Prediction.match_id == match_id, Prediction.user_tg_id == user_tg_id
        )
    )
    return res.scalar_one_or_none()


async def upsert_prediction(
    session: AsyncSession, match_id: int, user_tg_id: int, choice: Choice
) -> Prediction:
    """Создать или обновить прогноз атомарно (INSERT ... ON CONFLICT DO UPDATE).

    Атомарность защищает от гонки при двойном/быстром нажатии: раньше два
    одновременных запроса оба видели «прогноза нет» и оба пытались вставить —
    второй падал с UNIQUE constraint. Теперь конфликт по (match_id, user_tg_id)
    просто обновляет выбор.
    """
    choice_val = choice.value if isinstance(choice, Choice) else str(choice)
    stmt = (
        sqlite_insert(Prediction)
        .values(match_id=match_id, user_tg_id=user_tg_id, choice=choice_val)
        .on_conflict_do_update(
            index_elements=["match_id", "user_tg_id"],
            set_={"choice": choice_val, "updated_at": utcnow()},
        )
    )
    await session.execute(stmt)
    await session.flush()
    pred = await get_prediction(session, match_id, user_tg_id)
    assert pred is not None
    return pred


async def count_predictions(session: AsyncSession, match_id: int) -> int:
    res = await session.execute(
        select(func.count()).select_from(Prediction).where(
            Prediction.match_id == match_id
        )
    )
    return int(res.scalar_one())


async def list_predictions_for_match(
    session: AsyncSession, match_id: int
) -> list[Prediction]:
    res = await session.execute(
        select(Prediction).where(Prediction.match_id == match_id)
    )
    return list(res.scalars().all())


# ----------------------------- Vote messages ---------------------------------
async def add_vote_message(
    session: AsyncSession, match_id: int, chat_id: int, message_id: int
) -> VoteMessage:
    vm = VoteMessage(match_id=match_id, chat_id=chat_id, message_id=message_id)
    session.add(vm)
    await session.flush()
    return vm


async def has_open_vote_message(session: AsyncSession, match_id: int) -> bool:
    res = await session.execute(
        select(func.count())
        .select_from(VoteMessage)
        .where(
            VoteMessage.match_id == match_id,
            VoteMessage.status == VoteStatus.OPEN,
        )
    )
    return int(res.scalar_one()) > 0


async def get_vote_messages_for_match(
    session: AsyncSession, match_id: int
) -> list[VoteMessage]:
    res = await session.execute(
        select(VoteMessage).where(VoteMessage.match_id == match_id)
    )
    return list(res.scalars().all())


async def close_vote_messages_for_match(session: AsyncSession, match_id: int) -> None:
    for vm in await get_vote_messages_for_match(session, match_id):
        vm.status = VoteStatus.CLOSED


# ----------------------------- Leaderboard -----------------------------------
async def clear_matches_and_predictions(session: AsyncSession) -> None:
    """Удалить все матчи, прогнозы и сообщения-голосовалки (для дев-сброса).
    Пользователи остаются."""
    from sqlalchemy import delete

    await session.execute(delete(VoteMessage))
    await session.execute(delete(Prediction))
    await session.execute(delete(Match))


async def leaderboard(session: AsyncSession) -> list[tuple[User, int]]:
    """Список (User, сумма очков) по убыванию очков. Только участники, сделавшие
    хотя бы один прогноз (inner join), — даже если очков пока 0."""
    pts = func.coalesce(func.sum(Prediction.points_awarded), 0)
    res = await session.execute(
        select(User, pts.label("pts"))
        .join(Prediction, Prediction.user_tg_id == User.tg_id)
        .group_by(User.tg_id)
        .order_by(pts.desc(), func.count(Prediction.id).desc(), User.tg_id)
    )
    return [(row[0], int(row[1])) for row in res.all()]


def _add_seconds(dt: datetime, seconds: float) -> datetime:
    from datetime import timedelta

    return dt + timedelta(seconds=seconds)
