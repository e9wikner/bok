-- Allow invoice drafts to represent the final sent/exported state.

CREATE TABLE IF NOT EXISTS invoice_drafts_new (
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
    CHECK(status IN ('draft', 'needs_review', 'sent', 'rejected'))
);

INSERT INTO invoice_drafts_new (
    id,
    customer_id,
    customer_name,
    customer_org_number,
    customer_email,
    invoice_date,
    due_date,
    reference,
    description,
    status,
    amount_ex_vat,
    vat_amount,
    amount_inc_vat,
    agent_summary,
    agent_confidence,
    agent_warnings,
    approved_invoice_id,
    approved_voucher_id,
    created_at,
    created_by,
    updated_at
)
SELECT
    id,
    customer_id,
    customer_name,
    customer_org_number,
    customer_email,
    invoice_date,
    due_date,
    reference,
    description,
    CASE WHEN status IN ('approved', 'booked') THEN 'sent' ELSE status END,
    amount_ex_vat,
    vat_amount,
    amount_inc_vat,
    agent_summary,
    agent_confidence,
    agent_warnings,
    approved_invoice_id,
    approved_voucher_id,
    created_at,
    created_by,
    updated_at
FROM invoice_drafts;

CREATE TABLE IF NOT EXISTS invoice_draft_rows_new (
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
    FOREIGN KEY(draft_id) REFERENCES invoice_drafts_new(id) ON DELETE CASCADE,
    FOREIGN KEY(article_id) REFERENCES articles(id),
    FOREIGN KEY(revenue_account) REFERENCES accounts(code),
    CHECK(quantity > 0),
    CHECK(unit_price >= 0),
    CHECK(vat_code IN ('MP1', 'MP2', 'MP3', 'MF'))
);

INSERT INTO invoice_draft_rows_new
SELECT * FROM invoice_draft_rows;

CREATE TABLE IF NOT EXISTS invoice_draft_attachments_new (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(draft_id) REFERENCES invoice_drafts_new(id) ON DELETE CASCADE,
    UNIQUE(draft_id, sha256)
);

INSERT INTO invoice_draft_attachments_new
SELECT * FROM invoice_draft_attachments;

DROP TABLE invoice_draft_attachments;
DROP TABLE invoice_draft_rows;
DROP TABLE invoice_drafts;
ALTER TABLE invoice_drafts_new RENAME TO invoice_drafts;
ALTER TABLE invoice_draft_rows_new RENAME TO invoice_draft_rows;
ALTER TABLE invoice_draft_attachments_new RENAME TO invoice_draft_attachments;

CREATE INDEX IF NOT EXISTS idx_invoice_drafts_status ON invoice_drafts(status);
CREATE INDEX IF NOT EXISTS idx_invoice_drafts_customer ON invoice_drafts(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoice_draft_rows_draft ON invoice_draft_rows(draft_id);
CREATE INDEX IF NOT EXISTS idx_invoice_draft_attachments_draft ON invoice_draft_attachments(draft_id);

INSERT INTO schema_version (version) VALUES (16);
