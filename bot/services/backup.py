"""Резервное копирование базы SQLite.

Используем онлайн-бэкап SQLite (`Connection.backup`) — он делает консистентную
копию даже при активной работе бота, в отличие от простого копирования файла.
Копии складываются в <папка_БД>/backups, хранится последние `keep` штук.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def make_backup(db_path: str, keep: int) -> Path | None:
    src = Path(db_path)
    if not src.exists():
        logger.warning("Бэкап пропущен: файла БД ещё нет (%s)", src)
        return None
    backups_dir = src.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = backups_dir / f"{src.stem}-{ts}.sqlite3"
    with sqlite3.connect(src) as source, sqlite3.connect(dst) as target:
        source.backup(target)
    _prune(backups_dir, src.stem, keep)
    logger.info("Бэкап БД создан: %s", dst.name)
    return dst


def _prune(backups_dir: Path, stem: str, keep: int) -> None:
    if keep <= 0:
        return
    files = sorted(backups_dir.glob(f"{stem}-*.sqlite3"))
    for old in files[:-keep]:
        try:
            old.unlink()
        except OSError:
            logger.warning("Не удалось удалить старый бэкап: %s", old)
