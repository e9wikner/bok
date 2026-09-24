"""Repository for `thread_drafts` (migration 028,
SPEC-flode-verifikationer.md §6).

All SQL for `thread_drafts` lives here — see AGENTS.md's layering rule. Same
`@staticmethod` form and `_commit: bool = True` convention as
`repositories/decision_repo.py`, so `foresla_verifikation` (F6) can write
draft, row and post in one transaction, and the posting route (F11) can mark
the row posted inside the posting's own transaction.

§6.2's lifecycle is enforced here, not trusted to callers: every status
change is a single `UPDATE ... WHERE status = 'pending'`, and a zero
`rowcount` raises `ThreadDraftTransitionError`. Posted and superseded are
final.
"""

import json
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple

from db.database import db
from domain.models import ThreadDraft

STATUSES = ("pending", "posted", "superseded")


class ThreadDraftTransitionError(ValueError):
    """A write that §6.2 does not allow from the row's current state —
    including the row not existing (`current_status is None`)."""

    def __init__(
        self, voucher_id: str, target_status: str, current_status: Optional[str]
    ):
        self.voucher_id = voucher_id
        self.target_status = target_status
        self.current_status = current_status
        state = current_status if current_status is not None else "missing"
        super().__init__(
            f"thread draft {voucher_id}: cannot apply '{target_status}' "
            f"from '{state}'"
        )


