-- Migration 017: Simple payroll v1 with payslip-backed salary booking

CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    personal_number TEXT,
    email TEXT,
    bank_account TEXT,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employee_salary_settings (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL UNIQUE,
    gross_monthly_salary INTEGER NOT NULL,
    preliminary_tax INTEGER NOT NULL,
    employer_fee_rate_bp INTEGER,
    employer_fee_amount INTEGER,
    payment_day INTEGER NOT NULL DEFAULT 25,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(employee_id) REFERENCES employees(id),
    CHECK(gross_monthly_salary >= 0),
    CHECK(preliminary_tax >= 0),
    CHECK(employer_fee_rate_bp IS NULL OR employer_fee_rate_bp >= 0),
    CHECK(employer_fee_amount IS NULL OR employer_fee_amount >= 0),
    CHECK(payment_day >= 1 AND payment_day <= 31)
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    payment_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'system',
    generated_at TIMESTAMP,
    CHECK(month >= 1 AND month <= 12),
    CHECK(status IN ('draft', 'generated', 'booked')),
    UNIQUE(year, month, payment_date)
);

CREATE TABLE IF NOT EXISTS payslips (
    id TEXT PRIMARY KEY,
    payroll_run_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,
    payment_date DATE NOT NULL,
    gross_salary INTEGER NOT NULL,
    preliminary_tax INTEGER NOT NULL,
    employer_fee INTEGER NOT NULL,
    net_salary INTEGER NOT NULL,
    total_employer_cost INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'generated',
    pdf_sent_at TIMESTAMP,
    bank_transaction_id TEXT,
    voucher_id TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(payroll_run_id) REFERENCES payroll_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(employee_id) REFERENCES employees(id),
    FOREIGN KEY(bank_transaction_id) REFERENCES bank_transactions(id),
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    CHECK(gross_salary >= 0),
    CHECK(preliminary_tax >= 0),
    CHECK(employer_fee >= 0),
    CHECK(net_salary >= 0),
    CHECK(total_employer_cost >= 0),
    CHECK(status IN ('generated', 'sent', 'booked')),
    UNIQUE(payroll_run_id, employee_id)
);

CREATE INDEX IF NOT EXISTS idx_employees_active ON employees(active);
CREATE INDEX IF NOT EXISTS idx_payroll_runs_period ON payroll_runs(year, month);
CREATE INDEX IF NOT EXISTS idx_payslips_run ON payslips(payroll_run_id);
CREATE INDEX IF NOT EXISTS idx_payslips_employee ON payslips(employee_id);
CREATE INDEX IF NOT EXISTS idx_payslips_voucher ON payslips(voucher_id);
CREATE INDEX IF NOT EXISTS idx_payslips_bank_tx ON payslips(bank_transaction_id);

INSERT OR IGNORE INTO accounts (code, name, account_type, active) VALUES
('1930', 'Företagskonto', 'asset', 1),
('2710', 'Personalskatt', 'liability', 1),
('2730', 'Avräkning arbetsgivaravgifter', 'liability', 1),
('7010', 'Löner', 'expense', 1),
('7510', 'Arbetsgivaravgifter', 'expense', 1);

INSERT OR IGNORE INTO schema_version (version) VALUES (17);
