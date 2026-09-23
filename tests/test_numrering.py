"""Tests for voucher numbering (docs/redesign/SPEC-flode-verifikationer.md §4).

Grows across tasks F1–F3 of `tasks/flode-verifikationer/todo.md`. Test case
numbers refer to the table in SPEC §14.1.

F1 (cases 1–4) is migration 027: `vouchers` is rebuilt so that `number` is
nullable, a draft has no number and a posted voucher always has one. Each case
builds a database at schema version 26 — the shape production has today, with
numbered drafts — and then runs 027 through the real runner,
`Database.init_db`, so that the `PRAGMA foreign_keys` handling is exercised the
way it runs at startup.
"""

import glob
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

from db.database import db

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"

# 014's trigger bodies as SQLite stores them (the `CREATE TRIGGER` statement
# without `IF NOT EXISTS` and the trailing semicolon). 027 must re-create them
# verbatim.
TRIGGERS_014 = {
    "prevent_update_posted_vouchers": (
        "CREATE TRIGGER prevent_update_posted_vouchers\n"
        "BEFORE UPDATE ON vouchers\n"
        "WHEN OLD.status = 'posted'\n"
        "BEGIN\n"
        "    SELECT RAISE(ABORT, 'posted vouchers are immutable');\n"
        "END"
    ),
    "prevent_delete_posted_vouchers": (
        "CREATE TRIGGER prevent_delete_posted_vouchers\n"
        "BEFORE DELETE ON vouchers\n"
        "WHEN OLD.status = 'posted'\n"
        "BEGIN\n"
        "    SELECT RAISE(ABORT, 'posted vouchers are immutable');\n"
        "END"
    ),
    "prevent_update_rows_for_posted_vouchers": (
        "CREATE TRIGGER prevent_update_rows_for_posted_vouchers\n"
        "BEFORE UPDATE ON voucher_rows\n"
        "WHEN EXISTS (\n"
        "    SELECT 1 FROM vouchers\n"
        "    WHERE vouchers.id = OLD.voucher_id\n"
        "      AND vouchers.status = 'posted'\n"
        ")\n"
        "BEGIN\n"
        "    SELECT RAISE(ABORT, 'rows for posted vouchers are immutable');\n"
        "END"
    ),
    "prevent_delete_rows_for_posted_vouchers": (
        "CREATE TRIGGER prevent_delete_rows_for_posted_vouchers\n"
        "BEFORE DELETE ON voucher_rows\n"
        "WHEN EXISTS (\n"
        "    SELECT 1 FROM vouchers\n"
        "    WHERE vouchers.id = OLD.voucher_id\n"
        "      AND vouchers.status = 'posted'\n"
        ")\n"
        "BEGIN\n"
        "    SELECT RAISE(ABORT, 'rows for posted vouchers are immutable');\n"
        "END"
    ),
}

# The indexes 001 creates on `vouchers`, as SQLite stores them.
INDEXES_001 = {
    "idx_vouchers_period": "CREATE INDEX idx_vouchers_period ON vouchers(period_id)",
    "idx_vouchers_series_number": (
        "CREATE INDEX idx_vouchers_series_number ON vouchers(series, number)"
    ),
    "idx_vouchers_status": "CREATE INDEX idx_vouchers_status ON vouchers(status)",
    "idx_vouchers_date": "CREATE INDEX idx_vouchers_date ON vouchers(date)",
}

