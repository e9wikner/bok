-- Migration 056: temporary review keys (docs/granskning.md §3)
--
-- A logged-in human presses "Kopiera uppdrag till agent" in the Granskning
-- view and gets a prompt with a key that lives about an hour
-- (`services/review_token.py`). The key has exactly the review key's rights
-- (`api/deps.py::review_key_allows`): it reads, and it uploads a review
-- report. Only its sha256 is stored; the plaintext is shown once.
--
-- Both tables are append-only. A key ends when `expires_at` passes or when a
-- row in `review_token_revocations` names it.

BEGIN;

CREATE TABLE IF NOT EXISTS review_tokens (
    id              TEXT PRIMARY KEY,
    token_sha256    TEXT NOT NULL UNIQUE,
    fiscal_year_id  TEXT REFERENCES fiscal_years(id),
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS review_token_revocations (
    token_id    TEXT PRIMARY KEY NOT NULL REFERENCES review_tokens(id),
    revoked_by  TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER prevent_update_review_tokens
BEFORE UPDATE ON review_tokens
BEGIN SELECT RAISE(ABORT, 'review tokens are append-only'); END;

CREATE TRIGGER prevent_delete_review_tokens
BEFORE DELETE ON review_tokens
BEGIN SELECT RAISE(ABORT, 'review tokens are append-only'); END;

CREATE TRIGGER prevent_update_review_token_revocations
BEFORE UPDATE ON review_token_revocations
BEGIN SELECT RAISE(ABORT, 'review token revocations are append-only'); END;

CREATE TRIGGER prevent_delete_review_token_revocations
BEFORE DELETE ON review_token_revocations
BEGIN SELECT RAISE(ABORT, 'review token revocations are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (56);

COMMIT;
