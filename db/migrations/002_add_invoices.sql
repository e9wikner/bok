-- Fas 2: Fakturering & Moms (Invoicing & VAT)
-- Adds tables for invoices, payments, credit notes

-- Kundfakturor (Customer Invoices)
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    invoice_number TEXT NOT NULL UNIQUE,  -- e.g., "20260301001"
    customer_name TEXT NOT NULL,
    customer_org_number TEXT,  -- Swedish org number (personnummer/orgnr)
    customer_email TEXT,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, sent, partially_paid, paid, overdue, cancelled
    amount_ex_vat INTEGER NOT NULL DEFAULT 0,  -- In öre
    vat_amount INTEGER NOT NULL DEFAULT 0,  -- In öre
    amount_inc_vat INTEGER NOT NULL DEFAULT 0,  -- In öre
    paid_amount INTEGER NOT NULL DEFAULT 0,  -- Cumulative in öre
    voucher_id TEXT,  -- Linked to accounting voucher
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    sent_at TIMESTAMP,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    CHECK(due_date >= invoice_date),
    CHECK(status IN ('draft', 'sent', 'partially_paid', 'paid', 'overdue', 'cancelled'))
);

-- Invoice rows
CREATE TABLE IF NOT EXISTS invoice_rows (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,  -- In öre
    vat_code TEXT NOT NULL,  -- MP1 (25%), MP2 (12%), MP3 (6%), MF (0%)
    amount_ex_vat INTEGER NOT NULL,  -- quantity * unit_price in öre
    vat_amount INTEGER NOT NULL,  -- Calculated VAT in öre
    amount_inc_vat INTEGER NOT NULL,  -- amount_ex_vat + vat_amount in öre
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    CHECK(quantity > 0),
    CHECK(unit_price >= 0),
    CHECK(vat_code IN ('MP1', 'MP2', 'MP3', 'MF'))
);

-- Payments
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    amount INTEGER NOT NULL,  -- In öre
    payment_date DATE NOT NULL,
    payment_method TEXT NOT NULL,  -- bank_transfer, card, cash, etc
    reference TEXT,
    voucher_id TEXT,  -- Linked to payment accounting voucher
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    FOREIGN KEY(invoice_id) REFERENCES invoices(id),
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    CHECK(amount > 0)
);

-- Kreditfakturor (Credit Notes)
CREATE TABLE IF NOT EXISTS credit_notes (
    id TEXT PRIMARY KEY,
    credit_note_number TEXT NOT NULL UNIQUE,  -- e.g., "CN-20260301-ABCD1234"
    invoice_id TEXT NOT NULL,
    reason TEXT NOT NULL,  -- Reason for credit
    amount_ex_vat INTEGER NOT NULL,  -- In öre
    vat_amount INTEGER NOT NULL,  -- In öre
    amount_inc_vat INTEGER NOT NULL,  -- In öre
    credit_date DATE NOT NULL,
    voucher_id TEXT,  -- Linked to accounting voucher
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    FOREIGN KEY(invoice_id) REFERENCES invoices(id),
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    CHECK(amount_ex_vat > 0)
);

-- Momsrapportering (VAT Reporting)
-- Summary table for monthly VAT returns
CREATE TABLE IF NOT EXISTS vat_reports (
    id TEXT PRIMARY KEY,
    period_id TEXT NOT NULL,
    report_date DATE NOT NULL,
    total_sales_ex_vat INTEGER NOT NULL DEFAULT 0,
    total_vat_25 INTEGER NOT NULL DEFAULT 0,
    total_vat_12 INTEGER NOT NULL DEFAULT 0,
    total_vat_6 INTEGER NOT NULL DEFAULT 0,
    total_input_vat INTEGER NOT NULL DEFAULT 0,
    net_vat_due INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, submitted, paid
    submitted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(period_id) REFERENCES periods(id),
    UNIQUE(period_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_name);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON invoices(due_date);
CREATE INDEX IF NOT EXISTS idx_invoice_rows_invoice ON invoice_rows(invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);
CREATE INDEX IF NOT EXISTS idx_credit_notes_invoice ON credit_notes(invoice_id);
CREATE INDEX IF NOT EXISTS idx_vat_reports_period ON vat_reports(period_id);

-- Update schema version
INSERT INTO schema_version (version) VALUES (2);
