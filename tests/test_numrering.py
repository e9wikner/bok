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
from datetime import date
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

    # 027 was applied; later migrations (028, …) run too and raise MAX.
    assert (
        conn.execute("SELECT 1 FROM schema_version WHERE version = 27").fetchone()
        is not None
    )
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


# --- F2: the number is set at posting (cases 5–11) ---------------------------
#
# A draft has no number; `post_voucher` takes MAX(number) + 1 over *posted*
# vouchers in the same series and fiscal year — or an explicit number, for the
# SIE4 import — in the same UPDATE that flips the status (SPEC §4.3).

ROWS = [
    {"account": "1510", "debit": 10000, "credit": 0},
    {"account": "3011", "debit": 0, "credit": 10000},
]


def _draft(ledger, period, series: str = "A", day: int = 10):
    return ledger.create_voucher(
        series=series,
        date=date(period.year, period.month, day),
        period_id=period.id,
        description=f"Test {series}",
        rows_data=ROWS,
        created_by="test",
    )


def _stored_number(voucher_id: str):
    row = db.execute(
        "SELECT number FROM vouchers WHERE id = ?", (voucher_id,)
    ).fetchone()
    return row["number"]


def test_5_create_voucher_has_no_number(ledger_service, test_period):
    """Case 5: a draft is created without a number, in memory and on disk."""
    draft = _draft(ledger_service, test_period)

    assert draft.number is None
    assert _stored_number(draft.id) is None
    assert ledger_service.vouchers.get(draft.id).number is None


def test_6_post_takes_next_number_among_posted(ledger_service, test_period):
    """Case 6: posting gives MAX(number) + 1 among posted in the series and
    year; other series and drafts do not count."""
    first = ledger_service.post_voucher(_draft(ledger_service, test_period).id)
    assert first.number == 1
    assert _stored_number(first.id) == 1

    _draft(ledger_service, test_period)  # a draft does not take a number
    ledger_service.post_voucher(_draft(ledger_service, test_period, series="B").id)

    second = ledger_service.post_voucher(_draft(ledger_service, test_period).id)
    assert second.number == 2
    assert second.status.value == "posted"


def test_7_later_draft_posted_first_gets_lower_number(ledger_service, test_period):
    """Case 7: the number follows the order of posting, not of creation."""
    earlier = _draft(ledger_service, test_period)
    later = _draft(ledger_service, test_period)

    assert ledger_service.post_voucher(later.id).number == 1
    assert ledger_service.post_voucher(earlier.id).number == 2


def test_8_deleted_draft_leaves_no_gap(ledger_service, test_period):
    """Case 8: deleting a draft consumes no number."""
    a = _draft(ledger_service, test_period)
    b = _draft(ledger_service, test_period)
    c = _draft(ledger_service, test_period)
    ledger_service.vouchers.delete_draft(b.id)

    numbers = [ledger_service.post_voucher(v.id).number for v in (a, c)]
    assert numbers == [1, 2]


def test_9_new_fiscal_year_starts_at_one(ledger_service, test_period):
    """Case 9: the series restarts at 1 in each fiscal year."""
    for _ in range(2):
        ledger_service.post_voucher(_draft(ledger_service, test_period).id)

    next_year = ledger_service.periods.create_fiscal_year(
        start_date=date(2027, 1, 1), end_date=date(2027, 12, 31)
    )
    period_2027 = ledger_service.periods.create_period(
        fiscal_year_id=next_year.id,
        year=2027,
        month=1,
        start_date=date(2027, 1, 1),
        end_date=date(2027, 1, 31),
    )

    posted = ledger_service.post_voucher(_draft(ledger_service, period_2027).id)
    assert posted.number == 1
    assert (
        ledger_service.post_voucher(_draft(ledger_service, test_period).id).number == 3
    )


SIE4_WITH_NUMBERS = """#FLAGGA 0
#FORMAT PC8
#PROGRAM "Test" 1.0
#FNAMN "Test AB"
#FORGN 5566778899
#RAR 0 20100101 20101231
#KONTO 1930 "Företagskonto"
#KONTO 3010 "Försäljning"
#VER A 5 20100115 "Femte"
{
#TRANS 1930 {} 10000 20100115
#TRANS 3010 {} -10000 20100115
}
#VER A 7 20100210 "Sjunde"
{
#TRANS 1930 {} 20000 20100210
#TRANS 3010 {} -20000 20100210
}
#VER B 2 20100301 "Andra B"
{
#TRANS 1930 {} 30000 20100301
#TRANS 3010 {} -30000 20100301
}
"""


