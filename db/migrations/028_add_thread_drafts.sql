-- Migration 028: flode-verifikationer — thread_drafts (SPEC-flode-verifikationer.md §6)
--
-- The link between a draft voucher, the thread it was proposed in, the
-- decision it follows and the correction note it answers. A `draft` post is
-- never rewritten (SPEC-tradar.md §8.4), so whether the card was posted or
-- replaced has to live somewhere else — this table.
--
-- No foreign key to `vouchers`: a superseded draft is deleted
-- (`VoucherRepository.delete_draft`, §6.2) while its row here stays, because
-- the post in the thread stays and must still be able to say what happened to
-- it. And no column on `vouchers`: the link lives beside the ledger, not in
-- it — the ledger's table was just rebuilt in 027 and carries nothing about
-- threads.
--
-- The two CHECKs put §6.2's lifecycle in the schema: three states and no
-- more, and a posted row always says when. That only pending -> posted and
-- pending -> superseded happen is `ThreadDraftRepository`'s job
-- (`WHERE status = 'pending'`); a CHECK cannot see the previous value.

CREATE TABLE IF NOT EXISTS thread_drafts (
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
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES thread_posts(id),
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (correction_note_id) REFERENCES correction_notes(id),
    CHECK (status IN ('pending', 'posted', 'superseded')),
    CHECK (status != 'posted' OR posted_at IS NOT NULL)
);

-- `GET /api/v1/drafts?view_key=…&status=…` (§10), oldest first.
CREATE INDEX IF NOT EXISTS idx_thread_drafts_view_status
    ON thread_drafts(view_key, status, created_at);

-- `correction_already_pending` (§7.4): one pending correction per original,
-- in any thread.
CREATE INDEX IF NOT EXISTS idx_thread_drafts_pending_correction
    ON thread_drafts(correction_of) WHERE status = 'pending';

INSERT OR IGNORE INTO schema_version (version) VALUES (28);
