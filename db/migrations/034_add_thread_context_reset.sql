-- Migration 034: a view's conversation can be reset (SPEC-tradar.md §6.3)
--
-- A reset is a boundary, not a deletion. `thread_posts` is append-only
-- (SPEC-tradar.md §8.2 p.4), and `decisions`/`thread_drafts` reference its
-- rows, so nothing is removed: `context_from_seq` is the highest `seq` that
-- was in the thread when the human reset it, and the thread window only
-- considers posts after it. The older posts stay readable in the thread,
-- collapsed above a divider. `context_reset_at` is what the divider shows.
--
-- 0 / NULL = never reset: every post is eligible for the window, as before.
-- The reset itself is audit-logged (`entity_type = 'thread'`).

ALTER TABLE threads ADD COLUMN context_from_seq INTEGER NOT NULL DEFAULT 0;
ALTER TABLE threads ADD COLUMN context_reset_at TIMESTAMP;

INSERT OR IGNORE INTO schema_version (version) VALUES (34);
