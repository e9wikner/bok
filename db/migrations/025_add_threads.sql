-- Migration 025: tradar — threads and thread_posts (SPEC-tradar.md §4)
--
-- One thread per (view_key, fiscal_year_id): the UNIQUE below is decision
-- §12.3 written into the schema, not a convention the service layer is
-- trusted to keep. The CHECK on `type` is the same kind of guarantee for the
-- eight post types datakontrakt.md §1 lists — a ninth type sneaking in is a
-- renderer that silently falls through on the client.

CREATE TABLE IF NOT EXISTS threads (
    id              TEXT PRIMARY KEY,
    view_key        TEXT NOT NULL,
    fiscal_year_id  TEXT NOT NULL,
    model           TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id),
    UNIQUE (view_key, fiscal_year_id)
);

CREATE TABLE IF NOT EXISTS thread_posts (
    id           TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    type         TEXT NOT NULL,
    actor        TEXT NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    body_json    TEXT NOT NULL,
    traces_json  TEXT,
    run_id       TEXT,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES agent_runs(id),
    UNIQUE (thread_id, seq),
    CHECK (type IN ('agent_text','user_text','user_file','decision',
                    'options','draft','error','receipt'))
);

CREATE INDEX IF NOT EXISTS idx_thread_posts_thread_seq ON thread_posts(thread_id, seq);

INSERT OR IGNORE INTO schema_version (version) VALUES (25);
