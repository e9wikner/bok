-- Migration 048: avtal och medgivanden som underlag för flera transaktioner
--
-- Service: services/agreement_booking.py. Test: tests/test_agreement_booking.py.
--
-- An autogiro mandate, a loan agreement or a subscription has no date or
-- amount of its own: it is the underlag behind every transaction it covers
-- in the statements. The agent may not decide on its own how many that is,
-- so it asks with a decision card (`foresla_avtalsbokforing`): book these
-- transactions with this underlag, debit/credit these accounts -- once, or
-- once and approve the underlag for the coming transactions of the fiscal
-- year. Only a logged-in human's press answers it.
--
-- 1. `agreement_bookings`: the card. It carries the pattern the coming
--    transactions are recognised by (bank account, amount, text) and the
--    kontering every voucher gets (the bank account against
--    `counter_account_code`). A row moves only out of `pending`, as the
--    other card tables do. While a card is pending the underlag is out of
--    the intake pass's queue (`repositories/intake_repo.py`).
-- 2. `agreement_booking_transactions`: the transactions the card names, the
--    set the human approved. Append-only.
-- 3. `agreement_followup_attempts`: one row per transaction an intake pass
--    tried to book under a standing approval and did not. A transaction
--    with such a row is not tried again by the pass; it stays open for a
--    human. Append-only.
--
-- The standing approval itself is a row in `intake_reuse_approvals`
-- (migration 044) with the card's decision, revocable the same way.

CREATE TABLE IF NOT EXISTS agreement_bookings (
    id                    TEXT PRIMARY KEY,
    decision_id           TEXT NOT NULL UNIQUE REFERENCES decisions(id),
    thread_id             TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    intake_source_id      TEXT NOT NULL REFERENCES intake_sources(id),
    fiscal_year_id        TEXT NOT NULL REFERENCES fiscal_years(id),
    account_code          TEXT NOT NULL,
    amount_ore            INTEGER NOT NULL,
    description           TEXT NOT NULL,
    counter_account_code  TEXT NOT NULL,
    book_option_id        TEXT NOT NULL REFERENCES decision_options(id),
    standing_option_id    TEXT NOT NULL REFERENCES decision_options(id),
    status                TEXT NOT NULL DEFAULT 'pending',
    created_by            TEXT NOT NULL,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at           TIMESTAMP,
    resolved_by           TEXT,
    CHECK (amount_ore != 0),
    CHECK (status IN ('pending', 'approved', 'approved_standing', 'declined',
                      'superseded'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agreement_bookings_pending
    ON agreement_bookings(intake_source_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_agreement_bookings_source
    ON agreement_bookings(intake_source_id);

CREATE TABLE IF NOT EXISTS agreement_booking_transactions (
    booking_id           TEXT NOT NULL REFERENCES agreement_bookings(id),
    bank_transaction_id  TEXT NOT NULL REFERENCES bank_transactions(id),
    PRIMARY KEY (booking_id, bank_transaction_id)
);

CREATE TRIGGER IF NOT EXISTS prevent_update_agreement_booking_transactions
BEFORE UPDATE ON agreement_booking_transactions
BEGIN SELECT RAISE(ABORT, 'agreement booking transactions are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_agreement_booking_transactions
BEFORE DELETE ON agreement_booking_transactions
BEGIN SELECT RAISE(ABORT, 'agreement booking transactions are append-only'); END;

CREATE TABLE IF NOT EXISTS agreement_followup_attempts (
    id                   TEXT PRIMARY KEY,
    booking_id           TEXT NOT NULL REFERENCES agreement_bookings(id),
    bank_transaction_id  TEXT NOT NULL REFERENCES bank_transactions(id),
    agent_run_id         TEXT,
    reason               TEXT NOT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agreement_followup_attempts_tx
    ON agreement_followup_attempts(bank_transaction_id);

CREATE TRIGGER IF NOT EXISTS prevent_update_agreement_followup_attempts
BEFORE UPDATE ON agreement_followup_attempts
BEGIN SELECT RAISE(ABORT, 'agreement follow-up attempts are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_agreement_followup_attempts
BEFORE DELETE ON agreement_followup_attempts
BEGIN SELECT RAISE(ABORT, 'agreement follow-up attempts are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (48);
