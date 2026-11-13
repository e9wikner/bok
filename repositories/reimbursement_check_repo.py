"""`reimbursement_checks` (migration 045): the utläggs cards and the underlag
waiting on them. A row moves only out of `pending`, as the other card
tables do."""

import uuid
from datetime import datetime
from typing import Optional

from db.database import db
from domain.reimbursement import ReimbursementCheck
from repositories.dates import as_datetime

#: SQL fragment for `intake_sources`: the source is not waiting on a pending
#: utläggs card. Used by the intake pass's queue.
NOT_WAITING_FOR_REIMBURSEMENT_SQL = (
    "NOT EXISTS (SELECT 1 FROM reimbursement_checks rc"
    " WHERE rc.status = 'pending' AND rc.intake_source_id = intake_sources.id)"
)


class ReimbursementCheckRepository:
    @staticmethod
    def create(
        *,
        intake_source_id: str,
        bank_transaction_id: str,
        decision_id: str,
        reimbursement_option_id: str,
        company_paid_option_id: str,
        thread_id: str,
        created_by: str,
        _commit: bool = True,
    ) -> ReimbursementCheck:
        check_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO reimbursement_checks
            (id, intake_source_id, bank_transaction_id, decision_id,
             reimbursement_option_id, company_paid_option_id, thread_id,
             status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                check_id,
                intake_source_id,
                bank_transaction_id,
                decision_id,
                reimbursement_option_id,
                company_paid_option_id,
                thread_id,
                created_by,
                datetime.now(),
            ),
        )
        if _commit:
            db.commit()
        check = ReimbursementCheckRepository.get(check_id)
        assert check is not None
        return check

    @staticmethod
    def get(check_id: str) -> Optional[ReimbursementCheck]:
        row = db.execute(
            "SELECT * FROM reimbursement_checks WHERE id = ?", (check_id,)
        ).fetchone()
        return ReimbursementCheckRepository._to_check(row) if row else None

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[ReimbursementCheck]:
        row = db.execute(
            "SELECT * FROM reimbursement_checks WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return ReimbursementCheckRepository._to_check(row) if row else None

    @staticmethod
    def latest_for_source(source_id: str) -> Optional[ReimbursementCheck]:
        """The source's newest card that is not superseded: pending, or the
        answer that counts."""
        row = db.execute(
            """
            SELECT * FROM reimbursement_checks
            WHERE intake_source_id = ? AND status != 'superseded'
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (source_id,),
        ).fetchone()
        return ReimbursementCheckRepository._to_check(row) if row else None

    @staticmethod
    def resolve(
        check_id: str, status: str, *, actor: str, _commit: bool = True
    ) -> None:
        """Only a pending row moves: a second press is a no-op here."""
        db.execute(
            """
            UPDATE reimbursement_checks
            SET status = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, datetime.now(), actor, check_id),
        )
        if _commit:
            db.commit()

    @staticmethod
    def _to_check(row) -> ReimbursementCheck:
        return ReimbursementCheck(
            id=row["id"],
            intake_source_id=row["intake_source_id"],
            bank_transaction_id=row["bank_transaction_id"],
            decision_id=row["decision_id"],
            reimbursement_option_id=row["reimbursement_option_id"],
            company_paid_option_id=row["company_paid_option_id"],
            thread_id=row["thread_id"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=as_datetime(row["created_at"]),  # type: ignore[arg-type]
            resolved_at=as_datetime(row["resolved_at"]),
            resolved_by=row["resolved_by"],
        )
