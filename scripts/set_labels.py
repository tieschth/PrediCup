"""Импортировать отображаемые имена (label) из CSV/текста.

Формат файла — по строке на участника, разделитель «;» или «,» или табуляция:
    идентификатор<разд>метка
где идентификатор — это @username, username или tg_id. Пример:
    @vaskaaaak;Вася Пупкин
    475130843;Михаил К.
Строки, начинающиеся с #, и пустые — игнорируются.

Запуск (в Docker), файл положить в ./data (он виден контейнеру как /app/data):
    docker compose exec bot python scripts/set_labels.py data/labels.csv
"""
from __future__ import annotations

import os
import sqlite3
import sys


def _split(line: str) -> tuple[str, str] | None:
    for sep in (";", "\t", ","):
        if sep in line:
            ident, label = line.split(sep, 1)
            ident, label = ident.strip(), label.strip()
            if ident and label:
                return ident, label
            return None
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python scripts/set_labels.py <файл>")
        return
    src = sys.argv[1]
    if not os.path.exists(src):
        print(f"Файл не найден: {src}")
        return
    path = os.environ.get("DB_PATH", "data/predicup.sqlite3")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row

    updated, missing = 0, []
    with open(src, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parsed = _split(line)
            if not parsed:
                print(f"Пропуск (не разобрано): {line!r}")
                continue
            ident, label = parsed
            if ident.lstrip("@").isdigit():
                row = con.execute(
                    "SELECT tg_id FROM users WHERE tg_id=?", (int(ident.lstrip("@")),)
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT tg_id FROM users WHERE lower(username)=lower(?)",
                    (ident.lstrip("@"),),
                ).fetchone()
            if row is None:
                missing.append(ident)
                continue
            con.execute("UPDATE users SET label=? WHERE tg_id=?", (label, row["tg_id"]))
            updated += 1

    con.commit()
    con.close()
    print(f"Обновлено меток: {updated}")
    if missing:
        print("Не найдены пользователи:", ", ".join(missing))


if __name__ == "__main__":
    main()
