"""Оркестрация жизненного цикла матча: синхронизация, открытие/закрытие
голосования, резолв результата и начисление очков.

Эти функции вызываются и планировщиком (по расписанию), и дев-командами
(вручную) — поэтому принимают bot/session/settings/provider явно.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.db.models import Choice, Match, MatchStatus
from bot.keyboards.vote import build_vote_keyboard
from bot.services import presentation
from bot.services.football.base import MatchProvider
from bot.services.scoring import points_for

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------- синхронизация расписания ------------------------
async def sync_fixtures(session: AsyncSession, provider: MatchProvider) -> int:
    fixtures = await provider.fixtures()
    for f in fixtures:
        await repo.upsert_match(
            session,
            provider_match_id=f.provider_match_id,
            home_team=f.home_team,
            away_team=f.away_team,
            home_code=f.home_code,
            away_code=f.away_code,
            kickoff_utc=f.kickoff_utc,
            stage=f.stage,
            status=f.status,
            home_score=f.home_score,
            away_score=f.away_score,
        )
    await session.commit()
    return len(fixtures)


# --------------------------- открытие голосования ----------------------------
async def open_votes(bot: Bot, session: AsyncSession, settings: Settings) -> int:
    window = settings.app.bot.vote_open_hours_before * 3600
    matches = await repo.list_matches_for_vote_opening(session, _now(), window)
    opened = 0
    for match in matches:
        if await _post_vote(bot, session, settings, match):
            opened += 1
    await session.commit()
    return opened


async def open_next(
    bot: Bot, session: AsyncSession, settings: Settings, count: int = 1
) -> int:
    """Открыть голосование по ближайшим `count` предстоящим матчам без активной
    голосовалки, ИГНОРИРУЯ окно vote_open_hours_before. Для дев-команды /devopen."""
    huge_window = 10**9  # секунд — фактически без ограничения окна
    matches = await repo.list_matches_for_vote_opening(session, _now(), huge_window)
    opened = 0
    for match in matches[:count]:
        if await _post_vote(bot, session, settings, match):
            opened += 1
    await session.commit()
    return opened


async def _post_vote(
    bot: Bot, session: AsyncSession, settings: Settings, match: Match
) -> bool:
    tz = settings.app.bot.display_timezone
    count = await repo.count_predictions(session, match.id)
    text = presentation.vote_message_text(match, tz, count)
    kb = build_vote_keyboard(match)
    posted = False
    for chat_id in settings.app.roles.allowed_chats:
        try:
            msg = await bot.send_message(chat_id, text, reply_markup=kb)
            await repo.add_vote_message(session, match.id, chat_id, msg.message_id)
            posted = True
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось открыть голосование в чате %s: %s", chat_id, exc)
    return posted


async def refresh_vote_message_counts(
    bot: Bot, session: AsyncSession, settings: Settings, match: Match
) -> None:
    """Обновить счётчик прогнозов в сообщениях голосовалки (после нового голоса)."""
    tz = settings.app.bot.display_timezone
    count = await repo.count_predictions(session, match.id)
    text = presentation.vote_message_text(match, tz, count)
    kb = build_vote_keyboard(match)
    for vm in await repo.get_vote_messages_for_match(session, match.id):
        try:
            await bot.edit_message_text(
                text, chat_id=vm.chat_id, message_id=vm.message_id, reply_markup=kb
            )
        except TelegramBadRequest:
            pass  # текст не изменился / сообщение недоступно — не критично


# --------------------------- закрытие голосования ----------------------------
async def close_votes(bot: Bot, session: AsyncSession, settings: Settings) -> int:
    matches = await repo.list_matches_to_close(session, _now())
    for match in matches:
        await _close_match(bot, session, settings, match)
    await session.commit()
    return len(matches)


async def _close_match(
    bot: Bot, session: AsyncSession, settings: Settings, match: Match
) -> None:
    if match.status == MatchStatus.SCHEDULED:
        match.status = MatchStatus.LIVE
    tz = settings.app.bot.display_timezone
    count = await repo.count_predictions(session, match.id)
    text = presentation.closed_message_text(match, tz, count)
    for vm in await repo.get_vote_messages_for_match(session, match.id):
        try:
            await bot.edit_message_text(
                text, chat_id=vm.chat_id, message_id=vm.message_id, reply_markup=None
            )
        except TelegramBadRequest:
            pass
    await repo.close_vote_messages_for_match(session, match.id)


# --------------------------- резолв результата -------------------------------
async def resolve_results(
    bot: Bot, session: AsyncSession, settings: Settings, provider: MatchProvider
) -> int:
    matches = await repo.list_started_unresolved(session, _now())
    resolved = 0
    for match in matches:
        result = await provider.result(match.provider_match_id)
        if result is None or result.status != MatchStatus.FINISHED:
            continue
        if result.outcome is None:
            continue
        await _finalize(bot, session, settings, match, result.home_score,
                        result.away_score, result.outcome)
        resolved += 1
    if resolved:
        await session.commit()
    return resolved


async def force_resolve(
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    match: Match,
    home_score: int,
    away_score: int,
    outcome: Choice,
) -> None:
    """Ручной резолв матча (дев-команда /devresult), минуя проверку kickoff."""
    await _finalize(bot, session, settings, match, home_score, away_score, outcome)
    await session.commit()


async def _finalize(
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    match: Match,
    home_score: int | None,
    away_score: int | None,
    outcome: Choice,
) -> None:
    """Зафиксировать результат, начислить очки, опубликовать итог. Используется и
    резолвером, и дев-командой /devresult."""
    match.home_score = home_score
    match.away_score = away_score
    match.outcome = outcome
    match.status = MatchStatus.FINISHED
    match.resolved = True

    # на всякий случай закрываем голосование, если ещё открыто
    await _close_match(bot, session, settings, match)

    predictions = await repo.list_predictions_for_match(session, match.id)
    winners: list[int] = []
    losers: list[int] = []
    for pred in predictions:
        pts = points_for(pred.choice, outcome, settings.app.scoring)
        pred.points_awarded = pts
        (winners if pts > 0 else losers).append(pred.user_tg_id)
    await session.flush()

    await _post_result(bot, session, settings, match, outcome, winners, losers)


async def _post_result(
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    match: Match,
    outcome: Choice,
    winner_ids: list[int],
    loser_ids: list[int],
) -> None:
    score = f"{match.home_score}:{match.away_score}"
    title = presentation.match_title(match)
    pts = settings.app.scoring.correct_outcome
    win_names = await _names(session, winner_ids)
    lose_names = await _names(session, loser_ids)
    lines = [
        "🏁 <b>Итог матча</b>",
        f"{title}",
        f"📊 Счёт: <b>{score}</b>",
        f"✅ {presentation.choice_label(match, outcome)}",
        "",
        f"Угадали (+{pts}): {', '.join(win_names) if win_names else '—'}",
        f"Не угадали: {', '.join(lose_names) if lose_names else '—'}",
    ]
    text = "\n".join(lines)
    for chat_id in settings.app.roles.allowed_chats:
        try:
            await bot.send_message(chat_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось отправить итог в чат %s: %s", chat_id, exc)


async def _names(session: AsyncSession, user_ids: list[int]) -> list[str]:
    from bot.db.models import User

    out: list[str] = []
    for uid in user_ids:
        user = await session.get(User, uid)
        if user is None:
            out.append(str(uid))
        elif user.username:
            out.append(f"@{user.username}")
        else:
            out.append(html.escape(user.display_name or str(uid)))
    return out