# Today's data: posted and draft vouchers in two series, a posted correction,
# and drafts that carry a number — as the code writes them before F2.
SEED_V26 = """
INSERT INTO fiscal_years (id, start_date, end_date)
    VALUES ('fy26', '2026-01-01', '2026-12-31');
INSERT INTO periods (id, fiscal_year_id, year, month, start_date, end_date)
    VALUES ('p2601', 'fy26', 2026, 1, '2026-01-01', '2026-01-31');
INSERT OR IGNORE INTO accounts (code, name, account_type)
    VALUES ('1930', 'Företagskonto', 'asset');
INSERT OR IGNORE INTO accounts (code, name, account_type)
    VALUES ('6110', 'Kontorsmateriel', 'expense');

INSERT INTO vouchers (id, series, number, date, period_id, fiscal_year_id,
                      description, status, correction_of, created_at,
                      created_by, posted_at)
VALUES
  ('vA1', 'A', 1, '2026-01-05', 'p2601', 'fy26', 'Pennor', 'posted', NULL,
   '2026-01-05 09:00:00', 'agent', '2026-01-05 09:01:00'),
  ('vA2', 'A', 2, '2026-01-06', 'p2601', 'fy26', 'Papper', 'posted', NULL,
   '2026-01-06 10:00:00', 'system', '2026-01-06 10:00:30'),
  ('vA3', 'A', 3, '2026-01-07', 'p2601', 'fy26', 'Utkast med nummer', 'draft',
   NULL, '2026-01-07 11:00:00', 'agent', NULL),
  ('vB1', 'B', 1, '2026-01-08', 'p2601', 'fy26', 'Rättelse av A1', 'posted',
   'vA1', '2026-01-08 12:00:00', 'user', '2026-01-08 12:05:00'),
  ('vB2', 'B', 2, '2026-01-09', 'p2601', 'fy26', 'Rättelse av A2 (utkast)',
   'draft', 'vA2', '2026-01-09 13:00:00', 'agent', NULL);

INSERT INTO voucher_rows (id, voucher_id, account_code, debit, credit,
                          description, created_at)
VALUES
  ('rA1d', 'vA1', '6110', 12500, 0, 'Pennor', '2026-01-05 09:00:00'),
  ('rA1k', 'vA1', '1930', 0, 12500, NULL, '2026-01-05 09:00:00'),
  ('rA2d', 'vA2', '6110', 9900, 0, 'Papper', '2026-01-06 10:00:00'),
  ('rA2k', 'vA2', '1930', 0, 9900, NULL, '2026-01-06 10:00:00'),
  ('rA3d', 'vA3', '6110', 100, 0, NULL, '2026-01-07 11:00:00'),
  ('rA3k', 'vA3', '1930', 0, 100, NULL, '2026-01-07 11:00:00'),
  ('rB1d', 'vB1', '1930', 12500, 0, NULL, '2026-01-08 12:00:00'),
  ('rB1k', 'vB1', '6110', 0, 12500, NULL, '2026-01-08 12:00:00'),
  ('rB2d', 'vB2', '1930', 9900, 0, NULL, '2026-01-09 13:00:00'),
  ('rB2k', 'vB2', '6110', 0, 9900, NULL, '2026-01-09 13:00:00');

-- A child row whose foreign key is `ON DELETE SET NULL`: if `DROP TABLE
-- vouchers` ever ran with foreign keys on, this link would be lost.
INSERT INTO correction_notes (id, voucher_id, note_text, status,
                              suggested_voucher_id, created_by)
VALUES ('cn1', 'vA2', 'Fel konto', 'suggested', 'vB2', 'user');
"""


# --- helpers ----------------------------------------------------------------


def _migration_version(path: Path) -> int:
    return int(path.name.split("_")[0])


def _apply_up_to(conn: sqlite3.Connection, max_version: int) -> None:
    """Apply migrations up to and including `max_version`, the way
    `Database.init_db` does, so the database looks like one that was last
    started before 027 existed."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = _migration_version(path)
        if version > max_version:
            continue
        conn.executescript(path.read_text())
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (version,)
        )
        conn.commit()


def _rows(conn: sqlite3.Connection, sql: str) -> List[Dict[str, Any]]:
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]


@pytest.fixture
def v26_db() -> Iterator[str]:
    """A database file at schema version 26 with today's data in it.

    The global `db` is pointed at it, so `db.init_db()` in a test runs 027
    through the real runner.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    original_path = db.db_path
    db.db_path = path
    db.disconnect()

    conn = db.connect()
    _apply_up_to(conn, 26)
    assert _schema_version(conn) == 26
    conn.executescript(SEED_V26)
    conn.commit()

    yield path

    db.disconnect()
    db.db_path = original_path
    for f in glob.glob(path + "*"):
        os.remove(f)


