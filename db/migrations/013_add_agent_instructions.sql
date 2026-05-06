-- Versioned Markdown instructions for accounting agents

CREATE TABLE IF NOT EXISTS agent_instruction_documents (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL UNIQUE,
    active_version_id TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_instruction_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_markdown TEXT NOT NULL,
    change_summary TEXT,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES agent_instruction_documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, version)
);

CREATE INDEX IF NOT EXISTS idx_agent_instruction_versions_document
    ON agent_instruction_versions(document_id, version DESC);

INSERT INTO schema_version (version) VALUES (13);
