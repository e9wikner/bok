-- Migration: Add SRU mappings table for INK2 tax declaration support

CREATE TABLE IF NOT EXISTS account_sru_mappings (
    id TEXT PRIMARY KEY,
    fiscal_year_id TEXT NOT NULL REFERENCES fiscal_years(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    sru_field VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fiscal_year_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_account_sru_mappings_fiscal_year ON account_sru_mappings(fiscal_year_id);

CREATE INDEX IF NOT EXISTS idx_account_sru_mappings_field ON account_sru_mappings(sru_field);
