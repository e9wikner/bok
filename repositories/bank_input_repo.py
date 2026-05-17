"""Repository for uploaded bank inputs and bank source traceability."""

from datetime import datetime
from typing import Optional
import uuid

from db.database import db
from domain.models import (
    BankInput,
    BankInputTransactionLink,
    VoucherBankInput,
    VoucherBankTransaction,
)
from domain.types import BankInputStatus


class BankInputRepository:
    """Manage bank input records, import links, and voucher traceability."""

    @staticmethod
    def create_bank_input(
        bank_input_id: str,
        bank_connection_id: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        stored_path: str,
        uploaded_by: str,
        status: str = BankInputStatus.PENDING.value,
        _commit: bool = True,
    ) -> BankInput:
        now = datetime.now()
        db.execute(
            """
            INSERT INTO bank_inputs
            (id, bank_connection_id, status, original_filename, mime_type,
             size_bytes, sha256, stored_path, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bank_input_id,
                bank_connection_id,
                status,
                original_filename,
                mime_type,
                size_bytes,
                sha256,
                stored_path,
                uploaded_by,
                now,
            ),
        )
        if _commit:
            db.commit()

        return BankInput(
            id=bank_input_id,
            bank_connection_id=bank_connection_id,
            status=BankInputStatus(status),
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            stored_path=stored_path,
            uploaded_by=uploaded_by,
            uploaded_at=now,
        )

    @staticmethod
    def get_bank_input(bank_input_id: str) -> Optional[BankInput]:
        row = db.execute(
            "SELECT * FROM bank_inputs WHERE id = ? LIMIT 1",
            (bank_input_id,),
        ).fetchone()
        return BankInputRepository._row_to_bank_input(row) if row else None

    @staticmethod
    def get_by_sha256(sha256: str) -> Optional[BankInput]:
        row = db.execute(
            "SELECT * FROM bank_inputs WHERE sha256 = ? LIMIT 1",
            (sha256,),
        ).fetchone()
        return BankInputRepository._row_to_bank_input(row) if row else None

    @staticmethod
    def list_by_status(status: str | None = None, limit: int = 100, offset: int = 0) -> list[BankInput]:
        if status:
            rows = db.execute(
                """
                SELECT * FROM bank_inputs
                WHERE status = ?
                ORDER BY uploaded_at ASC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM bank_inputs
                ORDER BY uploaded_at ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [BankInputRepository._row_to_bank_input(row) for row in rows]

    @staticmethod
    def count_by_status(status: str | None = None) -> int:
        if status:
            row = db.execute(
                "SELECT COUNT(*) AS count FROM bank_inputs WHERE status = ?",
                (status,),
            ).fetchone()
        else:
            row = db.execute("SELECT COUNT(*) AS count FROM bank_inputs").fetchone()
        return row["count"] if row else 0

    @staticmethod
    def count_agent_relevant() -> int:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM bank_inputs
            WHERE status IN ('pending', 'processed', 'failed')
            """
        ).fetchone()
        return row["count"] if row else 0

    @staticmethod
    def update_processing_result(
        bank_input_id: str,
        status: str,
        imported_count: int,
        skipped_count: int,
        detected_format: str | None = None,
        parse_error: str | None = None,
        _commit: bool = True,
    ) -> BankInput:
        processed_at = datetime.now()
        db.execute(
            """
            UPDATE bank_inputs
            SET status = ?, detected_format = ?, imported_count = ?,
                skipped_count = ?, parse_error = ?, processed_at = ?
            WHERE id = ?
            """,
            (
                status,
                detected_format,
                imported_count,
                skipped_count,
                parse_error,
                processed_at,
                bank_input_id,
            ),
        )
        if _commit:
            db.commit()
        bank_input = BankInputRepository.get_bank_input(bank_input_id)
        if bank_input is None:
            raise ValueError(f"Bank input not found after update: {bank_input_id}")
        return bank_input

    @staticmethod
    def create_transaction_link(
        bank_input_id: str,
        bank_transaction_id: str,
        _commit: bool = True,
    ) -> BankInputTransactionLink:
        link_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT OR IGNORE INTO bank_input_transactions
            (id, bank_input_id, bank_transaction_id, linked_at)
            VALUES (?, ?, ?, ?)
            """,
            (link_id, bank_input_id, bank_transaction_id, now),
        )
        if _commit:
            db.commit()
        row = db.execute(
            """
            SELECT * FROM bank_input_transactions
            WHERE bank_input_id = ? AND bank_transaction_id = ?
            LIMIT 1
            """,
            (bank_input_id, bank_transaction_id),
        ).fetchone()
        return BankInputRepository._row_to_transaction_link(row)

    @staticmethod
    def create_voucher_bank_input_link(
        voucher_id: str,
        bank_input_id: str,
        linked_by: str,
        _commit: bool = True,
    ) -> VoucherBankInput:
        link_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT OR IGNORE INTO voucher_bank_inputs
            (id, voucher_id, bank_input_id, linked_by, linked_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (link_id, voucher_id, bank_input_id, linked_by, now),
        )
        if _commit:
            db.commit()
        row = db.execute(
            """
            SELECT * FROM voucher_bank_inputs
            WHERE voucher_id = ? AND bank_input_id = ?
            LIMIT 1
            """,
            (voucher_id, bank_input_id),
        ).fetchone()
        return BankInputRepository._row_to_voucher_bank_input(row)

    @staticmethod
    def create_voucher_bank_transaction_link(
        voucher_id: str,
        bank_transaction_id: str,
        linked_by: str,
        _commit: bool = True,
    ) -> VoucherBankTransaction:
        link_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO voucher_bank_transactions
            (id, voucher_id, bank_transaction_id, linked_by, linked_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (link_id, voucher_id, bank_transaction_id, linked_by, now),
        )
        if _commit:
            db.commit()
        row = db.execute(
            """
            SELECT * FROM voucher_bank_transactions
            WHERE voucher_id = ? AND bank_transaction_id = ?
            LIMIT 1
            """,
            (voucher_id, bank_transaction_id),
        ).fetchone()
        return BankInputRepository._row_to_voucher_bank_transaction(row)

    @staticmethod
    def list_transaction_ids_for_input(bank_input_id: str) -> list[str]:
        rows = db.execute(
            """
            SELECT bank_transaction_id
            FROM bank_input_transactions
            WHERE bank_input_id = ?
            ORDER BY linked_at ASC
            """,
            (bank_input_id,),
        ).fetchall()
        return [row["bank_transaction_id"] for row in rows]

    @staticmethod
    def count_transactions_for_input(bank_input_id: str) -> int:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM bank_input_transactions
            WHERE bank_input_id = ?
            """,
            (bank_input_id,),
        ).fetchone()
        return row["count"] if row else 0

    @staticmethod
    def list_transaction_signals_for_input(bank_input_id: str) -> list[dict]:
        rows = db.execute(
            """
            SELECT bt.id, bt.status, bt.matched_voucher_id
            FROM bank_input_transactions bit
            JOIN bank_transactions bt ON bt.id = bit.bank_transaction_id
            WHERE bit.bank_input_id = ?
            ORDER BY bit.linked_at ASC
            """,
            (bank_input_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_input_ids_for_transaction(bank_transaction_id: str) -> list[str]:
        rows = db.execute(
            """
            SELECT bank_input_id
            FROM bank_input_transactions
            WHERE bank_transaction_id = ?
            ORDER BY linked_at ASC
            """,
            (bank_transaction_id,),
        ).fetchall()
        return [row["bank_input_id"] for row in rows]

    @staticmethod
    def mark_transactions_booked(
        bank_transaction_ids: list[str],
        voucher_id: str,
        _commit: bool = True,
    ) -> None:
        now = datetime.now()
        for transaction_id in bank_transaction_ids:
            db.execute(
                """
                UPDATE bank_transactions
                SET status = 'booked', matched_voucher_id = ?, booked_at = ?
                WHERE id = ?
                """,
                (voucher_id, now, transaction_id),
            )
        if _commit:
            db.commit()

    @staticmethod
    def list_inputs_for_voucher(voucher_id: str) -> list[VoucherBankInput]:
        rows = db.execute(
            """
            SELECT * FROM voucher_bank_inputs
            WHERE voucher_id = ?
            ORDER BY linked_at ASC
            """,
            (voucher_id,),
        ).fetchall()
        return [BankInputRepository._row_to_voucher_bank_input(row) for row in rows]

    @staticmethod
    def list_voucher_links_for_input(bank_input_id: str) -> list[VoucherBankInput]:
        rows = db.execute(
            """
            SELECT * FROM voucher_bank_inputs
            WHERE bank_input_id = ?
            ORDER BY linked_at ASC
            """,
            (bank_input_id,),
        ).fetchall()
        return [BankInputRepository._row_to_voucher_bank_input(row) for row in rows]

    @staticmethod
    def list_transactions_for_voucher(voucher_id: str) -> list[VoucherBankTransaction]:
        rows = db.execute(
            """
            SELECT * FROM voucher_bank_transactions
            WHERE voucher_id = ?
            ORDER BY linked_at ASC
            """,
            (voucher_id,),
        ).fetchall()
        return [BankInputRepository._row_to_voucher_bank_transaction(row) for row in rows]

    @staticmethod
    def _row_to_bank_input(row) -> BankInput:
        return BankInput(
            id=row["id"],
            bank_connection_id=row["bank_connection_id"],
            status=BankInputStatus(row["status"]),
            original_filename=row["original_filename"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            stored_path=row["stored_path"],
            uploaded_by=row["uploaded_by"],
            uploaded_at=BankInputRepository._parse_datetime(row["uploaded_at"]),
            detected_format=row["detected_format"],
            imported_count=row["imported_count"],
            skipped_count=row["skipped_count"],
            parse_error=row["parse_error"],
            processed_at=BankInputRepository._parse_datetime(row["processed_at"])
            if row["processed_at"]
            else None,
        )

    @staticmethod
    def _row_to_transaction_link(row) -> BankInputTransactionLink:
        return BankInputTransactionLink(
            id=row["id"],
            bank_input_id=row["bank_input_id"],
            bank_transaction_id=row["bank_transaction_id"],
            linked_at=BankInputRepository._parse_datetime(row["linked_at"]),
        )

    @staticmethod
    def _row_to_voucher_bank_input(row) -> VoucherBankInput:
        return VoucherBankInput(
            id=row["id"],
            voucher_id=row["voucher_id"],
            bank_input_id=row["bank_input_id"],
            linked_by=row["linked_by"],
            linked_at=BankInputRepository._parse_datetime(row["linked_at"]),
        )

    @staticmethod
    def _row_to_voucher_bank_transaction(row) -> VoucherBankTransaction:
        return VoucherBankTransaction(
            id=row["id"],
            voucher_id=row["voucher_id"],
            bank_transaction_id=row["bank_transaction_id"],
            linked_by=row["linked_by"],
            linked_at=BankInputRepository._parse_datetime(row["linked_at"]),
        )

    @staticmethod
    def _parse_datetime(value) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)
