"""VAT (moms) declaration service.

Calculates Swedish VAT declaration boxes from posted vouchers and exports the
data as Skatteverket eSKD XML and a human-readable PDF.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from typing import Dict, List, Optional

from db.database import get_db
from domain.validation import ValidationError
from repositories.period_repo import PeriodRepository
from services.pdf_export import CompanyInfo, PDFEngine


@dataclass
class VatSourceAccount:
    """Account contribution to one VAT declaration box."""

    account_code: str
    account_name: str
    amount: int  # öre


@dataclass
class VatDeclaration:
    """A generated VAT declaration."""

    id: str
    period_year: int
    period_month: int  # 0 for quarterly/other aggregate periods
    period_quarter: Optional[int] = None
    period_code: str = ""

    # Sales (försäljning), amounts in öre
    sales_25: int = 0  # Ruta 05
    sales_12: int = 0  # Ruta 06
    sales_6: int = 0  # Ruta 07
    sales_exempt: int = 0  # Ruta 08

    # Output VAT (utgående moms), amounts in öre
    vat_out_25: int = 0  # Ruta 10
    vat_out_12: int = 0  # Ruta 11
    vat_out_6: int = 0  # Ruta 12

    # Input VAT (ingående moms)
    vat_in: int = 0  # Ruta 48

    # Calculated
    vat_to_pay: int = 0  # Ruta 49, positive = pay, negative = refund

    status: str = "draft"
    created_at: datetime = field(default_factory=datetime.now)
    company_name: str = ""
    org_number: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    sources: Dict[str, List[VatSourceAccount]] = field(default_factory=dict)


VAT_BOXES = [
    ("05", "Momspliktig försäljning som inte ingår i annan ruta nedan", "sales_25"),
    ("06", "Momspliktiga uttag", "sales_12"),
    ("07", "Beskattningsunderlag vid vinstmarginalbeskattning", "sales_6"),
    ("08", "Hyresinkomster vid frivillig skattskyldighet", "sales_exempt"),
    ("10", "Utgående moms 25 %", "vat_out_25"),
    ("11", "Utgående moms 12 %", "vat_out_12"),
    ("12", "Utgående moms 6 %", "vat_out_6"),
    ("48", "Ingående moms att dra av", "vat_in"),
    ("49", "Moms att betala eller få tillbaka", "vat_to_pay"),
]


def _to_sek(value_ore: int) -> int:
    """Round öre to whole SEK, matching Skatteverket export files."""

    if value_ore >= 0:
        return int((value_ore + 50) // 100)
    return -int((abs(value_ore) + 50) // 100)


def _format_sek(value_ore: int) -> str:
    return f"{_to_sek(value_ore):,}".replace(",", " ")


class VatReportService:
    """Generate and manage VAT declarations."""

    def generate_monthly(self, year: int, month: int) -> VatDeclaration:
        """Generate VAT declaration for a specific calendar month."""

        if month < 1 or month > 12:
            raise ValidationError("invalid_month", "Month must be 1-12")
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1).replace(day=1)
            end = date.fromordinal(end.toordinal() - 1)
        decl = self._calculate_for_dates(start, end, period_month=month)
        self._save_declaration(decl)
        return decl

    def generate_quarterly(self, year: int, quarter: int) -> VatDeclaration:
        """Generate VAT declaration for a quarter."""

        if quarter < 1 or quarter > 4:
            raise ValidationError("invalid_quarter", "Quarter must be 1-4")
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        end = date(year, end_month, 31 if end_month == 12 else 1)
        if end_month != 12:
            end = date(year, end_month + 1, 1)
            end = date.fromordinal(end.toordinal() - 1)
        decl = self._calculate_for_dates(
            start,
            end,
            period_month=0,
            period_quarter=quarter,
            period_code=f"{year}Q{quarter}",
        )
        self._save_declaration(decl)
        return decl

    def generate_yearly(self, year: int) -> VatDeclaration:
        """Generate annual VAT declaration.

        Skatteverket eSKD annual VAT files use the period code YYYY12. The
        attached iOrdning reference for 2025 is such an annual declaration.
        """

        fiscal_year = next(
            (fy for fy in PeriodRepository.list_fiscal_years() if fy.start_date.year == year),
            None,
        )
        if fiscal_year:
            start = fiscal_year.start_date
            end = fiscal_year.end_date
        else:
            start = date(year, 1, 1)
            end = date(year, 12, 31)
        decl = self._calculate_for_dates(
            start,
            end,
            period_month=12,
            period_code=f"{year}12",
        )
        self._save_declaration(decl)
        return decl

    def preview_yearly(self, year: int) -> VatDeclaration:
        """Calculate annual VAT declaration without saving it."""

        fiscal_year = next(
            (fy for fy in PeriodRepository.list_fiscal_years() if fy.start_date.year == year),
            None,
        )
        start = fiscal_year.start_date if fiscal_year else date(year, 1, 1)
        end = fiscal_year.end_date if fiscal_year else date(year, 12, 31)
        return self._calculate_for_dates(
            start,
            end,
            period_month=12,
            period_code=f"{year}12",
        )

    def get_declaration(self, decl_id: str) -> Optional[VatDeclaration]:
        """Get a specific VAT declaration."""

        row = get_db().execute(
            "SELECT * FROM vat_declarations WHERE id = ?", (decl_id,)
        ).fetchone()
        return self._row_to_declaration(row) if row else None

    def list_declarations(self, year: Optional[int] = None) -> List[VatDeclaration]:
        """List all saved VAT declarations."""

        sql = "SELECT * FROM vat_declarations"
        params = []
        if year:
            sql += " WHERE period_year = ?"
            params.append(year)
        sql += " ORDER BY period_year DESC, period_month DESC, created_at DESC"

        rows = get_db().execute(sql, tuple(params)).fetchall()
        return [self._row_to_declaration(r) for r in rows]

    def format_skv_summary(self, decl: VatDeclaration) -> Dict:
        """Format declaration as API JSON."""

        total_out = decl.vat_out_25 + decl.vat_out_12 + decl.vat_out_6

        return {
            "id": decl.id,
            "period": decl.period_code or self._period_label(decl),
            "period_year": decl.period_year,
            "period_month": decl.period_month,
            "period_quarter": decl.period_quarter,
            "start_date": decl.start_date.isoformat() if decl.start_date else None,
            "end_date": decl.end_date.isoformat() if decl.end_date else None,
            "status": decl.status,
            "company": {
                "name": decl.company_name,
                "org_number": decl.org_number,
            },
            "boxes": [
                {
                    "box": box,
                    "label": label,
                    "amount": getattr(decl, attr),
                    "amount_sek": _to_sek(getattr(decl, attr)),
                    "sources": [
                        {
                            "account_code": source.account_code,
                            "account_name": source.account_name,
                            "amount": source.amount,
                            "amount_sek": _to_sek(source.amount),
                        }
                        for source in decl.sources.get(box, [])
                    ],
                }
                for box, label, attr in VAT_BOXES
            ],
            "skv_4700": {
                "ruta_05_forsaljning_25": _to_sek(decl.sales_25),
                "ruta_06_forsaljning_12": _to_sek(decl.sales_12),
                "ruta_07_forsaljning_6": _to_sek(decl.sales_6),
                "ruta_08_momsfri_forsaljning": _to_sek(decl.sales_exempt),
                "ruta_10_utgaende_moms_25": _to_sek(decl.vat_out_25),
                "ruta_11_utgaende_moms_12": _to_sek(decl.vat_out_12),
                "ruta_12_utgaende_moms_6": _to_sek(decl.vat_out_6),
                "ruta_48_ingaende_moms": _to_sek(decl.vat_in),
                "ruta_49_moms_att_betala": _to_sek(decl.vat_to_pay),
            },
            "summary": {
                "total_sales_sek": _to_sek(
                    decl.sales_25 + decl.sales_12 + decl.sales_6 + decl.sales_exempt
                ),
                "total_output_vat_sek": _to_sek(total_out),
                "total_input_vat_sek": _to_sek(decl.vat_in),
                "net_vat_sek": _to_sek(decl.vat_to_pay),
                "action": "betala" if decl.vat_to_pay > 0 else "få tillbaka",
            },
        }

    def export_eskd(self, decl: VatDeclaration) -> bytes:
        """Export declaration as Skatteverket eSKD XML."""

        org_number = decl.org_number or ""
        period = decl.period_code or f"{decl.period_year}{decl.period_month:02d}"
        lines = [
            '<?xml version="1.0" encoding="ISO-8859-1"?>',
            '<!DOCTYPE eSKDUpload PUBLIC "-//Skatteverket, Sweden//DTD Skatteverket eSKDUpload-DTD Version 6.0//SV" "https://www1.skatteverket.se/demoeskd/eSKDUpload_6p0.dtd">',
            '<eSKDUpload Version="6.0">',
            f"\t<OrgNr>{escape(org_number)}</OrgNr>",
            "\t<Moms>",
            f"\t\t<Period>{escape(period)}</Period>",
        ]

        tag_values = [
            ("ForsMomsEjAnnan", decl.sales_25),
            ("MomsUtgHog", decl.vat_out_25),
            ("MomsIngAvdr", decl.vat_in),
        ]
        if decl.sales_12:
            tag_values.append(("ForsMomsUttag", decl.sales_12))
        if decl.sales_6:
            tag_values.append(("BeskattnVMB", decl.sales_6))
        if decl.sales_exempt:
            tag_values.append(("HyresinkFriv", decl.sales_exempt))
        if decl.vat_out_12:
            tag_values.append(("MomsUtgMedel", decl.vat_out_12))
        if decl.vat_out_6:
            tag_values.append(("MomsUtgLag", decl.vat_out_6))

        for tag, value in tag_values:
            amount = _to_sek(value)
            if amount:
                lines.append(f"\t\t<{tag}>{amount}</{tag}>")

        net_vat = _to_sek(decl.vat_to_pay)
        if net_vat >= 0:
            lines.append(f"\t\t<MomsBetala>{net_vat}</MomsBetala>")
        else:
            lines.append(f"\t\t<MomsFaTillbaka>{abs(net_vat)}</MomsFaTillbaka>")

        lines.extend(["\t</Moms>", "</eSKDUpload>", ""])
        return "\n".join(lines).encode("iso-8859-1")

    def export_pdf(self, decl: VatDeclaration) -> bytes:
        """Export declaration as PDF."""

        company = CompanyInfo(name=decl.company_name or "Företag", org_number=decl.org_number)
        engine = PDFEngine()
        context = {
            "company": company,
            "declaration": decl,
            "boxes": self.format_skv_summary(decl)["boxes"],
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "format_sek": _format_sek,
        }
        return engine.render_pdf("vat_declaration.html", context)

    def _calculate_for_dates(
        self,
        start: date,
        end: date,
        period_month: int,
        period_quarter: Optional[int] = None,
        period_code: Optional[str] = None,
    ) -> VatDeclaration:
        db = get_db()
        company = self._read_company_info()
        decl = VatDeclaration(
            id=str(uuid.uuid4()),
            period_year=start.year,
            period_month=period_month,
            period_quarter=period_quarter,
            period_code=period_code or self._period_code(start.year, period_month, period_quarter),
            company_name=company.get("name", ""),
            org_number=company.get("org_number", ""),
            start_date=start,
            end_date=end,
        )

        rows = db.execute(
            """
            SELECT
                vr.account_code,
                COALESCE(a.name, '') AS account_name,
                SUM(vr.debit) AS debit,
                SUM(vr.credit) AS credit
            FROM voucher_rows vr
            JOIN vouchers v ON v.id = vr.voucher_id
            LEFT JOIN accounts a ON a.code = vr.account_code
            WHERE v.status = 'posted'
              AND v.date >= ?
              AND v.date <= ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM voucher_rows settlement
                  WHERE settlement.voucher_id = v.id
                    AND settlement.account_code = '2650'
              )
              AND (
                  CAST(vr.account_code AS INTEGER) BETWEEN 3000 AND 3799
                  OR vr.account_code IN ('2610', '2620', '2630', '2640')
              )
            GROUP BY vr.account_code, a.name
            ORDER BY vr.account_code
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        for row in rows:
            code = row["account_code"]
            debit = row["debit"] or 0
            credit = row["credit"] or 0
            net_credit = credit - debit
            net_debit = debit - credit
            name = row["account_name"] or code

            if code == "2610":
                self._add_source(decl, "10", code, name, max(net_credit, 0))
                decl.vat_out_25 += max(net_credit, 0)
            elif code == "2620":
                self._add_source(decl, "11", code, name, max(net_credit, 0))
                decl.vat_out_12 += max(net_credit, 0)
            elif code == "2630":
                self._add_source(decl, "12", code, name, max(net_credit, 0))
                decl.vat_out_6 += max(net_credit, 0)
            elif code == "2640":
                self._add_source(decl, "48", code, name, max(net_debit, 0))
                decl.vat_in += max(net_debit, 0)
            elif self._is_sales_25_account(code):
                self._add_source(decl, "05", code, name, max(net_credit, 0))
                decl.sales_25 += max(net_credit, 0)

        # Fallback for systems that only booked VAT accounts.
        if decl.sales_25 == 0 and decl.vat_out_25:
            decl.sales_25 = decl.vat_out_25 * 4
        if decl.sales_12 == 0 and decl.vat_out_12:
            decl.sales_12 = int(round(decl.vat_out_12 / 0.12))
        if decl.sales_6 == 0 and decl.vat_out_6:
            decl.sales_6 = int(round(decl.vat_out_6 / 0.06))

        total_out = decl.vat_out_25 + decl.vat_out_12 + decl.vat_out_6
        decl.vat_to_pay = total_out - decl.vat_in
        decl.sources["49"] = [
            VatSourceAccount("10-12", "Summa utgående moms", total_out),
            VatSourceAccount("48", "Ingående moms att dra av", -decl.vat_in),
        ]
        return decl

    def _save_declaration(self, decl: VatDeclaration) -> None:
        """Save VAT declaration to database."""

        db = get_db()
        db.execute(
            """CREATE TABLE IF NOT EXISTS vat_declarations (
                id TEXT PRIMARY KEY,
                period_year INTEGER NOT NULL,
                period_month INTEGER NOT NULL,
                period_quarter INTEGER,
                sales_25 INTEGER DEFAULT 0,
                sales_12 INTEGER DEFAULT 0,
                sales_6 INTEGER DEFAULT 0,
                sales_exempt INTEGER DEFAULT 0,
                vat_out_25 INTEGER DEFAULT 0,
                vat_out_12 INTEGER DEFAULT 0,
                vat_out_6 INTEGER DEFAULT 0,
                vat_in INTEGER DEFAULT 0,
                vat_to_pay INTEGER DEFAULT 0,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        db.execute(
            """INSERT OR REPLACE INTO vat_declarations
               (id, period_year, period_month, period_quarter,
                sales_25, sales_12, sales_6, sales_exempt,
                vat_out_25, vat_out_12, vat_out_6, vat_in, vat_to_pay, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decl.id,
                decl.period_year,
                decl.period_month,
                decl.period_quarter,
                decl.sales_25,
                decl.sales_12,
                decl.sales_6,
                decl.sales_exempt,
                decl.vat_out_25,
                decl.vat_out_12,
                decl.vat_out_6,
                decl.vat_in,
                decl.vat_to_pay,
                decl.status,
            ),
        )
        db.commit()

    def _row_to_declaration(self, row) -> VatDeclaration:
        return VatDeclaration(
            id=row["id"],
            period_year=row["period_year"],
            period_month=row["period_month"],
            period_quarter=row["period_quarter"],
            sales_25=row["sales_25"] or 0,
            sales_12=row["sales_12"] or 0,
            sales_6=row["sales_6"] or 0,
            sales_exempt=row["sales_exempt"] or 0,
            vat_out_25=row["vat_out_25"] or 0,
            vat_out_12=row["vat_out_12"] or 0,
            vat_out_6=row["vat_out_6"] or 0,
            vat_in=row["vat_in"] or 0,
            vat_to_pay=row["vat_to_pay"] or 0,
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"])
            if row["created_at"]
            else datetime.now(),
            period_code=f"{row['period_year']}{row['period_month']:02d}"
            if row["period_month"]
            else f"{row['period_year']} Q{row['period_quarter']}",
        )

    def _read_company_info(self) -> Dict[str, str]:
        rows = get_db().execute("SELECT key, value FROM company_info").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def _add_source(
        self,
        decl: VatDeclaration,
        box: str,
        account_code: str,
        account_name: str,
        amount: int,
    ) -> None:
        if amount == 0:
            return
        decl.sources.setdefault(box, []).append(
            VatSourceAccount(account_code, account_name, amount)
        )

    def _is_sales_25_account(self, account_code: str) -> bool:
        if not account_code.isdigit():
            return False
        account = int(account_code)
        return 3000 <= account <= 3799

    def _period_code(
        self,
        year: int,
        period_month: int,
        period_quarter: Optional[int],
    ) -> str:
        if period_month:
            return f"{year}{period_month:02d}"
        if period_quarter:
            return f"{year}Q{period_quarter}"
        return str(year)

    def _period_label(self, decl: VatDeclaration) -> str:
        if decl.period_month:
            return f"{decl.period_year}-{decl.period_month:02d}"
        if decl.period_quarter:
            return f"{decl.period_year} Q{decl.period_quarter}"
        return str(decl.period_year)
