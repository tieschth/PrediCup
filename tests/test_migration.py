"""Миграция живой БД: _ensure_schema доливает новые колонки в существующие
таблицы без потери данных."""
import sqlite3

from sqlalchemy import create_engine

from bot.db.session import _ensure_schema


def test_ensure_schema_adds_missing_columns(tmp_path):
    db = tmp_path / "old.sqlite3"
    raw = sqlite3.connect(db)
    # «старые» таблицы без новых колонок
    raw.execute("CREATE TABLE users (tg_id INTEGER PRIMARY KEY, username TEXT)")
    raw.execute("INSERT INTO users (tg_id, username) VALUES (1, 'a')")
    raw.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY, home_score INTEGER)")
    raw.execute("INSERT INTO matches (id, home_score) VALUES (1, 2)")
    raw.commit()
    raw.close()

    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        _ensure_schema(conn)
        _ensure_schema(conn)  # идемпотентность — повторный вызов не падает
    engine.dispose()

    con = sqlite3.connect(db)
    ucols = {r[1] for r in con.execute("PRAGMA table_info(users)")}
    mcols = {r[1] for r in con.execute("PRAGMA table_info(matches)")}
    assert {"label", "bonus_points"} <= ucols
    assert {"duration", "pen_home", "pen_away"} <= mcols
    # данные на месте, дефолты проставлены
    assert con.execute("SELECT username, bonus_points FROM users WHERE tg_id=1").fetchone() == ("a", 0)
    assert con.execute("SELECT duration FROM matches WHERE id=1").fetchone()[0] == "REGULAR"
    con.close()
