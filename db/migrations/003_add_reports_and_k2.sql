-- Fas 3: Rapporter & K2 Årsredovisning (Annual Reports)

-- K2 Annual Report (Årsredovisning för små företag)
CREATE TABLE IF NOT EXISTS annual_reports (
    id TEXT PRIMARY KEY,
    fiscal_year_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    org_number TEXT,
    report_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, finalized, submitted
    
    -- Administrative info
    managing_director_name TEXT,
    company_registration_number TEXT,
    
    -- Financial data
    revenue_total INTEGER NOT NULL DEFAULT 0,      -- Total revenue in öre
    operating_expenses INTEGER NOT NULL DEFAULT 0,  -- Total expenses in öre
    profit_loss INTEGER NOT NULL DEFAULT 0,        -- Net profit/loss in öre
    
    -- Balance sheet items
    assets_current INTEGER NOT NULL DEFAULT 0,     -- Current assets
    assets_fixed INTEGER NOT NULL DEFAULT 0,       -- Fixed assets
    liabilities_current INTEGER NOT NULL DEFAULT 0,
    liabilities_long_term INTEGER NOT NULL DEFAULT 0,
    equity_total INTEGER NOT NULL DEFAULT 0,
    
    -- K2 specific fields
    average_employees INTEGER,
    has_significant_events BOOLEAN DEFAULT 0,
    events_description TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalized_at TIMESTAMP,
    FOREIGN KEY(fiscal_year_id) REFERENCES fiscal_years(id),
    UNIQUE(fiscal_year_id)
);

-- Income Statement (Resultaträkning)
CREATE TABLE IF NOT EXISTS income_statements (
    id TEXT PRIMARY KEY,
    annual_report_id TEXT NOT NULL,
    
    -- Revenue section
    revenue_services INTEGER NOT NULL DEFAULT 0,    -- Service revenue
    revenue_goods INTEGER NOT NULL DEFAULT 0,       -- Goods revenue
    revenue_other INTEGER NOT NULL DEFAULT 0,       -- Other revenue
    revenue_total INTEGER NOT NULL DEFAULT 0,
    
    -- Expenses section
    personnel_costs INTEGER NOT NULL DEFAULT 0,
    depreciation INTEGER NOT NULL DEFAULT 0,
    other_operating_costs INTEGER NOT NULL DEFAULT 0,
    financial_costs INTEGER NOT NULL DEFAULT 0,
    tax_expense INTEGER NOT NULL DEFAULT 0,
    
    -- Result
    operating_profit INTEGER NOT NULL DEFAULT 0,
    profit_before_tax INTEGER NOT NULL DEFAULT 0,
    net_profit_loss INTEGER NOT NULL DEFAULT 0,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(annual_report_id) REFERENCES annual_reports(id),
    UNIQUE(annual_report_id)
);

-- Balance Sheet (Balansräkning)
CREATE TABLE IF NOT EXISTS balance_sheets (
    id TEXT PRIMARY KEY,
    annual_report_id TEXT NOT NULL,
    
    -- Assets
    cash_and_equivalents INTEGER NOT NULL DEFAULT 0,
    receivables INTEGER NOT NULL DEFAULT 0,
    inventory INTEGER NOT NULL DEFAULT 0,
    other_current_assets INTEGER NOT NULL DEFAULT 0,
    current_assets_total INTEGER NOT NULL DEFAULT 0,
    
    tangible_assets INTEGER NOT NULL DEFAULT 0,
    intangible_assets INTEGER NOT NULL DEFAULT 0,
    financial_assets INTEGER NOT NULL DEFAULT 0,
    fixed_assets_total INTEGER NOT NULL DEFAULT 0,
    
    assets_total INTEGER NOT NULL DEFAULT 0,
    
    -- Liabilities & Equity
    short_term_debt INTEGER NOT NULL DEFAULT 0,
    payables INTEGER NOT NULL DEFAULT 0,
    other_current_liabilities INTEGER NOT NULL DEFAULT 0,
    current_liabilities_total INTEGER NOT NULL DEFAULT 0,
    
    long_term_debt INTEGER NOT NULL DEFAULT 0,
    other_long_term_liabilities INTEGER NOT NULL DEFAULT 0,
    long_term_liabilities_total INTEGER NOT NULL DEFAULT 0,
    
    share_capital INTEGER NOT NULL DEFAULT 0,
    retained_earnings INTEGER NOT NULL DEFAULT 0,
    current_year_result INTEGER NOT NULL DEFAULT 0,
    equity_total INTEGER NOT NULL DEFAULT 0,
    
    liabilities_and_equity_total INTEGER NOT NULL DEFAULT 0,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(annual_report_id) REFERENCES annual_reports(id),
    UNIQUE(annual_report_id)
);

