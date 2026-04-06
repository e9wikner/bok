-- Bokföringssystem - Initial Schema (Fas 1: Grundbokföring)
-- Database: SQLite
-- Regulatory: BFL, BFNAR 2013:2, BAS 2026

-- Räkenskapsår (Fiscal Years)
CREATE TABLE IF NOT EXISTS fiscal_years (
    id TEXT PRIMARY KEY,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    locked BOOLEAN NOT NULL DEFAULT 0,
    locked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(start_date, end_date),
    CHECK(start_date < end_date)
);

-- Redovisningsperioder (Accounting Periods)
-- One record per month within a fiscal year
CREATE TABLE IF NOT EXISTS periods (
    id TEXT PRIMARY KEY,
    fiscal_year_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    locked BOOLEAN NOT NULL DEFAULT 0,
    locked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(fiscal_year_id) REFERENCES fiscal_years(id),
    UNIQUE(fiscal_year_id, year, month),
    CHECK(month >= 1 AND month <= 12)
);

-- Konton (Chart of Accounts - BAS 2026)
CREATE TABLE IF NOT EXISTS accounts (
    code TEXT PRIMARY KEY,  -- e.g., "1510", "3011", "2610"
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,  -- asset, liability, equity, revenue, expense, vat_in, vat_out
    vat_code TEXT,  -- e.g., "MP1" (25%), "IP" (ingående)
    sru_code TEXT,  -- Skatteverkets rapporteringskoder
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense', 'vat_in', 'vat_out', 'correction'))
);

-- Verifikationer (Vouchers) - Append-only
-- Status: draft (can be changed), posted (immutable)
CREATE TABLE IF NOT EXISTS vouchers (
    id TEXT PRIMARY KEY,
    series TEXT NOT NULL,  -- "A", "B", etc. (B = corrections)
    number INTEGER NOT NULL,
    date DATE NOT NULL,
    period_id TEXT NOT NULL,
    fiscal_year_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, posted
    correction_of TEXT,  -- If this is a correction voucher, reference original voucher_id
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    posted_at TIMESTAMP,
    FOREIGN KEY(period_id) REFERENCES periods(id),
    FOREIGN KEY(fiscal_year_id) REFERENCES fiscal_years(id),
    FOREIGN KEY(correction_of) REFERENCES vouchers(id),
    UNIQUE(series, number, fiscal_year_id),
    CHECK(status IN ('draft', 'posted'))
);

-- Konteringsrader (Voucher Rows)
-- All amounts in öre (1 kr = 100 öre)
CREATE TABLE IF NOT EXISTS voucher_rows (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    account_code TEXT NOT NULL,
    debit INTEGER NOT NULL DEFAULT 0,  -- In öre (1 kr = 100)
    credit INTEGER NOT NULL DEFAULT 0,  -- In öre
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE,
    FOREIGN KEY(account_code) REFERENCES accounts(code),
    CHECK(debit >= 0 AND credit >= 0),
    CHECK((debit > 0 AND credit = 0) OR (debit = 0 AND credit > 0) OR (debit = 0 AND credit = 0))
);

-- Behandlingshistorik (Audit Log)
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,  -- voucher, period, account, etc
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- created, updated, posted, locked, deleted
    actor TEXT NOT NULL,  -- user ID or "system"
    payload TEXT,  -- JSON with before/after values
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Verifikationsbilagor (Voucher Attachments)
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE,
    UNIQUE(voucher_id, filename)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_vouchers_period ON vouchers(period_id);
CREATE INDEX IF NOT EXISTS idx_vouchers_series_number ON vouchers(series, number);
CREATE INDEX IF NOT EXISTS idx_vouchers_status ON vouchers(status);
CREATE INDEX IF NOT EXISTS idx_vouchers_date ON vouchers(date);
CREATE INDEX IF NOT EXISTS idx_voucher_rows_voucher ON voucher_rows(voucher_id);
CREATE INDEX IF NOT EXISTS idx_voucher_rows_account ON voucher_rows(account_code);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_periods_fiscal_year ON periods(fiscal_year_id);
CREATE INDEX IF NOT EXISTS idx_attachments_voucher ON attachments(voucher_id);

-- Version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_version (version) VALUES (1);
