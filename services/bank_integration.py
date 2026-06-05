"""Bank integration service - connects to Open Banking (Tink) for transaction import.

This service handles:
1. Bank connection management (connect, disconnect, status)
2. Transaction synchronization (fetch new transactions)
3. Transaction deduplication
4. Triggering auto-categorization after import

For production: Use Tink API (https://docs.tink.com/)
For development: Supports manual CSV import and mock data
"""

import csv
import io
import uuid
import json
from datetime import date, datetime
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from db.database import db
from domain.validation import ValidationError


@dataclass
class BankConnection:
    """Represents a connected bank account."""
    id: str
    provider: str
    bank_name: str
    account_number: Optional[str] = None
    iban: Optional[str] = None
    currency: str = "SEK"
    status: str = "pending"
    last_sync_at: Optional[datetime] = None
    sync_from_date: Optional[date] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class BankTransaction:
    """A transaction imported from the bank."""
    id: str
    bank_connection_id: str
    external_id: Optional[str] = None
    transaction_date: date = field(default_factory=date.today)
    booking_date: Optional[date] = None
    amount: int = 0  # öre, negative = expense
    currency: str = "SEK"
    description: Optional[str] = None
    counterpart_name: Optional[str] = None
    counterpart_account: Optional[str] = None
    reference: Optional[str] = None
    category_code: Optional[str] = None
    raw_data: Optional[str] = None
    status: str = "pending"
    matched_voucher_id: Optional[str] = None
    suggested_account_code: Optional[str] = None
    suggested_confidence: float = 0.0
    categorized_at: Optional[datetime] = None
    booked_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class CsvImportResult:
    """Detailed result from importing a detected bank CSV format."""

    imported_count: int
    skipped_count: int
    imported_transaction_ids: list[str]
    skipped_external_ids: list[str]
    detected_format: str


