"""VAT (moms) declaration service.

Calculates Swedish VAT declaration boxes from posted vouchers and exports the
data as Skatteverket eSKD XML and a human-readable PDF.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from typing import Dict, List, Optional, Tuple

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

    # Sales (försäljning), amounts in öre. The attribute names predate the
    # box mapping and are kept because they are the `vat_declarations`
    # columns: `sales_25` is ruta 05 -- all taxable sales whatever the rate,
    # the rate shows in 10-12 -- and 06/07/08 are uttag, vinstmarginal and
    # hyresinkomster, not 12 % and 6 % sales.
    sales_25: int = 0  # Ruta 05
    sales_12: int = 0  # Ruta 06 Momspliktiga uttag
    sales_6: int = 0  # Ruta 07 Vinstmarginalbeskattning
    sales_exempt: int = 0  # Ruta 08 Hyresinkomster, frivillig skattskyldighet
    sales_other: int = 0  # Ruta 42 Övrig försäljning m.m.

    # Output VAT (utgående moms), amounts in öre
    vat_out_25: int = 0  # Ruta 10
    vat_out_12: int = 0  # Ruta 11
    vat_out_6: int = 0  # Ruta 12

    # Purchases with reverse charge (omvänd skattskyldighet), migration 045:
    # the base on 4535/4531 (against 4598) and the calculated VAT on 2614.
    purchases_services_eu: int = 0  # Ruta 21
    purchases_services_non_eu: int = 0  # Ruta 22
    vat_out_reverse_25: int = 0  # Ruta 30

    # Input VAT (ingående moms), 2640 and 2645
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
    warnings: List[str] = field(default_factory=list)


VAT_BOXES = [
    ("05", "Momspliktig försäljning som inte ingår i annan ruta nedan", "sales_25"),
    ("06", "Momspliktiga uttag", "sales_12"),
    ("07", "Beskattningsunderlag vid vinstmarginalbeskattning", "sales_6"),
    ("08", "Hyresinkomster vid frivillig skattskyldighet", "sales_exempt"),
    ("42", "Övrig försäljning m.m.", "sales_other"),
    ("10", "Utgående moms 25 %", "vat_out_25"),
    ("11", "Utgående moms 12 %", "vat_out_12"),
    ("12", "Utgående moms 6 %", "vat_out_6"),
    (
        "21",
        "Inköp av tjänster från ett annat EU-land enligt huvudregeln",
        "purchases_services_eu",
    ),
    ("22", "Inköp av tjänster från ett land utanför EU", "purchases_services_non_eu"),
    ("30", "Utgående moms 25 % på inköp i rutorna 20-24", "vat_out_reverse_25"),
    ("48", "Ingående moms att dra av", "vat_in"),
    ("49", "Moms att betala eller få tillbaka", "vat_to_pay"),
]


# What the sales columns in `vat_declarations` mean (migration 047): 1 is the
# original 12 %/6 %/momsfri meaning, 2 the box mapping in VAT_BOXES.
BOX_LAYOUT = 2


# Reverse-charge accounts (migration 045) and the box each one fills.
REVERSE_CHARGE_BOXES = {"2614": "30", "4535": "21", "4531": "22"}


def _to_sek(value_ore: int) -> int:
    """Round öre to whole SEK, matching Skatteverket export files."""

    if value_ore >= 0:
        return int((value_ore + 50) // 100)
    return -int((abs(value_ore) + 50) // 100)


def _total_output_vat(decl: "VatDeclaration") -> int:
    """Boxes 10-12 and 30: the output VAT on sales and on reverse-charge
    purchases. Box 30 is offset by the same amount in box 48 (2645) when the
    purchase is fully deductible."""
    return decl.vat_out_25 + decl.vat_out_12 + decl.vat_out_6 + decl.vat_out_reverse_25


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
            (
                fy
                for fy in PeriodRepository.list_fiscal_years()
                if fy.start_date.year == year
            ),
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
            (
                fy
                for fy in PeriodRepository.list_fiscal_years()
                if fy.start_date.year == year
            ),
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

    def preview_for_dates(self, start: date, end: date) -> VatDeclaration:
        """Calculate the declaration for a fiscal year's dates, unsaved.

        The period code is the last month (YYYYMM), as for an annual
        declaration on eSKD.
        """
        return self._calculate_for_dates(
            start, end, period_month=12, period_code=f"{end.year}{end.month:02d}"
        )

    def get_declaration(self, decl_id: str) -> Optional[VatDeclaration]:
        """Get a specific VAT declaration."""

        row = (
            get_db()
            .execute("SELECT * FROM vat_declarations WHERE id = ?", (decl_id,))
            .fetchone()
        )
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

        total_out = _total_output_vat(decl)

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
            "warnings": list(decl.warnings),
            "skv_4700": {
                "ruta_05_momspliktig_forsaljning": _to_sek(decl.sales_25),
                "ruta_06_momspliktiga_uttag": _to_sek(decl.sales_12),
                "ruta_07_vinstmarginal": _to_sek(decl.sales_6),
                "ruta_08_hyresinkomster": _to_sek(decl.sales_exempt),
                "ruta_42_ovrig_forsaljning": _to_sek(decl.sales_other),
                "ruta_10_utgaende_moms_25": _to_sek(decl.vat_out_25),
                "ruta_11_utgaende_moms_12": _to_sek(decl.vat_out_12),
                "ruta_12_utgaende_moms_6": _to_sek(decl.vat_out_6),
                "ruta_21_inkop_tjanster_eu": _to_sek(decl.purchases_services_eu),
                "ruta_22_inkop_tjanster_utanfor_eu": _to_sek(
                    decl.purchases_services_non_eu
                ),
                "ruta_30_utgaende_moms_inkop_25": _to_sek(decl.vat_out_reverse_25),
                "ruta_48_ingaende_moms": _to_sek(decl.vat_in),
                "ruta_49_moms_att_betala": _to_sek(decl.vat_to_pay),
            },
            "summary": {
                "total_sales_sek": _to_sek(
                    decl.sales_25
                    + decl.sales_12
                    + decl.sales_6
                    + decl.sales_exempt
                    + decl.sales_other
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
            tag_values.append(("UttagMoms", decl.sales_12))
        if decl.sales_6:
            tag_values.append(("UlagMargbesk", decl.sales_6))
        if decl.sales_exempt:
            tag_values.append(("HyrinkomstFriv", decl.sales_exempt))
        if decl.sales_other:
            tag_values.append(("ForsOvrigt", decl.sales_other))
        if decl.vat_out_12:
            tag_values.append(("MomsUtgMedel", decl.vat_out_12))
        if decl.vat_out_6:
            tag_values.append(("MomsUtgLag", decl.vat_out_6))
        if decl.purchases_services_eu:
            tag_values.append(("InkopTjanstAnnatEg", decl.purchases_services_eu))
        if decl.purchases_services_non_eu:
            tag_values.append(("InkopTjanstUtomEg", decl.purchases_services_non_eu))
        if decl.vat_out_reverse_25:
            tag_values.append(("MomsInkopUtgHog", decl.vat_out_reverse_25))

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

        company = CompanyInfo(
            name=decl.company_name or "Företag", org_number=decl.org_number
        )
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
            period_code=period_code
            or self._period_code(start.year, period_month, period_quarter),
            company_name=company.get("name", ""),
            org_number=company.get("org_number", ""),
            start_date=start,
            end_date=end,
        )

        # Per voucher and account, so that each sales line can be sorted into
        # ruta 05 or 42 against the output VAT on its own voucher
        # (`_classify_sales`). The year-end
        # settlement (the voucher that books 2650) is left out, and so is
        # öres- och kronutjämning (3740-3799): it is not a sale.
        rows = db.execute(
            """
            SELECT
                vr.voucher_id,
                v.date AS voucher_date,
                vr.account_code,
                COALESCE(a.name, '') AS account_name,
                SUM(vr.debit) AS debit,
                SUM(vr.credit) AS credit
            FROM voucher_rows vr
            JOIN vouchers v ON v.id = vr.voucher_id
            LEFT JOIN accounts a ON a.code = vr.account_code
            WHERE v.status = 'posted'
              AND v.series != 'IB'
              AND v.date >= ?
              AND v.date <= ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM voucher_rows settlement
                  WHERE settlement.voucher_id = v.id
                    AND settlement.account_code = '2650'
              )
              AND (
                  CAST(vr.account_code AS INTEGER) BETWEEN 3000 AND 3739
                  OR CAST(vr.account_code AS INTEGER) BETWEEN 2610 AND 2649
                  OR vr.account_code IN ('4531', '4535')
              )
            GROUP BY vr.voucher_id, v.date, vr.account_code, a.name
            ORDER BY vr.voucher_id, vr.account_code
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        per_box: Dict[tuple, int] = {}
        sales_by_voucher: Dict[str, List[tuple]] = {}
        vat_by_voucher: Dict[str, Dict[str, int]] = {}
        voucher_dates: Dict[str, str] = {}
        for row in rows:
            code = row["account_code"]
            net_credit = (row["credit"] or 0) - (row["debit"] or 0)
            name = row["account_name"] or code
            out_box = self._output_vat_box(code)
            if out_box:
                box, amount = out_box, net_credit
                by_rate = vat_by_voucher.setdefault(row["voucher_id"], {})
                by_rate[out_box] = by_rate.get(out_box, 0) + net_credit
            elif code in REVERSE_CHARGE_BOXES:
                # Omvänd skattskyldighet (migration 045): the calculated VAT
                # on 2614 is box 30 (credit), the base on 4535/4531 box 21/22
                # (debit). 2645, its deductible side, is in box 48 below.
                box = REVERSE_CHARGE_BOXES[code]
                amount = net_credit if code == "2614" else -net_credit
            elif self._is_input_vat_account(code):
                box, amount = "48", -net_credit
            elif self._is_sales_account(code):
                if net_credit:
                    sales_by_voucher.setdefault(row["voucher_id"], []).append(
                        (code, name, net_credit)
                    )
                    voucher_dates[row["voucher_id"]] = str(row["voucher_date"])
                continue
            else:
                continue
            per_box[(box, code, name)] = per_box.get((box, code, name), 0) + amount

        for voucher_id, lines in sales_by_voucher.items():
            classified, unsure = self._classify_sales(
                lines, vat_by_voucher.get(voucher_id, {})
            )
            if unsure:
                decl.warnings.append(
                    f"En verifikation den {voucher_dates[voucher_id]} har "
                    "försäljning med och utan moms som inte går att skilja åt "
                    "per konto. Ruta 05 har fått det belopp momsen motsvarar, "
                    "resten ligger i ruta 42. Kontrollera verifikationen."
                )
            for box, code, name, amount in classified:
                per_box[(box, code, name)] = per_box.get((box, code, name), 0) + amount

        attr = {
            "05": "sales_25",
            "42": "sales_other",
            "10": "vat_out_25",
            "11": "vat_out_12",
            "12": "vat_out_6",
            "21": "purchases_services_eu",
            "22": "purchases_services_non_eu",
            "30": "vat_out_reverse_25",
            "48": "vat_in",
        }
        for (box, code, name), amount in sorted(per_box.items()):
            if amount == 0:
                continue
            self._add_source(decl, box, code, name, amount)
            setattr(decl, attr[box], getattr(decl, attr[box]) + amount)

        for box in ("05", "42", "21", "22", "30", "48"):
            label = f"ruta {box}"
            value = getattr(decl, attr[box])
            if value < 0:
                decl.warnings.append(
                    f"{label} blir negativ ({_to_sek(value)} kr) och redovisas som 0. "
                    "Kontrollera verifikationerna bakom raden."
                )
                setattr(decl, attr[box], 0)

        # Fallback for systems that only booked VAT accounts.
        if decl.sales_25 == 0 and decl.vat_out_25:
            decl.sales_25 = decl.vat_out_25 * 4

        total_out = _total_output_vat(decl)
        decl.vat_to_pay = total_out - decl.vat_in
        decl.sources["49"] = [
            VatSourceAccount("10-12, 30", "Summa utgående moms", total_out),
            VatSourceAccount("48", "Ingående moms att dra av", -decl.vat_in),
        ]
        return decl

    #: Output-VAT box -> rate, to work out the taxable base the VAT implies.
    _OUTPUT_VAT_RATES = {
        "10": Decimal("0.25"),
        "11": Decimal("0.12"),
        "12": Decimal("0.06"),
    }

    #: More sales lines than this on one voucher are not searched for a subset.
    _MAX_SUBSET_LINES = 12

    @classmethod
    def _classify_sales(
        cls, lines: List[tuple], vat_by_box: Dict[str, int]
    ) -> Tuple[List[tuple], bool]:
        """Sort one voucher's sales lines `(code, name, net_credit)` into ruta
        05 (momspliktig) and ruta 42 (övrig försäljning).

        The output VAT on the voucher implies the taxable base (VAT / rate,
        per rate). The lines whose sum matches that base, within the rounding
        the VAT may carry, are ruta 05 and the rest ruta 42. A voucher with no
        output VAT is all ruta 42. When no set of whole lines matches, ruta 05
        gets the implied base, split over the lines pro rata, and the second
        value is True so that the caller can warn.

        Returns `[(box, code, name, amount)]` and the warning flag."""
        base_dec = Decimal(0)
        tolerance = Decimal(0)
        for box, vat in vat_by_box.items():
            rate = cls._OUTPUT_VAT_RATES[box]
            if vat:
                base_dec += Decimal(vat) / rate
                # Up to 50 öre of rounding in the VAT, scaled up to the base.
                tolerance += Decimal(50) / rate
        base = int(base_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        tol = int(tolerance.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        def whole(taxable: set) -> List[tuple]:
            return [
                ("05" if i in taxable else "42", code, name, amount)
                for i, (code, name, amount) in enumerate(lines)
            ]

        if base == 0:
            return whole(set()), False
        total = sum(amount for _, _, amount in lines)
        if abs(total - base) <= tol:
            return whole(set(range(len(lines)))), False

        if len(lines) <= cls._MAX_SUBSET_LINES:
            best: Optional[Tuple[int, set]] = None
            for mask in range(1, 1 << len(lines)):
                subset = {i for i in range(len(lines)) if mask >> i & 1}
                diff = abs(sum(lines[i][2] for i in subset) - base)
                if diff <= tol and (best is None or diff < best[0]):
                    best = (diff, subset)
            if best is not None:
                return whole(best[1]), False

        # VAT on a non-sales account, or a credit note against a sale on the
        # same voucher, leaves no exempt part to find: all of it is taxable.
        if (total > 0) != (base > 0) or abs(total) <= abs(base):
            return whole(set(range(len(lines)))), False

        out: List[tuple] = []
        left = base
        for i, (code, name, amount) in enumerate(lines):
            if i == len(lines) - 1:
                taxable = left
            else:
                taxable = int(
                    (Decimal(amount) * base / total).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
                left -= taxable
            out.append(("05", code, name, taxable))
            out.append(("42", code, name, amount - taxable))
        return out, True

    def _save_declaration(self, decl: VatDeclaration) -> None:
        """Save VAT declaration to database."""

        db = get_db()
        db.execute("""CREATE TABLE IF NOT EXISTS vat_declarations (
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                purchases_services_eu INTEGER DEFAULT 0,
                purchases_services_non_eu INTEGER DEFAULT 0,
                vat_out_reverse_25 INTEGER DEFAULT 0,
                sales_other INTEGER DEFAULT 0,
                box_layout INTEGER NOT NULL DEFAULT 1
            )""")
        db.execute(
            """INSERT OR REPLACE INTO vat_declarations
               (id, period_year, period_month, period_quarter,
                sales_25, sales_12, sales_6, sales_exempt,
                vat_out_25, vat_out_12, vat_out_6, vat_in, vat_to_pay, status,
                purchases_services_eu, purchases_services_non_eu,
                vat_out_reverse_25, sales_other, box_layout)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                decl.purchases_services_eu,
                decl.purchases_services_non_eu,
                decl.vat_out_reverse_25,
                decl.sales_other,
                BOX_LAYOUT,
            ),
        )
        db.commit()

    def _row_to_declaration(self, row) -> VatDeclaration:
        sales_25 = row["sales_25"] or 0
        sales_12 = row["sales_12"] or 0
        sales_6 = row["sales_6"] or 0
        sales_exempt = row["sales_exempt"] or 0
        sales_other = row["sales_other"] or 0
        if row["box_layout"] == 1:
            # Saved before migration 047: sales_12/sales_6 were 12 % and 6 %
            # sales (ruta 05 now), sales_exempt was momsfri försäljning
            # (ruta 42 now).
            sales_25 += sales_12 + sales_6
            sales_other += sales_exempt
            sales_12 = sales_6 = sales_exempt = 0
        return VatDeclaration(
            id=row["id"],
            period_year=row["period_year"],
            period_month=row["period_month"],
            period_quarter=row["period_quarter"],
            sales_25=sales_25,
            sales_12=sales_12,
            sales_6=sales_6,
            sales_exempt=sales_exempt,
            sales_other=sales_other,
            vat_out_25=row["vat_out_25"] or 0,
            vat_out_12=row["vat_out_12"] or 0,
            vat_out_6=row["vat_out_6"] or 0,
            vat_in=row["vat_in"] or 0,
            vat_to_pay=row["vat_to_pay"] or 0,
            purchases_services_eu=row["purchases_services_eu"] or 0,
            purchases_services_non_eu=row["purchases_services_non_eu"] or 0,
            vat_out_reverse_25=row["vat_out_reverse_25"] or 0,
            status=row["status"],
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if row["created_at"]
                else datetime.now()
            ),
            period_code=(
                f"{row['period_year']}{row['period_month']:02d}"
                if row["period_month"]
                else f"{row['period_year']} Q{row['period_quarter']}"
            ),
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

    @staticmethod
    def _output_vat_box(account_code: str) -> Optional[str]:
        """Ruta for an output-VAT account: 2610-2612 25 %, 2620-2622 12 %,
        2630-2632 6 % (BAS; 2614-2619 etc. are reverse charge and import)."""
        if not account_code.isdigit():
            return None
        n = int(account_code)
        if 2610 <= n <= 2612:
            return "10"
        if 2620 <= n <= 2622:
            return "11"
        if 2630 <= n <= 2632:
            return "12"
        return None

    @staticmethod
    def _is_input_vat_account(account_code: str) -> bool:
        return account_code.isdigit() and 2640 <= int(account_code) <= 2649

    @staticmethod
    def _is_sales_account(account_code: str) -> bool:
        return account_code.isdigit() and 3000 <= int(account_code) <= 3739

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