class ThreadDraftRepository:
    """Manage `thread_drafts` persistence."""

    @staticmethod
    def create(
        *,
        voucher_id: str,
        thread_id: str,
        post_id: str,
        view_key: str,
        decision_id: Optional[str] = None,
        correction_of: Optional[str] = None,
        correction_note_id: Optional[str] = None,
        intake_source_ids: Sequence[str] = (),
        bank_input_ids: Sequence[str] = (),
        bank_transaction_ids: Sequence[str] = (),
        _commit: bool = True,
    ) -> ThreadDraft:
        """Insert one row, `status='pending'`. `post_id` must already exist
        (a real foreign key), so the `draft` post is written first.

        The three id lists are the traceability a posting of this draft must
        link (migration 029); stored as one JSON object."""
        now = datetime.now()
        traceability = {
            "intake_source_ids": list(intake_source_ids),
            "bank_input_ids": list(bank_input_ids),
            "bank_transaction_ids": list(bank_transaction_ids),
        }
        db.execute(
            """
            INSERT INTO thread_drafts
            (voucher_id, thread_id, post_id, view_key, decision_id,
             correction_of, correction_note_id, status, created_at,
             traceability_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                voucher_id,
                thread_id,
                post_id,
                view_key,
                decision_id,
                correction_of,
                correction_note_id,
                now,
                json.dumps(traceability),
            ),
        )
        if _commit:
            db.commit()
        return ThreadDraft(
            voucher_id=voucher_id,
            thread_id=thread_id,
            post_id=post_id,
            view_key=view_key,
            status="pending",
            decision_id=decision_id,
            correction_of=correction_of,
            correction_note_id=correction_note_id,
            created_at=now,
            intake_source_ids=traceability["intake_source_ids"],
            bank_input_ids=traceability["bank_input_ids"],
            bank_transaction_ids=traceability["bank_transaction_ids"],
        )

    @staticmethod
    def get(voucher_id: str) -> Optional[ThreadDraft]:
        row = db.execute(
            "SELECT * FROM thread_drafts WHERE voucher_id = ? LIMIT 1", (voucher_id,)
        ).fetchone()
        return ThreadDraftRepository._row_to_draft(row) if row else None

    @staticmethod
    def get_by_post(post_id: str) -> Optional[ThreadDraft]:
        row = db.execute(
            "SELECT * FROM thread_drafts WHERE post_id = ? LIMIT 1", (post_id,)
        ).fetchone()
        return ThreadDraftRepository._row_to_draft(row) if row else None

    @staticmethod
    def list(
        *,
        view_key: str,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Tuple[List[ThreadDraft], int]:
        """Drafts for one view, oldest first, and the total before `limit`
        (§10). `status` is one of `STATUSES`, or `None`/`'all'` for every
        status."""
        clauses = ["view_key = ?"]
        params: List[Any] = [view_key]
        if status is not None and status != "all":
            if status not in STATUSES:
                raise ValueError(f"unknown thread draft status: {status!r}")
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses)

        total = db.execute(
            "SELECT COUNT(*) AS n FROM thread_drafts" + where, tuple(params)
        ).fetchone()["n"]

        sql = "SELECT * FROM thread_drafts" + where + " ORDER BY created_at, rowid"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = db.execute(sql, tuple(params)).fetchall()
        return [ThreadDraftRepository._row_to_draft(r) for r in rows], total

    @staticmethod
    def count_pending_not_yet_counted(
        *,
        view_key: Optional[str],
        open_note_statuses: Sequence[str],
        notes_counted: bool,
    ) -> int:
        """The pending drafts `DecisionService.count_waiting` adds on top of
        the open decisions (§11.3), in one statement.

        A pending draft is left out when what it answers is already counted
        in the same number: its `decision_id` is an open decision in the same
        filter (`view_key`, or every view when `None`), or -- when
        `notes_counted`, i.e. the synthetic `correction:` decisions are in
        the count -- its `correction_note_id` is an open correction note.
        The rest are counted once per decision, once per note, and one each
        when they answer neither: `COUNT(DISTINCT ...)` over that key, so a
        decision with two pending drafts still waits as one thing."""
        placeholders = ", ".join("?" for _ in open_note_statuses)
        note_counted = (
            f"(cn.id IS NOT NULL AND cn.status IN ({placeholders}))"
            if notes_counted and open_note_statuses
            else "0"
        )
        sql = f"""
            SELECT COUNT(DISTINCT COALESCE(
                'decision:' || td.decision_id,
                'note:' || td.correction_note_id,
                'draft:' || td.voucher_id
            )) AS n
            FROM thread_drafts td
            LEFT JOIN decisions d ON d.id = td.decision_id
            LEFT JOIN correction_notes cn ON cn.id = td.correction_note_id
            WHERE td.status = 'pending'
              AND (? IS NULL OR td.view_key = ?)
              AND NOT (
                  d.id IS NOT NULL AND d.status = 'open'
                  AND (? IS NULL OR d.view_key = ?)
              )
              AND NOT {note_counted}
        """
        params: List[Any] = [view_key, view_key, view_key, view_key]
        if notes_counted:
            params.extend(open_note_statuses)
        return db.execute(sql, tuple(params)).fetchone()["n"]

    @staticmethod
    def pending_for_correction_of(voucher_id: str) -> Optional[ThreadDraft]:
        """The pending draft that corrects `voucher_id`, in any thread —
        `correction_already_pending` (§7.4). Oldest first if there were ever
        more than one."""
        row = db.execute(
            "SELECT * FROM thread_drafts "
            "WHERE correction_of = ? AND status = 'pending' "
            "ORDER BY created_at, rowid LIMIT 1",
            (voucher_id,),
        ).fetchone()
        return ThreadDraftRepository._row_to_draft(row) if row else None

    @staticmethod
    def pending_in_period(period_id: str) -> List[ThreadDraft]:
        """The pending drafts whose voucher lies in `period_id`, oldest
        first -- what a lock of the period marks `period_locked` (F16)."""
        rows = db.execute(
            "SELECT td.* FROM thread_drafts td "
            "JOIN vouchers v ON v.id = td.voucher_id "
            "WHERE td.status = 'pending' AND v.period_id = ? "
            "ORDER BY td.created_at, td.rowid",
            (period_id,),
        ).fetchall()
        return [ThreadDraftRepository._row_to_draft(r) for r in rows]

    @staticmethod
    def mark_posted(
        voucher_id: str, posted_at: datetime, _commit: bool = True
    ) -> ThreadDraft:
        """`pending -> posted` (§6.2), in the posting's transaction (§8.1)."""
        return ThreadDraftRepository._update_pending(
            voucher_id,
            "posted",
            "status = 'posted', posted_at = ?",
            (posted_at,),
            _commit,
        )

    @staticmethod
    def mark_superseded(
        voucher_id: str, replaced_by: str, _commit: bool = True
    ) -> ThreadDraft:
        """`pending -> superseded` (§6.2), pointing at the replacing draft."""
        return ThreadDraftRepository._update_pending(
            voucher_id,
            "superseded",
            "status = 'superseded', replaced_by = ?",
            (replaced_by,),
            _commit,
        )

    @staticmethod
    def set_error(
        voucher_id: str,
        code: str,
        post_id: Optional[str],
        _commit: bool = True,
    ) -> ThreadDraft:
        """A failed posting attempt (§9): the status stays `pending`.
        `post_id` is the `error` post, or `None` when none was written."""
        return ThreadDraftRepository._update_pending(
            voucher_id,
            "error",
            "last_error_code = ?, last_error_post_id = ?",
            (code, post_id),
            _commit,
        )

    @staticmethod
    def set_receipt(voucher_id: str, post_id: str, _commit: bool = True) -> ThreadDraft:
        """The `receipt` post written after commit (§8.1). Only on a posted
        row, and only once: a second receipt for the same draft is a bug in
        the resume path, not something to overwrite silently."""
        cursor = db.execute(
            "UPDATE thread_drafts SET receipt_post_id = ? "
            "WHERE voucher_id = ? AND status = 'posted' "
            "AND receipt_post_id IS NULL",
            (post_id, voucher_id),
        )
        return ThreadDraftRepository._after_update(
            cursor.rowcount, voucher_id, "receipt", _commit
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _update_pending(
        voucher_id: str,
        target: str,
        assignments: str,
        params: Tuple[Any, ...],
        _commit: bool,
    ) -> ThreadDraft:
        cursor = db.execute(
            f"UPDATE thread_drafts SET {assignments} "
            "WHERE voucher_id = ? AND status = 'pending'",
            (*params, voucher_id),
        )
        return ThreadDraftRepository._after_update(
            cursor.rowcount, voucher_id, target, _commit
        )

    @staticmethod
    def _after_update(
        rowcount: int, voucher_id: str, target: str, _commit: bool
    ) -> ThreadDraft:
        draft = ThreadDraftRepository.get(voucher_id)
        if rowcount != 1 or draft is None:
            raise ThreadDraftTransitionError(
                voucher_id, target, draft.status if draft else None
            )
        if _commit:
            db.commit()
        return draft

    @staticmethod
    def _row_to_draft(row) -> ThreadDraft:
        traceability = json.loads(row["traceability_json"] or "{}")
        return ThreadDraft(
            voucher_id=row["voucher_id"],
            thread_id=row["thread_id"],
            post_id=row["post_id"],
            view_key=row["view_key"],
            status=row["status"],
            decision_id=row["decision_id"],
            correction_of=row["correction_of"],
            correction_note_id=row["correction_note_id"],
            replaced_by=row["replaced_by"],
            posted_at=_parse_datetime(row["posted_at"]),
            receipt_post_id=row["receipt_post_id"],
            last_error_code=row["last_error_code"],
            last_error_post_id=row["last_error_post_id"],
            created_at=_parse_required_datetime(row["created_at"]),
            intake_source_ids=list(traceability.get("intake_source_ids", [])),
            bank_input_ids=list(traceability.get("bank_input_ids", [])),
            bank_transaction_ids=list(traceability.get("bank_transaction_ids", [])),
        )


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _parse_required_datetime(value: Any) -> datetime:
    """`created_at` is `NOT NULL` in the schema."""
    parsed = _parse_datetime(value)
    assert parsed is not None
    return parsed
