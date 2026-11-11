"""`statement_followup_attempts` (migration 049): append-only."""

import uuid
from datetime import datetime
from typing import Optional

from db.database import db


class StatementFollowupRepository:
    @staticmethod
    def record_attempt(
        *,
        bank_transaction_id: str,
        agent_run_id: Optional[str],
        reason: str,
        _commit: bool = True,
    ) -> None:
        db.execute(
            """
            INSERT INTO statement_followup_attempts
            (id, bank_transaction_id, agent_run_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
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
            "SELECT DISTINCT bank_transaction_id FROM statement_followup_attempts"
        ).fetchall()
        return {row["bank_transaction_id"] for row in rows}

    @staticmethod
    def agreement_transaction_ids() -> set:
        """Transactions an agreement card names or a follow-up of one tried:
        the agreement decides those, never this pass."""
        rows = db.execute("""
            SELECT bank_transaction_id FROM agreement_booking_transactions
            UNION
            SELECT bank_transaction_id FROM agreement_followup_attempts
            """).fetchall()
        return {row["bank_transaction_id"] for row in rows}
