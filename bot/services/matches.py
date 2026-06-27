"""Оркестрация жизненного цикла матча: синхронизация, открытие/закрытие
голосования, резолв результата и начисление очков.

Эти функции вызываются и планировщиком (по расписанию), и дев-командами
(вручную) — поэтому принимают bot/session/settings/provider явно.
"""
from __future__ import annotations

import html
import logging
import time
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.db.models import Choice, Match, MatchDuration, MatchStatus, User
from bot.keyboards.vote import build_vote_keyboard
from bot.services import presentation
from bot.services.football.base import MatchProvider, ResultDTO
from bot.services.scoring import winning_choices

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
            duration=f.duration,
            pen_home=f.pen_home,
            pen_away=f.pen_away,
        )
    await session.commit()
    return len(fixtures)


# --------------------------- открытие голосования ----------------------------
async def open_votes(bot: Bot, session: AsyncSession, settings: Settings) -> int:
    window = settings.app.scheduler.open_window_hours * 3600
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
    голосовалки, ИГНОРИРУЯ окно open_window_hours. Для дев-команды /devopen."""
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
            logger.info(
                "Открыто голосование: матч #%s %s vs %s (чат %s)",
                match.id, match.home_team, match.away_team, chat_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось открыть голосование в чате %s: %s", chat_id, exc)
    return posted


# Не правим счётчик чаще, чем раз в N секунд на матч — иначе при частых голосах
# Telegram включает flood control (RetryAfter). Счётчик может слегка отставать.
_EDIT_MIN_INTERVAL = 20.0
_last_count_edit: dict[int, float] = {}


async def refresh_vote_message_counts(
    bot: Bot, session: AsyncSession, settings: Settings, match: Match
) -> None:
    """Обновить счётчик прогнозов в сообщениях голосовалки (после нового голоса).

    Best-effort: при flood control или иной ошибке просто пропускаем — голос уже
    сохранён, а актуальный счётчик подтянется при следующем обновлении/закрытии.
    """
    now = time.monotonic()
    if now - _last_count_edit.get(match.id, 0.0) < _EDIT_MIN_INTERVAL:
        return
    _last_count_edit[match.id] = now

    tz = settings.app.bot.display_timezone
    count = await repo.count_predictions(session, match.id)
    text = presentation.vote_message_text(match, tz, count)
    kb = build_vote_keyboard(match)
    for vm in await repo.get_vote_messages_for_match(session, match.id):
        try:
            await bot.edit_message_text(
                text, chat_id=vm.chat_id, message_id=vm.message_id, reply_markup=kb
            )
        except (TelegramBadRequest, TelegramRetryAfter):
            pass  # не изменилось / недоступно / лимит — не критично
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось обновить счётчик матча %s: %s", match.id, exc)


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
        except (TelegramBadRequest, TelegramRetryAfter):
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось закрыть голосовалку матча %s: %s", match.id, exc)
    await repo.close_vote_messages_for_match(session, match.id)


# --------------------------- резолв результата -------------------------------
def _result_changed(match: Match, r: ResultDTO) -> bool:
    return (
        match.home_score != r.home_score
        or match.away_score != r.away_score
        or (match.duration or MatchDuration.REGULAR.value) != r.duration
        or match.pen_home != r.pen_home
        or match.pen_away != r.pen_away
    )


def _apply_result_fields(match: Match, r: ResultDTO) -> None:
    match.home_score = r.home_score
    match.away_score = r.away_score
    match.duration = r.duration
    match.pen_home = r.pen_home
    match.pen_away = r.pen_away
    match.status = MatchStatus.FINISHED


def _score_predictions(match: Match, predictions, scoring) -> dict[int, int]:
    """Проставить очки прогнозам по текущему результату. Возвращает {pred_id: очки}."""
    wins = winning_choices(match, scoring)
    new_points: dict[int, int] = {}
    for pred in predictions:
        pts = wins.get(str(pred.choice), 0)
        pred.points_awarded = pts
        new_points[pred.id] = pts
    return new_points


async def resolve_results(
    bot: Bot, session: AsyncSession, settings: Settings, provider: MatchProvider
) -> int:
    matches = await repo.list_started_unresolved(session, _now())
    resolved = 0
    for match in matches:
        result = await provider.result(match.provider_match_id)
        if result is None or result.status != MatchStatus.FINISHED:
            continue
        if result.home_score is None or result.away_score is None:
            continue
        _apply_result_fields(match, result)
        await _finalize(bot, session, settings, match)
        resolved += 1
    if resolved:
        await session.commit()
    return resolved


async def reverify_results(
    bot: Bot, session: AsyncSession, settings: Settings, provider: MatchProvider
) -> int:
    """Повторно сверить недавно завершённые матчи с API: если счёт/исход
    скорректирован (отменённые голы и т.п.) — обновить и пересчитать очки, при
    изменении баллов опубликовать поправку в чат."""
    window_h = settings.app.scheduler.reverify_window_hours
    since = _now() - timedelta(hours=window_h)
    matches = await repo.list_resolved_in_window(session, since)
    changed = 0
    for match in matches:
        result = await provider.result(match.provider_match_id)
        if result is None or result.status != MatchStatus.FINISHED:
            continue
        if result.home_score is None or result.away_score is None:
            continue
        if not _result_changed(match, result):
            continue

        predictions = await repo.list_predictions_for_match(session, match.id)
        old_points = {p.id: p.points_awarded for p in predictions}
        old_score = f"{match.home_score}:{match.away_score}"

        _apply_result_fields(match, result)
        new_points = _score_predictions(match, predictions, settings.app.scoring)
        await session.flush()
        changed += 1

        points_changed = new_points != old_points
        logger.info(
            "Перепроверка: матч #%s обновлён %s -> %s:%s (duration=%s), очки %s",
            match.id, old_score, match.home_score, match.away_score,
            match.duration, "пересчитаны" if points_changed else "без изменений",
        )
        if points_changed:
            await _post_correction(bot, session, settings, match, old_score)
    if changed:
        await session.commit()
    return changed


async def force_resolve(
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    match: Match,
    home_score: int,
    away_score: int,
    duration: str = MatchDuration.REGULAR.value,
    pen_home: int | None = None,
    pen_away: int | None = None,
) -> None:
    """Ручной резолв матча (дев-команда /devresult), минуя проверку kickoff."""
    _apply_result_fields(
        match,
        ResultDTO(
            provider_match_id=match.provider_match_id,
            status=MatchStatus.FINISHED,
            home_score=home_score,
            away_score=away_score,
            duration=duration,
            pen_home=pen_home,
            pen_away=pen_away,
        ),
    )
    await _finalize(bot, session, settings, match)
    await session.commit()


async def _finalize(
    bot: Bot, session: AsyncSession, settings: Settings, match: Match
) -> None:
    """Начислить очки по текущему результату матча и опубликовать итог."""
    match.resolved = True
    await _close_match(bot, session, settings, match)

    predictions = await repo.list_predictions_for_match(session, match.id)
    new_points = _score_predictions(match, predictions, settings.app.scoring)
    winners = sum(1 for v in new_points.values() if v > 0)
    await session.flush()

    logger.info(
        "Матч #%s %s %s завершён (%s), угадали %s из %s",
        match.id, match.home_team, match.away_team,
        _score_line(match), winners, len(predictions),
    )
    await _post_result(bot, session, settings, match)


def _score_line(match: Match) -> str:
    """Человекочитаемый счёт с учётом доп.времени/пенальти."""
    base = f"{match.home_score}:{match.away_score}"
    dur = (match.duration or MatchDuration.REGULAR.value).upper()
    if dur == MatchDuration.EXTRA_TIME.value:
        return f"{base} (доп. время)"
    if dur == MatchDuration.PENALTY_SHOOTOUT.value:
        pens = ""
        if match.pen_home is not None and match.pen_away is not None:
            pens = f", пенальти {match.pen_home}:{match.pen_away}"
        return f"{base} (осн.+доп.){pens}"
    return base


async def _winners_block(session: AsyncSession, match: Match, settings: Settings) -> str:
    """Список угадавших, сгруппированный по варианту (для плей-офф — с баллами)."""
    wins = winning_choices(match, settings.app.scoring)
    if not wins:
        return "Угадавших нет."
    predictions = await repo.list_predictions_for_match(session, match.id)
    lines: list[str] = []
    # порядок отображения вариантов стабильный: по убыванию очков, затем по коду
    for code, pts in sorted(wins.items(), key=lambda kv: (-kv[1], kv[0])):
        uids = [p.user_tg_id for p in predictions if str(p.choice) == code]
        names = await _names(session, uids)
        label = presentation.choice_label(match, code)
        who = ", ".join(names) if names else "—"
        lines.append(f"✅ {label} (+{pts}): {who}")
    return "\n".join(lines)


async def _post_result(
    bot: Bot, session: AsyncSession, settings: Settings, match: Match
) -> None:
    block = await _winners_block(session, match, settings)
    text = (
        "🏁 <b>Итог матча</b>\n"
        f"{presentation.match_title(match)}\n"
        f"📊 Счёт: <b>{_score_line(match)}</b>\n\n"
        f"{block}"
    )
    await _broadcast(bot, settings, text)


async def _post_correction(
    bot: Bot, session: AsyncSession, settings: Settings, match: Match, old_score: str
) -> None:
    block = await _winners_block(session, match, settings)
    text = (
        "✏️ <b>Результат матча уточнён</b>\n"
        f"{presentation.match_title(match)}\n"
        f"Было: {old_score} → стало: <b>{_score_line(match)}</b>\n"
        "Очки пересчитаны.\n\n"
        f"{block}"
    )
    await _broadcast(bot, settings, text)


async def _broadcast(bot: Bot, settings: Settings, text: str) -> None:
    for chat_id in settings.app.roles.allowed_chats:
        try:
            await bot.send_message(chat_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось отправить сообщение в чат %s: %s", chat_id, exc)


async def _names(session: AsyncSession, user_ids: list[int]) -> list[str]:
    out: list[str] = []
    for uid in user_ids:
        user = await session.get(User, uid)
        out.append(presentation.display_name(user) if user else str(uid))
    return out
