"""ORM-модели SQLAlchemy 2.x.

Схема намеренно расширяема: для угадывания точного счёта в Prediction добавятся
поля predicted_home/away, для плей-офф в Match — after_extra_time/penalties.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Хранит datetime в UTC и всегда отдаёт его как timezone-aware.

    SQLite не сохраняет tzinfo, из-за чего «голые» даты при чтении нельзя
    сравнивать с aware-датами. Этот тип нормализует значения на входе (→ UTC) и
    проставляет UTC на выходе.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Choice(str, enum.Enum):
    """Выбор участника / исход матча (групповой этап: П1 / Х / П2)."""

    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


class PlayoffChoice(str, enum.Enum):
    """Варианты голосования на плей-офф (7 исходов).

    R_* — в основное время; ET_* — в дополнительное; PEN_* — по пенальти.
    R_DRAW — ничья в основное время (матч пошёл в доп.время/пенальти).
    """

    R_HOME = "R_HOME"
    R_AWAY = "R_AWAY"
    R_DRAW = "R_DRAW"
    ET_HOME = "ET_HOME"
    ET_AWAY = "ET_AWAY"
    PEN_HOME = "PEN_HOME"
    PEN_AWAY = "PEN_AWAY"


# Стадии плей-офф (по названиям football-data.org). Всё остальное — групповой этап.
PLAYOFF_STAGES = frozenset(
    {"LAST_32", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "THIRD_PLACE", "FINAL"}
)


class MatchDuration(str, enum.Enum):
    REGULAR = "REGULAR"
    EXTRA_TIME = "EXTRA_TIME"
    PENALTY_SHOOTOUT = "PENALTY_SHOOTOUT"


class MatchStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"


class VoteStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Заданное вручную отображаемое имя (приоритет в таблице/итогах над username).
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Ручная корректировка очков (бонусы/штрафы), суммируется в таблице лидеров.
    bonus_points: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_match_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="group")
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    home_code: Mapped[str] = mapped_column(String(8))
    away_code: Mapped[str] = mapped_column(String(8))
    kickoff_utc: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[MatchStatus] = mapped_column(
        String(16), default=MatchStatus.SCHEDULED
    )
    # fullTime — итоговый счёт (включая доп.время). penalties — серия пенальти.
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[str] = mapped_column(String(20), default=MatchDuration.REGULAR.value)
    pen_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pen_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(12), nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False)

    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    vote_messages: Mapped[list["VoteMessage"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )

    @property
    def is_playoff(self) -> bool:
        return self.stage.upper() in PLAYOFF_STAGES

    @property
    def teams_known(self) -> bool:
        """Команды определены (не плейсхолдеры плей-офф вроде TBD)."""
        bad = {"", "TBD", "NONE"}
        return (
            (self.home_team or "").strip().upper() not in bad
            and (self.away_team or "").strip().upper() not in bad
        )


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("match_id", "user_tg_id", name="uq_prediction_match_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    user_tg_id: Mapped[int] = mapped_column(ForeignKey("users.tg_id"), index=True)
    choice: Mapped[Choice] = mapped_column(String(8))
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow
    )

    match: Mapped["Match"] = relationship(back_populates="predictions")


class VoteMessage(Base):
    """Сообщение-голосовалка в чате (одно на матч на чат)."""

    __tablename__ = "vote_messages"
    __table_args__ = (
        UniqueConstraint("match_id", "chat_id", name="uq_votemsg_match_chat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[VoteStatus] = mapped_column(String(16), default=VoteStatus.OPEN)

    match: Mapped["Match"] = relationship(back_populates="vote_messages")
