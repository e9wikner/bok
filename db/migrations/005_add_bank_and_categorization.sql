-- Migration 005: Bank integration, auto-categorization, and BFL compliance
-- Adds tables for bank connections, transactions, categorization rules, and compliance checks

-- Bank connections (Tink/Open Banking)
CREATE TABLE IF NOT EXISTS bank_connections (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'tink',  -- tink, plaid, manual
    bank_name TEXT NOT NULL,
    account_number TEXT,  -- masked, e.g. "****1234"
    iban TEXT,
    currency TEXT NOT NULL DEFAULT 'SEK',
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, active, expired, error
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    consent_expires_at TIMESTAMP,
    last_sync_at TIMESTAMP,
    sync_from_date DATE,
    metadata TEXT,  -- JSON: extra provider data
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Bank transactions (imported from bank)
CREATE TABLE IF NOT EXISTS bank_transactions (
    id TEXT PRIMARY KEY,
    bank_connection_id TEXT NOT NULL REFERENCES bank_connections(id),
    external_id TEXT,  -- ID from bank/provider (for dedup)
    transaction_date DATE NOT NULL,
    booking_date DATE,
    amount INTEGER NOT NULL,  -- In öre, negative = expense
    currency TEXT NOT NULL DEFAULT 'SEK',
    description TEXT,
    counterpart_name TEXT,  -- Motpart
    counterpart_account TEXT,
    reference TEXT,
    category_code TEXT,  -- Provider category if available
    raw_data TEXT,  -- JSON: full transaction from provider
    -- Processing status
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, categorized, booked, ignored, manual
    matched_voucher_id TEXT REFERENCES vouchers(id),
    suggested_account_code TEXT,
    suggested_confidence REAL DEFAULT 0.0,  -- 0.0-1.0
    categorized_at TIMESTAMP,
    booked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bank_connection_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_bank_tx_status ON bank_transactions(status);
CREATE INDEX IF NOT EXISTS idx_bank_tx_date ON bank_transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_bank_tx_connection ON bank_transactions(bank_connection_id);

-- Categorization rules (learned patterns)
CREATE TABLE IF NOT EXISTS categorization_rules (
    id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL,  -- keyword, regex, counterpart, amount_range, learned
    priority INTEGER NOT NULL DEFAULT 100,  -- Lower = higher priority
    -- Match criteria (any combination)
    match_description TEXT,  -- Keyword or regex pattern
    match_counterpart TEXT,
    match_amount_min INTEGER,  -- öre
    match_amount_max INTEGER,  -- öre
    match_is_expense INTEGER,  -- 1 = expense, 0 = income, NULL = both
    -- Result
    target_account_code TEXT NOT NULL,
    target_vat_code TEXT,  -- MP1, MP2, MP3, MF
    target_description_template TEXT,  -- e.g. "Kontorsmaterial {counterpart}"
    -- Metadata
    confidence REAL NOT NULL DEFAULT 1.0,  -- Rules = 1.0, learned < 1.0
    times_used INTEGER NOT NULL DEFAULT 0,
    times_overridden INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',  -- manual, learned, system
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cat_rules_active ON categorization_rules(active, priority);

-- BFL compliance checks log
CREATE TABLE IF NOT EXISTS compliance_checks (
    id TEXT PRIMARY KEY,
    check_type TEXT NOT NULL,  -- voucher_timeliness, period_closing, balance_check, vat_deadline, etc
    severity TEXT NOT NULL DEFAULT 'warning',  -- info, warning, error, critical
    status TEXT NOT NULL DEFAULT 'open',  -- open, acknowledged, resolved, false_positive
    entity_type TEXT,  -- voucher, period, account, transaction
    entity_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    recommendation TEXT,
    deadline DATE,  -- When must this be resolved?
    resolved_at TIMESTAMP,
    resolved_by TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_compliance_status ON compliance_checks(status, severity);
CREATE INDEX IF NOT EXISTS idx_compliance_type ON compliance_checks(check_type);

-- Default categorization rules for Swedish small businesses
INSERT OR IGNORE INTO categorization_rules (id, rule_type, priority, match_description, match_is_expense, target_account_code, target_vat_code, target_description_template, source) VALUES
-- Income patterns
('rule-swish-income', 'keyword', 10, 'swish', 0, '3011', 'MP1', 'Swish-betalning', 'system'),
('rule-bankgiro-income', 'keyword', 20, 'bankgiro', 0, '3011', 'MP1', 'Bankgiro-inbetalning', 'system'),

-- Common expense patterns
('rule-hyra', 'keyword', 10, 'hyra', 1, '5010', 'MF', 'Lokalhyra', 'system'),
('rule-el', 'keyword', 10, 'ellevio|vattenfall|eon|fortum', 1, '5020', 'MP1', 'El och uppvärmning', 'system'),
('rule-telefon', 'keyword', 10, 'telia|tele2|telenor|tre|hallon', 1, '6211', 'MP1', 'Telekommunikation', 'system'),
('rule-internet', 'keyword', 10, 'bredband|fiber|comhem|bahnhof', 1, '6230', 'MP1', 'Internet', 'system'),
('rule-forsakring', 'keyword', 10, 'försäkring|trygg.hansa|if |folksam|länsförsäkr', 1, '6310', 'MF', 'Försäkring', 'system'),
('rule-kontorsmtrl', 'keyword', 20, 'clas ohlson|biltema|jula|dustin|kjell', 1, '6110', 'MP1', 'Kontorsmaterial', 'system'),
('rule-resekostnader', 'keyword', 20, 'sj |sas|flygbuss|taxi|uber|bolt', 1, '5810', 'MP1', 'Resekostnader', 'system'),
('rule-drivmedel', 'keyword', 20, 'circle k|ingo|okq8|preem|st1|shell', 1, '5611', 'MP1', 'Drivmedel', 'system'),
('rule-representation', 'keyword', 20, 'restaurang|lunch|middag|fika', 1, '6071', 'MP1', 'Representation', 'system'),
('rule-programvara', 'keyword', 20, 'google|microsoft|adobe|github|slack|zoom|spotify', 1, '6540', 'MP1', 'Programvara och licenser', 'system'),
('rule-bank', 'keyword', 5, 'bankavgift|kontoavgift|kortavgift', 1, '6570', 'MF', 'Bankavgifter', 'system'),
('rule-skatteverket', 'keyword', 5, 'skatteverket', 1, '2510', NULL, 'Skatteinbetalning', 'system'),
('rule-lon', 'keyword', 5, 'lön|löne', 1, '7010', NULL, 'Löneutbetalning', 'system'),
('rule-arbetsgivaravg', 'keyword', 5, 'arbetsgivaravgift', 1, '7510', NULL, 'Arbetsgivaravgifter', 'system'),

-- Swish patterns  
('rule-swish-expense', 'keyword', 15, 'swish', 1, '6990', 'MP1', 'Swish-betalning (övrig kostnad)', 'system');

-- Update schema version
INSERT OR IGNORE INTO schema_version (version) VALUES (5);
