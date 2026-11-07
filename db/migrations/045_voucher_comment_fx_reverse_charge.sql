-- Migration 045: utlägg, utländsk valuta och omvänd skattskyldighet
--
-- Services: services/exchange_rates.py, services/reimbursement_check.py,
-- services/reimbursement_proposal.py. Test: tests/test_utlagg.py,
-- tests/test_exchange_rates.py.
--
-- 1. `vouchers.comment`: free text on the voucher beside its `description`.
--    The agent writes it when it posts or proposes the voucher; for a
--    purchase in a foreign currency the server writes the rate line itself
--    (which rate, for which date, from which source). It is set at INSERT,
--    and the triggers from 014/027 refuse any UPDATE of a posted voucher, so
--    a posted voucher's comment never changes. A draft's may.
--
-- 2. `exchange_rates`: Riksbank's daily rates the server has fetched. A rate
--    behind a posted voucher must be reproducible, so rows are append-only.
--    `requested_date` is the purchase date asked for; `observation_date` the
--    banking day the rate is from (the same day, or the last banking day
--    before it on a weekend or a holiday).
--
-- 3. `reimbursement_checks`: an underlag in Utlägg/ whose amount matches a
--    transaction in one of the company's statements. A purchase the company
--    paid is not an utlägg, so the agent may not book it against 2820 until a
--    human has said which it is (a decision card). While the card is pending
--    the underlag is out of the intake pass's queue
--    (`repositories/intake_repo.py`).
--
-- 4. Accounts the rules need: 2820 for the debt to the person who paid, and
--    the BAS accounts for reverse charge on services bought from abroad --
--    2614/2645 for the VAT, 4531/4535 against 4598 for the base (boxes 21,
--    22, 30 and 48 in the VAT return). `vat_declarations` gets a column for
--    each of boxes 21, 22 and 30.

ALTER TABLE vouchers ADD COLUMN comment TEXT;

CREATE TABLE IF NOT EXISTS exchange_rates (
    id                TEXT PRIMARY KEY,
    currency          TEXT NOT NULL,
    requested_date    DATE NOT NULL,
    observation_date  DATE NOT NULL,
    rate              TEXT NOT NULL,
    series_id         TEXT NOT NULL,
    source            TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    fetched_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(currency) = 3),
    CHECK (observation_date <= requested_date),
    UNIQUE (currency, requested_date)
);

CREATE TRIGGER IF NOT EXISTS prevent_update_exchange_rates
BEFORE UPDATE ON exchange_rates
BEGIN
    SELECT RAISE(ABORT, 'exchange rates are append-only');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_exchange_rates
BEFORE DELETE ON exchange_rates
BEGIN
    SELECT RAISE(ABORT, 'exchange rates are append-only');
END;

CREATE TABLE IF NOT EXISTS reimbursement_checks (
    id                     TEXT PRIMARY KEY,
    intake_source_id       TEXT NOT NULL,
    bank_transaction_id    TEXT NOT NULL,
    decision_id            TEXT NOT NULL UNIQUE,
    reimbursement_option_id TEXT NOT NULL,
    company_paid_option_id TEXT NOT NULL,
    thread_id              TEXT NOT NULL,
    status                 TEXT NOT NULL DEFAULT 'pending',
    created_by             TEXT NOT NULL,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at            TIMESTAMP,
    resolved_by            TEXT,
    FOREIGN KEY (intake_source_id) REFERENCES intake_sources(id),
    FOREIGN KEY (bank_transaction_id) REFERENCES bank_transactions(id),
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    CHECK (status IN ('pending', 'reimbursement', 'company_paid', 'declined',
                      'superseded'))
);

-- One pending card per underlag.
CREATE UNIQUE INDEX IF NOT EXISTS idx_reimbursement_checks_pending
    ON reimbursement_checks(intake_source_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_reimbursement_checks_source
    ON reimbursement_checks(intake_source_id);

-- The VAT return's reverse-charge boxes (services/vat_report.py).
ALTER TABLE vat_declarations ADD COLUMN purchases_services_eu INTEGER DEFAULT 0;
ALTER TABLE vat_declarations ADD COLUMN purchases_services_non_eu INTEGER DEFAULT 0;
ALTER TABLE vat_declarations ADD COLUMN vat_out_reverse_25 INTEGER DEFAULT 0;

INSERT OR IGNORE INTO accounts (code, name, account_type, active) VALUES
('2820', 'Kortfristiga skulder till anställda', 'liability', 1),
('2614', 'Utgående moms omvänd skattskyldighet, 25 %', 'vat_out', 1),
('2645', 'Beräknad ingående moms på förvärv från utlandet', 'vat_in', 1),
('4531', 'Import tjänster land utanför EU, 25 % moms', 'expense', 1),
('4535', 'Inköp av tjänster från annat EU-land, 25 %', 'expense', 1),
('4598', 'Justering, omvänd moms', 'expense', 1);

INSERT OR IGNORE INTO schema_version (version) VALUES (45);
