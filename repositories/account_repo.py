"""Account repository - data access for accounts."""

from datetime import datetime
from typing import Dict, List, Optional

from db.database import db
from domain.models import Account
from domain.types import AccountType


class AccountRepository:
    """Manage accounts (Chart of Accounts - BAS 2026)."""

    @staticmethod
    def create(
        code: str,
        name: str,
        account_type: str,
        vat_code: Optional[str] = None,
        sru_code: Optional[str] = None,
        active: bool = True,
    ) -> Account:
        """Create new account."""
        sql = """
        INSERT INTO accounts (code, name, account_type, vat_code, sru_code, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        db.execute(
            sql, (code, name, account_type, vat_code, sru_code, int(active), now, now)
        )
        db.commit()

        return Account(
            code=code,
            name=name,
            account_type=AccountType(account_type),
            vat_code=vat_code,
            sru_code=sru_code,
            active=active,
            created_at=now,
        )

    @staticmethod
    def get(code: str) -> Optional[Account]:
        """Get account by code."""
        sql = "SELECT * FROM accounts WHERE code = ? LIMIT 1"
        cursor = db.execute(sql, (code,))
        row = cursor.fetchone()

        if not row:
            return None

        return Account(
            code=row["code"],
            name=row["name"],
            account_type=AccountType(row["account_type"]),
            vat_code=row["vat_code"],
            sru_code=row["sru_code"],
            active=bool(row["active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def list_all(active_only: bool = True) -> List[Account]:
        """List all accounts."""
        sql = "SELECT * FROM accounts"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY code"

        cursor = db.execute(sql)
        accounts = []
        for row in cursor.fetchall():
            accounts.append(
                Account(
                    code=row["code"],
                    name=row["name"],
                    account_type=AccountType(row["account_type"]),
                    vat_code=row["vat_code"],
                    sru_code=row["sru_code"],
                    active=bool(row["active"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return accounts

    @staticmethod
    def get_all_as_dict(active_only: bool = True) -> Dict[str, Account]:
        """Get all accounts as dictionary (code -> Account)."""
        accounts = AccountRepository.list_all(active_only=active_only)
        return {acc.code: acc for acc in accounts}

    @staticmethod
    def deactivate(code: str) -> bool:
        """Deactivate account."""
        sql = "UPDATE accounts SET active = 0, updated_at = ? WHERE code = ?"
        db.execute(sql, (datetime.now(), code))
        db.commit()
        return True

    @staticmethod
    def exists(code: str) -> bool:
        """Check if account exists."""
        sql = "SELECT 1 FROM accounts WHERE code = ? LIMIT 1"
        cursor = db.execute(sql, (code,))
        return cursor.fetchone() is not None

    @staticmethod
    def codes_with_transactions(fiscal_year_id: str) -> List[str]:
        """Accounts a posted voucher in the fiscal year has a row on, in code order.

        The opening balance is not a movement (`services/opening_balance.py`),
        so a posted `IB`-series voucher from before migration 033 does not
        count, and nor does a draft.
        """
        sql = """
        SELECT DISTINCT vr.account_code AS code
        FROM voucher_rows vr
        JOIN vouchers v ON v.id = vr.voucher_id
        WHERE v.fiscal_year_id = ? AND v.status = 'posted' AND v.series <> 'IB'
        ORDER BY vr.account_code
        """
        return [row["code"] for row in db.execute(sql, (fiscal_year_id,)).fetchall()]
