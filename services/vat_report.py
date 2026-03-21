"""VAT (Moms) declaration service.

Generates Swedish VAT declarations based on booked vouchers.
Supports monthly and quarterly reporting periods.

SKV 4700 format mapping:
- Ruta 05: Momspliktig försäljning 25%
- Ruta 06: Momspliktig försäljning 12%
- Ruta 07: Momspliktig försäljning 6%
- Ruta 08: Momsfri försäljning (export, etc)
- Ruta 10: Utgående moms 25%
- Ruta 11: Utgående moms 12%
- Ruta 12: Utgående moms 6%
- Ruta 48: Ingående moms
- Ruta 49: Moms att betala/få tillbaka
"""

import uuid
from datetime import date, datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field

from db.database import db
from domain.validation import ValidationError


@dataclass
class VatDeclaration:
    """A generated VAT declaration."""
    id: str
    period_year: int
    period_month: int  # 0 for quarterly
    period_quarter: Optional[int] = None  # 1-4 for quarterly
    
    # Sales (försäljning) - amounts in öre
    sales_25: int = 0  # Ruta 05
    sales_12: int = 0  # Ruta 06
    sales_6: int = 0   # Ruta 07
    sales_exempt: int = 0  # Ruta 08
    
    # Output VAT (utgående moms) - amounts in öre
    vat_out_25: int = 0  # Ruta 10
    vat_out_12: int = 0  # Ruta 11
    vat_out_6: int = 0   # Ruta 12
    
    # Input VAT (ingående moms)
    vat_in: int = 0  # Ruta 48
    
    # Calculated
    vat_to_pay: int = 0  # Ruta 49 (positive = pay, negative = refund)
    
    status: str = "draft"  # draft, final, submitted
    created_at: datetime = field(default_factory=datetime.now)


