-- Migration 041: förslag om ett nytt räkenskapsår (foresla_rakenskapsar).
-- Service: services/fiscal_year_proposal.py. Test: tests/test_rakenskapsar.py.
--
-- An underlag dated outside every fiscal year cannot be booked. The agent
-- proposes the year as a decision card in the thread; the human's press on
-- the card's create option creates it. This row binds the card to the dates
-- it shows, so the year created is exactly the one the human saw -- the agent
-- never names the dates again after the press.
--
-- `fiscal_year_proposal_sources` are the underlag waiting on the proposal.
-- While it is pending they are left out of the intake pass's queue
-- (`repositories/intake_repo.py`), so the pass neither abstains from them nor
-- reads them again every pass. When the year is created they are back in the
-- queue; when the human declines, they are recorded as failed.

CREATE TABLE IF NOT EXISTS fiscal_year_proposals (
    id                TEXT PRIMARY KEY,
    decision_id       TEXT NOT NULL UNIQUE,
    create_option_id  TEXT NOT NULL,
    thread_id         TEXT NOT NULL,
    start_date        DATE NOT NULL,
    end_date          DATE NOT NULL,
    document_date     DATE NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    fiscal_year_id    TEXT,
    created_by        TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at       TIMESTAMP,
    resolved_by       TEXT,
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (create_option_id) REFERENCES decision_options(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id),
    CHECK (status IN ('pending', 'created', 'declined', 'superseded')),
    CHECK (start_date < end_date),
    CHECK (status != 'created' OR fiscal_year_id IS NOT NULL)
);

-- One pending card per year: a second underlag for the same year joins the
-- card already in the thread instead of raising another.
CREATE UNIQUE INDEX IF NOT EXISTS idx_fiscal_year_proposals_pending
    ON fiscal_year_proposals(start_date, end_date)
    WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS fiscal_year_proposal_sources (
    proposal_id       TEXT NOT NULL,
    intake_source_id  TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (proposal_id, intake_source_id),
    FOREIGN KEY (proposal_id) REFERENCES fiscal_year_proposals(id),
    FOREIGN KEY (intake_source_id) REFERENCES intake_sources(id)
);

CREATE INDEX IF NOT EXISTS idx_fiscal_year_proposal_sources_source
    ON fiscal_year_proposal_sources(intake_source_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (41);
