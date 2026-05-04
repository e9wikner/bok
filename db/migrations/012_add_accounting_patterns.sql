-- Accounting pattern analysis and backtesting for agent rules

CREATE TABLE IF NOT EXISTS accounting_patterns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'suggested',
    match_type TEXT NOT NULL DEFAULT 'description',
    match_config_json TEXT NOT NULL,
    voucher_template_json TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    source TEXT NOT NULL DEFAULT 'analysis',
    sample_count INTEGER NOT NULL DEFAULT 0,
    last_analyzed_at TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_by TEXT,
    approved_at TIMESTAMP,
    CHECK(status IN ('suggested', 'active', 'rejected', 'archived')),
    CHECK(confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_accounting_patterns_status ON accounting_patterns(status);
CREATE INDEX IF NOT EXISTS idx_accounting_patterns_source ON accounting_patterns(source);
CREATE INDEX IF NOT EXISTS idx_accounting_patterns_confidence ON accounting_patterns(confidence DESC);

CREATE TABLE IF NOT EXISTS accounting_pattern_examples (
    id TEXT PRIMARY KEY,
    pattern_id TEXT NOT NULL,
    voucher_id TEXT NOT NULL,
    match_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(pattern_id) REFERENCES accounting_patterns(id) ON DELETE CASCADE,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    UNIQUE(pattern_id, voucher_id)
);

CREATE INDEX IF NOT EXISTS idx_accounting_pattern_examples_pattern ON accounting_pattern_examples(pattern_id);
CREATE INDEX IF NOT EXISTS idx_accounting_pattern_examples_voucher ON accounting_pattern_examples(voucher_id);

CREATE TABLE IF NOT EXISTS accounting_pattern_evaluations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    baseline_rule_ids_json TEXT NOT NULL,
    candidate_rule_ids_json TEXT NOT NULL,
    fiscal_year_id TEXT,
    date_from DATE,
    date_to DATE,
    status TEXT NOT NULL DEFAULT 'completed',
    summary_json TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    CHECK(status IN ('running', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_accounting_pattern_evaluations_created ON accounting_pattern_evaluations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_accounting_pattern_evaluations_status ON accounting_pattern_evaluations(status);

CREATE TABLE IF NOT EXISTS accounting_pattern_evaluation_cases (
    id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    voucher_id TEXT NOT NULL,
    baseline_result_json TEXT,
    candidate_result_json TEXT,
    actual_result_json TEXT NOT NULL,
    baseline_score REAL NOT NULL DEFAULT 0.0,
    candidate_score REAL NOT NULL DEFAULT 0.0,
    winner TEXT NOT NULL DEFAULT 'unchanged',
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(evaluation_id) REFERENCES accounting_pattern_evaluations(id) ON DELETE CASCADE,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    CHECK(winner IN ('baseline', 'candidate', 'unchanged', 'regression', 'none'))
);

CREATE INDEX IF NOT EXISTS idx_accounting_pattern_eval_cases_eval ON accounting_pattern_evaluation_cases(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_accounting_pattern_eval_cases_winner ON accounting_pattern_evaluation_cases(evaluation_id, winner);

INSERT INTO schema_version (version) VALUES (12);
