"""Opening balance repository - stated IB and per-year account movements."""

from datetime import date, datetime
from typing import Dict, Optional

from db.database import db


class OpeningBalanceRepository:
    """Data access for `opening_balances` and the sums IB is derived from.

    Amounts are öre, debit positive (SIE4 sign convention).
    """

    @staticmethod
    def get_stated(fiscal_year_id: str) -> Dict[str, int]:
        """The IB entered or imported for a fiscal year, per account."""
        rows = db.execute(
            "SELECT account_code, amount FROM opening_balances "
            "WHERE fiscal_year_id = ?",
            (fiscal_year_id,),
        ).fetchall()
        return {row["account_code"]: row["amount"] for row in rows}

    @staticmethod
    def replace_stated(
        fiscal_year_id: str,
        balances: Dict[str, int],
        actor: str,
        _commit: bool = True,
    ) -> None:
        """Replace a fiscal year's stated IB. Zero amounts are dropped."""
        db.execute(
            "DELETE FROM opening_balances WHERE fiscal_year_id = ?",
            (fiscal_year_id,),
        )
        now = datetime.now()
        db.executemany(
            "INSERT INTO opening_balances "
            "(fiscal_year_id, account_code, amount, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (fiscal_year_id, code, amount, actor, now)
                for code, amount in sorted(balances.items())
                if amount != 0
            ],
        )
        if _commit:
            db.commit()

    @staticmethod
    def movements(fiscal_year_id: str, before: Optional[date] = None) -> Dict[str, int]:
        """Net of every posted voucher in the fiscal year, per account --
        only those dated before *before*, if given.

        The `IB` series is left out: a posted IB voucher from before
        migration 033 is opening state, not a movement.
        """
        sql = """
            SELECT vr.account_code, SUM(vr.debit - vr.credit) AS net
            FROM voucher_rows vr
            JOIN vouchers v ON v.id = vr.voucher_id
            WHERE v.fiscal_year_id = ?
              AND v.status = 'posted'
              AND v.series != 'IB'
        """
        params: tuple = (fiscal_year_id,)
        if before is not None:
            sql += " AND v.date < ?"
            params += (before.isoformat(),)
        rows = db.execute(sql + " GROUP BY vr.account_code", params).fetchall()
        return {row["account_code"]: row["net"] for row in rows if row["net"]}
