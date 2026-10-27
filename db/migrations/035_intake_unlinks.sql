-- Migration 035: underlag-ersatt -- a link can be undone, and the undoing stays
--
-- A wrongly linked underlag must be replaceable "och lämna spår" (flöde 4,
-- D10). Nothing is removed for that: a link row stays where it is, and a row
-- in `voucher_intake_unlinks` says it no longer holds -- who, why, on what
-- basis. The *current* link of a source is the one without such a row.
--
-- `voucher_intake_sources` had `UNIQUE(intake_source_id)`, the guard against
-- booking one receipt twice. A source that has been unlinked must be able to
-- carry a new link while the old row stays as history, and SQLite cannot drop
-- a UNIQUE with ALTER, so the table is rebuilt (the same order as 021 and
-- 027: foreign keys OFF, create, copy, drop, rename). The guard moves to a
-- trigger: at most one *current* link per source.
--
-- `intake_link_basis` was keyed by `intake_source_id` -- one basis per
-- source, since a source was linked once. It is rebuilt keyed by the link it
-- is the basis of (`link_id`), filled from the one link each source had.
--
-- Append-only in three layers, as vouchers are (AGENTS.md): the triggers
-- below refuse UPDATE and DELETE on all three tables, the repositories offer
-- insert and read only, and no endpoint rewrites or removes a row.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE voucher_intake_sources_new (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    intake_source_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    link_reason TEXT,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    FOREIGN KEY(intake_source_id) REFERENCES intake_sources(id)
);

INSERT INTO voucher_intake_sources_new
    (id, voucher_id, intake_source_id, linked_by, linked_at, link_reason)
SELECT id, voucher_id, intake_source_id, linked_by, linked_at, link_reason
FROM voucher_intake_sources;

DROP TABLE voucher_intake_sources;
ALTER TABLE voucher_intake_sources_new RENAME TO voucher_intake_sources;

CREATE INDEX idx_voucher_intake_sources_voucher ON voucher_intake_sources(voucher_id);
CREATE INDEX idx_voucher_intake_sources_source ON voucher_intake_sources(intake_source_id);

CREATE TABLE intake_link_basis_new (
    link_id            TEXT PRIMARY KEY NOT NULL REFERENCES voucher_intake_sources(id),
    intake_source_id   TEXT NOT NULL REFERENCES intake_sources(id),
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

INSERT INTO intake_link_basis_new
    (link_id, intake_source_id, voucher_id, basis, interpretation_id,
     decision_id, actor, agent_run_id, thread_id, created_at)
SELECT vis.id, b.intake_source_id, b.voucher_id, b.basis, b.interpretation_id,
       b.decision_id, b.actor, b.agent_run_id, b.thread_id, b.created_at
FROM intake_link_basis b
JOIN voucher_intake_sources vis ON vis.intake_source_id = b.intake_source_id;

DROP TABLE intake_link_basis;
ALTER TABLE intake_link_basis_new RENAME TO intake_link_basis;

CREATE INDEX idx_intake_link_basis_source ON intake_link_basis(intake_source_id);
CREATE INDEX idx_intake_link_basis_decision ON intake_link_basis(decision_id);

CREATE TABLE voucher_intake_unlinks (
    link_id           TEXT PRIMARY KEY NOT NULL REFERENCES voucher_intake_sources(id),
    intake_source_id  TEXT NOT NULL REFERENCES intake_sources(id),
    voucher_id        TEXT NOT NULL REFERENCES vouchers(id),
    basis             TEXT NOT NULL,
    decision_id       TEXT REFERENCES decisions(id),
    reason            TEXT NOT NULL,
    actor             TEXT NOT NULL,
    agent_run_id      TEXT REFERENCES agent_runs(id),
    thread_id         TEXT REFERENCES threads(id),
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (basis IN ('human', 'decision')),
    CHECK ((basis = 'decision') = (decision_id IS NOT NULL)),
    CHECK (length(trim(reason)) > 0)
);

CREATE INDEX idx_voucher_intake_unlinks_source ON voucher_intake_unlinks(intake_source_id);
CREATE INDEX idx_voucher_intake_unlinks_decision ON voucher_intake_unlinks(decision_id);

-- The old UNIQUE(intake_source_id), for current links: a source carries at
-- most one link that has not been undone.
CREATE TRIGGER one_current_link_per_source
BEFORE INSERT ON voucher_intake_sources
WHEN EXISTS (
    SELECT 1 FROM voucher_intake_sources vis
    WHERE vis.intake_source_id = NEW.intake_source_id
      AND NOT EXISTS (
          SELECT 1 FROM voucher_intake_unlinks u WHERE u.link_id = vis.id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'intake source is already linked');
END;

-- An unlink names the link it undoes, and that link's source and voucher.
CREATE TRIGGER unlink_matches_link
BEFORE INSERT ON voucher_intake_unlinks
WHEN NOT EXISTS (
    SELECT 1 FROM voucher_intake_sources vis
    WHERE vis.id = NEW.link_id
      AND vis.intake_source_id = NEW.intake_source_id
      AND vis.voucher_id = NEW.voucher_id
)
BEGIN
    SELECT RAISE(ABORT, 'unlink does not match its link');
END;

CREATE TRIGGER prevent_update_voucher_intake_sources
BEFORE UPDATE ON voucher_intake_sources
BEGIN SELECT RAISE(ABORT, 'voucher intake links are append-only'); END;

CREATE TRIGGER prevent_delete_voucher_intake_sources
BEFORE DELETE ON voucher_intake_sources
BEGIN SELECT RAISE(ABORT, 'voucher intake links are append-only'); END;

CREATE TRIGGER prevent_update_intake_link_basis
BEFORE UPDATE ON intake_link_basis
BEGIN SELECT RAISE(ABORT, 'intake link basis is append-only'); END;

CREATE TRIGGER prevent_delete_intake_link_basis
BEFORE DELETE ON intake_link_basis
BEGIN SELECT RAISE(ABORT, 'intake link basis is append-only'); END;

CREATE TRIGGER prevent_update_voucher_intake_unlinks
BEFORE UPDATE ON voucher_intake_unlinks
BEGIN SELECT RAISE(ABORT, 'voucher intake unlinks are append-only'); END;

CREATE TRIGGER prevent_delete_voucher_intake_unlinks
BEFORE DELETE ON voucher_intake_unlinks
BEGIN SELECT RAISE(ABORT, 'voucher intake unlinks are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (35);

COMMIT;

PRAGMA foreign_keys = ON;
