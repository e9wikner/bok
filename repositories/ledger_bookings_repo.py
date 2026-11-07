"""Outgoing invoices and salary payouts read off the ledger.

An invoice issued in BokAI and a payslip booked in BokAI each know their
voucher (`invoices.voucher_id`, `payslips.voucher_id`). An invoice issued in
another system, or a salary booked from an underlag or imported from SIE4,
exists only as a posted voucher. These queries find those vouchers by their
accounts, so Fakturering and Löner can show them beside BokAI's own.

Only what the ledger still holds counts: posted, not an `IB`-series voucher
(opening state, services/opening_balance.py), not a correction, and not
makulerad (`CANCELLED_SQL`).

Layering (AGENTS.md): all SQL, no business rules beyond the selection.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, List, Optional

from db.database import db
from domain.statement_coverage import STATEMENT_ACCOUNT_RANGE
from repositories.voucher_repo import CANCELLED_SQL

# Kundfordringar, intäkter, utgående moms (BAS).
RECEIVABLE_RANGE = ("1500", "1519")
REVENUE_RANGE = ("3000", "3799")
OUTPUT_VAT_RANGE = ("2610", "2639")
# Löner och ersättningar till anställda och företagsledare (BAS 70-72), och
# personalskatten som en utbetalning drar av.
SALARY_RANGE = ("7000", "7299")
PERSONAL_TAX = "2710"
# Kortfristiga skulder till anställda: nettolönen bokad som skuld, betald senare.
EMPLOYEE_DEBT_RANGE = ("2820", "2829")


def _between(column: str, rng: tuple) -> str:
    return f"{column} BETWEEN '{rng[0]}' AND '{rng[1]}'"


def _net(voucher: str, rng: tuple, sign: str) -> str:
    """The voucher's net on *rng*, `debit - credit` or `credit - debit`."""
    return (
        f"COALESCE((SELECT SUM({sign}) FROM voucher_rows n"
        f" WHERE n.voucher_id = {voucher} AND {_between('n.account_code', rng)}), 0)"
    )


# Unaliased `vouchers`, as `CANCELLED_SQL` needs.
_IN_LEDGER_SQL = (
    "vouchers.status = 'posted' AND vouchers.series != 'IB'"
    " AND vouchers.correction_of IS NULL"
    f" AND NOT {CANCELLED_SQL}"
)


@dataclass
class LedgerVoucher:
    id: str
    series: str
    number: Optional[int]
    date: date
    description: str


@dataclass
class LedgerInvoice(LedgerVoucher):
    """Kundfordran inklusive moms, och momsen."""

    amount_inc_vat: int
    vat_amount: int


@dataclass
class ReceivableCredit(LedgerVoucher):
    """En verifikation som minskar kundfordringarna: en betalning, en kvittning."""

    amount: int


@dataclass
class LedgerSalary(LedgerVoucher):
    # Debet på lönekontona. Inte alltid bruttolönen: semesterlön tagen ur
    # semesterlöneskulden (2920) står inte på dem.
    gross: int
    tax: int
    # Krediterat bankkonto, annars skuld till den anställde (2820); None
    # när ingetdera står i verifikationen.
    net: Optional[int]


def _base(row: Any) -> dict:
    return {
        "id": row["id"],
        "series": row["series"],
        "number": row["number"],
        "date": date.fromisoformat(str(row["date"])[:10]),
        "description": row["description"] or "",
    }


def _range_params(date_from: Optional[date], date_to: Optional[date]):
    sql, params = "", []
    if date_from is not None:
        sql += " AND vouchers.date >= ?"
        params.append(date_from.isoformat())
    if date_to is not None:
        sql += " AND vouchers.date <= ?"
        params.append(date_to.isoformat())
    return sql, params


