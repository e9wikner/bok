-- Migration 054: a human's standing choice to have the salaries booked
-- automatically on the payment day
--
-- Service: services/payroll_auto.py. Test: tests/test_lon_automatisk.py.
--
-- With the choice on, the server creates the month's payroll run on its
-- payment day (the salary settings' `payment_day`, 25 by default), its
-- payslips, and one posted voucher per payslip dated the payment day:
-- debit 7000/7510, credit 2710/2730 and the net salary on the bank account
-- the statements are imported for. The payslip is the voucher's underlag.
-- The bank transaction is linked afterwards by the statement matching
-- (`services/statement_match.py`) when the statement is imported.
--
-- The choice is a logged-in human's press (`PUT /payroll/auto-booking`; the
-- API key gets `403 human_only`), like a reuse approval (migration 044) is
-- a human's standing approval. Each change is a new row; the current choice
-- is the newest row. A month is booked automatically only when its payment
-- day is on or after the day the choice was turned on, so turning it on never
-- books a month that already passed: that is the button's job.

BEGIN;

CREATE TABLE IF NOT EXISTS payroll_auto_booking_settings (
    id          TEXT PRIMARY KEY,
    enabled     BOOLEAN NOT NULL,
    set_by      TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER prevent_update_payroll_auto_booking_settings
BEFORE UPDATE ON payroll_auto_booking_settings
BEGIN SELECT RAISE(ABORT, 'payroll auto booking settings are append-only'); END;

CREATE TRIGGER prevent_delete_payroll_auto_booking_settings
BEFORE DELETE ON payroll_auto_booking_settings
BEGIN SELECT RAISE(ABORT, 'payroll auto booking settings are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (54);

COMMIT;
