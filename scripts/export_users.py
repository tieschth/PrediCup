"""Выгрузить список участников: username | имя из ТГ | текущая метка | очки.

Печатает таблицу и сохраняет CSV в data/users_export.csv — этот файл удобно
передать человеку, который проставит «правильные» отображаемые имена.

Запуск (в Docker):
    docker compose exec bot python scripts/export_users.py
"""
from __future__ import annotations

import csv
import os
import sqlite3


def main() -> None:
    path = os.environ.get("DB_PATH", "data/predicup.sqlite3")
    if not os.path.exists(path):
        print(f"Файл БД не найден: {path}")
        return
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT u.tg_id, u.username, u.display_name, u.label,
               COALESCE(SUM(p.points_awarded), 0) + COALESCE(u.bonus_points, 0) AS total
        FROM users u
        LEFT JOIN predictions p ON p.user_tg_id = u.tg_id
        GROUP BY u.tg_id
        ORDER BY total DESC, u.tg_id
        """
    ).fetchall()
    con.close()

    out_csv = os.path.join(os.path.dirname(path), "users_export.csv")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["tg_id", "username", "tg_name", "label", "points"])
        for r in rows:
            w.writerow([r["tg_id"], r["username"] or "", r["display_name"] or "",
                        r["label"] or "", r["total"]])

    print(f"{'tg_id':<12} {'username':<20} {'имя в ТГ':<22} {'метка':<16} очки")
    print("-" * 78)
    for r in rows:
        print(
            f"{r['tg_id']:<12} {('@'+r['username']) if r['username'] else '':<20} "
            f"{(r['display_name'] or ''):<22} {(r['label'] or ''):<16} {r['total']}"
        )
    print(f"\nCSV сохранён: {out_csv}")


if __name__ == "__main__":
    main()
