"""Repository for `thread_invoice_drafts` (migration 039,
docs/redesign/SPEC-fakturering-f1.md §4).

All SQL for `thread_invoice_drafts` lives here (AGENTS.md's layering rule),
in the same `@staticmethod` / `_commit` form as `thread_draft_repo.py`.

§4.2's lifecycle is enforced here, not trusted to callers: every status
change is a single `UPDATE ... WHERE status = 'pending'`, and a zero
`rowcount` raises `ThreadDraftTransitionError`. Issued, superseded and
rejected are final.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from db.database import db
from domain.models import InvoiceProposal
from repositories.thread_draft_repo import ThreadDraftTransitionError

STATUSES = ("pending", "issued", "superseded", "rejected")


class InvoiceProposalRepository:
    """Manage `thread_invoice_drafts` persistence."""

    @staticmethod
    def create(
        *,
        draft_id: str,
        thread_id: str,
        post_id: str,
        view_key: str,
        decision_id: Optional[str] = None,
        _commit: bool = True,
    ) -> InvoiceProposal:
        """Insert one `pending` row. The draft and the `draft` post must
        already exist (real foreign keys)."""
        now = datetime.now()
        db.execute(
            """
            INSERT INTO thread_invoice_drafts
            (draft_id, thread_id, post_id, view_key, decision_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (draft_id, thread_id, post_id, view_key, decision_id, now),
        )
        if _commit:
            db.commit()
        return InvoiceProposal(
            draft_id=draft_id,
            thread_id=thread_id,
            post_id=post_id,
            view_key=view_key,
            decision_id=decision_id,
            created_at=now,
        )

    @staticmethod
    def get(draft_id: str) -> Optional[InvoiceProposal]:
        row = db.execute(
            "SELECT * FROM thread_invoice_drafts WHERE draft_id = ? LIMIT 1",
            (draft_id,),
        ).fetchone()
        return InvoiceProposalRepository._row_to_proposal(row) if row else None

    @staticmethod
    def pending_post_ids(draft_ids: Sequence[str]) -> Dict[str, str]:
        """`draft_id -> post_id` for the drafts among `draft_ids` that have a
        pending card, in one query."""
        ids = list(dict.fromkeys(draft_ids))
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = db.execute(
            "SELECT draft_id, post_id FROM thread_invoice_drafts "
            f"WHERE status = 'pending' AND draft_id IN ({placeholders})",
            tuple(ids),
        ).fetchall()
        return {r["draft_id"]: r["post_id"] for r in rows}

    @staticmethod
    def list(
        *,
        view_key: str,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Tuple[List[InvoiceProposal], int]:
        """Proposals for one view, oldest first, and the total before
        `limit`. `status` is one of `STATUSES`, or `None`/`'all'`."""
        clauses = ["view_key = ?"]
        params: List[Any] = [view_key]
        if status is not None and status != "all":
            if status not in STATUSES:
                raise ValueError(f"unknown invoice proposal status: {status!r}")
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses)
        total = db.execute(
            "SELECT COUNT(*) AS n FROM thread_invoice_drafts" + where, tuple(params)
        ).fetchone()["n"]
        sql = (
            "SELECT * FROM thread_invoice_drafts"
            + where
            + " ORDER BY created_at, rowid"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = db.execute(sql, tuple(params)).fetchall()
        return [InvoiceProposalRepository._row_to_proposal(r) for r in rows], total

    @staticmethod
    def count_pending_not_yet_counted(*, view_key: Optional[str]) -> int:
        """The pending proposals `DecisionService.count_waiting` adds on top
        of the open decisions (§10.3), with `thread_drafts`' rule: one whose
        `decision_id` is an open decision in the same filter is already
        counted; the rest once per decision, else one each."""
        row = db.execute(
            """
            SELECT COUNT(DISTINCT COALESCE(
                'decision:' || tid.decision_id,
                'invoice:' || tid.draft_id
            )) AS n
            FROM thread_invoice_drafts tid
            LEFT JOIN decisions d ON d.id = tid.decision_id
            WHERE tid.status = 'pending'
              AND (? IS NULL OR tid.view_key = ?)
              AND NOT (
                  d.id IS NOT NULL AND d.status = 'open'
                  AND (? IS NULL OR d.view_key = ?)
              )
            """,
            (view_key, view_key, view_key, view_key),
        ).fetchone()
        return row["n"]

    @staticmethod
    def decision_ids_pending(view_key: str) -> List[str]:
        """Decisions with a pending proposal in the view (for the view's
        rows, like FV §11.2: the proposal stands in the decision's place)."""
        rows = db.execute(
            "SELECT DISTINCT decision_id FROM thread_invoice_drafts "
            "WHERE status = 'pending' AND view_key = ? AND decision_id IS NOT NULL",
            (view_key,),
        ).fetchall()
        return [r["decision_id"] for r in rows]

    # -- transitions ------------------------------------------------------

    @staticmethod
    def mark_issued(
        draft_id: str, invoice_id: str, issued_at: datetime, _commit: bool = True
    ) -> InvoiceProposal:
        """`pending -> issued`, in the issue's transaction (§7.3)."""
        return InvoiceProposalRepository._update_pending(
            draft_id,
            "issued",
            "status = 'issued', invoice_id = ?, issued_at = ?",
            (invoice_id, issued_at),
            _commit,
        )

    @staticmethod
    def mark_superseded(
        draft_id: str, replaced_by: str, _commit: bool = True
    ) -> InvoiceProposal:
        """`pending -> superseded`, pointing at the replacing draft (§4.2)."""
        return InvoiceProposalRepository._update_pending(
            draft_id,
            "superseded",
            "status = 'superseded', replaced_by = ?",
            (replaced_by,),
            _commit,
        )

    @staticmethod
    def mark_rejected(draft_id: str, _commit: bool = True) -> InvoiceProposal:
        """`pending -> rejected` (§5.4, `reject_reason`)."""
        return InvoiceProposalRepository._update_pending(
            draft_id, "rejected", "status = 'rejected'", (), _commit
        )

    @staticmethod
    def set_error(
        draft_id: str, code: str, post_id: Optional[str], _commit: bool = True
    ) -> InvoiceProposal:
        """A failed issue (§9): the status stays `pending`."""
        return InvoiceProposalRepository._update_pending(
            draft_id,
            "error",
            "last_error_code = ?, last_error_post_id = ?",
            (code, post_id),
            _commit,
        )

    @staticmethod
    def set_receipt(
        draft_id: str, post_id: str, _commit: bool = True
    ) -> InvoiceProposal:
        """The `receipt` post written after commit (§7.4). Only on an issued
        row, and only once."""
        cursor = db.execute(
            "UPDATE thread_invoice_drafts SET receipt_post_id = ? "
            "WHERE draft_id = ? AND status = 'issued' AND receipt_post_id IS NULL",
            (post_id, draft_id),
        )
        return InvoiceProposalRepository._after_update(
            cursor.rowcount, draft_id, "receipt", _commit
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _update_pending(
        draft_id: str,
        target: str,
        assignments: str,
        params: Tuple[Any, ...],
        _commit: bool,
    ) -> InvoiceProposal:
        cursor = db.execute(
            f"UPDATE thread_invoice_drafts SET {assignments} "
            "WHERE draft_id = ? AND status = 'pending'",
            (*params, draft_id),
        )
        return InvoiceProposalRepository._after_update(
            cursor.rowcount, draft_id, target, _commit
        )

    @staticmethod
    def _after_update(
        rowcount: int, draft_id: str, target: str, _commit: bool
    ) -> InvoiceProposal:
        proposal = InvoiceProposalRepository.get(draft_id)
        if rowcount != 1 or proposal is None:
            raise ThreadDraftTransitionError(
                draft_id, target, proposal.status if proposal else None
            )
        if _commit:
            db.commit()
        return proposal

    @staticmethod
    def _row_to_proposal(row) -> InvoiceProposal:
        return InvoiceProposal(
            draft_id=row["draft_id"],
            thread_id=row["thread_id"],
            post_id=row["post_id"],
            view_key=row["view_key"],
            status=row["status"],
            decision_id=row["decision_id"],
            replaced_by=row["replaced_by"],
            invoice_id=row["invoice_id"],
            issued_at=_parse_datetime(row["issued_at"]),
            receipt_post_id=row["receipt_post_id"],
            last_error_code=row["last_error_code"],
            last_error_post_id=row["last_error_post_id"],
            created_at=_parse_datetime(row["created_at"]) or datetime.now(),
        )


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
