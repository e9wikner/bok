-- Migration 026: beslut — decisions and decision_options (SPEC-beslut.md §4)
--
-- `UNIQUE (post_id)` is decision §4's guarantee that one `decision` post
-- carries exactly one decision row — without it the same card in the thread
-- could answer to two rows with different status. The two `answered` CHECKs
-- put the answer's integrity in the schema instead of in a service that can
-- have a bug: an answered decision without a timestamp, or without either
-- an option or free text, is not an answer.

CREATE TABLE IF NOT EXISTS decisions (
    id              TEXT PRIMARY KEY,
    thread_id       TEXT NOT NULL,
    post_id         TEXT NOT NULL,
    view_key        TEXT NOT NULL,
    kind            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    title           TEXT NOT NULL,
    amount_ore      INTEGER,
    reason          TEXT NOT NULL,
    consequence     TEXT NOT NULL,
    source_kind     TEXT,
    source_id       TEXT,
    source_date     DATE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    answered_at     TIMESTAMP,
    answered_by     TEXT,
    answer_option_id TEXT,
    answer_text     TEXT,
    answer_post_id  TEXT,
    reminded_at     TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES thread_posts(id),
    FOREIGN KEY (answer_post_id) REFERENCES thread_posts(id),
    UNIQUE (post_id),
    CHECK (kind IN ('abstention', 'approval')),
    CHECK (status IN ('open', 'answered', 'superseded')),
    CHECK (status != 'answered' OR answered_at IS NOT NULL),
    CHECK (status != 'answered' OR answer_option_id IS NOT NULL OR answer_text IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS decision_options (
    id           TEXT PRIMARY KEY,
    decision_id  TEXT NOT NULL,
    position     INTEGER NOT NULL,
    title        TEXT NOT NULL,
    account      TEXT,
    amount_ore   INTEGER,
    rationale    TEXT NOT NULL,
    recommended  INTEGER NOT NULL DEFAULT 0,
    is_exit      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE,
    UNIQUE (decision_id, position),
    CHECK (recommended IN (0, 1)),
    CHECK (is_exit IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_thread ON decisions(thread_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (26);
