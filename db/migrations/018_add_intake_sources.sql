-- Migration 018: Intake source material and voucher traceability
-- Stores voucher source files before vouchers exist and links them to posted vouchers.

CREATE TABLE IF NOT EXISTS intake_sources (
    id TEXT PRIMARY KEY,
    source_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    explanation TEXT,
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    deleted_by TEXT,
    UNIQUE(sha256),
    CHECK(source_type IS NULL OR source_type IN ('receipt', 'supplier_invoice', 'customer_invoice', 'reimbursement', 'other')),
    CHECK(status IN ('pending', 'processing', 'processed', 'skipped', 'failed', 'needs_attention', 'deleted')),
    CHECK(size_bytes >= 0)
);

CREATE TABLE IF NOT EXISTS intake_processing_attempts (
    id TEXT PRIMARY KEY,
    intake_source_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    warnings TEXT,
    error_detail TEXT,
    voucher_id TEXT,
    actor TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(intake_source_id) REFERENCES intake_sources(id),
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    CHECK(status IN ('processing', 'processed', 'failed'))
);

CREATE TABLE IF NOT EXISTS voucher_intake_sources (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    intake_source_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    link_reason TEXT,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    FOREIGN KEY(intake_source_id) REFERENCES intake_sources(id),
    UNIQUE(voucher_id, intake_source_id),
    UNIQUE(intake_source_id)
);

CREATE INDEX IF NOT EXISTS idx_intake_sources_status ON intake_sources(status);
CREATE INDEX IF NOT EXISTS idx_intake_sources_sha256 ON intake_sources(sha256);
CREATE INDEX IF NOT EXISTS idx_intake_attempts_source ON intake_processing_attempts(intake_source_id);
CREATE INDEX IF NOT EXISTS idx_intake_attempts_voucher ON intake_processing_attempts(voucher_id);
CREATE INDEX IF NOT EXISTS idx_voucher_intake_sources_voucher ON voucher_intake_sources(voucher_id);
CREATE INDEX IF NOT EXISTS idx_voucher_intake_sources_source ON voucher_intake_sources(intake_source_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (18);
