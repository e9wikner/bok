-- Migration 032: flode-underlag — intake_link_basis and voucher_source_references
-- (SPEC-flode-underlag.md §5)
--
-- `intake_link_basis`: why an underlag was linked to an already posted
-- voucher after the fact (`koppla_underlag`, `POST /intake/{id}/link`). One
-- row per source -- a source is linked once, `UNIQUE(intake_source_id)` in
-- `voucher_intake_sources` -- naming the interpretation the server compared
-- and, for `basis = 'decision'`, the answered decision. A link made by a
-- posting has no row here: it carries its underlag through the posting.
--
-- `voucher_source_references` (D2): a difference booked as its own voucher
-- (A-121) refers to the receipt through the voucher that carries the link
-- (A-118), without the receipt being linked twice. Written by the server in
-- the posting's transaction, from the decision -- never by the agent.
--
-- Append-only in the same three layers as vouchers (AGENTS.md): the four
-- triggers below, repositories without update/delete, and no endpoint that
-- rewrites or removes a link. Neither table has a column that is filled in
-- later (§5: no `receipt_post_id`). No existing table is touched.
--
-- The two DDL blocks below are §5 verbatim; the second block's comment is
-- carried out by the two triggers after it.

CREATE TABLE intake_link_basis (
    intake_source_id   TEXT PRIMARY KEY REFERENCES intake_sources(id),
    voucher_id         TEXT NOT NULL REFERENCES vouchers(id),
    basis              TEXT NOT NULL,
    interpretation_id  TEXT NOT NULL REFERENCES intake_interpretations(id),
    decision_id        TEXT REFERENCES decisions(id),
    actor              TEXT NOT NULL,
    agent_run_id       TEXT REFERENCES agent_runs(id),
    thread_id          TEXT REFERENCES threads(id),
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (basis IN ('exact_match', 'decision')),
    CHECK ((basis = 'decision') = (decision_id IS NOT NULL))
);

CREATE TRIGGER prevent_update_intake_link_basis
BEFORE UPDATE ON intake_link_basis
BEGIN SELECT RAISE(ABORT, 'intake link basis is append-only'); END;

CREATE TRIGGER prevent_delete_intake_link_basis
BEFORE DELETE ON intake_link_basis
BEGIN SELECT RAISE(ABORT, 'intake link basis is append-only'); END;

CREATE INDEX idx_intake_link_basis_decision ON intake_link_basis(decision_id);

CREATE TABLE voucher_source_references (
    voucher_id        TEXT PRIMARY KEY REFERENCES vouchers(id),   -- A-121
    intake_source_id  TEXT NOT NULL REFERENCES intake_sources(id), -- kvittot
    via_voucher_id    TEXT NOT NULL REFERENCES vouchers(id),       -- A-118, som bär kopplingen
    decision_id       TEXT NOT NULL REFERENCES decisions(id),
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (voucher_id != via_voucher_id)
);
-- samma två triggrar: ingen UPDATE, ingen DELETE

CREATE TRIGGER prevent_update_voucher_source_references
BEFORE UPDATE ON voucher_source_references
BEGIN SELECT RAISE(ABORT, 'voucher source references are append-only'); END;

CREATE TRIGGER prevent_delete_voucher_source_references
BEFORE DELETE ON voucher_source_references
BEGIN SELECT RAISE(ABORT, 'voucher source references are append-only'); END;

CREATE INDEX idx_voucher_source_references_via
    ON voucher_source_references(via_voucher_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (32);
