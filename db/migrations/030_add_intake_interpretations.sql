-- Migration 030: underlagstolkning — intake_interpretations
-- (SPEC-underlagstolkning.md §5)
--
-- What the agent read from an underlag (claims), what the server computed
-- from it at that moment (checks, confidence, match, candidates -- facts),
-- and who and where. `tolka_underlag` writes one row per call; a new
-- interpretation of the same source is a new row, and the latest one
-- (`ORDER BY created_at, rowid`) is the one that counts.
--
-- Append-only in the same three layers as vouchers (AGENTS.md): the two
-- triggers below, `InterpretationRepository` without update/delete, and no
-- endpoint that writes. The match is a snapshot: whether it is still open is
-- derived when read (§8, `still_open`), never by changing the row.
--
-- The DDL below is §5 verbatim.

CREATE TABLE intake_interpretations (
    id                TEXT PRIMARY KEY,
    intake_source_id  TEXT NOT NULL REFERENCES intake_sources(id),
    -- Vad modellen läste (påståenden)
    vendor            TEXT,
    document_date     DATE,
    currency          TEXT NOT NULL DEFAULT 'SEK',
    total_ore         INTEGER NOT NULL,
    vat_ore           INTEGER,
    lines_json        TEXT NOT NULL DEFAULT '[]',   -- [{text, amount_ore, vat_rate}]
    -- Vad servern räknade (fakta, i tolkningsögonblicket)
    checks_json       TEXT NOT NULL,                -- §6.3
    confidence        TEXT NOT NULL,
    match_json        TEXT,                         -- §7.4, NULL = ingen entydig match
    candidates_json   TEXT NOT NULL DEFAULT '[]',
    expected_voucher_id TEXT REFERENCES vouchers(id),
    -- Vem och var
    actor             TEXT NOT NULL,
    agent_run_id      TEXT REFERENCES agent_runs(id),
    thread_id         TEXT REFERENCES threads(id),
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (confidence IN ('high', 'medium', 'low')),
    CHECK (total_ore >= 0),
    CHECK (vat_ore IS NULL OR vat_ore >= 0)
);
CREATE INDEX idx_interpretations_source ON intake_interpretations(intake_source_id, created_at);

CREATE TRIGGER prevent_update_intake_interpretations
BEFORE UPDATE ON intake_interpretations
BEGIN SELECT RAISE(ABORT, 'intake interpretations are append-only'); END;

CREATE TRIGGER prevent_delete_intake_interpretations
BEFORE DELETE ON intake_interpretations
BEGIN SELECT RAISE(ABORT, 'intake interpretations are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (30);
