-- Migration 055: granskningsrapporter (docs/granskning.md §5)
--
-- An external agent reviews a fiscal year for the board and uploads a
-- report: a summary, its findings (anmärkningar) and the vouchers it
-- examined. Bok runs no review itself; it stores what was uploaded and
-- shows it. A review is the board's own control (ABL 8 kap. 4 §).
--
-- Everything is append-only, like the intake links (migration 035): the
-- triggers below refuse UPDATE and DELETE on all four tables, the repository
-- offers insert and read only, and no endpoint rewrites or removes a row. A
-- wrong report is replaced by a new report, not by a change.
--
-- `review_reports.id` is the agent's own UUID: the same id again returns the
-- stored report (`services/review.py`), never a duplicate.
-- `instruction_sha256` is stored as sent; the UI compares it with the
-- current instruction and says when a report was made against an older one.
-- That every voucher id is a posted voucher in the report's fiscal year is
-- checked by `ReviewService` before anything is written.

BEGIN;

CREATE TABLE IF NOT EXISTS review_reports (
    id                  TEXT PRIMARY KEY,
    fiscal_year_id      TEXT NOT NULL REFERENCES fiscal_years(id),
    reviewer_agent      TEXT NOT NULL,
    reviewer_model      TEXT NOT NULL,
    instruction_sha256  TEXT NOT NULL,
    summary_markdown    TEXT NOT NULL,
    uploaded_by         TEXT NOT NULL,
    uploaded_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_reports_fiscal_year
    ON review_reports(fiscal_year_id);

CREATE TABLE IF NOT EXISTS review_findings (
    id                    TEXT PRIMARY KEY,
    report_id             TEXT NOT NULL REFERENCES review_reports(id),
    position              INTEGER NOT NULL,
    severity              TEXT NOT NULL
                          CHECK (severity IN ('material', 'should_fix', 'observation')),
    area                  TEXT NOT NULL,
    title                 TEXT NOT NULL,
    description           TEXT NOT NULL,
    rule                  TEXT,
    amount_ore            INTEGER,
    suggested_correction  TEXT,
    UNIQUE (report_id, position)
);

CREATE TABLE IF NOT EXISTS review_finding_vouchers (
    finding_id  TEXT NOT NULL REFERENCES review_findings(id),
    voucher_id  TEXT NOT NULL REFERENCES vouchers(id),
    PRIMARY KEY (finding_id, voucher_id)
);

CREATE INDEX IF NOT EXISTS idx_review_finding_vouchers_voucher
    ON review_finding_vouchers(voucher_id);

CREATE TABLE IF NOT EXISTS review_examined_vouchers (
    report_id   TEXT NOT NULL REFERENCES review_reports(id),
    voucher_id  TEXT NOT NULL REFERENCES vouchers(id),
    PRIMARY KEY (report_id, voucher_id)
);

CREATE INDEX IF NOT EXISTS idx_review_examined_vouchers_voucher
    ON review_examined_vouchers(voucher_id);

CREATE TRIGGER prevent_update_review_reports
BEFORE UPDATE ON review_reports
BEGIN SELECT RAISE(ABORT, 'review reports are append-only'); END;

CREATE TRIGGER prevent_delete_review_reports
BEFORE DELETE ON review_reports
BEGIN SELECT RAISE(ABORT, 'review reports are append-only'); END;

CREATE TRIGGER prevent_update_review_findings
BEFORE UPDATE ON review_findings
BEGIN SELECT RAISE(ABORT, 'review findings are append-only'); END;

CREATE TRIGGER prevent_delete_review_findings
BEFORE DELETE ON review_findings
BEGIN SELECT RAISE(ABORT, 'review findings are append-only'); END;

CREATE TRIGGER prevent_update_review_finding_vouchers
BEFORE UPDATE ON review_finding_vouchers
BEGIN SELECT RAISE(ABORT, 'review finding vouchers are append-only'); END;

CREATE TRIGGER prevent_delete_review_finding_vouchers
BEFORE DELETE ON review_finding_vouchers
BEGIN SELECT RAISE(ABORT, 'review finding vouchers are append-only'); END;

CREATE TRIGGER prevent_update_review_examined_vouchers
BEFORE UPDATE ON review_examined_vouchers
BEGIN SELECT RAISE(ABORT, 'review examined vouchers are append-only'); END;

CREATE TRIGGER prevent_delete_review_examined_vouchers
BEFORE DELETE ON review_examined_vouchers
BEGIN SELECT RAISE(ABORT, 'review examined vouchers are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (55);

COMMIT;
