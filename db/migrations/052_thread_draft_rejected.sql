-- Migration 052: a human can discard a voucher proposal
--
-- A thread draft could only be posted or replaced by a new proposal (028).
-- An agent that proposes a voucher which should not be booked at all -- a
-- duplicate, or one that a later, combined proposal makes redundant -- left
-- a card nobody could get rid of. `rejected` is the fourth state: the human
-- pressed `Kasta` on the card (`POST /api/v1/drafts/{id}/reject`). Like
-- `superseded` the draft voucher is deleted (it never took a number, so no
-- gap is left) while this row stays, because the `draft` post stays and must
-- still say what happened to it.
--
-- `rejected_at` and `rejected_by` say when and who; the audit log says it
-- too. A CHECK cannot be changed with ALTER in SQLite, so the table is
-- rebuilt (foreign keys OFF, create, copy, drop, rename, as in 040). No
-- other table's foreign key names `thread_drafts`, and it has no triggers;
-- its two indexes are created again.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE thread_drafts_new (
    voucher_id          TEXT PRIMARY KEY,
    thread_id           TEXT NOT NULL,
    post_id             TEXT NOT NULL UNIQUE,
    view_key            TEXT NOT NULL,
    decision_id         TEXT,
    correction_of       TEXT,
    correction_note_id  TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    replaced_by         TEXT,
    posted_at           TIMESTAMP,
    receipt_post_id     TEXT,
    last_error_code     TEXT,
    last_error_post_id  TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    traceability_json   TEXT,
    rejected_at         TIMESTAMP,
    rejected_by         TEXT,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES thread_posts(id),
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (correction_note_id) REFERENCES correction_notes(id),
    CHECK (status IN ('pending', 'posted', 'superseded', 'rejected')),
    CHECK (status != 'posted' OR posted_at IS NOT NULL),
    CHECK (status != 'rejected' OR rejected_at IS NOT NULL)
);

INSERT INTO thread_drafts_new
    (voucher_id, thread_id, post_id, view_key, decision_id, correction_of,
     correction_note_id, status, replaced_by, posted_at, receipt_post_id,
     last_error_code, last_error_post_id, created_at, traceability_json)
SELECT voucher_id, thread_id, post_id, view_key, decision_id, correction_of,
       correction_note_id, status, replaced_by, posted_at, receipt_post_id,
       last_error_code, last_error_post_id, created_at, traceability_json
FROM thread_drafts;

DROP TABLE thread_drafts;
ALTER TABLE thread_drafts_new RENAME TO thread_drafts;

CREATE INDEX idx_thread_drafts_view_status
    ON thread_drafts(view_key, status, created_at);

CREATE INDEX idx_thread_drafts_pending_correction
    ON thread_drafts(correction_of) WHERE status = 'pending';

INSERT OR IGNORE INTO schema_version (version) VALUES (52);

COMMIT;

PRAGMA foreign_keys = ON;
