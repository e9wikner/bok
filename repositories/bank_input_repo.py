"""Repository for uploaded bank inputs and bank source traceability."""

import uuid
from datetime import datetime
from typing import Optional

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
    def list_by_status(
        status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[BankInput]:
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
        row = db.execute("""
            SELECT COUNT(*) AS count
            FROM bank_inputs
            WHERE status IN ('pending', 'processed', 'failed')
            """).fetchone()
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
    def delete_bank_input(bank_input_id: str, _commit: bool = True) -> None:
        db.execute(
            "DELETE FROM bank_input_transactions WHERE bank_input_id = ?",
            (bank_input_id,),
        )
        db.execute(
            "DELETE FROM bank_inputs WHERE id = ?",
            (bank_input_id,),
        )
        if _commit:
            db.commit()

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
            "SELECT * FROM voucher_bank_transactions WHERE id = ?", (link_id,)
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

    #: A file link holds while one of the file's transactions has a current
    #: link to the voucher, or none of them ever had one -- a file linked on
    #: its own, without transactions (migration 040).
    _INPUT_LINK_HOLDS_SQL = """
        (EXISTS (
            SELECT 1 FROM current_voucher_bank_transactions c
            JOIN bank_input_transactions bit
              ON bit.bank_transaction_id = c.bank_transaction_id
            WHERE c.voucher_id = vbi.voucher_id
              AND bit.bank_input_id = vbi.bank_input_id
        ) OR NOT EXISTS (
            SELECT 1 FROM voucher_bank_transactions vbt
            JOIN bank_input_transactions bit
              ON bit.bank_transaction_id = vbt.bank_transaction_id
            WHERE vbt.voucher_id = vbi.voucher_id
              AND bit.bank_input_id = vbi.bank_input_id
        ))
    """

    @staticmethod
    def list_inputs_for_voucher(voucher_id: str) -> list[VoucherBankInput]:
        rows = db.execute(
            f"""
            SELECT vbi.* FROM voucher_bank_inputs vbi
            WHERE vbi.voucher_id = ?
              AND {BankInputRepository._INPUT_LINK_HOLDS_SQL}
            ORDER BY vbi.linked_at ASC
            """,
            (voucher_id,),
        ).fetchall()
        return [BankInputRepository._row_to_voucher_bank_input(row) for row in rows]

    @staticmethod
    def list_voucher_links_for_input(bank_input_id: str) -> list[VoucherBankInput]:
        rows = db.execute(
            f"""
            SELECT vbi.* FROM voucher_bank_inputs vbi
            WHERE vbi.bank_input_id = ?
              AND {BankInputRepository._INPUT_LINK_HOLDS_SQL}
            ORDER BY vbi.linked_at ASC
            """,
            (bank_input_id,),
        ).fetchall()
        return [BankInputRepository._row_to_voucher_bank_input(row) for row in rows]

    @staticmethod
    def list_transactions_for_voucher(voucher_id: str) -> list[VoucherBankTransaction]:
        rows = db.execute(
            """
            SELECT * FROM current_voucher_bank_transactions
            WHERE voucher_id = ?
            ORDER BY linked_at ASC
            """,
            (voucher_id,),
        ).fetchall()
        return [
            BankInputRepository._row_to_voucher_bank_transaction(row) for row in rows
        ]

    # --- undoing a statement link (migration 040) -------------------------

    @staticmethod
    def current_transaction_link(
        bank_transaction_id: str,
    ) -> Optional[VoucherBankTransaction]:
        row = db.execute(
            """
            SELECT * FROM current_voucher_bank_transactions
            WHERE bank_transaction_id = ?
            """,
            (bank_transaction_id,),
        ).fetchone()
        return (
            BankInputRepository._row_to_voucher_bank_transaction(row) if row else None
        )

    @staticmethod
    def create_transaction_unlink(
        link_id: str,
        bank_transaction_id: str,
        voucher_id: str,
        reason: str,
        actor: str,
        thread_id: Optional[str] = None,
        _commit: bool = True,
    ) -> None:
        db.execute(
            """
            INSERT INTO voucher_bank_transaction_unlinks
            (link_id, bank_transaction_id, voucher_id, reason, actor, thread_id,
             created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                bank_transaction_id,
                voucher_id,
                reason,
                actor,
                thread_id,
                datetime.now(),
            ),
        )
        if _commit:
            db.commit()

    @staticmethod
    def unlinked_voucher_ids(bank_transaction_id: str) -> list[str]:
        """The vouchers *bank_transaction_id* was linked to and unlinked
        from."""
        rows = db.execute(
            """
            SELECT DISTINCT voucher_id FROM voucher_bank_transaction_unlinks
            WHERE bank_transaction_id = ?
            """,
            (bank_transaction_id,),
        ).fetchall()
        return [row["voucher_id"] for row in rows]

    @staticmethod
    def release_transaction(bank_transaction_id: str, _commit: bool = True) -> None:
        """Undo `mark_transactions_booked` for one transaction."""
        db.execute(
            """
            UPDATE bank_transactions
            SET status = 'pending', matched_voucher_id = NULL, booked_at = NULL
            WHERE id = ?
            """,
            (bank_transaction_id,),
        )
        if _commit:
            db.commit()

    # --- statement matching (services/statement_match.py) ----------------

    @staticmethod
    def list_unlinked_transactions_with_account() -> list[dict]:
        """Bank transactions not linked to any voucher, with the account
        their statement was imported for, oldest first."""
        rows = db.execute("""
            SELECT bt.id, bt.transaction_date, bt.amount, bt.description,
                   bt.counterpart_name, bc.account_number AS account_code
            FROM bank_transactions bt
            JOIN bank_connections bc ON bc.id = bt.bank_connection_id
            WHERE bt.matched_voucher_id IS NULL
              AND bt.status != 'ignored'
              AND bc.account_number IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM current_voucher_bank_transactions vbt
                  WHERE vbt.bank_transaction_id = bt.id
              )
            ORDER BY bt.transaction_date ASC, bt.created_at ASC
            """).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def get_transaction_with_account(bank_transaction_id: str) -> Optional[dict]:
        """One transaction, its account, and the voucher it is linked to."""
        row = db.execute(
            """
            SELECT bt.id, bt.transaction_date, bt.amount, bt.description,
                   bt.counterpart_name, bt.status, bt.matched_voucher_id,
                   bc.account_number AS account_code,
                   (SELECT vbt.voucher_id FROM current_voucher_bank_transactions vbt
                    WHERE vbt.bank_transaction_id = bt.id) AS linked_voucher_id
            FROM bank_transactions bt
            JOIN bank_connections bc ON bc.id = bt.bank_connection_id
            WHERE bt.id = ?
            """,
            (bank_transaction_id,),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_statement_match_vouchers(
        account_code: str,
        amount_ore: int,
        date_from: str,
        date_to: str,
        input_vat_range: tuple[str, str],
    ) -> list[dict]:
        """Posted vouchers a statement transaction on *account_code* can be
        underlag for: the net of their rows on that account equals
        *amount_ore* (debit positive, like money in), dated within the
        window, and that account not covered by a linked transaction yet.

        Never an opening balance, a SIE4 import, a correction, a reversed
        voucher or a purchase (input VAT).
        """
        rows = db.execute(
            """
            SELECT v.id, v.series, v.number, v.date, v.description,
                   SUM(r.debit - r.credit) AS net_ore
            FROM vouchers v
            JOIN voucher_rows r ON r.voucher_id = v.id AND r.account_code = ?
            WHERE v.status = 'posted'
              AND v.series != 'IB'
              AND v.created_by != 'sie4_import'
              AND v.correction_of IS NULL
              AND v.date BETWEEN ? AND ?
              AND NOT EXISTS (
                  SELECT 1 FROM vouchers c
                  WHERE c.correction_of = v.id AND c.status = 'posted'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM voucher_rows vat
                  WHERE vat.voucher_id = v.id
                    AND vat.account_code BETWEEN ? AND ?
              )
              AND NOT EXISTS (
                  SELECT 1 FROM current_voucher_bank_transactions vbt
                  JOIN bank_transactions bt ON bt.id = vbt.bank_transaction_id
                  JOIN bank_connections bc ON bc.id = bt.bank_connection_id
                  WHERE vbt.voucher_id = v.id AND bc.account_number = ?
              )
            GROUP BY v.id
            HAVING net_ore = ?
            ORDER BY v.date ASC, v.number ASC
            """,
            (
                account_code,
                date_from,
                date_to,
                input_vat_range[0],
                input_vat_range[1],
                account_code,
                amount_ore,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def voucher_link_on_account(voucher_id: str, account_code: str) -> Optional[str]:
        """The transaction already linked to *voucher_id* for *account_code*."""
        row = db.execute(
            """
            SELECT vbt.bank_transaction_id
            FROM current_voucher_bank_transactions vbt
            JOIN bank_transactions bt ON bt.id = vbt.bank_transaction_id
            JOIN bank_connections bc ON bc.id = bt.bank_connection_id
            WHERE vbt.voucher_id = ? AND bc.account_number = ?
            LIMIT 1
            """,
            (voucher_id, account_code),
        ).fetchone()
        return row["bank_transaction_id"] if row else None

    @staticmethod
    def list_statement_links_for_voucher(voucher_id: str) -> list[dict]:
        """The statement transactions linked to *voucher_id*, each with the
        first file it was imported from -- what the voucher shows as its
        underlag."""
        rows = db.execute(
            """
            SELECT bt.id AS bank_transaction_id, bt.transaction_date,
                   bt.amount, bt.description, bc.account_number AS account_code,
                   vbt.linked_by, vbt.linked_at,
                   (SELECT bi.id FROM bank_input_transactions bit
                    JOIN bank_inputs bi ON bi.id = bit.bank_input_id
                    WHERE bit.bank_transaction_id = bt.id
                    ORDER BY bit.linked_at ASC LIMIT 1) AS bank_input_id,
                   (SELECT bi.original_filename FROM bank_input_transactions bit
                    JOIN bank_inputs bi ON bi.id = bit.bank_input_id
                    WHERE bit.bank_transaction_id = bt.id
                    ORDER BY bit.linked_at ASC LIMIT 1) AS original_filename
            FROM current_voucher_bank_transactions vbt
            JOIN bank_transactions bt ON bt.id = vbt.bank_transaction_id
            JOIN bank_connections bc ON bc.id = bt.bank_connection_id
            WHERE vbt.voucher_id = ?
            ORDER BY bc.account_number ASC, bt.transaction_date ASC
            """,
            (voucher_id,),
        ).fetchall()
        return [dict(row) for row in rows]

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
            processed_at=(
                BankInputRepository._parse_datetime(row["processed_at"])
                if row["processed_at"]
                else None
            ),
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
