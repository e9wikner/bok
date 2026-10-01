"""Company-info proposals (migration 042)."""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Mapping, Optional

from db.database import db
from domain.models import CompanyInfoProposal


class CompanyInfoProposalRepository:
    @staticmethod
    def create(
        *,
        decision_id: str,
        thread_id: str,
        fill_option_id: Optional[str],
        overwrite_option_id: Optional[str],
        fill_values: Mapping[str, str],
        overwrite_values: Mapping[str, str],
        created_by: str,
        _commit: bool = True,
    ) -> CompanyInfoProposal:
        proposal_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO company_info_proposals
            (id, decision_id, thread_id, fill_option_id, overwrite_option_id,
             fill_values, overwrite_values, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                proposal_id,
                decision_id,
                thread_id,
                fill_option_id,
                overwrite_option_id,
                json.dumps(dict(fill_values), ensure_ascii=False),
                json.dumps(dict(overwrite_values), ensure_ascii=False),
                created_by,
                datetime.now(),
            ),
        )
        if _commit:
            db.commit()
        proposal = CompanyInfoProposalRepository.get(proposal_id)
        assert proposal is not None
        return proposal

    @staticmethod
    def get(proposal_id: str) -> Optional[CompanyInfoProposal]:
        row = db.execute(
            "SELECT * FROM company_info_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        return CompanyInfoProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[CompanyInfoProposal]:
        row = db.execute(
            "SELECT * FROM company_info_proposals WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return CompanyInfoProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def list_pending() -> List[CompanyInfoProposal]:
        rows = db.execute(
            "SELECT * FROM company_info_proposals WHERE status = 'pending' "
            "ORDER BY created_at"
        ).fetchall()
        return [CompanyInfoProposalRepository._to_proposal(row) for row in rows]

    @staticmethod
    def resolve(
        proposal_id: str, status: str, *, actor: str, _commit: bool = True
    ) -> None:
        """Move a pending proposal to `applied`, `declined` or `superseded`.
        Only a pending one moves: a second press is a no-op here."""
        db.execute(
            """
            UPDATE company_info_proposals
            SET status = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, datetime.now(), actor, proposal_id),
        )
        if _commit:
            db.commit()

    @staticmethod
    def _to_proposal(row) -> CompanyInfoProposal:
        def values(raw: Optional[str]) -> Dict[str, str]:
            return json.loads(raw) if raw else {}

        return CompanyInfoProposal(
            id=row["id"],
            decision_id=row["decision_id"],
            thread_id=row["thread_id"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=_datetime(row["created_at"]),
            fill_option_id=row["fill_option_id"],
            overwrite_option_id=row["overwrite_option_id"],
            fill_values=values(row["fill_values"]),
            overwrite_values=values(row["overwrite_values"]),
            resolved_at=(_datetime(row["resolved_at"]) if row["resolved_at"] else None),
            resolved_by=row["resolved_by"],
        )


def _datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
