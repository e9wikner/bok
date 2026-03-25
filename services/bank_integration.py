"""Bank integration service - connects to Open Banking (Tink) for transaction import.

This service handles:
1. Bank connection management (connect, disconnect, status)
2. Transaction synchronization (fetch new transactions)
3. Transaction deduplication
4. Triggering auto-categorization after import

For production: Use Tink API (https://docs.tink.com/)
For development: Supports manual CSV import and mock data
"""

import uuid
import json
from datetime import date, datetime
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
    ) -> Tuple[int, int]:
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

            # Update last sync timestamp
            db.execute(
                "UPDATE bank_connections SET last_sync_at = ?, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), datetime.now().isoformat(), connection_id)
            )

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
        date_column: str = "Datum",
        amount_column: str = "Belopp",
        description_column: str = "Text",
        delimiter: str = ";",
    ) -> Tuple[int, int]:
        """Import transactions from Swedish bank CSV format.
        
        Supports common Swedish bank CSV exports (SEB, Nordea, Handelsbanken, Swedbank).
        """
        import csv
        import io
        
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
        transactions = []
        
        for row in reader:
            # Parse amount (Swedish format: "1 234,56" or "-1234.56")
            amount_str = row.get(amount_column, "0")
            amount_str = amount_str.replace(" ", "").replace(",", ".")
            try:
                amount = float(amount_str)
            except ValueError:
                continue
            
            # Parse date
            date_str = row.get(date_column, "")
            
            transactions.append({
                "external_id": f"csv-{date_str}-{amount_str}-{row.get(description_column, '')}",
                "date": date_str,
                "amount": amount,
                "description": row.get(description_column, ""),
                "counterpart_name": row.get("Mottagare", row.get("Motpart", "")),
                "reference": row.get("Referens", row.get("OCR", "")),
            })
        
        return self.import_transactions(connection_id, transactions)

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
