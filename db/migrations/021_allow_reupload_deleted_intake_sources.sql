-- Migration 021: Allow re-upload of deleted intake sources
-- Replaces the full UNIQUE(sha256) table constraint with a partial unique index
-- that excludes soft-deleted sources, so users can re-upload a file after deleting it.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE _intake_sources_new (
    id TEXT PRIMARY KEY,
    source_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    explanation TEXT,
    agent_guidance TEXT,
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    deleted_by TEXT,
    CHECK(source_type IS NULL OR source_type IN ('receipt', 'supplier_invoice', 'customer_invoice', 'reimbursement', 'other')),
    CHECK(status IN ('pending', 'processing', 'processed', 'skipped', 'failed', 'needs_attention', 'deleted')),
    CHECK(size_bytes >= 0)
);

INSERT INTO _intake_sources_new
SELECT id, source_type, status, original_filename, mime_type, size_bytes,
       sha256, stored_path, explanation, agent_guidance, uploaded_by,
       uploaded_at, deleted_at, deleted_by
FROM intake_sources;

DROP TABLE intake_sources;

ALTER TABLE _intake_sources_new RENAME TO intake_sources;

CREATE INDEX idx_intake_sources_status ON intake_sources(status);
CREATE INDEX idx_intake_sources_sha256 ON intake_sources(sha256);
CREATE UNIQUE INDEX idx_intake_sources_sha256_active ON intake_sources(sha256) WHERE status != 'deleted';

COMMIT;

PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO schema_version (version) VALUES (21);
