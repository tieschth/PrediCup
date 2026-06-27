"""Ручная корректировка очков участнику (бонус/штраф).

Очки складываются с заработанными за прогнозы и попадают в таблицу лидеров.

Запуск (в Docker):
    docker compose exec bot python scripts/adjust_points.py @vaskaaaak +1
    docker compose exec bot python scripts/adjust_points.py 475130843 -2
"""
from __future__ import annotations

import os
import sqlite3
import sys


def main() -> None:
    if len(sys.argv) < 3:
        print("Использование: python scripts/adjust_points.py <@username|tg_id> <±N>")
        return
    ident, delta_raw = sys.argv[1], sys.argv[2]
    try:
        delta = int(delta_raw)
    except ValueError:
        print("Δ должно быть целым числом, например +1 или -2")
        return

    path = os.environ.get("DB_PATH", "data/predicup.sqlite3")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row

    if ident.lstrip("@").isdigit():
        row = con.execute(
            "SELECT tg_id, username, bonus_points FROM users WHERE tg_id=?",
            (int(ident.lstrip("@")),),
        ).fetchone()
    else:
        row = con.execute(
            "SELECT tg_id, username, bonus_points FROM users WHERE lower(username)=lower(?)",
            (ident.lstrip("@"),),
        ).fetchone()

    if row is None:
        print(f"Пользователь не найден: {ident}")
        con.close()
        return

    new_bonus = (row["bonus_points"] or 0) + delta
    con.execute("UPDATE users SET bonus_points=? WHERE tg_id=?", (new_bonus, row["tg_id"]))
    con.commit()
    con.close()
    print(
        f"@{row['username']} (id={row['tg_id']}): бонус {row['bonus_points'] or 0} "
        f"-> {new_bonus} (Δ {delta:+d})"
    )


if __name__ == "__main__":
    main()