-- Cash Flow Statement (Kassaflödesanalys)
CREATE TABLE IF NOT EXISTS cash_flows (
    id TEXT PRIMARY KEY,
    annual_report_id TEXT NOT NULL,
    
    -- Operating activities
    operating_cash_flow INTEGER NOT NULL DEFAULT 0,
    
    -- Investing activities
    investing_cash_flow INTEGER NOT NULL DEFAULT 0,
    
    -- Financing activities
    financing_cash_flow INTEGER NOT NULL DEFAULT 0,
    
    -- Net change
    net_change_cash INTEGER NOT NULL DEFAULT 0,
    beginning_cash INTEGER NOT NULL DEFAULT 0,
    ending_cash INTEGER NOT NULL DEFAULT 0,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(annual_report_id) REFERENCES annual_reports(id),
    UNIQUE(annual_report_id)
);

-- Report metadata for audit
CREATE TABLE IF NOT EXISTS report_audit (
    id TEXT PRIMARY KEY,
    annual_report_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- created, finalized, submitted
    actor TEXT NOT NULL,
    notes TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(annual_report_id) REFERENCES annual_reports(id)
);

-- API Keys for agent integration (Fas 4)
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,  -- Hash of the actual key
    name TEXT NOT NULL,
    description TEXT,
    agent_id TEXT,
    permissions TEXT,  -- JSON: ["read", "write", "invoice", "report"]
    active BOOLEAN NOT NULL DEFAULT 1,
    rate_limit_per_minute INTEGER DEFAULT 100,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP
);

-- Agent operation log (for tracking agent actions)
CREATE TABLE IF NOT EXISTS agent_operations (
    id TEXT PRIMARY KEY,
    api_key_id TEXT NOT NULL,
    operation TEXT NOT NULL,  -- create_voucher, create_invoice, post_voucher, etc
    resource_type TEXT NOT NULL,  -- voucher, invoice, payment
    resource_id TEXT,
    status TEXT NOT NULL DEFAULT 'success',  -- success, error, pending
    error_message TEXT,
    request_body TEXT,  -- JSON for audit
    response_body TEXT,  -- JSON for audit
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER,
    FOREIGN KEY(api_key_id) REFERENCES api_keys(id)
);

-- OpenAPI spec metadata (for agent documentation)
CREATE TABLE IF NOT EXISTS openapi_specs (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,  -- GET, POST, PUT, DELETE
    description TEXT,
    request_schema TEXT,  -- JSON Schema
    response_schema TEXT,  -- JSON Schema
    requires_idempotency BOOLEAN DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(endpoint, method)
);

-- Indexes
CREATE INDEX idx_annual_reports_fy ON annual_reports(fiscal_year_id);
CREATE INDEX idx_annual_reports_status ON annual_reports(status);
CREATE INDEX idx_income_statements_report ON income_statements(annual_report_id);
CREATE INDEX idx_balance_sheets_report ON balance_sheets(annual_report_id);
CREATE INDEX idx_cash_flows_report ON cash_flows(annual_report_id);
CREATE INDEX idx_api_keys_active ON api_keys(active);
CREATE INDEX idx_agent_operations_key ON agent_operations(api_key_id);
CREATE INDEX idx_agent_operations_timestamp ON agent_operations(timestamp);
CREATE INDEX idx_openapi_specs_endpoint ON openapi_specs(endpoint, method);

-- Update schema version
INSERT INTO schema_version (version) VALUES (3);
