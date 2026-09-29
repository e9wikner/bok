-- Migration 038: utfärdade fakturor (fakturering F0).
-- Spec: docs/redesign/SPEC-fakturering.md §4. Test: tests/test_fakturering_f0.py 8.
--
-- New columns go in with ALTER TABLE ADD COLUMN, except on `invoice_drafts`.
-- Its status CHECK (from 016) lists the allowed values, and SQLite cannot
-- change a CHECK in place, so that one table is rebuilt to allow `issued`.
-- The five new draft columns are part of the rebuilt table. The column list is
-- today's actual one: no migration after 016 touches `invoice_drafts`.
--
-- The rebuild follows 016/027:
--  * Foreign keys are OFF, or DROP TABLE runs as an implicit DELETE and
--    cascades away every row in invoice_draft_rows and
--    invoice_draft_attachments. The PRAGMA is a no-op inside a transaction, so
--    it stands before BEGIN (Database.init_db runs this file with
--    executescript, in autocommit).
--  * Only `invoice_drafts` is rebuilt. The foreign keys in invoice_draft_rows,
--    invoice_draft_attachments and (below) invoices.source_draft_id name
--    `invoice_drafts` and resolve to the rebuilt table after the rename, so
--    their rows stay where they are. No trigger or view names
--    `invoice_drafts`.
--
-- The triggers at the end make an issued invoice (issued_at IS NOT NULL)
-- append-only: only status and paid_amount may change. Invoices from before
-- F0 have issued_at NULL and are not affected. The UPDATE trigger lists every
-- other column of `invoices` by name; a later migration that adds a column to
-- `invoices` must re-create it with that column in the list.

PRAGMA foreign_keys = OFF;

BEGIN;

-- §4.1–4.4: invoice_drafts, rebuilt with status `issued` and the new columns.
CREATE TABLE invoice_drafts_new (
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
    invoice_number TEXT,        -- proposed; not unique (§4.1)
    customer_address TEXT,      -- copied from customers.address (§4.3)
    delivery_from DATE,         -- default delivery for rows without one (§4.2)
    delivery_to DATE,
    delivery_month TEXT,        -- YYYY-MM
    FOREIGN KEY(customer_id) REFERENCES customers(id),
    FOREIGN KEY(approved_invoice_id) REFERENCES invoices(id),
    FOREIGN KEY(approved_voucher_id) REFERENCES vouchers(id),
    CHECK(due_date >= invoice_date),
    CHECK(status IN ('draft', 'needs_review', 'sent', 'rejected', 'issued'))
);

INSERT INTO invoice_drafts_new (
    id, customer_id, customer_name, customer_org_number, customer_email,
    invoice_date, due_date, reference, description, status,
    amount_ex_vat, vat_amount, amount_inc_vat,
    agent_summary, agent_confidence, agent_warnings,
    approved_invoice_id, approved_voucher_id,
    created_at, created_by, updated_at
)
SELECT
    id, customer_id, customer_name, customer_org_number, customer_email,
    invoice_date, due_date, reference, description, status,
    amount_ex_vat, vat_amount, amount_inc_vat,
    agent_summary, agent_confidence, agent_warnings,
    approved_invoice_id, approved_voucher_id,
    created_at, created_by, updated_at
FROM invoice_drafts;

DROP TABLE invoice_drafts;
ALTER TABLE invoice_drafts_new RENAME TO invoice_drafts;

-- Indexes from 016
CREATE INDEX idx_invoice_drafts_status ON invoice_drafts(status);
CREATE INDEX idx_invoice_drafts_customer ON invoice_drafts(customer_id);

-- §4.2: rows get unit, decimal quantity, delivery and article number.
-- quantity_centi is the quantity times 100; existing rows get quantity * 100.
ALTER TABLE invoice_draft_rows ADD COLUMN unit TEXT NOT NULL DEFAULT 'st';
ALTER TABLE invoice_draft_rows ADD COLUMN quantity_centi INTEGER
    CHECK(quantity_centi > 0);
ALTER TABLE invoice_draft_rows ADD COLUMN delivery_from DATE;
ALTER TABLE invoice_draft_rows ADD COLUMN delivery_to DATE;
ALTER TABLE invoice_draft_rows ADD COLUMN delivery_month TEXT;
ALTER TABLE invoice_draft_rows ADD COLUMN article_number TEXT;
UPDATE invoice_draft_rows SET quantity_centi = quantity * 100;

