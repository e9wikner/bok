-- Migration 007: Add VAT declarations table
-- SKV 4700 format support for Swedish VAT reporting

CREATE TABLE IF NOT EXISTS vat_declarations (
    id TEXT PRIMARY KEY,
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL DEFAULT 0,  -- 0 for quarterly declarations
    period_quarter INTEGER,  -- 1-4 for quarterly, NULL for monthly
    
    -- Sales (försäljning) - amounts in öre
    sales_25 INTEGER DEFAULT 0,  -- Ruta 05: Försäljning 25% moms
    sales_12 INTEGER DEFAULT 0,  -- Ruta 06: Försäljning 12% moms
    sales_6 INTEGER DEFAULT 0,   -- Ruta 07: Försäljning 6% moms
    sales_exempt INTEGER DEFAULT 0,  -- Ruta 08: Momsfri försäljning
    
    -- Output VAT (utgående moms) - amounts in öre
    vat_out_25 INTEGER DEFAULT 0,  -- Ruta 10: Utgående moms 25%
    vat_out_12 INTEGER DEFAULT 0,  -- Ruta 11: Utgående moms 12%
    vat_out_6 INTEGER DEFAULT 0,   -- Ruta 12: Utgående moms 6%
    
    -- Input VAT (ingående moms)
    vat_in INTEGER DEFAULT 0,  -- Ruta 48: Ingående moms att dra av
    
    -- Calculated
    vat_to_pay INTEGER DEFAULT 0,  -- Ruta 49: Moms att betala/få tillbaka
    
    status TEXT DEFAULT 'draft',  -- draft, final, submitted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finalized_at TIMESTAMP,
    submitted_at TIMESTAMP
);

-- Index for efficient queries
CREATE INDEX IF NOT EXISTS idx_vat_declarations_year ON vat_declarations(period_year);
CREATE INDEX IF NOT EXISTS idx_vat_declarations_period ON vat_declarations(period_year, period_month);
CREATE INDEX IF NOT EXISTS idx_vat_declarations_status ON vat_declarations(status);
