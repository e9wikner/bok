"""Period repository - data access for periods and fiscal years."""

from typing import Optional, List
from datetime import datetime, date
import uuid
from db.database import db
from domain.models import Period, FiscalYear


class PeriodRepository:
    """Manage periods and fiscal years."""
    
    @staticmethod
    def create_fiscal_year(
        start_date: date,
        end_date: date,
    ) -> FiscalYear:
        """Create new fiscal year (typically Jan 1 - Dec 31)."""
        fy_id = str(uuid.uuid4())
        sql = """
        INSERT INTO fiscal_years (id, start_date, end_date, locked, created_at)
        VALUES (?, ?, ?, 0, ?)
        """
        now = datetime.now()
        db.execute(sql, (fy_id, start_date, end_date, now))
        db.commit()
        
        return FiscalYear(
            id=fy_id,
            start_date=start_date,
            end_date=end_date,
            created_at=now
        )
    
    @staticmethod
    def create_period(
        fiscal_year_id: str,
        year: int,
        month: int,
        start_date: date,
        end_date: date,
    ) -> Period:
        """Create new period (typically monthly)."""
        period_id = str(uuid.uuid4())
        sql = """
        INSERT INTO periods (id, fiscal_year_id, year, month, start_date, end_date, locked, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """
        now = datetime.now()
        db.execute(sql, (period_id, fiscal_year_id, year, month, start_date, end_date, now))
        db.commit()
        
        return Period(
            id=period_id,
            fiscal_year_id=fiscal_year_id,
            year=year,
            month=month,
            start_date=start_date,
            end_date=end_date,
            created_at=now
        )
    
    @staticmethod
    def get_fiscal_year(fy_id: str) -> Optional[FiscalYear]:
        """Get fiscal year by ID."""
        sql = "SELECT * FROM fiscal_years WHERE id = ? LIMIT 1"
        cursor = db.execute(sql, (fy_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        locked_at = row["locked_at"]
        if locked_at:
            locked_at = datetime.fromisoformat(locked_at)
        
        return FiscalYear(
            id=row["id"],
            start_date=datetime.fromisoformat(row["start_date"]).date(),
            end_date=datetime.fromisoformat(row["end_date"]).date(),
            locked=bool(row["locked"]),
            locked_at=locked_at,
            created_at=datetime.fromisoformat(row["created_at"])
        )
    
    @staticmethod
    def get_period(period_id: str) -> Optional[Period]:
        """Get period by ID."""
        sql = "SELECT * FROM periods WHERE id = ? LIMIT 1"
        cursor = db.execute(sql, (period_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        locked_at = row["locked_at"]
        if locked_at:
            locked_at = datetime.fromisoformat(locked_at)
        
        return Period(
            id=row["id"],
            fiscal_year_id=row["fiscal_year_id"],
            year=row["year"],
            month=row["month"],
            start_date=datetime.fromisoformat(row["start_date"]).date(),
            end_date=datetime.fromisoformat(row["end_date"]).date(),
            locked=bool(row["locked"]),
            locked_at=locked_at,
            created_at=datetime.fromisoformat(row["created_at"])
        )
    
    @staticmethod
    def get_period_by_date(fiscal_year_id: str, target_date: date) -> Optional[Period]:
        """Get period containing the given date."""
        sql = """
        SELECT * FROM periods 
        WHERE fiscal_year_id = ? AND start_date <= ? AND end_date >= ?
        LIMIT 1
        """
        cursor = db.execute(sql, (fiscal_year_id, target_date, target_date))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        locked_at = row["locked_at"]
        if locked_at:
            locked_at = datetime.fromisoformat(locked_at)
        
        return Period(
            id=row["id"],
            fiscal_year_id=row["fiscal_year_id"],
            year=row["year"],
            month=row["month"],
            start_date=datetime.fromisoformat(row["start_date"]).date(),
            end_date=datetime.fromisoformat(row["end_date"]).date(),
            locked=bool(row["locked"]),
            locked_at=locked_at,
            created_at=datetime.fromisoformat(row["created_at"])
        )
    
    @staticmethod
    def list_periods(fiscal_year_id: str) -> List[Period]:
        """List all periods for a fiscal year."""
        sql = """
        SELECT * FROM periods 
        WHERE fiscal_year_id = ?
        ORDER BY year, month
        """
        cursor = db.execute(sql, (fiscal_year_id,))
        periods = []
        for row in cursor.fetchall():
            locked_at = row["locked_at"]
            if locked_at:
                locked_at = datetime.fromisoformat(locked_at)
            
            periods.append(Period(
                id=row["id"],
                fiscal_year_id=row["fiscal_year_id"],
                year=row["year"],
                month=row["month"],
                start_date=datetime.fromisoformat(row["start_date"]).date(),
                end_date=datetime.fromisoformat(row["end_date"]).date(),
                locked=bool(row["locked"]),
                locked_at=locked_at,
                created_at=datetime.fromisoformat(row["created_at"])
            ))
        return periods
    
    @staticmethod
    def lock_period(period_id: str) -> bool:
        """Lock period (irreversible - BFL varaktighet requirement)."""
        sql = "UPDATE periods SET locked = 1, locked_at = ? WHERE id = ?"
        db.execute(sql, (datetime.now(), period_id))
        db.commit()
        return True
    
    @staticmethod
    def lock_fiscal_year(fy_id: str) -> bool:
        """Lock fiscal year."""
        sql = "UPDATE fiscal_years SET locked = 1, locked_at = ? WHERE id = ?"
        db.execute(sql, (datetime.now(), fy_id))
        db.commit()
        return True
