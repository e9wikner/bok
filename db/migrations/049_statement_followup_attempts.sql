-- Migration 049: kontoutdragets okopplade rader i intagspasset
--
-- Service: services/statement_followup.py. Test: tests/test_statement_followup.py.
--
-- A statement transaction that no voucher accounts for and that has no
-- underlag in the queue -- a transfer between own accounts, a tax-account
-- event, a bank fee, the payment of an invoice already booked -- used to wait
-- until a human pointed at it: the intake pass only took underlag. The pass
-- now gives each such transaction a session of its own after the queue.
--
-- `statement_followup_attempts`: one row per transaction a session did not
-- book. A transaction with such a row is not tried again by the pass; it
-- stays open for a human, in /v4 and in `las_okopplade_banktransaktioner`.
-- A booked transaction needs no row: it is linked, and so no longer open.
-- Append-only.

CREATE TABLE IF NOT EXISTS statement_followup_attempts (
    id                   TEXT PRIMARY KEY,
    bank_transaction_id  TEXT NOT NULL REFERENCES bank_transactions(id),
    agent_run_id         TEXT,
    reason               TEXT NOT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_statement_followup_attempts_tx
    ON statement_followup_attempts(bank_transaction_id);

CREATE TRIGGER IF NOT EXISTS prevent_update_statement_followup_attempts
BEFORE UPDATE ON statement_followup_attempts
BEGIN SELECT RAISE(ABORT, 'statement follow-up attempts are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_statement_followup_attempts
BEFORE DELETE ON statement_followup_attempts
BEGIN SELECT RAISE(ABORT, 'statement follow-up attempts are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (49);