def test_10_sie4_import_keeps_file_numbers(test_db):
    """Case 10: the file's numbers survive, gaps included; the next voucher
    posted in the app continues after the file's highest."""
    from services.ledger import LedgerService
    from services.sie4_import import SIE4Importer

    importer = SIE4Importer(api_url="http://test", api_key="test")
    assert importer.import_content(SIE4_WITH_NUMBERS) is True, importer.errors

    rows = db.execute(
        "SELECT series, number, status, description FROM vouchers "
        "ORDER BY series, number"
    ).fetchall()
    assert [(r["series"], r["number"], r["status"]) for r in rows] == [
        ("A", 5, "posted"),
        ("A", 7, "posted"),
        ("B", 2, "posted"),
    ]

    period_id = db.execute(
        "SELECT period_id FROM vouchers WHERE number = 7"
    ).fetchone()["period_id"]
    ledger = LedgerService()
    draft = ledger.create_voucher(
        series="A",
        date=date(2010, 2, 20),
        period_id=period_id,
        description="Efter importen",
        rows_data=[
            {"account": "1930", "debit": 100, "credit": 0},
            {"account": "3010", "debit": 0, "credit": 100},
        ],
    )
    assert draft.number is None
    assert ledger.post_voucher(draft.id).number == 8


def test_11_correct_sets_b_number_at_posting(ledger_service, test_period, auth_headers):
    """Case 11: `/correct` yields a posted B-series voucher numbered at
    posting, as before; a B draft does not take a number."""
    from fastapi.testclient import TestClient

    from api.main import app

    original = ledger_service.post_voucher(_draft(ledger_service, test_period).id)
    stray_b_draft = _draft(ledger_service, test_period, series="B")

    response = TestClient(app).post(
        f"/api/v1/vouchers/{original.id}/correct",
        json={
            "corrected_rows": [
                {"account": "1510", "debit": 12000, "credit": 0},
                {"account": "3011", "debit": 0, "credit": 12000},
            ],
            "reason": "Fel belopp",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["series"] == "B"
    assert body["status"] == "posted"
    assert body["number"] == 1
    assert _stored_number(body["id"]) == 1
    assert _stored_number(stray_b_draft.id) is None

    # A correction draft (the correction-notes path) has no number until it
    # is posted.
    draft = ledger_service.create_correction(
        original_voucher_id=original.id,
        correction_rows=[
            {"account": "3011", "debit": 10000, "credit": 0},
            {"account": "1510", "debit": 0, "credit": 10000},
        ],
    )
    assert draft.number is None
    assert _stored_number(draft.id) is None
    assert ledger_service.post_voucher(draft.id).number == 2


def test_10b_api_explicit_number_only_with_auto_post(
    ledger_service, test_period, auth_headers
):
    """Case 10, over HTTP: an explicit `number` is set at posting, so it is
    refused on a draft and kept with `auto_post`."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    body = {
        "series": "A",
        "number": 42,
        "date": "2026-03-10",
        "period_id": test_period.id,
        "description": "Explicit",
        "rows": ROWS,
    }

    refused = client.post("/api/v1/vouchers", json=body, headers=auth_headers)
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "number_requires_auto_post"
    assert db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"] == 0

    posted = client.post(
        "/api/v1/vouchers", json={**body, "auto_post": True}, headers=auth_headers
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["number"] == 42
    assert posted.json()["status"] == "posted"


# --- F3: a number may be None, and the gap check runs per fiscal year --------
#
# Case 12 is the gap check (SPEC §4.5): numbers restart at 1 each fiscal year,
# so grouping on `series` alone lets a gap hide behind the other year's
# vouchers. Case 13 is the backend half of "API and old pages": a draft reads
# as `number: null` everywhere, and nothing answers 500 for one.


def _second_year_period(ledger):
    year = ledger.periods.create_fiscal_year(
        start_date=date(2027, 1, 1), end_date=date(2027, 12, 31)
    )
    return ledger.periods.create_period(
        fiscal_year_id=year.id,
        year=2027,
        month=1,
        start_date=date(2027, 1, 1),
        end_date=date(2027, 1, 31),
    )


def test_12_gap_check_finds_gap_in_second_fiscal_year(ledger_service, test_period):
    """Case 12: A1, A2 in 2026 and A1, A3 in 2027. Grouped on series alone
    that is 4 vouchers over 1–3 and looks gap-free; per year, 2027 lacks A2."""
    from services.compliance import ComplianceService

    period_2027 = _second_year_period(ledger_service)
    for number in (1, 2):
        ledger_service.post_voucher(
            _draft(ledger_service, test_period).id, number=number
        )
    for number in (1, 3):
        ledger_service.post_voucher(
            _draft(ledger_service, period_2027).id, number=number
        )
    _draft(ledger_service, period_2027)  # a draft is not a gap, nor a number

    issues = ComplianceService()._check_voucher_sequence()

    assert len(issues) == 1, [i.title for i in issues]
    issue = issues[0]
    assert issue.check_type == "voucher_sequence"
    assert "A-serien" in issue.title
    assert "2027" in issue.title
    assert "1 luckor" in issue.description or "1 lucka" in issue.description
    assert "1-3" in issue.description


def test_12b_gap_check_is_quiet_when_each_year_is_contiguous(
    ledger_service, test_period
):
    """Case 12, the other side: each year 1..n with no gap is not flagged."""
    from services.compliance import ComplianceService

    period_2027 = _second_year_period(ledger_service)
    for period, count in ((test_period, 3), (period_2027, 2)):
        for _ in range(count):
            ledger_service.post_voucher(_draft(ledger_service, period).id)

    assert ComplianceService()._check_voucher_sequence() == []


def test_12c_run_all_checks_keeps_one_open_issue_per_series_and_year(
    ledger_service, test_period
):
    """F15: a gap in A 2026 and in A 2027 are two open issues, not one --
    each carries its series and fiscal year as `entity_id` -- and a second
    run adds neither again."""
    from services.compliance import ComplianceService

    period_2027 = _second_year_period(ledger_service)
    for period in (test_period, period_2027):
        for number in (1, 3):
            ledger_service.post_voucher(
                _draft(ledger_service, period).id, number=number
            )

    service = ComplianceService()
    service.run_all_checks()
    service.run_all_checks()

    open_gaps = [
        i for i in service.get_open_issues() if i.check_type == "voucher_sequence"
    ]
    assert len(open_gaps) == 2, [i.title for i in open_gaps]
    assert {i.entity_id for i in open_gaps} == {
        f"A:{test_period.fiscal_year_id}",
        f"A:{period_2027.fiscal_year_id}",
    }
    assert {i.entity_type for i in open_gaps} == {"voucher_series"}


def test_13_api_gives_null_number_for_draft(ledger_service, test_period, auth_headers):
    """Case 13, backend: a draft is `number: null` in the single read and the
    list, and a number once posted; its audit trail answers 200."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    draft = _draft(ledger_service, test_period)

    one = client.get(f"/api/v1/vouchers/{draft.id}", headers=auth_headers)
    assert one.status_code == 200, one.text
    assert one.json()["number"] is None
    assert one.json()["status"] == "draft"

    listed = client.get("/api/v1/vouchers", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert [v["number"] for v in listed.json()["vouchers"]] == [None]

    audit = client.get(f"/api/v1/vouchers/{draft.id}/audit", headers=auth_headers)
    assert audit.status_code == 200, audit.text

    ledger_service.post_voucher(draft.id)
    posted = client.get(f"/api/v1/vouchers/{draft.id}", headers=auth_headers)
    assert posted.json()["number"] == 1
    assert posted.json()["status"] == "posted"


def test_13b_routes_that_format_numbers_do_not_fail_on_drafts(
    ledger_service, test_period, auth_headers
):
    """Case 13, backend: with a draft beside a posted voucher, the list sorted
    on number, the general ledger and the compliance run all answer 200, and
    the ledger report shows only the posted voucher."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    ledger_service.post_voucher(_draft(ledger_service, test_period).id)
    _draft(ledger_service, test_period)

    for order in ("asc", "desc"):
        response = client.get(
            f"/api/v1/vouchers?sort_by=number&sort_order={order}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text

    ledger = client.get(
        "/api/v1/reports/general-ledger/1510",
        params={"fiscal_year_id": test_period.fiscal_year_id},
        headers=auth_headers,
    )
    assert ledger.status_code == 200, ledger.text
    assert [t["voucher_number"] for t in ledger.json()["transactions"]] == ["A1"]

    from services.compliance import ComplianceService

    ComplianceService().run_all_checks()


def test_13c_list_all_puts_drafts_last_in_both_directions(ledger_service, test_period):
    """`list_all(sort_by='number')`: posted by series and number in the asked
    direction, drafts (NULL) after them either way."""
    from repositories.voucher_repo import VoucherRepository

    early_draft = _draft(ledger_service, test_period)
    for series in ("A", "A", "B"):
        ledger_service.post_voucher(_draft(ledger_service, test_period, series).id)
    late_draft = _draft(ledger_service, test_period, series="B")

    def order(direction):
        vouchers, total = VoucherRepository.list_all(
            sort_by="number", sort_order=direction
        )
        assert total == 5
        return [(v.series.value, v.number) for v in vouchers]

    assert order("asc")[:3] == [("A", 1), ("A", 2), ("B", 1)]
    assert order("desc")[:3] == [("B", 1), ("A", 2), ("A", 1)]
    for direction in ("asc", "desc"):
        assert [n for _, n in order(direction)[3:]] == [None, None]

    # Among themselves, drafts follow series in the asked direction.
    assert [v.id for v in VoucherRepository.list_all(sort_by="number")[0][3:]] == [
        late_draft.id,
        early_draft.id,
    ]


def test_13d_agent_reads_a_draft_as_number_null(ledger_service, test_period):
    """The agent's `las_verifikationer` gives `number: None` for a draft — no
    crash and no invented number — and the number once posted."""
    from services.agent_tools import execute_tool
    from services.llm import LLMCapabilities

    draft = _draft(ledger_service, test_period)
    caps = LLMCapabilities(
        cache_breakpoint=True, pdf_document_blocks=True, refusal_stop_reason=True
    )

    result = execute_tool(
        "las_verifikationer",
        {"period_id": test_period.id},
        actor="agent",
        capabilities=caps,
    )
    assert [(v["id"], v["number"], v["status"]) for v in result["items"]] == [
        (draft.id, None, "draft")
    ]

    ledger_service.post_voucher(draft.id)
    result = execute_tool("las_verifikationer", {}, actor="agent", capabilities=caps)
    assert result["items"][0]["number"] == 1
