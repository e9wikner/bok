-- Migration 027: a draft has no number; the number is set when the voucher is posted.
-- Spec: docs/redesign/SPEC-flode-verifikationer.md §4.2. Tests: tests/test_numrering.py 1–4.
--
-- SQLite cannot drop NOT NULL with ALTER TABLE, so `vouchers` is rebuilt using
-- SQLite's documented order (create new, copy, drop old, rename). The column
-- list is today's actual one: no migration after 001 adds columns to
-- `vouchers` (checked with PRAGMA table_info and grep over db/migrations).
--
-- Posted rows are copied unchanged. Drafts lose their number.
--
-- Two things this file is written around (both shown in test 3):
--  * Foreign keys must be OFF, or DROP TABLE runs as an implicit DELETE: it is
--    refused by children without ON DELETE action, or cascades away every row
--    in voucher_rows. The PRAGMA is a no-op inside a transaction, so it stands
--    before BEGIN; Database.init_db runs this file with executescript, which
--    commits any pending transaction first and then runs in autocommit.
--  * The voucher_rows triggers from 014 name `vouchers`. While that table does
--    not exist, ALTER TABLE ... RENAME refuses to run ("error in trigger ...:
--    no such table: main.vouchers"). They are dropped inside the transaction
--    and re-created, verbatim from 014, after the rename. The two triggers on
--    `vouchers` itself go with DROP TABLE and are re-created the same way.
--    DROP TABLE is not stopped by prevent_delete_posted_vouchers: SQLite fires
--    no triggers for it.
--
-- Nothing else references `vouchers` by trigger or view. Foreign keys in other
-- tables name `vouchers` and resolve to the rebuilt table after the rename.
-- PRAGMA foreign_key_check is asserted empty by test 1; in executescript its
-- result would be discarded, so it is not run here.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE vouchers_new (
    id TEXT PRIMARY KEY,
    series TEXT NOT NULL,  -- "A", "B", etc. (B = corrections)
    number INTEGER,  -- NULL while draft; set when posted
    date DATE NOT NULL,
    period_id TEXT NOT NULL,
    fiscal_year_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, posted
    correction_of TEXT,  -- If this is a correction voucher, reference original voucher_id
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    posted_at TIMESTAMP,
    FOREIGN KEY(period_id) REFERENCES periods(id),
    FOREIGN KEY(fiscal_year_id) REFERENCES fiscal_years(id),
    FOREIGN KEY(correction_of) REFERENCES vouchers(id),
    UNIQUE(series, number, fiscal_year_id),  -- several NULLs are allowed
    CHECK(status IN ('draft', 'posted')),
    CHECK((status = 'draft' AND number IS NULL) OR
          (status = 'posted' AND number IS NOT NULL))
);

INSERT INTO vouchers_new (
    id, series, number, date, period_id, fiscal_year_id, description,
    status, correction_of, created_at, created_by, posted_at
)
SELECT
    id, series,
    CASE WHEN status = 'draft' THEN NULL ELSE number END,
    date, period_id, fiscal_year_id, description,
    status, correction_of, created_at, created_by, posted_at
FROM vouchers;

DROP TRIGGER prevent_update_rows_for_posted_vouchers;
DROP TRIGGER prevent_delete_rows_for_posted_vouchers;

DROP TABLE vouchers;
ALTER TABLE vouchers_new RENAME TO vouchers;

-- Indexes from 001
CREATE INDEX idx_vouchers_period ON vouchers(period_id);
CREATE INDEX idx_vouchers_series_number ON vouchers(series, number);
CREATE INDEX idx_vouchers_status ON vouchers(status);
CREATE INDEX idx_vouchers_date ON vouchers(date);

-- Triggers from 014, verbatim
CREATE TRIGGER prevent_update_posted_vouchers
BEFORE UPDATE ON vouchers
WHEN OLD.status = 'posted'
BEGIN
    SELECT RAISE(ABORT, 'posted vouchers are immutable');
END;

CREATE TRIGGER prevent_delete_posted_vouchers
BEFORE DELETE ON vouchers
WHEN OLD.status = 'posted'
BEGIN
    SELECT RAISE(ABORT, 'posted vouchers are immutable');
END;

CREATE TRIGGER prevent_update_rows_for_posted_vouchers
BEFORE UPDATE ON voucher_rows
WHEN EXISTS (
    SELECT 1 FROM vouchers
    WHERE vouchers.id = OLD.voucher_id
      AND vouchers.status = 'posted'
)
BEGIN
    SELECT RAISE(ABORT, 'rows for posted vouchers are immutable');
END;

CREATE TRIGGER prevent_delete_rows_for_posted_vouchers
BEFORE DELETE ON voucher_rows
WHEN EXISTS (
    SELECT 1 FROM vouchers
    WHERE vouchers.id = OLD.voucher_id
      AND vouchers.status = 'posted'
)
BEGIN
    SELECT RAISE(ABORT, 'rows for posted vouchers are immutable');
END;

INSERT OR IGNORE INTO schema_version (version) VALUES (27);

COMMIT;

PRAGMA foreign_keys = ON;
