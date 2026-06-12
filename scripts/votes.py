"""Показать прогнозы игроков с человекочитаемым выбором.

Запуск (в Docker):
    docker compose exec bot python scripts/votes.py            # все прогнозы
    docker compose exec bot python scripts/votes.py kuz9sh     # только @kuz9sh
"""
from __future__ import annotations

import os
import sqlite3
import sys

_CHOICE = {"HOME": "победа 1-й", "AWAY": "победа 2-й", "DRAW": "ничья"}


def main() -> None:
    username = sys.argv[1].lstrip("@") if len(sys.argv) > 1 else None
    path = os.environ.get("DB_PATH", "data/predicup.sqlite3")
    if not os.path.exists(path):
        print(f"Файл БД не найден: {path}")
        sys.exit(1)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row

    sql = (
        "SELECT u.username, m.id AS mid, m.home_team, m.away_team, m.kickoff_utc, "
        "p.choice, p.points_awarded "
        "FROM predictions p "
        "JOIN users u ON u.tg_id = p.user_tg_id "
        "JOIN matches m ON m.id = p.match_id "
    )
    params: tuple = ()
    if username:
        sql += "WHERE u.username = ? "
        params = (username,)
    sql += "ORDER BY m.kickoff_utc, u.username"

    rows = con.execute(sql, params).fetchall()
    if not rows:
        print("Прогнозов не найдено" + (f" для @{username}" if username else ""))
        return

    title = f"Прогнозы @{username}" if username else "Все прогнозы"
    print(f"=== {title} ===")
    for r in rows:
        pick = _CHOICE.get(r["choice"], r["choice"])
        who = f"@{r['username']}" if r["username"] else "—"
        prefix = "" if username else f"{who}: "
        print(
            f"  {prefix}матч #{r['mid']} {r['home_team']} vs {r['away_team']} "
            f"→ {pick} ({r['choice']}), +{r['points_awarded']}"
        )
    con.close()


if __name__ == "__main__":
    main()
