-- Enforce immutability for posted vouchers at database level

CREATE TRIGGER IF NOT EXISTS prevent_update_posted_vouchers
BEFORE UPDATE ON vouchers
WHEN OLD.status = 'posted'
BEGIN
    SELECT RAISE(ABORT, 'posted vouchers are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_posted_vouchers
BEFORE DELETE ON vouchers
WHEN OLD.status = 'posted'
BEGIN
    SELECT RAISE(ABORT, 'posted vouchers are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_update_rows_for_posted_vouchers
BEFORE UPDATE ON voucher_rows
WHEN EXISTS (
    SELECT 1 FROM vouchers
    WHERE vouchers.id = OLD.voucher_id
      AND vouchers.status = 'posted'
)
BEGIN
    SELECT RAISE(ABORT, 'rows for posted vouchers are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_rows_for_posted_vouchers
BEFORE DELETE ON voucher_rows
WHEN EXISTS (
    SELECT 1 FROM vouchers
    WHERE vouchers.id = OLD.voucher_id
      AND vouchers.status = 'posted'
)
BEGIN
    SELECT RAISE(ABORT, 'rows for posted vouchers are immutable');
END;

INSERT INTO schema_version (version) VALUES (14);