class LedgerBookingRepository:
    @staticmethod
    def invoices_outside_bokai(
        date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> List[LedgerInvoice]:
        """Vouchers that book a sale on credit -- debit kundfordringar,
        credit revenue -- and are not the voucher of a BokAI invoice. Oldest
        first."""
        receivable = _net("vouchers.id", RECEIVABLE_RANGE, "n.debit - n.credit")
        vat = _net("vouchers.id", OUTPUT_VAT_RANGE, "n.credit - n.debit")
        revenue = _net("vouchers.id", REVENUE_RANGE, "n.credit - n.debit")
        range_sql, params = _range_params(date_from, date_to)
        rows = db.execute(
            f"SELECT vouchers.id, vouchers.series, vouchers.number, vouchers.date,"
            f" vouchers.description, {receivable} AS receivable, {vat} AS vat"
            " FROM vouchers"
            f" WHERE {_IN_LEDGER_SQL}"
            f" AND {receivable} > 0 AND {revenue} > 0"
            " AND NOT EXISTS (SELECT 1 FROM invoices i WHERE i.voucher_id = vouchers.id)"
            f"{range_sql}"
            " ORDER BY vouchers.date, vouchers.series, vouchers.number",
            tuple(params),
        ).fetchall()
        return [
            LedgerInvoice(
                **_base(r), amount_inc_vat=r["receivable"], vat_amount=r["vat"]
            )
            for r in rows
        ]

    @staticmethod
    def receivable_credits() -> List[ReceivableCredit]:
        """Every voucher that lowers kundfordringar and is not the payment of
        a BokAI invoice, oldest first -- the payments an invoice outside
        BokAI can be settled by."""
        credit = _net("vouchers.id", RECEIVABLE_RANGE, "n.credit - n.debit")
        rows = db.execute(
            f"SELECT vouchers.id, vouchers.series, vouchers.number, vouchers.date,"
            f" vouchers.description, {credit} AS amount"
            " FROM vouchers"
            f" WHERE {_IN_LEDGER_SQL} AND {credit} > 0"
            " AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.voucher_id = vouchers.id)"
            " ORDER BY vouchers.date, vouchers.series, vouchers.number"
        ).fetchall()
        return [ReceivableCredit(**_base(r), amount=r["amount"]) for r in rows]

    @staticmethod
    def salaries_outside_bokai(
        date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> List[LedgerSalary]:
        """Vouchers that pay out a salary -- a salary account debited, and
        personalskatt or a bank account credited -- and are not the voucher
        of a BokAI payslip. An accrual (7090 mot 2920) credits neither.
        Oldest first."""
        gross = _net("vouchers.id", SALARY_RANGE, "n.debit - n.credit")
        tax = _net("vouchers.id", (PERSONAL_TAX, PERSONAL_TAX), "n.credit - n.debit")
        bank = _net("vouchers.id", STATEMENT_ACCOUNT_RANGE, "n.credit - n.debit")
        debt = _net("vouchers.id", EMPLOYEE_DEBT_RANGE, "n.credit - n.debit")
        range_sql, params = _range_params(date_from, date_to)
        rows = db.execute(
            f"SELECT vouchers.id, vouchers.series, vouchers.number, vouchers.date,"
            f" vouchers.description, {gross} AS gross, {tax} AS tax, {bank} AS bank,"
            f" {debt} AS debt"
            " FROM vouchers"
            f" WHERE {_IN_LEDGER_SQL}"
            f" AND {gross} > 0 AND ({tax} > 0 OR {bank} > 0)"
            " AND NOT EXISTS (SELECT 1 FROM payslips p WHERE p.voucher_id = vouchers.id)"
            f"{range_sql}"
            " ORDER BY vouchers.date, vouchers.series, vouchers.number",
            tuple(params),
        ).fetchall()
        return [
            LedgerSalary(
                **_base(r),
                gross=r["gross"],
                tax=r["tax"],
                net=(
                    r["bank"] if r["bank"] > 0 else r["debt"] if r["debt"] > 0 else None
                ),
            )
            for r in rows
        ]