ALTER TABLE invoice_rows ADD COLUMN unit TEXT NOT NULL DEFAULT 'st';
ALTER TABLE invoice_rows ADD COLUMN quantity_centi INTEGER
    CHECK(quantity_centi > 0);
ALTER TABLE invoice_rows ADD COLUMN delivery_from DATE;
ALTER TABLE invoice_rows ADD COLUMN delivery_to DATE;
ALTER TABLE invoice_rows ADD COLUMN delivery_month TEXT;
ALTER TABLE invoice_rows ADD COLUMN article_number TEXT;
UPDATE invoice_rows SET quantity_centi = quantity * 100;

-- §4.3: the customer on the invoice.
ALTER TABLE invoices ADD COLUMN customer_address TEXT;
ALTER TABLE invoices ADD COLUMN payment_terms_days INTEGER;
ALTER TABLE invoices ADD COLUMN customer_reference TEXT;
ALTER TABLE customers ADD COLUMN contact_person TEXT;

-- §4.4: issuing. ADD COLUMN cannot carry UNIQUE, so the uniqueness of
-- source_draft_id is a unique index (several NULLs are allowed).
ALTER TABLE invoices ADD COLUMN source_draft_id TEXT
    REFERENCES invoice_drafts(id);
ALTER TABLE invoices ADD COLUMN pdf_sha256 TEXT;
ALTER TABLE invoices ADD COLUMN pdf_path TEXT;
ALTER TABLE invoices ADD COLUMN issued_at TIMESTAMP;
ALTER TABLE invoices ADD COLUMN issued_by TEXT;

CREATE UNIQUE INDEX idx_invoices_source_draft ON invoices(source_draft_id);

-- §4.4: an issued invoice is append-only. Only status and paid_amount change.
CREATE TRIGGER prevent_update_issued_invoices
BEFORE UPDATE ON invoices
WHEN OLD.issued_at IS NOT NULL AND (
       NEW.id IS NOT OLD.id
    OR NEW.invoice_number IS NOT OLD.invoice_number
    OR NEW.customer_name IS NOT OLD.customer_name
    OR NEW.customer_org_number IS NOT OLD.customer_org_number
    OR NEW.customer_email IS NOT OLD.customer_email
    OR NEW.invoice_date IS NOT OLD.invoice_date
    OR NEW.due_date IS NOT OLD.due_date
    OR NEW.description IS NOT OLD.description
    OR NEW.amount_ex_vat IS NOT OLD.amount_ex_vat
    OR NEW.vat_amount IS NOT OLD.vat_amount
    OR NEW.amount_inc_vat IS NOT OLD.amount_inc_vat
    OR NEW.voucher_id IS NOT OLD.voucher_id
    OR NEW.created_at IS NOT OLD.created_at
    OR NEW.created_by IS NOT OLD.created_by
    OR NEW.sent_at IS NOT OLD.sent_at
    OR NEW.customer_address IS NOT OLD.customer_address
    OR NEW.payment_terms_days IS NOT OLD.payment_terms_days
    OR NEW.customer_reference IS NOT OLD.customer_reference
    OR NEW.source_draft_id IS NOT OLD.source_draft_id
    OR NEW.pdf_sha256 IS NOT OLD.pdf_sha256
    OR NEW.pdf_path IS NOT OLD.pdf_path
    OR NEW.issued_at IS NOT OLD.issued_at
    OR NEW.issued_by IS NOT OLD.issued_by
)
BEGIN
    SELECT RAISE(ABORT, 'issued invoices are immutable except status and paid_amount');
END;

CREATE TRIGGER prevent_delete_issued_invoices
BEFORE DELETE ON invoices
WHEN OLD.issued_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'issued invoices are immutable');
END;

-- A row may neither change nor move into or out of an issued invoice.
CREATE TRIGGER prevent_update_rows_for_issued_invoices
BEFORE UPDATE ON invoice_rows
WHEN EXISTS (
    SELECT 1 FROM invoices
    WHERE invoices.id IN (OLD.invoice_id, NEW.invoice_id)
      AND invoices.issued_at IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT, 'rows for issued invoices are immutable');
END;

CREATE TRIGGER prevent_delete_rows_for_issued_invoices
BEFORE DELETE ON invoice_rows
WHEN EXISTS (
    SELECT 1 FROM invoices
    WHERE invoices.id = OLD.invoice_id
      AND invoices.issued_at IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT, 'rows for issued invoices are immutable');
END;

INSERT OR IGNORE INTO schema_version (version) VALUES (38);

COMMIT;

PRAGMA foreign_keys = ON;
