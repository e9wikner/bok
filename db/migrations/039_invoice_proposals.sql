-- Migration 039: fakturaförslag i tråden (fakturering F1).
-- Spec: docs/redesign/SPEC-fakturering-f1.md §4. Test: tests/test_fakturering_f1.py.
--
-- The link between an invoice draft proposed in a thread, its `draft` card
-- and the decision it follows -- `thread_drafts` (028) for invoices. A card is
-- never rewritten (SPEC-tradar.md §8.4), so whether it was issued, replaced
-- or rejected lives here. One row per draft: a change is a new draft that
-- replaces the old one (§4.2, beslut 1), never an edit in place.
--
-- A thread reset (034) removes nothing, so the row follows its thread as
-- `thread_drafts` does.

CREATE TABLE IF NOT EXISTS thread_invoice_drafts (
    draft_id            TEXT PRIMARY KEY,
    post_id             TEXT NOT NULL UNIQUE,
    thread_id           TEXT NOT NULL,
    view_key            TEXT NOT NULL,
    decision_id         TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    replaced_by         TEXT,
    invoice_id          TEXT,
    issued_at           TIMESTAMP,
    receipt_post_id     TEXT,
    last_error_code     TEXT,
    last_error_post_id  TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (draft_id) REFERENCES invoice_drafts(id),
    FOREIGN KEY (post_id) REFERENCES thread_posts(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    CHECK (status IN ('pending', 'issued', 'superseded', 'rejected')),
    CHECK (status != 'issued' OR (invoice_id IS NOT NULL AND issued_at IS NOT NULL)),
    CHECK (status != 'superseded' OR replaced_by IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_thread_invoice_drafts_view_status
    ON thread_invoice_drafts(view_key, status, created_at);

INSERT OR IGNORE INTO schema_version (version) VALUES (39);
