-- Migration 036: a bank transaction linked to a voucher is underlag
--
-- A transaction from an imported account statement (CSV) now counts as the
-- voucher's underlag for that account (repositories/voucher_repo.py,
-- MISSING_ATTACHMENT_SQL): a transfer 1930 -> 1630 is covered once it is
-- linked to a transaction on each of the two statements. The links are
-- then part of the audit trail and, like `intake_link_basis`, append-only:
-- no UPDATE, no DELETE. A wrong link is not undone -- the voucher is
-- reversed and re-posted.

CREATE TRIGGER IF NOT EXISTS prevent_update_voucher_bank_transactions
BEFORE UPDATE ON voucher_bank_transactions
BEGIN SELECT RAISE(ABORT, 'voucher bank transaction links are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_voucher_bank_transactions
BEFORE DELETE ON voucher_bank_transactions
BEGIN SELECT RAISE(ABORT, 'voucher bank transaction links are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_update_voucher_bank_inputs
BEFORE UPDATE ON voucher_bank_inputs
BEGIN SELECT RAISE(ABORT, 'voucher bank input links are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_voucher_bank_inputs
BEFORE DELETE ON voucher_bank_inputs
BEGIN SELECT RAISE(ABORT, 'voucher bank input links are append-only'); END;

CREATE INDEX IF NOT EXISTS idx_bank_connections_account_number
    ON bank_connections(account_number);

INSERT OR IGNORE INTO schema_version (version) VALUES (36);