class VatReportService:
    """Generate and manage VAT declarations."""

    def generate_monthly(self, year: int, month: int) -> VatDeclaration:
        """Generate VAT declaration for a specific month.
        
        Collects all VAT-related transactions from posted vouchers
        in the given period and calculates declaration amounts.
        """
        decl_id = str(uuid.uuid4())
        
        # Get all VAT-related voucher rows for the period
        rows = db.execute("""
            SELECT vr.account_code, SUM(vr.debit) as total_debit, SUM(vr.credit) as total_credit
            FROM voucher_rows vr
            JOIN vouchers v ON v.id = vr.voucher_id
            JOIN periods p ON p.id = v.period_id
            WHERE v.status = 'posted'
            AND p.year = ? AND p.month = ?
            AND vr.account_code IN (
                '2610', '2620', '2630',  -- Utgående moms
                '2640',                   -- Ingående moms
                '3011', '3012', '3013', '3014',  -- Försäljning
                '3041', '3042', '3043', '3044',  -- Försäljning tjänster
                '3051', '3052', '3053',  -- Diverse
                '3211', '3212', '3213',  -- EU
                '3231', '3232', '3233',  -- Export
                '3305', '3308'  -- Momsfri
            )
            GROUP BY vr.account_code
        """, (year, month)).fetchall()

        decl = VatDeclaration(id=decl_id, period_year=year, period_month=month)
        
        for row in rows:
            code = row["account_code"]
            # Net amount (credit - debit for revenue/VAT out, debit - credit for VAT in)
            net_credit = (row["total_credit"] or 0) - (row["total_debit"] or 0)
            net_debit = (row["total_debit"] or 0) - (row["total_credit"] or 0)
            
            # Utgående moms (output VAT)
            if code == "2610":
                decl.vat_out_25 = net_credit
            elif code == "2620":
                decl.vat_out_12 = net_credit
            elif code == "2630":
                decl.vat_out_6 = net_credit
            
            # Ingående moms (input VAT)
            elif code == "2640":
                decl.vat_in = net_debit
            
            # Sales accounts - reverse-calculate from VAT or use revenue accounts
            # Revenue at 25%
            elif code in ("3011", "3041"):
                decl.sales_25 += net_credit
            # Revenue at 12%
            elif code in ("3012", "3042"):
                decl.sales_12 += net_credit
            # Revenue at 6%
            elif code in ("3013", "3043"):
                decl.sales_6 += net_credit
            # Exempt / export
            elif code in ("3014", "3044", "3305", "3308", "3231", "3232", "3233"):
                decl.sales_exempt += net_credit

        # If sales weren't tracked separately, calculate from VAT
        if decl.sales_25 == 0 and decl.vat_out_25 > 0:
            decl.sales_25 = int(decl.vat_out_25 / 0.25)
        if decl.sales_12 == 0 and decl.vat_out_12 > 0:
            decl.sales_12 = int(decl.vat_out_12 / 0.12)
        if decl.sales_6 == 0 and decl.vat_out_6 > 0:
            decl.sales_6 = int(decl.vat_out_6 / 0.06)

        # Calculate total VAT to pay
        total_out = decl.vat_out_25 + decl.vat_out_12 + decl.vat_out_6
        decl.vat_to_pay = total_out - decl.vat_in

        # Save declaration
        self._save_declaration(decl)
        
        return decl

    def generate_quarterly(self, year: int, quarter: int) -> VatDeclaration:
        """Generate VAT declaration for a quarter (Q1-Q4)."""
        if quarter < 1 or quarter > 4:
            raise ValidationError("invalid_quarter", "Quarter must be 1-4")
        
        start_month = (quarter - 1) * 3 + 1
        months = [start_month, start_month + 1, start_month + 2]
        
        # Generate individual months and aggregate
        combined = VatDeclaration(
            id=str(uuid.uuid4()),
            period_year=year,
            period_month=0,
            period_quarter=quarter,
        )
        
        for month in months:
            monthly = self.generate_monthly(year, month)
            combined.sales_25 += monthly.sales_25
            combined.sales_12 += monthly.sales_12
            combined.sales_6 += monthly.sales_6
            combined.sales_exempt += monthly.sales_exempt
            combined.vat_out_25 += monthly.vat_out_25
            combined.vat_out_12 += monthly.vat_out_12
            combined.vat_out_6 += monthly.vat_out_6
            combined.vat_in += monthly.vat_in
        
        total_out = combined.vat_out_25 + combined.vat_out_12 + combined.vat_out_6
        combined.vat_to_pay = total_out - combined.vat_in
        
        self._save_declaration(combined)
        return combined

    def get_declaration(self, decl_id: str) -> Optional[VatDeclaration]:
        """Get a specific VAT declaration."""
        row = db.execute(
            "SELECT * FROM vat_declarations WHERE id = ?", (decl_id,)
        ).fetchone()
        return self._row_to_declaration(row) if row else None

    def list_declarations(self, year: Optional[int] = None) -> List[VatDeclaration]:
        """List all VAT declarations."""
        sql = "SELECT * FROM vat_declarations"
        params = []
        if year:
            sql += " WHERE period_year = ?"
            params.append(year)
        sql += " ORDER BY period_year DESC, period_month DESC"
        
        rows = db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_declaration(r) for r in rows]

    def format_skv_summary(self, decl: VatDeclaration) -> Dict:
        """Format declaration as SKV 4700 summary."""
        total_out = decl.vat_out_25 + decl.vat_out_12 + decl.vat_out_6
        
        period_label = (
            f"{decl.period_year}-{decl.period_month:02d}"
            if decl.period_month > 0
            else f"{decl.period_year} Q{decl.period_quarter}"
        )
        
        return {
            "period": period_label,
            "status": decl.status,
            "skv_4700": {
                "ruta_05_forsaljning_25": decl.sales_25 / 100,
                "ruta_06_forsaljning_12": decl.sales_12 / 100,
                "ruta_07_forsaljning_6": decl.sales_6 / 100,
                "ruta_08_momsfri_forsaljning": decl.sales_exempt / 100,
                "ruta_10_utgaende_moms_25": decl.vat_out_25 / 100,
                "ruta_11_utgaende_moms_12": decl.vat_out_12 / 100,
                "ruta_12_utgaende_moms_6": decl.vat_out_6 / 100,
                "ruta_48_ingaende_moms": decl.vat_in / 100,
                "ruta_49_moms_att_betala": decl.vat_to_pay / 100,
            },
            "summary": {
                "total_sales_sek": (decl.sales_25 + decl.sales_12 + decl.sales_6 + decl.sales_exempt) / 100,
                "total_output_vat_sek": total_out / 100,
                "total_input_vat_sek": decl.vat_in / 100,
                "net_vat_sek": decl.vat_to_pay / 100,
                "action": "betala" if decl.vat_to_pay > 0 else "få tillbaka",
            },
        }

    def _save_declaration(self, decl: VatDeclaration) -> None:
        """Save VAT declaration to database."""
        try:
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
                (decl.id, decl.period_year, decl.period_month, decl.period_quarter,
                 decl.sales_25, decl.sales_12, decl.sales_6, decl.sales_exempt,
                 decl.vat_out_25, decl.vat_out_12, decl.vat_out_6,
                 decl.vat_in, decl.vat_to_pay, decl.status)
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

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
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )
