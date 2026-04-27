-- Migration: Rebuild SRU mappings FK to reference account codes.
--
-- Migration 009 incorrectly referenced accounts(id), but accounts are keyed by
-- code. Preserve mappings that already store account codes and drop impossible
-- rows that point at non-existent account identifiers.

PRAGMA foreign_keys = OFF;

CREATE TABLE account_sru_mappings_new (
    id TEXT PRIMARY KEY,
    fiscal_year_id TEXT NOT NULL REFERENCES fiscal_years(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(code) ON DELETE CASCADE,
    sru_field VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fiscal_year_id, account_id)
);

INSERT INTO account_sru_mappings_new (
    id,
    fiscal_year_id,
    account_id,
    sru_field,
    created_at,
    updated_at
)
SELECT
    m.id,
    m.fiscal_year_id,
    m.account_id,
    m.sru_field,
    m.created_at,
    m.updated_at
FROM account_sru_mappings m
JOIN accounts a ON a.code = m.account_id;

DROP TABLE account_sru_mappings;

ALTER TABLE account_sru_mappings_new RENAME TO account_sru_mappings;

CREATE INDEX IF NOT EXISTS idx_account_sru_mappings_fiscal_year
    ON account_sru_mappings(fiscal_year_id);

CREATE INDEX IF NOT EXISTS idx_account_sru_mappings_field
    ON account_sru_mappings(sru_field);

PRAGMA foreign_keys = ON;
