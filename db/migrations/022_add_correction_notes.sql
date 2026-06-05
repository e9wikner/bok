-- Migration 022: Add correction notes for draft correction suggestions

CREATE TABLE IF NOT EXISTS correction_notes (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    note_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    suggested_voucher_id TEXT,
    rejection_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP,
    resolved_at TIMESTAMP,
    CHECK(status IN ('pending', 'suggested', 'applied', 'dismissed', 'rejected')),
    FOREIGN KEY (voucher_id) REFERENCES vouchers(id),
    FOREIGN KEY (suggested_voucher_id) REFERENCES vouchers(id)
);

CREATE INDEX IF NOT EXISTS idx_correction_notes_voucher ON correction_notes(voucher_id);
CREATE INDEX IF NOT EXISTS idx_correction_notes_status ON correction_notes(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_correction_notes_active_voucher
    ON correction_notes(voucher_id)
    WHERE status IN ('pending', 'suggested');

INSERT OR IGNORE INTO schema_version (version) VALUES (22);
