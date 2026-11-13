"""SRU Export Service for Swedish INK2 Tax Declaration.

SRU = Skatteverkets Rapporterings-Utbyte
Generates INFO.SRU and BLANKETTER.SRU files for electronic tax filing.
"""

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from db.database import get_db

if TYPE_CHECKING:
    from services.tax_adjustments import Justering
from domain.sru_fields import (
    BALANCE_ASSET_FIELDS,
    BALANCE_EQUITY_LIABILITY_FIELDS,
    COST_FIELDS,
    CREDIT_FIELDS,
    DERIVED_RESULT_ACCOUNTS,
    EXPENSE_FIELDS,
    INCOME_FIELDS,
    default_account_mappings,
    field_labels,
)

# The account-to-field table lives in domain/sru_fields.py so that the export
# and the on-screen declaration cannot disagree about what a field code means.
DEFAULT_SRU_MAPPINGS: Dict[str, List[int]] = default_account_mappings()

# Ledger balances are debit-positive öre. Credit-balance fields (equity,
# liabilities, income) are negated, cost fields reported as absolute amounts,
# so every INK2R box holds the positive figure the form asks for.
CREDIT_BALANCE_FIELDS = set(CREDIT_FIELDS)
ALWAYS_POSITIVE_FIELDS = set(COST_FIELDS)

INK2S_DERIVED_FIELDS = {
    "7650",
    "7750",
    "7651",
    "7653",
    "7754",
    "7654",
    "7667",
    "7670",
    "7770",
}
INK2S_EXPORT_ORDER = [
    "7650",
    "7750",
    "7651",
    "7653",
    "7754",
    "7654",
    "7667",
    "7670",
    "7770",
]
# Fields in INK2S that reduce the taxable result.
INK2S_MINUS_FIELDS = {"7754"}


def blankett_period(fiscal_year_end: str) -> str:
    """Skatteverkets blankettversion, t.ex. "2025P4", ur räkenskapsårets slut.

    Deklarationsperioden följer slutmånaden: januari–april P1, maj–juni P2,
    juli–augusti P3 och september–december P4.
    """
    year = fiscal_year_end[:4]
    month = int(fiscal_year_end[4:6])
    if month <= 4:
        p = 1
    elif month <= 6:
        p = 2
    elif month <= 8:
        p = 3
    else:
        p = 4
    return f"{year}P{p}"


INK2R_ZERO_EXPORT_FIELDS = {"7321", "7370"}


def _is_derived_result_account(account_code: str) -> bool:
    """Whether an account holds the year's result (BAS 899x), not an INK2R row."""
    try:
        return int(account_code) in DERIVED_RESULT_ACCOUNTS
    except ValueError:
        return False


@dataclass
class SRUFieldValue:
    """Value for a single SRU field."""

    field_number: str
    description: str
    value: int  # In SEK (not öre)
    source_accounts: List[str]  # Which accounts contributed
    source_account_values: Optional[List[Dict[str, int | str]]] = None


@dataclass
class SRUDeclaration:
    """Complete SRU declaration data."""

    fiscal_year_id: str
    company_org_number: str
    company_name: str
    fiscal_year_start: str  # YYYYMMDD
    fiscal_year_end: str  # YYYYMMDD
    fields: Dict[str, SRUFieldValue]
    contact_name: Optional[str] = None
    address: Optional[str] = None
    postnr: Optional[str] = None
    postort: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    uppdragstagare: bool = False
    revision: bool = False

    def get_field_value(self, field_number: str) -> int:
        """Get numeric value for a field (0 if not found)."""
        field = self.fields.get(field_number)
        return field.value if field else 0


