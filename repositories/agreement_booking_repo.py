"""`agreement_bookings` and its two append-only tables (migration 048)."""

import uuid
from datetime import datetime
from typing import Any, Iterable, List, Optional

from db.database import db
from domain.agreement_booking import AgreementBooking

#: SQL fragment for `intake_sources`: the source is not waiting on a pending
#: agreement card. Used by the intake pass's queue.
NOT_WAITING_FOR_AGREEMENT_SQL = (
    "NOT EXISTS (SELECT 1 FROM agreement_bookings ab"
    " WHERE ab.status = 'pending' AND ab.intake_source_id = intake_sources.id)"
)


def _dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class AgreementBookingRepository:
    @staticmethod
    def create(
        *,
        decision_id: str,
        thread_id: str,
        intake_source_id: str,
        fiscal_year_id: str,
        account_code: str,
        amount_ore: int,
        description: str,
        counter_account_code: str,
        book_option_id: str,
        standing_option_id: str,
        bank_transaction_ids: Iterable[str],
        created_by: str,
        _commit: bool = True,
    ) -> AgreementBooking:
        booking_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO agreement_bookings
            (id, decision_id, thread_id, intake_source_id, fiscal_year_id,
             account_code, amount_ore, description, counter_account_code,
             book_option_id, standing_option_id, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                booking_id,
                decision_id,
                thread_id,
                intake_source_id,
                fiscal_year_id,
                account_code,
                amount_ore,
                description,
                counter_account_code,
                book_option_id,
                standing_option_id,
                created_by,
                datetime.now(),
            ),
        )
        for transaction_id in dict.fromkeys(bank_transaction_ids):
            db.execute(
                """
                INSERT INTO agreement_booking_transactions
                (booking_id, bank_transaction_id) VALUES (?, ?)
                """,
                (booking_id, transaction_id),
            )
        if _commit:
            db.commit()
        booking = AgreementBookingRepository.get(booking_id)
        assert booking is not None
        return booking

    @staticmethod
    def get(booking_id: str) -> Optional[AgreementBooking]:
        row = db.execute(
            "SELECT * FROM agreement_bookings WHERE id = ?", (booking_id,)
        ).fetchone()
        return AgreementBookingRepository._to_booking(row) if row else None

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[AgreementBooking]:
        row = db.execute(
            "SELECT * FROM agreement_bookings WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        return AgreementBookingRepository._to_booking(row) if row else None

    @staticmethod
    def pending_for_source(source_id: str) -> Optional[AgreementBooking]:
        row = db.execute(
            """
            SELECT * FROM agreement_bookings
            WHERE intake_source_id = ? AND status = 'pending'
            """,
            (source_id,),
        ).fetchone()
        return AgreementBookingRepository._to_booking(row) if row else None

    @staticmethod
    def approved_for_source(source_id: str) -> List[AgreementBooking]:
        """The source's approved cards, newest first."""
        rows = db.execute(
            """
            SELECT * FROM agreement_bookings
            WHERE intake_source_id = ?
              AND status IN ('approved', 'approved_standing')
            ORDER BY created_at DESC, rowid DESC
            """,
            (source_id,),
        ).fetchall()
        return [AgreementBookingRepository._to_booking(row) for row in rows]

    @staticmethod
    def sources_with_approved() -> List[str]:
        """The underlag with at least one approved card, oldest card first."""
        rows = db.execute("""
            SELECT intake_source_id, MIN(created_at) AS first_at
            FROM agreement_bookings
            WHERE status IN ('approved', 'approved_standing')
            GROUP BY intake_source_id
            ORDER BY first_at ASC
            """).fetchall()
        return [row["intake_source_id"] for row in rows]

    @staticmethod
    def resolve(
        booking_id: str, status: str, *, actor: str, _commit: bool = True
    ) -> None:
        """Only a pending row moves: a second press is a no-op here."""
        db.execute(
            """
            UPDATE agreement_bookings
            SET status = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, datetime.now(), actor, booking_id),
        )
        if _commit:
            db.commit()

    # -- follow-up attempts ------------------------------------------------

    @staticmethod
    def record_attempt(
        *,
        booking_id: str,
        bank_transaction_id: str,
        agent_run_id: Optional[str],
        reason: str,
        _commit: bool = True,
    ) -> None:
        db.execute(
            """
            INSERT INTO agreement_followup_attempts
            (id, booking_id, bank_transaction_id, agent_run_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                booking_id,
                bank_transaction_id,
                agent_run_id,
                reason,
                datetime.now(),
            ),
        )
        if _commit:
            db.commit()

    @staticmethod
    def attempted_transaction_ids() -> set:
        rows = db.execute(
            "SELECT DISTINCT bank_transaction_id FROM agreement_followup_attempts"
        ).fetchall()
        return {row["bank_transaction_id"] for row in rows}

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _transaction_ids(booking_id: str) -> List[str]:
        rows = db.execute(
            """
            SELECT abt.bank_transaction_id FROM agreement_booking_transactions abt
            JOIN bank_transactions bt ON bt.id = abt.bank_transaction_id
            WHERE abt.booking_id = ?
            ORDER BY bt.transaction_date ASC, bt.id ASC
            """,
            (booking_id,),
        ).fetchall()
        return [row["bank_transaction_id"] for row in rows]

    @staticmethod
    def _to_booking(row) -> AgreementBooking:
        return AgreementBooking(
            id=row["id"],
            decision_id=row["decision_id"],
            thread_id=row["thread_id"],
            intake_source_id=row["intake_source_id"],
            fiscal_year_id=row["fiscal_year_id"],
            account_code=row["account_code"],
            amount_ore=int(row["amount_ore"]),
            description=row["description"],
            counter_account_code=row["counter_account_code"],
            book_option_id=row["book_option_id"],
            standing_option_id=row["standing_option_id"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=_dt(row["created_at"]),  # type: ignore[arg-type]
            resolved_at=_dt(row["resolved_at"]),
            resolved_by=row["resolved_by"],
            bank_transaction_ids=AgreementBookingRepository._transaction_ids(row["id"]),
        )
