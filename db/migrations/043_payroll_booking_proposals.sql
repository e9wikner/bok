-- Migration 043: förslag om att bokföra en lön eller en AGI
-- (foresla_lonebokforing, foresla_agi_bokforing).
-- Service: services/payroll_proposal.py. Test: tests/test_lonebokforing.py.
--
-- The agent proposes the booking as a decision card in a thread; a logged-in
-- human's press books it. This row binds the card to what it shows -- the
-- payslip and the bank transaction that paid it, or the AGI month and the
-- date of its vouchers -- so what is booked is exactly what the human saw.
--
-- `kind = 'payslip'` carries `payslip_id` and `bank_transaction_id`;
-- `kind = 'agi'` carries `agi_year`, `agi_month` and `voucher_date`.

CREATE TABLE IF NOT EXISTS payroll_booking_proposals (
    id                  TEXT PRIMARY KEY,
    decision_id         TEXT NOT NULL UNIQUE,
    thread_id           TEXT NOT NULL,
    kind                TEXT NOT NULL,
    book_option_id      TEXT NOT NULL,
    payslip_id          TEXT,
    bank_transaction_id TEXT,
    agi_year            INTEGER,
    agi_month           INTEGER,
    voucher_date        DATE,
    status              TEXT NOT NULL DEFAULT 'pending',
    created_by          TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolved_by         TEXT,
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (book_option_id) REFERENCES decision_options(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (payslip_id) REFERENCES payslips(id),
    FOREIGN KEY (bank_transaction_id) REFERENCES bank_transactions(id),
    CHECK (kind IN ('payslip', 'agi')),
    CHECK (
        (kind = 'payslip' AND payslip_id IS NOT NULL AND bank_transaction_id IS NOT NULL)
        OR (kind = 'agi' AND agi_year IS NOT NULL AND agi_month IS NOT NULL)
    ),
    CHECK (status IN ('pending', 'booked', 'declined', 'superseded', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_booking_proposals_pending
    ON payroll_booking_proposals(status, kind);

INSERT OR IGNORE INTO schema_version (version) VALUES (43);
