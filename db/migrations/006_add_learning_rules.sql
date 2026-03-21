-- Migration 006: Add AI Learning Tables
-- Skapar tabeller för att spåra inlärda regler från användarkorrigeringar

-- Tabell för inlärda regler från korrigeringar
CREATE TABLE learning_rules (
    id TEXT PRIMARY KEY,
    company_id TEXT,  -- För multi-company support i framtiden
    
    -- Vad ska matchas
    pattern_type TEXT NOT NULL,  -- 'keyword', 'regex', 'counterparty', 'amount_range', 'composite'
    pattern_value TEXT NOT NULL, -- 'resa', 'hotel.*', 'Stefan Wikner', '1000-5000', etc.
    
    -- Vad ska ändras
    original_account TEXT,  -- NULL = nya transaktioner utan konto
    corrected_account TEXT NOT NULL,  -- 5610, 7690, etc.
    
    -- Metadata
    description TEXT,  -- Mänsklig läsbar förklaring: "Resor bör bokföras på 5610"
    confidence REAL DEFAULT 0.5,  -- 0.0-1.0, ökar med varje korrigering
    usage_count INTEGER DEFAULT 1,
    success_count INTEGER DEFAULT 1,  -- Hur många gånger regeln använts korrekt
    
    -- Källa
    source_voucher_id TEXT,  -- Vilken verifikation skapade denna regel
    created_by TEXT,  -- user_id eller 'ai'
    
    -- Tider
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    last_confirmed TIMESTAMP,  -- Senast en användare bekräftade regeln
    
    -- Status
    is_active BOOLEAN DEFAULT 1,
    is_golden BOOLEAN DEFAULT 0,  -- Manuellt bekräftad av redovisningskonsult
    
    FOREIGN KEY (source_voucher_id) REFERENCES vouchers(id)
);

-- Index för snabb lookup
CREATE INDEX idx_learning_rules_company ON learning_rules(company_id);
CREATE INDEX idx_learning_rules_pattern ON learning_rules(pattern_type, pattern_value);
CREATE INDEX idx_learning_rules_original ON learning_rules(original_account);
CREATE INDEX idx_learning_rules_confidence ON learning_rules(confidence DESC);
CREATE INDEX idx_learning_rules_active ON learning_rules(is_active, confidence DESC);

-- Tabell för att spåra korrigeringar (audit trail för ML)
CREATE TABLE correction_history (
    id TEXT PRIMARY KEY,
    learning_rule_id TEXT,
    original_voucher_id TEXT NOT NULL,
    corrected_voucher_id TEXT,
    
    -- Vad ändrades
    original_data JSON,  -- {'account': '5410', 'amount': 50000}
    corrected_data JSON, -- {'account': '5610', 'amount': 50000}
    
    -- Analys
    change_type TEXT,  -- 'account', 'amount', 'description', 'vat_code', 'multiple'
    was_successful BOOLEAN,  -- Ledde korrigeringen till rätt resultat?
    
    -- Metadata
    corrected_by TEXT,
    correction_reason TEXT,  -- Fri text från användare
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (learning_rule_id) REFERENCES learning_rules(id),
    FOREIGN KEY (original_voucher_id) REFERENCES vouchers(id)
);

CREATE INDEX idx_correction_history_rule ON correction_history(learning_rule_id);
CREATE INDEX idx_correction_history_voucher ON correction_history(original_voucher_id);
