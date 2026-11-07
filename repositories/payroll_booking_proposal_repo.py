"""Payroll booking proposals (migration 043)."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from db.database import db
from domain.models import PayrollBookingProposal


class PayrollBookingProposalRepository:
    @staticmethod
    def create(
        *,
        decision_id: str,
        thread_id: str,
        kind: str,
        book_option_id: str,
        created_by: str,
        payslip_id: Optional[str] = None,
        bank_transaction_id: Optional[str] = None,
        agi_year: Optional[int] = None,
        agi_month: Optional[int] = None,
        voucher_date: Optional[date] = None,
        _commit: bool = True,
    ) -> PayrollBookingProposal:
        proposal_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO payroll_booking_proposals
            (id, decision_id, thread_id, kind, book_option_id, payslip_id,
             bank_transaction_id, agi_year, agi_month, voucher_date, status,
             created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                proposal_id,
                decision_id,
                thread_id,
                kind,
                book_option_id,
                payslip_id,
                bank_transaction_id,
                agi_year,
                agi_month,
                voucher_date.isoformat() if voucher_date else None,
                created_by,
                datetime.now(),
            ),
        )
        if _commit:
            db.commit()
        proposal = PayrollBookingProposalRepository.get(proposal_id)
        assert proposal is not None
        return proposal

    @staticmethod
    def get(proposal_id: str) -> Optional[PayrollBookingProposal]:
        row = db.execute(
            "SELECT * FROM payroll_booking_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        return PayrollBookingProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[PayrollBookingProposal]:
        row = db.execute(
            "SELECT * FROM payroll_booking_proposals WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return PayrollBookingProposalRepository._to_proposal(row) if row else None

    @staticmethod
    def pending_for_payslip(payslip_id: str) -> List[PayrollBookingProposal]:
        rows = db.execute(
            """
            SELECT * FROM payroll_booking_proposals
            WHERE kind = 'payslip' AND payslip_id = ? AND status = 'pending'
            ORDER BY created_at
            """,
            (payslip_id,),
        ).fetchall()
        return [PayrollBookingProposalRepository._to_proposal(row) for row in rows]

    @staticmethod
    def pending_for_bank_transaction(
        bank_transaction_id: str,
    ) -> List[PayrollBookingProposal]:
        rows = db.execute(
            """
            SELECT * FROM payroll_booking_proposals
            WHERE kind = 'payslip' AND bank_transaction_id = ?
              AND status = 'pending'
            ORDER BY created_at
            """,
            (bank_transaction_id,),
        ).fetchall()
        return [PayrollBookingProposalRepository._to_proposal(row) for row in rows]

    @staticmethod
    def pending_for_agi(year: int, month: int) -> List[PayrollBookingProposal]:
        rows = db.execute(
            """
            SELECT * FROM payroll_booking_proposals
            WHERE kind = 'agi' AND agi_year = ? AND agi_month = ?
              AND status = 'pending'
            ORDER BY created_at
            """,
            (year, month),
        ).fetchall()
        return [PayrollBookingProposalRepository._to_proposal(row) for row in rows]

    @staticmethod
    def resolve(
        proposal_id: str, status: str, *, actor: str, _commit: bool = True
    ) -> None:
        """Move a pending proposal to `booked`, `declined`, `superseded` or
        `failed`. Only a pending one moves: a second press is a no-op here."""
        db.execute(
            """
            UPDATE payroll_booking_proposals
            SET status = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, datetime.now(), actor, proposal_id),
        )
        if _commit:
            db.commit()

    @staticmethod
    def _to_proposal(row) -> PayrollBookingProposal:
        return PayrollBookingProposal(
            id=row["id"],
            decision_id=row["decision_id"],
            thread_id=row["thread_id"],
            kind=row["kind"],
            book_option_id=row["book_option_id"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=_datetime(row["created_at"]),
            payslip_id=row["payslip_id"],
            bank_transaction_id=row["bank_transaction_id"],
            agi_year=row["agi_year"],
            agi_month=row["agi_month"],
            voucher_date=_date(row["voucher_date"]) if row["voucher_date"] else None,
            resolved_at=(_datetime(row["resolved_at"]) if row["resolved_at"] else None),
            resolved_by=row["resolved_by"],
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
