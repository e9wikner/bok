-- Drop legacy AI rule/pattern tables. Agent guidance now lives in agent_instructions.
-- Correction history remains, but no longer references learning_rules.

CREATE TABLE IF NOT EXISTS correction_history_new (
    id TEXT PRIMARY KEY,
    original_voucher_id TEXT NOT NULL,
    corrected_voucher_id TEXT,
    original_data JSON,
    corrected_data JSON,
    change_type TEXT,
    was_successful BOOLEAN,
    corrected_by TEXT,
    correction_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (original_voucher_id) REFERENCES vouchers(id)
);

INSERT INTO correction_history_new (
    id,
    original_voucher_id,
    corrected_voucher_id,
    original_data,
    corrected_data,
    change_type,
    was_successful,
    corrected_by,
    correction_reason,
    created_at
)
SELECT
    id,
    original_voucher_id,
    corrected_voucher_id,
    original_data,
    corrected_data,
    change_type,
    was_successful,
    corrected_by,
    correction_reason,
    created_at
FROM correction_history;

DROP TABLE IF EXISTS correction_history;
ALTER TABLE correction_history_new RENAME TO correction_history;

CREATE INDEX IF NOT EXISTS idx_correction_history_voucher ON correction_history(original_voucher_id);

DROP TABLE IF EXISTS accounting_pattern_evaluation_cases;
DROP TABLE IF EXISTS accounting_pattern_evaluations;
DROP TABLE IF EXISTS accounting_pattern_examples;
DROP TABLE IF EXISTS accounting_patterns;
DROP TABLE IF EXISTS learning_rules;
