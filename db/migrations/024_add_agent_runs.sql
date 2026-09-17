-- Migration 024: Agent runtime — agent_runs and agent_run_events

CREATE TABLE IF NOT EXISTS agent_runs (
    id            TEXT PRIMARY KEY,
    trigger       TEXT NOT NULL,         -- 'schedule' | 'manual' | 'thread'
    status        TEXT NOT NULL,         -- 'running' | 'completed' | 'failed' | 'abandoned'
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    model         TEXT NOT NULL,         -- t.ex. 'opencode/claude-opus-5'
    protocol      TEXT NOT NULL,         -- 'messages' | 'chat'
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_ore      INTEGER NOT NULL DEFAULT 0,
    items_seen    INTEGER NOT NULL DEFAULT 0,
    items_posted  INTEGER NOT NULL DEFAULT 0,
    items_abstained INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    CHECK (status IN ('running','completed','failed','abandoned'))
);

CREATE TABLE IF NOT EXISTS agent_run_events (
    id            TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES agent_runs(id),
    seq           INTEGER NOT NULL,
    kind          TEXT NOT NULL,   -- 'item_started'|'tool_call'|'tool_result'|'posted'
                                   -- |'abstained'|'error'|'text'
    source_id     TEXT,
    voucher_id    TEXT,
    payload_json  TEXT NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    UNIQUE (run_id, seq)
);

INSERT OR IGNORE INTO schema_version (version) VALUES (24);