class SRUExportService:
    """Service for generating SRU export files."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def get_sru_mappings(self, fiscal_year_id: str) -> Dict[str, str]:
        """
        Get SRU mappings for a fiscal year.

        Returns {account_code: sru_field} dictionary.
        First checks database for imported SIE4 mappings,
        then falls back to the BAS coupling table in domain/sru_fields.py.
        """
        db = get_db()
        mappings = {}

        # First, get mappings from database (imported from SIE4)
        cursor = db.execute(
            """
            SELECT a.code, m.sru_field
            FROM account_sru_mappings m
            JOIN accounts a ON m.account_code = a.code
            WHERE m.fiscal_year_id = ?
            """,
            (fiscal_year_id,),
        )

        db_mappings = {row["code"]: row["sru_field"] for row in cursor.fetchall()}

        if db_mappings:
            mappings.update(db_mappings)
            # A saved year-specific mapping is a deliberate deviation from the
            # BAS coupling table (typically from a SIE4 #SRU import), so it is
            # worth surfacing which accounts no longer follow the standard.
            self.warnings.append(
                f"Årsspecifik SRU-mappning används för {len(db_mappings)} "
                "konton i stället för standardmappningen (BAS-kopplingstabellen)."
            )
            return mappings

        # Fill with the default BAS mappings only when there is no imported
        # SIE4 mapping. Imported SRU data is form-software specific and must be
        # treated as authoritative to avoid exporting accounts iOrdning left out.
        #
        # Using the standard mapping is the normal, expected path and is not
        # flagged. The genuine risk -- an account that carries a balance but
        # maps to no field -- is reported from calculate_sru_fields() once the
        # balances are known.
        for sru_field, account_ranges in DEFAULT_SRU_MAPPINGS.items():
            for account_num in account_ranges:
                account_code = str(account_num)
                if account_code not in mappings:
                    mappings[account_code] = sru_field

        return mappings

    def calculate_account_balances(self, fiscal_year_id: str) -> Dict[str, Dict]:
        """
        Calculate closing balances for all accounts in fiscal year.

        Returns {account_code: {id, name, balance, account_type}}.
        Balance is in öre (positive = debit, negative = credit).
        """
        db = get_db()
        fiscal_year = db.execute(
            "SELECT start_date, end_date FROM fiscal_years WHERE id = ?",
            (fiscal_year_id,),
        ).fetchone()
        if not fiscal_year:
            raise ValueError(f"Fiscal year {fiscal_year_id} not found")

        from repositories.opening_balance_repo import OpeningBalanceRepository
        from services.opening_balance import OpeningBalanceService, is_balance_account

        # Balance accounts: the fiscal year's IB (services/opening_balance.py)
        # plus the year's movements. Result accounts: the year's only.
        opening = OpeningBalanceService().balances(fiscal_year_id)
        movements = OpeningBalanceRepository.movements(fiscal_year_id)

        accounts = {}
        for row in db.execute(
            "SELECT code, name, account_type FROM accounts ORDER BY code"
        ).fetchall():
            code = row["code"]
            balance = movements.get(code, 0)
            if is_balance_account(code):
                balance += opening.get(code, 0)
            accounts[code] = {
                "id": code,
                "name": row["name"],
                "balance": balance,  # In öre
                "account_type": row["account_type"],
            }

        return accounts

    def calculate_sru_fields(self, fiscal_year_id: str) -> SRUDeclaration:
        """
        Calculate all SRU field values for a fiscal year.

        This is the main calculation method that aggregates account balances
        into the SRU fields needed for INK2 declaration.
        """
        self.errors = []
        self.warnings = []

        db = get_db()

        # Get fiscal year info
        fiscal_year = db.execute(
            "SELECT * FROM fiscal_years WHERE id = ?", (fiscal_year_id,)
        ).fetchone()

        if not fiscal_year:
            raise ValueError(f"Fiscal year {fiscal_year_id} not found")

        # Get company info
        company = self._get_company_info(db)

        if not company:
            raise ValueError("Company info not found")

        # Get SRU mappings
        sru_mappings = self.get_sru_mappings(fiscal_year_id)

        # Get account balances
        account_balances = self.calculate_account_balances(fiscal_year_id)

        # Calculate SRU fields
        fields = {}

        # Group accounts by the mapping they carry, then resolve alternatives
        # such as "7416/7520". BAS splits those rows on the sign of the *net*
        # balance of the whole row ("Om netto +/-"), not account by account, so
        # the grouping has to happen before the field is picked.
        mapped_balances: Dict[str, List[Dict]] = {}
        unmapped_accounts: List[str] = []
        for account_code, account_data in account_balances.items():
            mapping = sru_mappings.get(account_code)
            if not mapping:
                # 899x carries the year's result, which is derived from the
                # result rows below rather than mapped, so it is not missing.
                if account_data["balance"] != 0 and not _is_derived_result_account(
                    account_code
                ):
                    unmapped_accounts.append(account_code)
                continue
            mapped_balances.setdefault(mapping, []).append(
                {
                    "code": account_code,
                    "name": account_data["name"],
                    "balance": account_data["balance"],
                }
            )

        field_balances: Dict[str, List[Dict]] = {}
        for mapping, accounts in mapped_balances.items():
            net_balance = sum(a["balance"] for a in accounts)
            sru_field = self._resolve_sru_field(mapping, net_balance)
            field_balances.setdefault(sru_field, []).extend(accounts)

        if unmapped_accounts:
            self.warnings.append(
                "Konton med saldo saknar SRU-fält och ingår inte i deklarationen: "
                + ", ".join(sorted(unmapped_accounts))
            )

        # Create SRU field values
        field_descriptions = self._get_field_descriptions()

        for sru_field, accounts in field_balances.items():
            total_balance = sum(a["balance"] for a in accounts)
            value_sek = self._to_sru_value(sru_field, total_balance)
            source_account_values = []
            for account in accounts:
                account_value = self._to_sru_value(sru_field, account["balance"])
                if account_value != 0:
                    source_account_values.append(
                        {
                            "account": account["code"],
                            "name": account["name"],
                            "value": account_value,
                        }
                    )

            fields[sru_field] = SRUFieldValue(
                field_number=sru_field,
                description=field_descriptions.get(sru_field, "Okänd fältkod"),
                value=value_sek,
                source_accounts=[a["account"] for a in source_account_values],
                source_account_values=source_account_values,
            )

        # Calculate derived fields
        self._calculate_derived_fields(fields)
        from services.tax_adjustments import TaxAdjustmentService

        tax = TaxAdjustmentService().calculate(fiscal_year_id)
        self.tax_calculation = tax
        self.warnings.extend(tax.warnings)
        self._calculate_ink2s_fields(fields, tax.adjustments)

        # Validate balance sheet
        self._validate_balance_sheet(field_balances, account_balances)

        from services.bokslut_inputs import BokslutInputsService

        upplysningar = (
            BokslutInputsService().current(fiscal_year_id).get("ink2s.upplysningar", {})
        )

        return SRUDeclaration(
            fiscal_year_id=fiscal_year_id,
            company_org_number=company["org_number"].replace("-", ""),
            company_name=company["name"],
            fiscal_year_start=fiscal_year["start_date"].replace("-", ""),
            fiscal_year_end=fiscal_year["end_date"].replace("-", ""),
            fields=fields,
            contact_name=company.get("contact_name"),
            address=company.get("address"),
            postnr=company.get("postnr"),
            postort=company.get("postort"),
            email=company.get("email"),
            phone=company.get("phone"),
            uppdragstagare=bool(upplysningar.get("uppdragstagare", False)),
            revision=bool(upplysningar.get("revision", False)),
        )

    def _get_company_info(self, db) -> Optional[Dict[str, Any]]:
        """Get company info from the key/value table, with legacy row fallback."""
        try:
            rows = db.execute("SELECT key, value FROM company_info").fetchall()
            if rows:
                values = {row["key"]: row["value"] for row in rows}
                return {
                    "org_number": values.get("org_number") or "0000000000",
                    "name": values.get("name") or "Test Company",
                    "contact_name": values.get("contact_name"),
                    "address": values.get("address"),
                    "postnr": values.get("postnr"),
                    "postort": values.get("postort"),
                    "email": values.get("email"),
                    "phone": values.get("phone"),
                }
        except Exception:
            pass

        try:
            row = db.execute(
                "SELECT * FROM company_info ORDER BY id LIMIT 1"
            ).fetchone()
        except Exception:
            return {
                "org_number": "0000000000",
                "name": "Test Company",
            }

        if not row:
            return {
                "org_number": "0000000000",
                "name": "Test Company",
            }

        return {
            "org_number": row["org_number"],
            "name": row["name"],
        }

    def _sru_signed_ore(self, sru_field: str, balance_ore: int) -> int:
        """Apply the SRU sign convention to a debit-positive öre balance.

        Credit-balance boxes (equity, liabilities, income) are negated so the
        form shows the positive figure it asks for; cost boxes are reported as
        absolute amounts. Nothing is rounded here - callers that need whole
        kronor divide afterwards, so this can also be summed at full öre
        precision when the rounding must not creep in.
        """
        value = balance_ore
        if sru_field in CREDIT_BALANCE_FIELDS:
            value = -value
        if sru_field in ALWAYS_POSITIVE_FIELDS:
            value = abs(value)
        return value

    def _to_sru_value(self, sru_field: str, balance_ore: int) -> int:
        """Convert internal debit-positive öre balance to a whole-krona SRU value.

        Skatteverket wants whole kronor rounded the ordinary way (0,50 upward),
        not truncated: truncating understated every figure by up to a krona and
        pushed the balance sheet's two sides apart. Öre are exact here, so the
        rounding is done in ``Decimal`` to avoid binary-float tie surprises.
        """
        signed_ore = self._sru_signed_ore(sru_field, balance_ore)
        krona = (Decimal(signed_ore) / 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return int(krona)

    def _resolve_sru_field(self, sru_field: str, balance_ore: int) -> str:
        """Resolve imported slash alternatives like 7416/7520 for one account."""
        if "/" not in sru_field:
            return sru_field

        first, second = [part.strip() for part in sru_field.split("/", 1)]
        first_value = self._to_sru_value(first, balance_ore)
        return first if first_value >= 0 else second

    def _calculate_derived_fields(self, fields: Dict[str, SRUFieldValue]):
        """Calculate derived/summary fields from base fields."""
        income_fields = list(INCOME_FIELDS)
        expense_fields = list(EXPENSE_FIELDS)

        result = sum(fields[f].value for f in income_fields if f in fields) - sum(
            fields[f].value for f in expense_fields if f in fields
        )
        if result > 0 and "7450" not in fields:
            fields["7450"] = SRUFieldValue(
                field_number="7450",
                description="Årets resultat, vinst",
                value=result,
                source_accounts=[
                    f for f in income_fields + expense_fields if f in fields
                ],
                source_account_values=self._derived_source_account_values(
                    fields, income_fields, expense_fields
                ),
            )
        elif result < 0 and "7550" not in fields:
            fields["7550"] = SRUFieldValue(
                field_number="7550",
                description="Årets resultat, förlust",
                value=abs(result),
                source_accounts=[
                    f for f in income_fields + expense_fields if f in fields
                ],
                source_account_values=self._derived_source_account_values(
                    fields, income_fields, expense_fields
                ),
            )

    def _derived_source_account_values(
        self,
        fields: Dict[str, SRUFieldValue],
        positive_fields: List[str],
        negative_fields: List[str],
    ) -> List[Dict[str, int | str]]:
        """Carry account-level contributors into derived result fields."""
        values: List[Dict[str, int | str]] = []
        for field_number in positive_fields:
            field = fields.get(field_number)
            for account in field.source_account_values or [] if field else []:
                values.append(account)
        for field_number in negative_fields:
            field = fields.get(field_number)
            for account in field.source_account_values or [] if field else []:
                values.append(
                    {
                        "account": account["account"],
                        "name": account.get("name", ""),
                        "value": -int(account["value"]),
                    }
                )
        return values

    def _calculate_ink2s_fields(
        self,
        fields: Dict[str, SRUFieldValue],
        adjustments: Optional[Dict[str, "Justering"]] = None,
    ):
        """Calculate INK2S from INK2R and the tax adjustments.

        4.1 and 4.3a come straight from INK2R (3.26 and 3.25). 4.3c, 4.5c,
        4.6a and 4.6d come from ``services/tax_adjustments.py`` -- the
        ledger's non-deductible and tax-exempt accounts, the schablonintäkt
        on the opening periodiseringsfonder and the uppräkning on reversed
        ones -- each possibly replaced by an amount a human has stated.
        4.15/4.16 is the sum.
        """
        descriptions = self._get_field_descriptions()
        adjustments = adjustments or {}

        def put(code: str, value: int, sources: List[Dict[str, int | str]]):
            if value != 0:
                fields[code] = SRUFieldValue(
                    field_number=code,
                    description=descriptions.get(code, "Okänd fältkod"),
                    value=value,
                    source_accounts=[str(s["account"]) for s in sources],
                    source_account_values=sources,
                )

        profit = fields["7450"].value if "7450" in fields else 0
        loss = fields["7550"].value if "7550" in fields else 0
        tax = fields["7528"].value if "7528" in fields else 0
        put(
            "7650",
            profit,
            list(fields["7450"].source_account_values or []) if profit else [],
        )
        if loss:
            put("7750", loss, list(fields["7550"].source_account_values or []))
        put(
            "7651", tax, list(fields["7528"].source_account_values or []) if tax else []
        )

        plus = 0
        minus = 0
        for code, adj in adjustments.items():
            sources = [
                {
                    "account": s["account"],
                    "name": s.get("name", ""),
                    "value": int(s["value"]),
                }
                for s in adj.sources
            ]
            if adj.override is not None:
                sources = [
                    {"account": code, "name": "Angivet belopp", "value": adj.value}
                ]
            put(code, adj.value, sources)
            if code in INK2S_MINUS_FIELDS:
                minus += adj.value
            else:
                plus += adj.value

        taxable = profit - loss + tax + plus - minus
        total_sources: List[Dict[str, int | str]] = []
        for code in ["7650", "7651", *adjustments.keys()]:
            f = fields.get(code)
            if not f:
                continue
            sign = -1 if code in INK2S_MINUS_FIELDS else 1
            for s in f.source_account_values or []:
                total_sources.append(
                    {
                        "account": s["account"],
                        "name": s.get("name", ""),
                        "value": int(s["value"]) * sign,
                    }
                )
        if "7750" in fields:
            for s in fields["7750"].source_account_values or []:
                total_sources.append(
                    {
                        "account": s["account"],
                        "name": s.get("name", ""),
                        "value": -int(s["value"]),
                    }
                )
        if taxable >= 0:
            put("7670", taxable, total_sources)
        else:
            put("7770", -taxable, total_sources)

    def _validate_balance_sheet(
        self,
        field_balances: Dict[str, List[Dict]],
        account_balances: Dict[str, Dict],
    ):
        """Warn when INK2R's assets do not match equity plus liabilities.

        Worked out in öre, straight from the ledger balances, before any box is
        rounded to whole kronor. Double-entry then guarantees the check is
        exact: assets minus equity and liabilities is either zero (once the
        year's result has been closed to 2099) or exactly the year's result
        (until it has been). Rounding each box on its own would let the two
        sides drift a krona or two apart on a ledger that actually balances, so
        the comparison deliberately stays at öre precision.

        Any real difference means an account with a balance is mapped to a
        field that lies on neither side of the balance sheet nor in the result
        - a hole in the coupling table. A completely unmapped account is
        reported separately.
        """
        asset_fields = set(BALANCE_ASSET_FIELDS)
        equity_liability_fields = set(BALANCE_EQUITY_LIABILITY_FIELDS)
        income_fields = set(INCOME_FIELDS)
        expense_fields = set(EXPENSE_FIELDS)

        def side_total(wanted) -> int:
            return sum(
                self._sru_signed_ore(sru_field, sum(a["balance"] for a in accounts))
                for sru_field, accounts in field_balances.items()
                if sru_field in wanted
            )

        assets = side_total(asset_fields)
        equity_and_liabilities = side_total(equity_liability_fields)
        closed_result = -sum(
            data["balance"]
            for code, data in account_balances.items()
            if _is_derived_result_account(code)
        )
        result = side_total(income_fields) - side_total(expense_fields) + closed_result
        difference = assets - equity_and_liabilities

        if difference in (0, result):
            return

        self.warnings.append(
            "BALANSRÄKNINGEN STÄMMER INTE: tillgångar "
            f"({round(assets / 100)}) - eget kapital och skulder "
            f"({round(equity_and_liabilities / 100)}) = {difference / 100:.2f} SEK, "
            f"vilket varken är noll eller årets resultat ({result / 100:.2f} SEK)"
        )

    def _get_field_descriptions(self) -> Dict[str, str]:
        """Get human-readable descriptions for SRU fields."""
        return field_labels()

    def generate_info_sru(self, declaration: SRUDeclaration) -> str:
        """
        Generate INFO.SRU file content.

        This file contains metadata about the declaration.
        """

        def optional_attr(name: str) -> Optional[str]:
            value = getattr(declaration, name, None)
            return value if isinstance(value, str) and value else None

        lines = [
            "#DATABESKRIVNING_START",
            "#PRODUKT SRU",
            f"#SKAPAD {datetime.now().strftime('%Y%m%d %H%M%S')}",
            "#PROGRAM BOKAI 1.0",
            "#FILNAMN BLANKETTER.SRU",
            "#DATABESKRIVNING_SLUT",
            "#MEDIELEV_START",
            f"#ORGNR {declaration.company_org_number}",
            f"#NAMN {optional_attr('contact_name') or declaration.company_name}",
        ]

        optional_lines = [
            ("#ADRESS", optional_attr("address")),
            ("#POSTNR", optional_attr("postnr")),
            ("#POSTORT", optional_attr("postort")),
            ("#EMAIL", optional_attr("email")),
            ("#TELEFON", optional_attr("phone")),
        ]
        lines.extend(f"{prefix} {value}" for prefix, value in optional_lines if value)
        lines.append("#MEDIELEV_SLUT")

        return "\r\n".join(lines) + "\r\n"

    def generate_blanketter_sru(self, declaration: SRUDeclaration) -> str:
        """
        Generate BLANKETTER.SRU file content.

        The file holds INK2R and INK2S, which is the whole of what SRU accepts
        for an INK2 filing. Page 1 of INK2 — the main form with 1.1 Överskott
        av näringsverksamhet and the property and payroll-tax bases — has no
        blankett in the SRU specification: it is signed and filed in
        Skatteverket's e-tjänst, which pre-fills 1.1/1.2 from 4.15/4.16 in the
        INK2S below. The figures to check there are on the INK2 tab of the
        declaration page. See SKV 269, "Deklarationsblanketter": when the rest
        is filed electronically, page 1 of INK2 is filed separately.
        """
        lines = []
        timestamp = datetime.now().strftime("%Y%m%d %H%M%S")
        version = blankett_period(declaration.fiscal_year_end)

        # INK2R - Räkenskapsschema
        lines.extend(
            [
                f"#BLANKETT INK2R-{version}",
                f"#IDENTITET {declaration.company_org_number} {timestamp}",
                "#SYSTEMINFO BOKAI 1.0",
            ]
        )

        # Add fiscal year dates
        lines.append(f"#UPPGIFT 7011 {declaration.fiscal_year_start}")
        lines.append(f"#UPPGIFT 7012 {declaration.fiscal_year_end}")

        # Add all field values (sorted by field number)
        for field_number in sorted(declaration.fields.keys()):
            if field_number in INK2S_DERIVED_FIELDS:
                continue
            field = declaration.fields[field_number]
            if field.value != 0 or field_number in INK2R_ZERO_EXPORT_FIELDS:
                lines.append(f"#UPPGIFT {field_number} {field.value}")

        lines.append("#BLANKETTSLUT")

        # INK2S - Särskild blankett (Balansräkning)
        lines.extend(
            [
                f"#BLANKETT INK2S-{version}",
                f"#IDENTITET {declaration.company_org_number} {timestamp}",
                "#SYSTEMINFO BOKAI 1.0",
            ]
        )

        # Add balance sheet fields to INK2S
        for field_number in ["7011", "7012"]:
            lines.append(
                f"#UPPGIFT {field_number} "
                f"{declaration.fiscal_year_start if field_number == '7011' else declaration.fiscal_year_end}"
            )

        for field_number in INK2S_EXPORT_ORDER:
            if field_number in declaration.fields:
                field = declaration.fields[field_number]
                if field.value != 0:
                    lines.append(f"#UPPGIFT {field_number} {field.value}")

        # Upplysningar: uppdragstagare har biträtt (8040 ja / 8041 nej) och
        # årsredovisningen har reviderats (8044 ja / 8045 nej).
        lines.append(
            "#UPPGIFT 8040 X" if declaration.uppdragstagare else "#UPPGIFT 8041 X"
        )
        lines.append("#UPPGIFT 8044 X" if declaration.revision else "#UPPGIFT 8045 X")

        lines.append("#BLANKETTSLUT")
        lines.append("#FIL_SLUT")

        return "\r\n".join(lines) + "\r\n"

    def export_sru_zip(
        self, fiscal_year_id: str
    ) -> Tuple[bytes, str, List[str], List[str]]:
        """
        Generate complete SRU export as ZIP file.

        Returns: (zip_bytes, filename, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        try:
            # Calculate declaration data
            declaration = self.calculate_sru_fields(fiscal_year_id)

            # Generate files
            info_sru = self.generate_info_sru(declaration)
            blanketter_sru = self.generate_blanketter_sru(declaration)

            # Create ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # Skatteverket reads SRU files as ISO 8859-1, without BOM.
                zip_file.writestr("INFO.SRU", encode_sru(info_sru))
                zip_file.writestr("BLANKETTER.SRU", encode_sru(blanketter_sru))

            zip_bytes = zip_buffer.getvalue()

            # Generate filename
            safe_company_name = (
                "".join(
                    c
                    for c in declaration.company_name
                    if c.isalnum() or c in (" ", "-", "_")
                )
                .strip()
                .replace(" ", "_")
            )
            year = declaration.fiscal_year_end[:4]
            filename = f"{safe_company_name}_{year}_INK2_SRU.zip"

            return zip_bytes, filename, self.errors, self.warnings

        except Exception as e:
            self.errors.append(f"Export failed: {str(e)}")
            return b"", "", self.errors, self.warnings


def encode_sru(text: str) -> bytes:
    """SRU files are ISO 8859-1. Characters outside it become '?'."""
    return text.encode("iso-8859-1", errors="replace")


# Convenience function for API usage
def export_sru_for_fiscal_year(
    fiscal_year_id: str,
) -> Tuple[bytes, str, List[str], List[str]]:
    """
    Export SRU files for a fiscal year.

    Returns: (zip_bytes, filename, errors, warnings)
    """
    service = SRUExportService()
    return service.export_sru_zip(fiscal_year_id)
