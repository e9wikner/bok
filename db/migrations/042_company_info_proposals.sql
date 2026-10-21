-- Migration 042: förslag om bolagsuppgifter (foresla_bolagsinformation).
-- Service: services/company_info_proposal.py. Test: tests/test_bolagsinformation.py.
--
-- The agent proposes company details (seat, VAT number, bankgiro, F-skatt ...)
-- as a decision card in a thread; the human's press writes them. This row
-- binds the card to the values it shows, so what is written is exactly what
-- the human saw -- the agent never names the values again after the press.
--
-- `fill_values` go only into fields that are still empty when the card is
-- pressed. `overwrite_values` replace a stored value and are written only on
-- the card's overwrite option. Both are JSON objects of key -> text.

CREATE TABLE IF NOT EXISTS company_info_proposals (
    id                  TEXT PRIMARY KEY,
    decision_id         TEXT NOT NULL UNIQUE,
    thread_id           TEXT NOT NULL,
    fill_option_id      TEXT,
    overwrite_option_id TEXT,
    fill_values         TEXT NOT NULL DEFAULT '{}',
    overwrite_values    TEXT NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'pending',
    created_by          TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolved_by         TEXT,
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (fill_option_id) REFERENCES decision_options(id),
    FOREIGN KEY (overwrite_option_id) REFERENCES decision_options(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    CHECK (status IN ('pending', 'applied', 'declined', 'superseded'))
);

INSERT OR IGNORE INTO schema_version (version) VALUES (42);
