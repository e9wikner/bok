"""Fiscal-year proposals and the underlag waiting on them (migration 041)."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from db.database import db
from domain.models import FiscalYearProposal

#: SQL fragment for `intake_sources`: the source is not waiting on a pending
#: fiscal-year proposal. Used by the intake pass's queue.
NOT_WAITING_FOR_FISCAL_YEAR_SQL = (
    "NOT EXISTS (SELECT 1 FROM fiscal_year_proposal_sources fps"
    " JOIN fiscal_year_proposals fp ON fp.id = fps.proposal_id"
    " WHERE fp.status = 'pending' AND fps.intake_source_id = intake_sources.id)"
)


class FiscalYearProposalRepository:
    @staticmethod
    def create(
        *,
        decision_id: str,
        create_option_id: str,
        thread_id: str,
        start_date: date,
        end_date: date,
        document_date: date,
        created_by: str,
        _commit: bool = True,
    ) -> FiscalYearProposal:
        proposal_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO fiscal_year_proposals
            (id, decision_id, create_option_id, thread_id, start_date, end_date,
             document_date, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                proposal_id,
                decision_id,
                create_option_id,
                thread_id,
                start_date,
                end_date,
                document_date,
                created_by,
                now,
            ),
        )
        if _commit:
            db.commit()
        proposal = FiscalYearProposalRepository.get(proposal_id)
        assert proposal is not None
        return proposal

    @staticmethod
    def add_sources(
        proposal_id: str, source_ids: List[str], _commit: bool = True
    ) -> None:
        for source_id in source_ids:
            db.execute(
                "INSERT OR IGNORE INTO fiscal_year_proposal_sources "
                "(proposal_id, intake_source_id, created_at) VALUES (?, ?, ?)",
                (proposal_id, source_id, datetime.now()),
            )
        if _commit:
            db.commit()

    @staticmethod
    def get(proposal_id: str) -> Optional[FiscalYearProposal]:
        row = db.execute(
            "SELECT * FROM fiscal_year_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        return FiscalYearProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[FiscalYearProposal]:
        row = db.execute(
            "SELECT * FROM fiscal_year_proposals WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return FiscalYearProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def find_pending(start_date: date, end_date: date) -> Optional[FiscalYearProposal]:
        row = db.execute(
            "SELECT * FROM fiscal_year_proposals "
            "WHERE status = 'pending' AND start_date = ? AND end_date = ?",
            (start_date, end_date),
        ).fetchone()
        return FiscalYearProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def list_pending() -> List[FiscalYearProposal]:
        rows = db.execute(
            "SELECT * FROM fiscal_year_proposals WHERE status = 'pending' "
            "ORDER BY start_date"
        ).fetchall()
        return [FiscalYearProposalRepository._to_proposal(row) for row in rows]

    @staticmethod
    def pending_for_source(source_id: str) -> Optional[FiscalYearProposal]:
        row = db.execute(
            """
            SELECT fp.* FROM fiscal_year_proposals fp
            JOIN fiscal_year_proposal_sources fps ON fps.proposal_id = fp.id
            WHERE fp.status = 'pending' AND fps.intake_source_id = ?
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()
        return FiscalYearProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def resolve(
        proposal_id: str,
        status: str,
        *,
        actor: str,
        fiscal_year_id: Optional[str] = None,
        _commit: bool = True,
    ) -> None:
        """Move a pending proposal to `created`, `declined` or `superseded`.
        Only a pending one moves: a second press is a no-op here."""
        db.execute(
            """
            UPDATE fiscal_year_proposals
            SET status = ?, fiscal_year_id = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, fiscal_year_id, datetime.now(), actor, proposal_id),
        )
        if _commit:
            db.commit()

    @staticmethod
    def _source_ids(proposal_id: str) -> List[str]:
        rows = db.execute(
            "SELECT intake_source_id FROM fiscal_year_proposal_sources "
            "WHERE proposal_id = ? ORDER BY created_at, intake_source_id",
            (proposal_id,),
        ).fetchall()
        return [row["intake_source_id"] for row in rows]

    @staticmethod
    def _to_proposal(row) -> FiscalYearProposal:
        return FiscalYearProposal(
            id=row["id"],
            decision_id=row["decision_id"],
            create_option_id=row["create_option_id"],
            thread_id=row["thread_id"],
            start_date=_date(row["start_date"]),
            end_date=_date(row["end_date"]),
            document_date=_date(row["document_date"]),
            status=row["status"],
            created_by=row["created_by"],
            created_at=_datetime(row["created_at"]),
            fiscal_year_id=row["fiscal_year_id"],
            resolved_at=(_datetime(row["resolved_at"]) if row["resolved_at"] else None),
            resolved_by=row["resolved_by"],
            source_ids=FiscalYearProposalRepository._source_ids(row["id"]),
        )


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
