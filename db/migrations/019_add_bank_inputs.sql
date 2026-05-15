-- Migration 019: Bank input uploads and bank-driven voucher traceability
-- Stores uploaded bank CSV source material separately from voucher intake.

CREATE TABLE IF NOT EXISTS bank_inputs (
    id TEXT PRIMARY KEY,
    bank_connection_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detected_format TEXT,
    imported_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    parse_error TEXT,
    processed_at TIMESTAMP,
    UNIQUE(sha256),
    FOREIGN KEY(bank_connection_id) REFERENCES bank_connections(id),
    CHECK(status IN ('pending', 'processed', 'failed')),
    CHECK(size_bytes >= 0)
);

CREATE TABLE IF NOT EXISTS bank_input_transactions (
    id TEXT PRIMARY KEY,
    bank_input_id TEXT NOT NULL,
    bank_transaction_id TEXT NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(bank_input_id) REFERENCES bank_inputs(id),
    FOREIGN KEY(bank_transaction_id) REFERENCES bank_transactions(id),
    UNIQUE(bank_input_id, bank_transaction_id)
);

CREATE TABLE IF NOT EXISTS voucher_bank_inputs (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    bank_input_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    FOREIGN KEY(bank_input_id) REFERENCES bank_inputs(id),
    UNIQUE(voucher_id, bank_input_id)
);

CREATE TABLE IF NOT EXISTS voucher_bank_transactions (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    bank_transaction_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    FOREIGN KEY(bank_transaction_id) REFERENCES bank_transactions(id),
    UNIQUE(voucher_id, bank_transaction_id),
    UNIQUE(bank_transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_bank_inputs_status ON bank_inputs(status);
CREATE INDEX IF NOT EXISTS idx_bank_inputs_sha256 ON bank_inputs(sha256);
CREATE INDEX IF NOT EXISTS idx_bank_inputs_connection ON bank_inputs(bank_connection_id);
CREATE INDEX IF NOT EXISTS idx_bank_inputs_uploaded_at ON bank_inputs(uploaded_at);
CREATE INDEX IF NOT EXISTS idx_bank_input_tx_input ON bank_input_transactions(bank_input_id);
CREATE INDEX IF NOT EXISTS idx_bank_input_tx_transaction ON bank_input_transactions(bank_transaction_id);
CREATE INDEX IF NOT EXISTS idx_voucher_bank_inputs_voucher ON voucher_bank_inputs(voucher_id);
CREATE INDEX IF NOT EXISTS idx_voucher_bank_inputs_input ON voucher_bank_inputs(bank_input_id);
CREATE INDEX IF NOT EXISTS idx_voucher_bank_tx_voucher ON voucher_bank_transactions(voucher_id);
CREATE INDEX IF NOT EXISTS idx_voucher_bank_tx_transaction ON voucher_bank_transactions(bank_transaction_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (19);
