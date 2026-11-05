-- Migration 044: one underlag can support several vouchers
--
-- BFL requires an underlag behind every voucher. It does not require each
-- underlag to support only one voucher, and in practice many do: a loan
-- agreement behind every amortisation, an annual invoice that is accrued
-- month by month, a receipt that covers several transactions.
--
-- Migration 035 kept the old UNIQUE(intake_source_id) as the trigger
-- `one_current_link_per_source`: a guard against booking one receipt twice.
-- That guard now lives in the service layer. The server never links an
-- underlag that is already linked on its own (an exact match is only "still
-- open" for a source with no current link, `VoucherRepository.match_still_open`).
-- A further link needs a human's word: a press on a `foresla_delat_underlag`
-- card (below), a standing approval from one, or a press on a voucher
-- proposal card that says which vouchers the underlag already supports
-- (`DraftService`, `shared_intake_sources`).
--
-- What the schema still keeps: a source and a voucher share at most one
-- current link. The other triggers, which keep all three tables append-only,
-- are untouched.
--
-- The human's word for linking an underlag to one more voucher is a decision
-- card (`foresla_delat_underlag`, services/intake_reuse.py) with two yes
-- options: link this once, or link and approve the underlag for further
-- vouchers. `intake_link_proposals` binds the card to the source and voucher
-- it shows. A standing approval is a row in `intake_reuse_approvals`, bound to
-- one fiscal year -- the voucher's -- since a recurring underlag is approved
-- for at most a fiscal year. Within it the agent may post or link the
-- underlag to more vouchers on its own. A human can end it early with a row
-- in `intake_reuse_revocations`. Both tables are append-only.

BEGIN;

DROP TRIGGER IF EXISTS one_current_link_per_source;

CREATE TRIGGER one_current_link_per_source_and_voucher
BEFORE INSERT ON voucher_intake_sources
WHEN EXISTS (
    SELECT 1 FROM voucher_intake_sources vis
    WHERE vis.intake_source_id = NEW.intake_source_id
      AND vis.voucher_id = NEW.voucher_id
      AND NOT EXISTS (
          SELECT 1 FROM voucher_intake_unlinks u WHERE u.link_id = vis.id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'intake source is already linked to this voucher');
END;

CREATE TABLE IF NOT EXISTS intake_link_proposals (
    id                  TEXT PRIMARY KEY,
    decision_id         TEXT NOT NULL UNIQUE REFERENCES decisions(id),
    thread_id           TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    intake_source_id    TEXT NOT NULL REFERENCES intake_sources(id),
    voucher_id          TEXT NOT NULL REFERENCES vouchers(id),
    fiscal_year_id      TEXT NOT NULL REFERENCES fiscal_years(id),
    once_option_id      TEXT NOT NULL REFERENCES decision_options(id),
    standing_option_id  TEXT NOT NULL REFERENCES decision_options(id),
    status              TEXT NOT NULL DEFAULT 'pending',
    created_by          TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolved_by         TEXT,
    CHECK (status IN ('pending', 'linked', 'declined', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_intake_link_proposals_source
    ON intake_link_proposals(intake_source_id);

CREATE TABLE IF NOT EXISTS intake_reuse_approvals (
    id                TEXT PRIMARY KEY,
    intake_source_id  TEXT NOT NULL REFERENCES intake_sources(id),
    fiscal_year_id    TEXT NOT NULL REFERENCES fiscal_years(id),
    decision_id       TEXT NOT NULL UNIQUE REFERENCES decisions(id),
    approved_by       TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_intake_reuse_approvals_source
    ON intake_reuse_approvals(intake_source_id, fiscal_year_id);

CREATE TABLE IF NOT EXISTS intake_reuse_revocations (
    approval_id  TEXT PRIMARY KEY NOT NULL REFERENCES intake_reuse_approvals(id),
    revoked_by   TEXT NOT NULL,
    reason       TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER prevent_update_intake_reuse_approvals
BEFORE UPDATE ON intake_reuse_approvals
BEGIN SELECT RAISE(ABORT, 'intake reuse approvals are append-only'); END;

CREATE TRIGGER prevent_delete_intake_reuse_approvals
BEFORE DELETE ON intake_reuse_approvals
BEGIN SELECT RAISE(ABORT, 'intake reuse approvals are append-only'); END;

CREATE TRIGGER prevent_update_intake_reuse_revocations
BEFORE UPDATE ON intake_reuse_revocations
BEGIN SELECT RAISE(ABORT, 'intake reuse revocations are append-only'); END;

CREATE TRIGGER prevent_delete_intake_reuse_revocations
BEFORE DELETE ON intake_reuse_revocations
BEGIN SELECT RAISE(ABORT, 'intake reuse revocations are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (44);

COMMIT;
