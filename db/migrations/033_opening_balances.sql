-- Migration 033: ingående balans som saldo, inte verifikation
--
-- IB is state carried over from the previous fiscal year's closing balance,
-- not a business transaction, so it no longer lives in an `IB`-series
-- voucher. For a year with a preceding fiscal year in the books it is
-- derived on read (services/opening_balance.py): the previous year's
-- closing position, its unclosed result on 2099. Only the first year in the
-- books needs it entered, and that is what this table holds -- the IB as
-- stated (an SIE4 file's `#IB 0`, or typed in). For later years a stated IB
-- is kept for reconciliation only; the derived one is what counts.
--
-- amount: öre, debit positive (SIE4 sign convention).
--
-- The draft IB vouchers the SIE4 import used to leave behind are moved here
-- and deleted (drafts, so BFL's append-only rule does not apply). A posted
-- IB voucher stays -- posted vouchers are never removed -- and its rows are
-- copied here. Every consumer now ignores the `IB` series as movement.

CREATE TABLE opening_balances (
    fiscal_year_id TEXT NOT NULL REFERENCES fiscal_years(id),
    account_code   TEXT NOT NULL REFERENCES accounts(code),
    amount         INTEGER NOT NULL,
    updated_by     TEXT NOT NULL,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (fiscal_year_id, account_code),
    CHECK (amount != 0)
);

-- One IB voucher per year: the posted one if the year has one, else the
-- (latest) draft.
INSERT INTO opening_balances (fiscal_year_id, account_code, amount, updated_by)
SELECT v.fiscal_year_id, vr.account_code, SUM(vr.debit - vr.credit), 'migration_033'
FROM vouchers v
JOIN voucher_rows vr ON vr.voucher_id = v.id
WHERE v.id = (
    SELECT c.id FROM vouchers c
    WHERE c.series = 'IB' AND c.fiscal_year_id = v.fiscal_year_id
    ORDER BY c.status = 'posted' DESC, c.created_at DESC
    LIMIT 1
)
GROUP BY v.fiscal_year_id, vr.account_code
HAVING SUM(vr.debit - vr.credit) != 0;

INSERT INTO audit_log (id, entity_type, entity_id, action, actor, payload, timestamp)
SELECT lower(hex(randomblob(16))), 'voucher', v.id, 'deleted', 'migration_033',
       json_object(
           'reason', 'IB-utkast ersatt av ingående balans som saldo',
           'series', v.series,
           'fiscal_year_id', v.fiscal_year_id,
           'description', v.description,
           'rows', (
               SELECT json_group_array(json_object(
                   'account', r.account_code, 'debit', r.debit, 'credit', r.credit))
               FROM voucher_rows r WHERE r.voucher_id = v.id
           )
       ),
       CURRENT_TIMESTAMP
FROM vouchers v
WHERE v.series = 'IB' AND v.status = 'draft';

DELETE FROM voucher_rows
WHERE voucher_id IN (SELECT id FROM vouchers WHERE series = 'IB' AND status = 'draft');
DELETE FROM vouchers WHERE series = 'IB' AND status = 'draft';

-- A locked fiscal year's stated IB is as fixed as the rest of the year.
CREATE TRIGGER prevent_insert_opening_balances_locked_year
BEFORE INSERT ON opening_balances
WHEN (SELECT locked FROM fiscal_years WHERE id = NEW.fiscal_year_id) = 1
BEGIN SELECT RAISE(ABORT, 'fiscal year is locked'); END;

CREATE TRIGGER prevent_update_opening_balances_locked_year
BEFORE UPDATE ON opening_balances
WHEN (SELECT locked FROM fiscal_years WHERE id = OLD.fiscal_year_id) = 1
BEGIN SELECT RAISE(ABORT, 'fiscal year is locked'); END;

CREATE TRIGGER prevent_delete_opening_balances_locked_year
BEFORE DELETE ON opening_balances
WHEN (SELECT locked FROM fiscal_years WHERE id = OLD.fiscal_year_id) = 1
BEGIN SELECT RAISE(ABORT, 'fiscal year is locked'); END;

INSERT INTO schema_version (version) VALUES (33);
