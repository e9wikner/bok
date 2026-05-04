-- Customers, articles and agent-created invoice drafts

CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    org_number TEXT,
    email TEXT,
    address TEXT,
    payment_terms_days INTEGER NOT NULL DEFAULT 30,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_org_number
ON customers(org_number)
WHERE org_number IS NOT NULL AND org_number != '';

CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    article_number TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    unit TEXT NOT NULL DEFAULT 'st',
    unit_price INTEGER NOT NULL DEFAULT 0,
    vat_code TEXT NOT NULL DEFAULT 'MP1',
    revenue_account TEXT NOT NULL DEFAULT '3010',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(revenue_account) REFERENCES accounts(code),
    CHECK(unit_price >= 0),
    CHECK(vat_code IN ('MP1', 'MP2', 'MP3', 'MF'))
);

CREATE TABLE IF NOT EXISTS invoice_drafts (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    customer_name TEXT NOT NULL,
    customer_org_number TEXT,
    customer_email TEXT,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    reference TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'needs_review',
    amount_ex_vat INTEGER NOT NULL DEFAULT 0,
    vat_amount INTEGER NOT NULL DEFAULT 0,
    amount_inc_vat INTEGER NOT NULL DEFAULT 0,
    agent_summary TEXT,
    agent_confidence REAL,
    agent_warnings TEXT,
    approved_invoice_id TEXT,
    approved_voucher_id TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES customers(id),
    FOREIGN KEY(approved_invoice_id) REFERENCES invoices(id),
    FOREIGN KEY(approved_voucher_id) REFERENCES vouchers(id),
    CHECK(due_date >= invoice_date),
    CHECK(status IN ('draft', 'needs_review', 'approved', 'booked', 'rejected'))
);

CREATE TABLE IF NOT EXISTS invoice_draft_rows (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    article_id TEXT,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    vat_code TEXT NOT NULL,
    revenue_account TEXT NOT NULL,
    amount_ex_vat INTEGER NOT NULL,
    vat_amount INTEGER NOT NULL,
    amount_inc_vat INTEGER NOT NULL,
    source_note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(draft_id) REFERENCES invoice_drafts(id) ON DELETE CASCADE,
    FOREIGN KEY(article_id) REFERENCES articles(id),
    FOREIGN KEY(revenue_account) REFERENCES accounts(code),
    CHECK(quantity > 0),
    CHECK(unit_price >= 0),
    CHECK(vat_code IN ('MP1', 'MP2', 'MP3', 'MF'))
);

CREATE TABLE IF NOT EXISTS invoice_draft_attachments (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(draft_id) REFERENCES invoice_drafts(id) ON DELETE CASCADE,
    UNIQUE(draft_id, sha256)
);

CREATE INDEX IF NOT EXISTS idx_invoice_drafts_status ON invoice_drafts(status);
CREATE INDEX IF NOT EXISTS idx_invoice_drafts_customer ON invoice_drafts(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoice_draft_rows_draft ON invoice_draft_rows(draft_id);
CREATE INDEX IF NOT EXISTS idx_invoice_draft_attachments_draft ON invoice_draft_attachments(draft_id);

ALTER TABLE invoice_rows ADD COLUMN revenue_account TEXT;

INSERT INTO schema_version (version) VALUES (11);
