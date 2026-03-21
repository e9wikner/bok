-- Företagsinformation (Company Info)
-- Används av SIE4-export för att fylla i #FNAMN, #FORGN, #ADRESS etc.
-- Lagras som nyckel-värde-par för flexibilitet.

CREATE TABLE IF NOT EXISTS company_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index för snabb sökning
CREATE INDEX IF NOT EXISTS idx_company_info_key ON company_info(key);

-- Ytterligare index för SIE4-export: periodsaldon beräknas ofta
CREATE INDEX IF NOT EXISTS idx_voucher_rows_account_voucher ON voucher_rows(account_code, voucher_id);

-- Version tracking
INSERT INTO schema_version (version) VALUES (4);