def _scratch_copy(path: str, dest: Path) -> sqlite3.Connection:
    """An autocommit connection to a fresh copy of the database at `path`, for
    experiments that must not touch the fixture's file."""
    db.connect().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    copy = dest / f"scratch{len(list(dest.glob('scratch*.db')))}.db"
    shutil.copyfile(path, copy)
    conn = sqlite3.connect(copy, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


# --- F1: migration 027 --------------------------------------------------------


def test_1_migration_keeps_posted_rows_and_clears_draft_numbers(v26_db):
    """Case 1: every posted voucher identical field by field; drafts'
    `number` is NULL; `foreign_key_check` is empty."""
    conn = db.connect()
    columns_before = [tuple(r) for r in conn.execute("PRAGMA table_info(vouchers)")]
    posted_before = _rows(
        conn, "SELECT * FROM vouchers WHERE status = 'posted' ORDER BY id"
    )
    drafts_before = _rows(
        conn, "SELECT * FROM vouchers WHERE status = 'draft' ORDER BY id"
    )
    voucher_rows_before = _rows(conn, "SELECT * FROM voucher_rows ORDER BY id")
    notes_before = _rows(conn, "SELECT * FROM correction_notes ORDER BY id")
    assert len(posted_before) == 3 and len(drafts_before) == 2
    assert all(d["number"] is not None for d in drafts_before)

    db.init_db()
    conn = db.connect()

    assert _schema_version(conn) == 27
    # The runner's connection has foreign keys back on after 027.
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    # Same columns, same order, same types and defaults; only `number` lost
    # its NOT NULL.
    columns_after = [tuple(r) for r in conn.execute("PRAGMA table_info(vouchers)")]
    expected = [
        (c[0], c[1], c[2], 0, c[4], c[5]) if c[1] == "number" else c
        for c in columns_before
    ]
    assert columns_after == expected

    posted_after = _rows(
        conn, "SELECT * FROM vouchers WHERE status = 'posted' ORDER BY id"
    )
    assert posted_after == posted_before

    drafts_after = _rows(
        conn, "SELECT * FROM vouchers WHERE status = 'draft' ORDER BY id"
    )
    assert [d["number"] for d in drafts_after] == [None, None]
    assert [{**d, "number": None} for d in drafts_before] == drafts_after

    # Nothing hanging off `vouchers` was touched: had `DROP TABLE` run with
    # foreign keys on, `voucher_rows` would have cascaded away and the
    # correction note's `suggested_voucher_id` been set to NULL.
    assert _rows(conn, "SELECT * FROM voucher_rows ORDER BY id") == voucher_rows_before
    assert _rows(conn, "SELECT * FROM correction_notes ORDER BY id") == notes_before

    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    # Indexes from 001 and all four triggers from 014, verbatim.
    objects = {
        r["name"]: r["sql"]
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type IN ('index', 'trigger') AND sql LIKE '%vouchers%'"
        )
    }
    assert objects == {**INDEXES_001, **TRIGGERS_014}
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'vouchers_new'"
        ).fetchone()[0]
        == 0
    )


def test_2_schema_rejects_numbered_draft_and_unnumbered_posted(v26_db):
    """Case 2: a draft with a number is rejected; a posted voucher without
    one is rejected."""
    db.init_db()
    conn = db.connect()

    insert = (
        "INSERT INTO vouchers (id, series, number, date, period_id, "
        "fiscal_year_id, description, status, posted_at) "
        "VALUES (?, 'A', ?, '2026-01-10', 'p2601', 'fy26', 't', ?, ?)"
    )

    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(insert, ("d-num", 10, "draft", None))
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(insert, ("p-null", None, "posted", "2026-01-10"))
    conn.rollback()

    # The legal shapes go in, and two drafts without a number do not collide
    # on UNIQUE(series, number, fiscal_year_id).
    conn.execute(insert, ("d1", None, "draft", None))
    conn.execute(insert, ("d2", None, "draft", None))
    conn.execute(insert, ("p10", 10, "posted", "2026-01-10"))
    conn.commit()

    # Posting a draft without giving it a number is rejected too — which is
    # what makes F2 set the number in the same UPDATE as the status.
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute("UPDATE vouchers SET status = 'posted' WHERE id = 'd1'")
    conn.rollback()
    conn.execute(
        "UPDATE vouchers SET status = 'posted', number = 11, "
        "posted_at = '2026-01-11' WHERE id = 'd1' AND status = 'draft'"
    )
    conn.commit()
    assert (
        conn.execute("SELECT number FROM vouchers WHERE id = 'd1'").fetchone()[0] == 11
    )

    # UNIQUE still guards the posted series.
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        conn.execute(
            "UPDATE vouchers SET status = 'posted', number = 11, "
            "posted_at = '2026-01-11' WHERE id = 'd2'"
        )
    conn.rollback()


