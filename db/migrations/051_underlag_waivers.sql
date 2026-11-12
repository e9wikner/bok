-- Migration 051: a human approves a voucher without underlag
--
-- A posted voucher without a document stands in `Saknar underlag` until an
-- underlag is linked. Two kinds of voucher should not stand there:
--
--   later  the underlag exists but arrives after the posting (an invoice
--          that comes at month end). The voucher leaves the list, and the
--          underlag is still matched to it when it arrives -- the matching
--          reads `MISSING_DOCUMENT_SQL`, which ignores a waiver.
--   none   the voucher has no external underlag: an accrual, a
--          depreciation, a reclassification. The voucher itself, with its
--          description, is the document (BFNAR 2013:2, egenupprättad
--          verifikation).
--
-- A waiver is a logged-in human's press (`POST /vouchers/{id}/underlag-
-- waiver`; the API key gets `403 human_only`). It never touches the voucher.
-- Like a reuse approval (migration 044) it is append-only and ended by a row
-- in `voucher_underlag_waiver_revocations`; a "current" waiver is one
-- without such a row, and a voucher has at most one. That the voucher is
-- posted and lacks underlag is checked by `UnderlagWaiverService`.

BEGIN;

CREATE TABLE IF NOT EXISTS voucher_underlag_waivers (
    id          TEXT PRIMARY KEY,
    voucher_id  TEXT NOT NULL REFERENCES vouchers(id),
    reason      TEXT NOT NULL CHECK (reason IN ('later', 'none')),
    note        TEXT,
    waived_by   TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_voucher_underlag_waivers_voucher
    ON voucher_underlag_waivers(voucher_id);

CREATE TABLE IF NOT EXISTS voucher_underlag_waiver_revocations (
    waiver_id   TEXT PRIMARY KEY NOT NULL REFERENCES voucher_underlag_waivers(id),
    revoked_by  TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER one_current_underlag_waiver_per_voucher
BEFORE INSERT ON voucher_underlag_waivers
WHEN EXISTS (
    SELECT 1 FROM voucher_underlag_waivers w
    WHERE w.voucher_id = NEW.voucher_id
      AND NOT EXISTS (
          SELECT 1 FROM voucher_underlag_waiver_revocations r
          WHERE r.waiver_id = w.id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'voucher already has a current underlag waiver');
END;

CREATE TRIGGER prevent_update_voucher_underlag_waivers
BEFORE UPDATE ON voucher_underlag_waivers
BEGIN SELECT RAISE(ABORT, 'underlag waivers are append-only'); END;

CREATE TRIGGER prevent_delete_voucher_underlag_waivers
BEFORE DELETE ON voucher_underlag_waivers
BEGIN SELECT RAISE(ABORT, 'underlag waivers are append-only'); END;

CREATE TRIGGER prevent_update_voucher_underlag_waiver_revocations
BEFORE UPDATE ON voucher_underlag_waiver_revocations
BEGIN SELECT RAISE(ABORT, 'underlag waiver revocations are append-only'); END;

CREATE TRIGGER prevent_delete_voucher_underlag_waiver_revocations
BEFORE DELETE ON voucher_underlag_waiver_revocations
BEGIN SELECT RAISE(ABORT, 'underlag waiver revocations are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (51);

COMMIT;
