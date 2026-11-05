-- Migration 044: uppgifter till bokslutet som inte går att läsa ur bokföringen.
-- Service: services/bokslut_inputs.py. Test: tests/test_bokslut.py.
--
-- Årsredovisningens texter (verksamhet, ort, underskrifter, utdelning),
-- medeltal anställda och de skattemässiga justeringar i INK2S som en människa
-- fyller i (t.ex. 4.6d eller ett konto som ska räknas som skattefritt).
--
-- Raderna är append-only, som allt annat som ligger bakom en deklaration: en
-- ändring är en ny rad, den senaste raden per (år, nyckel) gäller, och en rad
-- med value_json NULL tar bort uppgiften. Vem som ändrade vad står kvar.

CREATE TABLE IF NOT EXISTS bokslut_inputs (
    id              TEXT PRIMARY KEY,
    fiscal_year_id  TEXT NOT NULL,
    key             TEXT NOT NULL,
    value_json      TEXT,
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    seq             INTEGER NOT NULL,
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bokslut_inputs_seq
    ON bokslut_inputs (fiscal_year_id, key, seq);

CREATE TRIGGER IF NOT EXISTS prevent_update_bokslut_inputs
BEFORE UPDATE ON bokslut_inputs
BEGIN SELECT RAISE(ABORT, 'bokslut inputs are append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_bokslut_inputs
BEFORE DELETE ON bokslut_inputs
BEGIN SELECT RAISE(ABORT, 'bokslut inputs are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (44);