def test_3_drop_table_is_not_stopped_by_delete_trigger(v26_db, tmp_path):
    """Case 3: shown, not assumed. `DROP TABLE vouchers` with posted rows is
    not stopped by `prevent_delete_posted_vouchers`, and the migration loses
    no posted row.

    The same experiment shows the two things that *do* bite, and which 027 is
    written around: with foreign keys on, the implicit delete cascades into
    `voucher_rows`; and the `RENAME` is refused while the `voucher_rows`
    triggers name a `vouchers` that no longer exists.
    """
    # (a) Foreign keys off, as in 027: DROP goes through, rows untouched.
    conn = _scratch_copy(v26_db, tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    conn.execute("DROP TABLE vouchers")
    assert conn.execute("SELECT COUNT(*) FROM voucher_rows").fetchone()[0] == 10
    conn.execute("ROLLBACK")
    conn.close()

    # (b) Foreign keys on: the delete trigger still does not fire, but
    # `DROP TABLE` becomes an implicit DELETE with foreign-key actions. With a
    # child that has no ON DELETE action (`correction_notes.voucher_id`) the
    # DROP is refused; without one, the DROP goes through and `voucher_rows`
    # cascades away. Either way 027 must turn foreign keys off first.
    conn = _scratch_copy(v26_db, tmp_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("DROP TABLE vouchers")
    conn.execute("ROLLBACK")
    conn.execute("DELETE FROM correction_notes")
    conn.execute("BEGIN")
    conn.execute("DROP TABLE vouchers")
    assert conn.execute("SELECT COUNT(*) FROM voucher_rows").fetchone()[0] == 0
    conn.execute("ROLLBACK")
    conn.close()

    # (c) With the voucher_rows triggers left in place, the RENAME fails.
    # This is why 027 drops those two triggers inside the transaction and
    # re-creates them after the RENAME.
    conn = _scratch_copy(v26_db, tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    conn.execute("CREATE TABLE vouchers_new AS SELECT * FROM vouchers")
    conn.execute("DROP TABLE vouchers")
    with pytest.raises(sqlite3.OperationalError, match="error in trigger"):
        conn.execute("ALTER TABLE vouchers_new RENAME TO vouchers")
    conn.execute("ROLLBACK")
    conn.close()

    # (d) The migration itself: no posted voucher lost.
    conn = db.connect()
    posted_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM vouchers WHERE status = 'posted' ORDER BY id"
        )
    ]
    db.init_db()
    conn = db.connect()
    assert [
        r[0]
        for r in conn.execute(
            "SELECT id FROM vouchers WHERE status = 'posted' ORDER BY id"
        )
    ] == posted_ids
    assert conn.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0] == 5


def test_4_triggers_still_guard_posted_vouchers_and_rows(v26_db):
    """Case 4: UPDATE/DELETE on a posted voucher and on its rows is rejected
    after the migration, as before; a draft stays editable."""
    db.init_db()
    conn = db.connect()

    attempts = [
        ("UPDATE vouchers SET description = 'x' WHERE id = 'vA1'", "posted vouchers"),
        (
            "UPDATE vouchers SET status = 'draft', number = NULL WHERE id = 'vA1'",
            "posted vouchers",
        ),
        ("DELETE FROM vouchers WHERE id = 'vA1'", "posted vouchers"),
        ("UPDATE voucher_rows SET debit = 1 WHERE id = 'rA1d'", "rows for posted"),
        ("DELETE FROM voucher_rows WHERE id = 'rA1d'", "rows for posted"),
        ("DELETE FROM voucher_rows WHERE voucher_id = 'vB1'", "rows for posted"),
    ]
    for sql, message in attempts:
        with pytest.raises(sqlite3.IntegrityError, match=message):
            conn.execute(sql)
        conn.rollback()

    assert (
        conn.execute("SELECT description FROM vouchers WHERE id = 'vA1'").fetchone()[0]
        == "Pennor"
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM voucher_rows WHERE voucher_id IN ('vA1', 'vB1')"
        ).fetchone()[0]
        == 4
    )

    # Drafts and their rows are still editable, and deleting a draft still
    # cascades to its rows.
    conn.execute("UPDATE vouchers SET description = 'ny' WHERE id = 'vA3'")
    conn.execute("UPDATE voucher_rows SET debit = 200 WHERE id = 'rA3d'")
    conn.execute("UPDATE voucher_rows SET credit = 200 WHERE id = 'rA3k'")
    conn.execute("DELETE FROM vouchers WHERE id = 'vA3'")
    conn.commit()
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM voucher_rows WHERE voucher_id = 'vA3'"
        ).fetchone()[0]
        == 0
    )
