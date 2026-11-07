-- Migration 037: the voucher that books a month's arbetsgivardeklaration
--
-- Booking the AGI moves the month's withheld tax (2710) and employer fees
-- (2730) to the tax account (1630), as two vouchers: the tax account debits
-- them as two transactions, and a statement transaction is matched to a
-- voucher by its whole amount on 1630. Each row records which voucher booked
-- which part (`kind`), so the same part is not booked twice. Like the other links to posted
-- vouchers it is append-only: a wrong booking is reversed with a B-series
-- voucher, and a month whose booking voucher is reversed may be booked again.

CREATE TABLE IF NOT EXISTS payroll_agi_bookings (
    id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    kind TEXT NOT NULL,
    voucher_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    CHECK(month >= 1 AND month <= 12),
    CHECK(kind IN ('tax', 'employer_fee'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_agi_bookings_period
    ON payroll_agi_bookings(year, month);

CREATE TRIGGER IF NOT EXISTS prevent_update_payroll_agi_bookings
BEFORE UPDATE ON payroll_agi_bookings
BEGIN SELECT RAISE(ABORT, 'payroll AGI bookings are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_payroll_agi_bookings
BEFORE DELETE ON payroll_agi_bookings
BEGIN SELECT RAISE(ABORT, 'payroll AGI bookings are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (37);
