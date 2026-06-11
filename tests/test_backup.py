import sqlite3

from bot.services.backup import make_backup


def _make_db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()


def test_backup_creates_consistent_copy(tmp_path):
    db = tmp_path / "predicup.sqlite3"
    _make_db(db)
    dst = make_backup(str(db), keep=14)
    assert dst is not None and dst.exists()
    con = sqlite3.connect(dst)
    assert con.execute("SELECT x FROM t").fetchone()[0] == 42
    con.close()


def test_backup_skips_when_no_db(tmp_path):
    assert make_backup(str(tmp_path / "nope.sqlite3"), keep=14) is None


def test_backup_prunes_old(tmp_path):
    db = tmp_path / "predicup.sqlite3"
    _make_db(db)
    backups = tmp_path / "backups"
    backups.mkdir()
    # старые «бэкапы», которых больше лимита
    for i in range(5):
        (backups / f"predicup-2026010{i}-000000.sqlite3").write_text("x")
    make_backup(str(db), keep=2)
    files = sorted(backups.glob("predicup-*.sqlite3"))
    assert len(files) == 2  # обрезано до keep
