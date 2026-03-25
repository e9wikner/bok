"""Voucher repository - data access for vouchers."""

from typing import Optional, List
from datetime import datetime, date
import uuid
from db.database import db
from domain.models import Voucher, VoucherRow
from domain.types import VoucherStatus, VoucherSeries


class VoucherRepository:
    """Manage vouchers (Verifikationer) - append-only storage."""
    
    @staticmethod
    def create(
        series: str,
        number: int,
        date: date,
        period_id: str,
        description: str,
        created_by: str = "system",
        _commit: bool = True,
    ) -> Voucher:
        """Create new draft voucher."""
        voucher_id = str(uuid.uuid4())
        sql = """
        INSERT INTO vouchers (id, series, number, date, period_id, description, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """
        now = datetime.now()
        db.execute(sql, (voucher_id, series, number, date, period_id, description, created_by, now))
        if _commit:
            db.commit()
        
        return Voucher(
            id=voucher_id,
            series=VoucherSeries(series),
            number=number,
            date=date,
            period_id=period_id,
            description=description,
            status=VoucherStatus.DRAFT,
            created_at=now,
            created_by=created_by
        )
    
    @staticmethod
    def add_row(
        voucher_id: str,
        account_code: str,
        debit: int = 0,
        credit: int = 0,
        description: Optional[str] = None,
        _commit: bool = True,
    ) -> VoucherRow:
        """Add accounting row to draft voucher."""
        row_id = str(uuid.uuid4())
        sql = """
        INSERT INTO voucher_rows (id, voucher_id, account_code, debit, credit, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        db.execute(sql, (row_id, voucher_id, account_code, debit, credit, description, now))
        if _commit:
            db.commit()
        
        return VoucherRow(
            id=row_id,
            voucher_id=voucher_id,
            account_code=account_code,
            debit=debit,
            credit=credit,
            description=description,
            created_at=now
        )
    
    @staticmethod
    def get(voucher_id: str) -> Optional[Voucher]:
        """Get voucher by ID with all rows."""
        sql = "SELECT * FROM vouchers WHERE id = ? LIMIT 1"
        cursor = db.execute(sql, (voucher_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        # Get rows
        rows_sql = "SELECT * FROM voucher_rows WHERE voucher_id = ? ORDER BY created_at"
        rows_cursor = db.execute(rows_sql, (voucher_id,))
        rows = []
        for row_data in rows_cursor.fetchall():
            rows.append(VoucherRow(
                id=row_data["id"],
                voucher_id=row_data["voucher_id"],
                account_code=row_data["account_code"],
                debit=row_data["debit"],
                credit=row_data["credit"],
                description=row_data["description"],
                created_at=datetime.fromisoformat(row_data["created_at"])
            ))
        
        posted_at = row["posted_at"]
        if posted_at:
            posted_at = datetime.fromisoformat(posted_at)
        
        return Voucher(
            id=row["id"],
            series=VoucherSeries(row["series"]),
            number=row["number"],
            date=datetime.fromisoformat(row["date"]).date(),
            period_id=row["period_id"],
            description=row["description"],
            status=VoucherStatus(row["status"]),
            rows=rows,
            correction_of=row["correction_of"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=row["created_by"],
            posted_at=posted_at
        )
    
    @staticmethod
    def list_for_period(period_id: str, status: Optional[str] = None) -> List[Voucher]:
        """List vouchers for a period."""
        sql = "SELECT id FROM vouchers WHERE period_id = ?"
        params = [period_id]
        
        if status:
            sql += " AND status = ?"
            params.append(status)
        
        sql += " ORDER BY date, series, number"
        
        cursor = db.execute(sql, tuple(params))
        vouchers = []
        for row in cursor.fetchall():
            voucher = VoucherRepository.get(row["id"])
            if voucher:
                vouchers.append(voucher)
        return vouchers
    
    @staticmethod
    def list_all(status: Optional[str] = None) -> List[Voucher]:
        """List all vouchers across all periods."""
        sql = "SELECT id FROM vouchers"
        params = []
        
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        
        sql += " ORDER BY date DESC, series, number"
        
        cursor = db.execute(sql, tuple(params))
        vouchers = []
        for row in cursor.fetchall():
            voucher = VoucherRepository.get(row["id"])
            if voucher:
                vouchers.append(voucher)
        return vouchers
    
    @staticmethod
    def get_next_number(series: str) -> int:
        """Get next sequential voucher number for series."""
        sql = "SELECT MAX(number) as max_num FROM vouchers WHERE series = ?"
        cursor = db.execute(sql, (series,))
        row = cursor.fetchone()
        return (row["max_num"] or 0) + 1
    
    @staticmethod
    def post(voucher_id: str) -> bool:
        """Post voucher (make immutable - BFL varaktighet requirement)."""
        sql = "UPDATE vouchers SET status = 'posted', posted_at = ? WHERE id = ?"
        db.execute(sql, (datetime.now(), voucher_id))
        db.commit()
        return True
    
    @staticmethod
    def create_correction(
        original_voucher_id: str,
        series: str = "B",
        created_by: str = "system",
        period_id_override: str = None,
    ) -> Voucher:
        """Create correction voucher (B-series) for an original voucher.

        If period_id_override is given, the correction is booked into that
        period instead of the original's (needed when the original period
        is locked).
        """
        # Get original voucher
        original = VoucherRepository.get(original_voucher_id)
        if not original:
            raise ValueError("Original voucher not found")

        target_period_id = period_id_override or original.period_id

        # Create new B-series voucher referencing the original
        correction_id = str(uuid.uuid4())
        number = VoucherRepository.get_next_number(series)

        sql = """
        INSERT INTO vouchers (id, series, number, date, period_id, description, status, correction_of, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
        """
        now = datetime.now()
        description = f"Correction of voucher {original.series}{original.number:06d}"

        db.execute(sql, (
            correction_id, series, number, now.date(),
            target_period_id, description, original_voucher_id, created_by, now
        ))
        db.commit()

        return Voucher(
            id=correction_id,
            series=VoucherSeries(series),
            number=number,
            date=now.date(),
            period_id=target_period_id,
            description=description,
            status=VoucherStatus.DRAFT,
            correction_of=original_voucher_id,
            created_at=now,
            created_by=created_by
        )
    
    @staticmethod
    def delete_draft(voucher_id: str) -> bool:
        """Delete draft voucher (before posting)."""
        voucher = VoucherRepository.get(voucher_id)
        if not voucher or voucher.is_posted():
            raise ValueError("Can only delete draft vouchers")
        
        # Delete rows
        db.execute("DELETE FROM voucher_rows WHERE voucher_id = ?", (voucher_id,))
        # Delete voucher
        db.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
        db.commit()
        return True
    
    @staticmethod
    def clear_rows(voucher_id: str) -> bool:
        """Clear all rows from a draft voucher."""
        db.execute("DELETE FROM voucher_rows WHERE voucher_id = ?", (voucher_id,))
        db.commit()
        return True