class BankIntegrationService:
    """Manages bank connections and transaction imports."""

    def create_connection(
        self,
        provider: str,
        bank_name: str,
        account_number: Optional[str] = None,
        iban: Optional[str] = None,
        currency: str = "SEK",
        sync_from_date: Optional[date] = None,
    ) -> BankConnection:
        """Register a new bank connection.
        
        In production, this would initiate OAuth flow with Tink/Plaid.
        For now, creates a connection record for manual import.
        """
        conn_id = str(uuid.uuid4())
        
        with db.transaction():
            db.execute(
                """INSERT INTO bank_connections 
                   (id, provider, bank_name, account_number, iban, currency, status, sync_from_date)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?)""",
                (conn_id, provider, bank_name, account_number, iban, currency,
                 sync_from_date.isoformat() if sync_from_date else None)
            )
        
        return BankConnection(
            id=conn_id, provider=provider, bank_name=bank_name,
            account_number=account_number, iban=iban, currency=currency,
            status="active", sync_from_date=sync_from_date
        )

    def get_connections(self) -> List[BankConnection]:
        """List all bank connections."""
        rows = db.execute("SELECT * FROM bank_connections ORDER BY created_at DESC").fetchall()
        return [self._row_to_connection(r) for r in rows]

    def get_connection(self, connection_id: str) -> Optional[BankConnection]:
        """Get a specific bank connection."""
        row = db.execute("SELECT * FROM bank_connections WHERE id = ?", (connection_id,)).fetchone()
        return self._row_to_connection(row) if row else None

    def import_transactions(
        self,
        connection_id: str,
        transactions: List[Dict],
        return_details: bool = False,
    ) -> Tuple[int, int] | Tuple[int, int, list[str], list[str]]:
        """Import transactions from bank data.
        
        Args:
            connection_id: Bank connection to import for
            transactions: List of transaction dicts with keys:
                - external_id (optional): ID from bank for dedup
                - date: Transaction date (YYYY-MM-DD)
                - amount: Amount in SEK (negative = expense). Will be converted to öre.
                - description: Transaction description
                - counterpart_name (optional): Name of counterpart
                - counterpart_account (optional): Account of counterpart
                - reference (optional): Payment reference
        
        Returns:
            Tuple of (imported_count, skipped_count)
        """
        connection = self.get_connection(connection_id)
        if not connection:
            raise ValidationError("connection_not_found", "Bank connection not found")
        if connection.status != "active":
            raise ValidationError("connection_inactive", f"Connection status: {connection.status}")

        imported = 0
        skipped = 0
        imported_transaction_ids: list[str] = []
        skipped_external_ids: list[str] = []

        with db.transaction():
            for tx_data in transactions:
                tx_id = str(uuid.uuid4())
                external_id = tx_data.get("external_id", tx_id)
                
                # Check for duplicates
                existing = db.execute(
                    "SELECT id FROM bank_transactions WHERE bank_connection_id = ? AND external_id = ?",
                    (connection_id, external_id)
                ).fetchone()
                
                if existing:
                    skipped += 1
                    skipped_external_ids.append(external_id)
                    continue

                # Convert amount: if float/int SEK → öre
                amount = tx_data.get("amount", 0)
                if isinstance(amount, float):
                    amount = int(amount * 100)
                elif isinstance(amount, int) and abs(amount) < 100000:
                    # Assume SEK if small number, convert to öre
                    amount = amount * 100

                tx_date = tx_data.get("date", date.today().isoformat())
                if isinstance(tx_date, date):
                    tx_date = tx_date.isoformat()

                db.execute(
                    """INSERT INTO bank_transactions 
                       (id, bank_connection_id, external_id, transaction_date, booking_date,
                        amount, currency, description, counterpart_name, counterpart_account,
                        reference, category_code, raw_data, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                    (tx_id, connection_id, external_id, tx_date,
                     tx_data.get("booking_date"), amount, connection.currency,
                     tx_data.get("description"), tx_data.get("counterpart_name"),
                     tx_data.get("counterpart_account"), tx_data.get("reference"),
                     tx_data.get("category_code"),
                     json.dumps(tx_data) if tx_data else None)
                )
                imported += 1
                imported_transaction_ids.append(tx_id)

            # Update last sync timestamp
            db.execute(
                "UPDATE bank_connections SET last_sync_at = ?, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), datetime.now().isoformat(), connection_id)
            )

        if return_details:
            return imported, skipped, imported_transaction_ids, skipped_external_ids
        return imported, skipped

    def get_transactions(
        self,
        connection_id: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BankTransaction]:
        """Query bank transactions with filters."""
        sql = "SELECT * FROM bank_transactions WHERE 1=1"
        params = []

        if connection_id:
            sql += " AND bank_connection_id = ?"
            params.append(connection_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if from_date:
            sql += " AND transaction_date >= ?"
            params.append(from_date.isoformat())
        if to_date:
            sql += " AND transaction_date <= ?"
            params.append(to_date.isoformat())

        sql += " ORDER BY transaction_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_transaction(r) for r in rows]

    def get_transaction(self, tx_id: str) -> Optional[BankTransaction]:
        """Get a single transaction."""
        row = db.execute("SELECT * FROM bank_transactions WHERE id = ?", (tx_id,)).fetchone()
        return self._row_to_transaction(row) if row else None

    def get_pending_count(self) -> int:
        """Count transactions awaiting categorization/booking."""
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM bank_transactions WHERE status = 'pending'"
        ).fetchone()
        return row["cnt"] if row else 0

    def update_transaction_status(
        self,
        tx_id: str,
        status: str,
        voucher_id: Optional[str] = None,
        account_code: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> None:
        """Update transaction processing status."""
        updates = ["status = ?", "categorized_at = ?"]
        params = [status, datetime.now().isoformat()]

        if voucher_id:
            updates.append("matched_voucher_id = ?")
            params.append(voucher_id)
            updates.append("booked_at = ?")
            params.append(datetime.now().isoformat())
        if account_code:
            updates.append("suggested_account_code = ?")
            params.append(account_code)
        if confidence is not None:
            updates.append("suggested_confidence = ?")
            params.append(confidence)

        params.append(tx_id)
        db.execute(
            f"UPDATE bank_transactions SET {', '.join(updates)} WHERE id = ?",
            tuple(params)
        )
        db.commit()

    def import_csv(
        self,
        connection_id: str,
        csv_content: str,
        date_column: str | None = None,
        amount_column: str | None = None,
        description_column: str | None = None,
        delimiter: str | None = None,
    ) -> CsvImportResult:
        """Import transactions from Swedish bank CSV format.
        
        Supports common Swedish bank CSV exports (SEB, Nordea, Handelsbanken, Swedbank).
        """
        detected = self._detect_csv_format(
            csv_content,
            date_column=date_column,
            amount_column=amount_column,
            description_column=description_column,
            delimiter=delimiter,
        )
        reader = csv.DictReader(
            io.StringIO(detected.get("csv_content", csv_content)),
            delimiter=detected["delimiter"],
        )
        transactions = []
        
        for row_number, row in enumerate(reader, start=2):
            # Parse amount (Swedish format: "1 234,56" or "-1234.56")
            amount_str = row.get(detected["amount"], "0")
            date_str = row.get(detected["date"], "")
            if detected.get("skip_incomplete_rows") and (not amount_str.strip() or not date_str.strip()):
                continue
            amount_str = self._normalize_amount(amount_str)
            try:
                amount = float(amount_str)
            except ValueError:
                raise ValidationError(
                    "invalid_bank_csv_row",
                    "Bank CSV row contains an invalid amount",
                    f"row={row_number}, amount={row.get(detected['amount'], '')}",
                )
            
            # Parse date
            if not date_str:
                raise ValidationError(
                    "invalid_bank_csv_row",
                    "Bank CSV row is missing a transaction date",
                    f"row={row_number}",
                )
            booking_date = row.get(detected["booking_date"]) if detected.get("booking_date") else None
            description_parts = [
                row.get(column, "").strip()
                for column in detected["description"]
                if row.get(column, "").strip()
            ]
            description = " - ".join(description_parts)
            
            transactions.append({
                "external_id": f"csv-{date_str}-{amount_str}-{description}",
                "date": date_str,
                "booking_date": booking_date,
                "amount": amount,
                "description": description,
                "counterpart_name": row.get(detected["counterpart_name"], "")
                if detected.get("counterpart_name")
                else row.get("Mottagare", row.get("Motpart", "")),
                "counterpart_account": row.get(detected["counterpart_account"], "")
                if detected.get("counterpart_account")
                else row.get("Motpartskonto", ""),
                "reference": row.get(detected["reference"], "")
                if detected.get("reference")
                else row.get("Referens", row.get("OCR", "")),
            })
        
        imported, skipped, imported_ids, skipped_external_ids = self.import_transactions(
            connection_id,
            transactions,
            return_details=True,
        )
        return CsvImportResult(
            imported_count=imported,
            skipped_count=skipped,
            imported_transaction_ids=imported_ids,
            skipped_external_ids=skipped_external_ids,
            detected_format=detected["format"],
        )

    def _detect_csv_format(
        self,
        csv_content: str,
        date_column: str | None = None,
        amount_column: str | None = None,
        description_column: str | None = None,
        delimiter: str | None = None,
    ) -> dict:
        """Detect a supported Swedish bank CSV format from delimiter and headers."""
        selected_delimiter = delimiter or self._detect_delimiter(csv_content)
        csv_content = self._strip_preamble(csv_content, selected_delimiter)
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=selected_delimiter)
        headers = set(reader.fieldnames or [])
        if date_column and amount_column and description_column:
            required = {date_column, amount_column, description_column}
            if required.issubset(headers):
                return {
                    "format": "custom_columns",
                    "delimiter": selected_delimiter,
                    "csv_content": csv_content,
                    "date": date_column,
                    "booking_date": None,
                    "amount": amount_column,
                    "description": [description_column],
                    "counterpart_name": "Mottagare" if "Mottagare" in headers else "Motpart" if "Motpart" in headers else None,
                    "counterpart_account": "Motpartskonto" if "Motpartskonto" in headers else None,
                    "reference": "Referens" if "Referens" in headers else "OCR" if "OCR" in headers else None,
                }

        known_formats = [
            {
                "format": "swedish_standard_semicolon",
                "delimiter": ";",
                "date": "Datum",
                "booking_date": None,
                "amount": "Belopp",
                "description": ["Text"],
                "counterpart_name": "Mottagare" if "Mottagare" in headers else "Motpart" if "Motpart" in headers else None,
                "counterpart_account": "Motpartskonto" if "Motpartskonto" in headers else None,
                "reference": "Referens" if "Referens" in headers else "OCR" if "OCR" in headers else None,
                "required": {"Datum", "Belopp", "Text"},
            },
            {
                "format": "swedish_booking_day_message",
                "delimiter": ";",
                "date": "Transaktionsdag",
                "booking_date": "Bokföringsdag",
                "amount": "Belopp",
                "description": ["Meddelande"],
                "counterpart_name": "Motpart" if "Motpart" in headers else None,
                "counterpart_account": "Motpartskonto" if "Motpartskonto" in headers else None,
                "reference": "Referens" if "Referens" in headers else "OCR" if "OCR" in headers else None,
                "required": {"Bokföringsdag", "Transaktionsdag", "Belopp", "Meddelande"},
            },
            {
                "format": "skatteverket_skattekonto",
                "delimiter": ";",
                "date": None,
                "booking_date": "Bokföringsdatum",
                "amount": "Belopp",
                "description": ["Text"],
                "counterpart_name": None,
                "counterpart_account": None,
                "reference": None,
                "required": {"Bokföringsdatum", "Text", "Belopp", "Saldo"},
                "skip_incomplete_rows": True,
            },
            {
                "format": "lansforsakringar_bank",
                "delimiter": ";",
                "date": "Transaktionsdatum",
                "booking_date": "Bokföringsdatum",
                "amount": "Belopp",
                "description": ["Transaktionstyp", "Meddelande"],
                "counterpart_name": None,
                "counterpart_account": None,
                "reference": "Meddelande" if "Meddelande" in headers else None,
                "required": {
                    "Bokföringsdatum",
                    "Transaktionsdatum",
                    "Transaktionstyp",
                    "Meddelande",
                    "Belopp",
                },
            },
        ]
        for mapping in known_formats:
            if mapping["delimiter"] == selected_delimiter and mapping["required"].issubset(headers):
                detected = dict(mapping)
                detected.pop("required")
                detected["csv_content"] = csv_content
                if detected["date"] is None:
                    detected["date"] = detected["booking_date"]
                return detected

        raise ValidationError(
            "unsupported_bank_csv_format",
            "Unsupported bank CSV format",
            f"headers={sorted(headers)}, delimiter={selected_delimiter}",
        )

    def _detect_delimiter(self, csv_content: str) -> str:
        first_line = csv_content.splitlines()[0] if csv_content.splitlines() else ""
        return ";" if first_line.count(";") >= first_line.count(",") else ","

    def _strip_preamble(self, csv_content: str, delimiter: str) -> str:
        """Return CSV content from the first supported transaction header row."""
        lines = csv_content.splitlines()
        known_header_markers = (
            {"Datum", "Belopp", "Text"},
            {"Bokföringsdag", "Transaktionsdag", "Belopp", "Meddelande"},
            {"Bokföringsdatum", "Text", "Belopp", "Saldo"},
            {"Bokföringsdatum", "Transaktionsdatum", "Transaktionstyp", "Meddelande", "Belopp"},
        )
        for index, line in enumerate(lines):
            row = next(csv.reader([line], delimiter=delimiter), [])
            headers = {cell.strip() for cell in row}
            if any(markers.issubset(headers) for markers in known_header_markers):
                return "\n".join(lines[index:])
            if len(row) >= 4 and self._is_iso_date(row[0].strip()):
                skatteverket_headers = delimiter.join(
                    ["Bokföringsdatum", "Text", "Belopp", "Saldo"]
                )
                return "\n".join([skatteverket_headers, *lines[index:]])
        return csv_content

    def _normalize_amount(self, amount: str) -> str:
        amount = (amount or "").strip().replace("\u00a0", " ").replace(" ", "")
        if "," in amount and "." in amount:
            amount = amount.replace(".", "")
        return amount.replace(",", ".")

    def _is_iso_date(self, value: str) -> bool:
        return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None

    def get_sync_summary(self) -> Dict:
        """Get summary of all bank syncs."""
        rows = db.execute("""
            SELECT 
                bc.bank_name,
                bc.status as connection_status,
                bc.last_sync_at,
                COUNT(bt.id) as total_transactions,
                SUM(CASE WHEN bt.status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN bt.status = 'categorized' THEN 1 ELSE 0 END) as categorized,
                SUM(CASE WHEN bt.status = 'booked' THEN 1 ELSE 0 END) as booked,
                SUM(CASE WHEN bt.status = 'ignored' THEN 1 ELSE 0 END) as ignored
            FROM bank_connections bc
            LEFT JOIN bank_transactions bt ON bt.bank_connection_id = bc.id
            GROUP BY bc.id
        """).fetchall()
        
        return {
            "connections": [dict(r) for r in rows],
            "total_pending": sum(r["pending"] or 0 for r in rows),
        }

    def _row_to_connection(self, row) -> BankConnection:
        return BankConnection(
            id=row["id"],
            provider=row["provider"],
            bank_name=row["bank_name"],
            account_number=row["account_number"],
            iban=row["iban"],
            currency=row["currency"],
            status=row["status"],
            last_sync_at=datetime.fromisoformat(row["last_sync_at"]) if row["last_sync_at"] else None,
            sync_from_date=date.fromisoformat(row["sync_from_date"]) if row["sync_from_date"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )

    def _row_to_transaction(self, row) -> BankTransaction:
        return BankTransaction(
            id=row["id"],
            bank_connection_id=row["bank_connection_id"],
            external_id=row["external_id"],
            transaction_date=date.fromisoformat(row["transaction_date"]),
            booking_date=date.fromisoformat(row["booking_date"]) if row["booking_date"] else None,
            amount=row["amount"],
            currency=row["currency"],
            description=row["description"],
            counterpart_name=row["counterpart_name"],
            counterpart_account=row["counterpart_account"],
            reference=row["reference"],
            category_code=row["category_code"],
            raw_data=row["raw_data"],
            status=row["status"],
            matched_voucher_id=row["matched_voucher_id"],
            suggested_account_code=row["suggested_account_code"],
            suggested_confidence=row["suggested_confidence"] or 0.0,
            categorized_at=datetime.fromisoformat(row["categorized_at"]) if row["categorized_at"] else None,
            booked_at=datetime.fromisoformat(row["booked_at"]) if row["booked_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )
