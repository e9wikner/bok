"""Repositories for `intake_link_proposals`, `intake_reuse_approvals` and
`intake_reuse_revocations` (migration 044: one underlag, several vouchers).

All SQL for the three tables lives here -- AGENTS.md's layering rule. An
approval and its revocation are append-only: insert and read, nothing else
(the triggers refuse the rest anyway). A proposal row moves only out of
`pending`, as the other card tables do.
"""

import uuid
from datetime import datetime
from typing import Any, List, Optional

from db.database import db
from domain.intake_link import IntakeLinkProposal, ReuseApproval


def _dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class IntakeLinkProposalRepository:
    """`intake_link_proposals`: one row per `foresla_delat_underlag` card."""

    @staticmethod
    def create(
        *,
        decision_id: str,
        thread_id: str,
        intake_source_id: str,
        voucher_id: str,
        fiscal_year_id: str,
        once_option_id: str,
        standing_option_id: str,
        created_by: str,
        _commit: bool = True,
    ) -> IntakeLinkProposal:
        proposal_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO intake_link_proposals
            (id, decision_id, thread_id, intake_source_id, voucher_id,
             fiscal_year_id, once_option_id, standing_option_id, status,
             created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                proposal_id,
                decision_id,
                thread_id,
                intake_source_id,
                voucher_id,
                fiscal_year_id,
                once_option_id,
                standing_option_id,
                created_by,
                datetime.now(),
            ),
        )
        if _commit:
            db.commit()
        proposal = IntakeLinkProposalRepository.get_by_decision(decision_id)
        assert proposal is not None
        return proposal

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[IntakeLinkProposal]:
        row = db.execute(
            "SELECT * FROM intake_link_proposals WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return _row_to_proposal(row) if row else None

    @staticmethod
    def resolve(
        proposal_id: str, status: str, *, actor: str, _commit: bool = True
    ) -> None:
        """`pending` -> *status*; a row already resolved is left as it is."""
        db.execute(
            """
            UPDATE intake_link_proposals
            SET status = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, datetime.now(), actor, proposal_id),
        )
        if _commit:
            db.commit()


class ReuseApprovalRepository:
    """`intake_reuse_approvals` and `intake_reuse_revocations`: insert and
    read only."""

    _SELECT = """
        SELECT a.*, r.created_at AS revoked_at, r.revoked_by AS revoked_by,
               r.reason AS revoke_reason
        FROM intake_reuse_approvals a
        LEFT JOIN intake_reuse_revocations r ON r.approval_id = a.id
    """

    @staticmethod
    def create(
        *,
        intake_source_id: str,
        fiscal_year_id: str,
        decision_id: str,
        approved_by: str,
        _commit: bool = True,
    ) -> ReuseApproval:
        approval_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO intake_reuse_approvals
            (id, intake_source_id, fiscal_year_id, decision_id, approved_by,
             created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                intake_source_id,
                fiscal_year_id,
                decision_id,
                approved_by,
                datetime.now(),
            ),
        )
        if _commit:
            db.commit()
        approval = ReuseApprovalRepository.get(approval_id)
        assert approval is not None
        return approval

    @staticmethod
    def get(approval_id: str) -> Optional[ReuseApproval]:
        row = db.execute(
            ReuseApprovalRepository._SELECT + " WHERE a.id = ?", (approval_id,)
        ).fetchone()
        return _row_to_approval(row) if row else None

    @staticmethod
    def active_for(source_id: str, fiscal_year_id: str) -> Optional[ReuseApproval]:
        """The source's unrevoked approval for the fiscal year, or `None`."""
        row = db.execute(
            ReuseApprovalRepository._SELECT
            + " WHERE a.intake_source_id = ? AND a.fiscal_year_id = ?"
            " AND r.approval_id IS NULL"
            " ORDER BY a.created_at DESC, a.rowid DESC LIMIT 1",
            (source_id, fiscal_year_id),
        ).fetchone()
        return _row_to_approval(row) if row else None

    @staticmethod
    def list_for_source(source_id: str) -> List[ReuseApproval]:
        """Every approval of the source, revoked ones included, oldest
        first."""
        rows = db.execute(
            ReuseApprovalRepository._SELECT
            + " WHERE a.intake_source_id = ? ORDER BY a.created_at, a.rowid",
            (source_id,),
        ).fetchall()
        return [_row_to_approval(r) for r in rows]

    @staticmethod
    def revoke(
        approval_id: str, *, revoked_by: str, reason: str, _commit: bool = True
    ) -> None:
        db.execute(
            """
            INSERT INTO intake_reuse_revocations
            (approval_id, revoked_by, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (approval_id, revoked_by, reason, datetime.now()),
        )
        if _commit:
            db.commit()


def _row_to_proposal(row) -> IntakeLinkProposal:
    created_at = _dt(row["created_at"])
    assert created_at is not None
    return IntakeLinkProposal(
        id=row["id"],
        decision_id=row["decision_id"],
        thread_id=row["thread_id"],
        intake_source_id=row["intake_source_id"],
        voucher_id=row["voucher_id"],
        fiscal_year_id=row["fiscal_year_id"],
        once_option_id=row["once_option_id"],
        standing_option_id=row["standing_option_id"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=created_at,
        resolved_at=_dt(row["resolved_at"]),
        resolved_by=row["resolved_by"],
    )


def _row_to_approval(row) -> ReuseApproval:
    created_at = _dt(row["created_at"])
    assert created_at is not None
    return ReuseApproval(
        id=row["id"],
        intake_source_id=row["intake_source_id"],
        fiscal_year_id=row["fiscal_year_id"],
        decision_id=row["decision_id"],
        approved_by=row["approved_by"],
        created_at=created_at,
        revoked_at=_dt(row["revoked_at"]),
        revoked_by=row["revoked_by"],
        revoke_reason=row["revoke_reason"],
    )
