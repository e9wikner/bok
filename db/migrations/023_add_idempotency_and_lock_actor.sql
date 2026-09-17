-- Migration 023: Idempotency keys for irreversible writes, and lock actor on periods

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT NOT NULL,
    endpoint TEXT NOT NULL,              -- "POST /api/v1/agent/vouchers"
    request_fingerprint TEXT NOT NULL,   -- sha256 of canonicalised request body
    state TEXT NOT NULL,                 -- in_flight | completed
    response_status INTEGER,             -- set when completed
    response_body TEXT,                  -- JSON, set when completed
    entity_type TEXT,                    -- "voucher"
    entity_id TEXT,                      -- id of the created entity
    actor TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    PRIMARY KEY (key, endpoint),
    CHECK (state IN ('in_flight', 'completed'))
);

CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);

-- A lock must be able to answer who, not only when.
ALTER TABLE periods ADD COLUMN locked_by TEXT;

-- Backfill from the audit trail. A period locked before this migration without an
-- audit row keeps NULL: a historical gap must show as a gap, never be guessed.
UPDATE periods
SET locked_by = (
    SELECT actor FROM audit_log
    WHERE audit_log.entity_type = 'period'
      AND audit_log.entity_id = periods.id
      AND audit_log.action = 'locked'
    ORDER BY audit_log.timestamp DESC
    LIMIT 1
)
WHERE locked = 1;

INSERT OR IGNORE INTO schema_version (version) VALUES (23);
