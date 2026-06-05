-- Migration 020: Add agent guidance to intake sources
-- Stores optional user-provided instructions for the agent on a per-source basis.

ALTER TABLE intake_sources ADD COLUMN agent_guidance TEXT;

INSERT OR IGNORE INTO schema_version (version) VALUES (20);
