"""Показать содержимое БД: пользователи, матчи, прогнозы, таблица очков.

Запуск (из корня проекта, в активированном venv):
    python scripts/inspect_db.py
    python scripts/inspect_db.py path\to\predicup.sqlite3
"""
from __future__ import annotations

import os
import sqlite3
import sys


def _db_path() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("DB_PATH", "data/predicup.sqlite3")


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    path = _db_path()
    if not os.path.exists(path):
        print(f"Файл БД не найден: {path}")
        sys.exit(1)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row

    _section("Пользователи")
    for r in con.execute("SELECT tg_id, username, display_name FROM users"):
        print(f"  {r['tg_id']}  @{r['username']}  {r['display_name']}")

    _section("Матчи")
    for r in con.execute(
        "SELECT id, home_team, away_team, kickoff_utc, status, "
        "home_score, away_score, outcome, resolved FROM matches ORDER BY id"
    ):
        score = (
            f"{r['home_score']}:{r['away_score']}"
            if r["home_score"] is not None
            else "—"
        )
        print(
            f"  #{r['id']} {r['home_team']} vs {r['away_team']} | "
            f"старт {r['kickoff_utc']} | {r['status']} | счёт {score} | "
            f"исход {r['outcome']} | resolved={bool(r['resolved'])}"
        )

    _section("Прогнозы")
    for r in con.execute(
        "SELECT p.match_id, p.user_tg_id, p.choice, p.points_awarded, "
        "u.username FROM predictions p LEFT JOIN users u ON u.tg_id = p.user_tg_id "
        "ORDER BY p.match_id, p.user_tg_id"
    ):
        print(
            f"  матч #{r['match_id']}  @{r['username']} ({r['user_tg_id']})  "
            f"-> {r['choice']}  (+{r['points_awarded']})"
        )

    _section("Таблица очков")
    rows = con.execute(
        "SELECT u.tg_id, u.username, "
        "COALESCE(SUM(p.points_awarded), 0) AS pts "
        "FROM users u LEFT JOIN predictions p ON p.user_tg_id = u.tg_id "
        "GROUP BY u.tg_id ORDER BY pts DESC"
    ).fetchall()
    for i, r in enumerate(rows, 1):
        print(f"  {i}. @{r['username']} ({r['tg_id']}) — {r['pts']}")

    con.close()


if __name__ == "__main__":
    main()
