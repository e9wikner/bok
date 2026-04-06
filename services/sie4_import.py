"""
SIE4 import functionality for Swedish accounting data exchange.

SIE (Standard Import/Export) format version 4 is the standard for
exchanging accounting data between Swedish accounting software.

Documentation: https://www.sie.se/sie4_format.pdf
"""

import re
from datetime import date
from typing import List, Dict, Optional
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class SIEVoucherRow:
    """Single row in a SIE voucher."""

    account: str
    amount: int  # In öre (positive = debit, negative = credit in SIE)
    description: Optional[str] = None
    quantity: Optional[Decimal] = None


@dataclass
class SIEVoucher:
    """A voucher (verifikat) from SIE file."""

    series: str
    number: int
    date: date
    description: str
    rows: List[SIEVoucherRow]
    signature: Optional[str] = None


@dataclass
class SIEAccount:
    """Account definition from SIE file."""

    code: str
    name: str
    type: str  # 1=asset, 2=liability, 3=equity, 4=revenue, 5=expense
    vat_code: Optional[str] = None


@dataclass
class SIECompany:
    """Company information from SIE file."""

    org_number: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


@dataclass
class SIEData:
    """Complete parsed SIE file data."""

    format_version: str  # "4" for SIE4
    program: Optional[str] = None
    company: Optional[SIECompany] = None
    accounts: List[SIEAccount] = None
    vouchers: List[SIEVoucher] = None
    fiscal_year_start: Optional[date] = None
    fiscal_year_end: Optional[date] = None
    # Opening balances: {account_code: amount_in_öre}
    # Positive = debit, negative = credit (SIE convention)
    opening_balances: Dict[str, int] = None

    def __post_init__(self):
        if self.accounts is None:
            self.accounts = []
        if self.vouchers is None:
            self.vouchers = []
        if self.opening_balances is None:
            self.opening_balances = {}


class SIE4Parser:
    """Parse SIE4 format files."""

    def __init__(self):
        self.errors: List[str] = []

    def parse_file(self, filepath: str) -> SIEData:
        """Parse a SIE4 file from disk."""
        with open(filepath, "rb") as f:
            raw = f.read()
        encoding = self._detect_encoding(raw)
        return self.parse_content(raw.decode(encoding))

    @staticmethod
    def _detect_encoding(raw: bytes) -> str:
        """Detect SIE file encoding from #FORMAT header."""
        if b"#FORMAT PC8" in raw or b"#FORMAT IBMPC" in raw:
            return "cp437"
        for enc in ["utf-8", "windows-1252"]:
            try:
                raw.decode(enc)
                return enc
            except UnicodeDecodeError:
                continue
        return "cp437"

    def parse_content(self, content: str) -> SIEData:
        """Parse SIE4 content from string."""
        data = SIEData(format_version="4")
        lines = content.split("\n")

        current_voucher: Optional[Dict] = None

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("{"):
                continue

            try:
                # Parse company info
                if line.startswith("#FNAMN "):
                    if not data.company:
                        data.company = SIECompany()
                    data.company.name = self._parse_string(line[7:])

                elif line.startswith("#FORGN "):
                    if not data.company:
                        data.company = SIECompany()
                    data.company.org_number = self._parse_org_number(line[7:])

                elif line.startswith("#FADRESS "):
                    if not data.company:
                        data.company = SIECompany()
                    parts = self._parse_array(line[8:])
                    data.company.address = ", ".join(parts[:3])
                    if len(parts) > 3:
                        data.company.phone = parts[3]

                # Parse format
                elif line.startswith("#FORMAT "):
                    data.format_version = self._parse_string(line[8:])

                elif line.startswith("#PROGRAM "):
                    data.program = self._parse_string(line[9:])

                # Parse fiscal year
                # Format: #RAR year_index start_date end_date
                # year_index: 0=current year, -1=previous year, etc.
                elif line.startswith("#RAR "):
                    parts = line[5:].split()
                    if len(parts) >= 3:
                        try:
                            year_index = int(parts[0])
                            # Only use year index 0 (current fiscal year)
                            if year_index == 0:
                                data.fiscal_year_start = self._parse_date(parts[1])
                                data.fiscal_year_end = self._parse_date(parts[2])
                        except ValueError:
                            pass

                # Parse account
                elif line.startswith("#KONTO "):
                    account = self._parse_account(line[7:])
                    if account:
                        data.accounts.append(account)

                # Parse opening balance (IB - ingående balans)
                # Format: #IB year account amount
                # year=0 for current fiscal year, -1 for previous, etc.
                elif line.startswith("#IB "):
                    ib = self._parse_opening_balance(line[4:])
                    if ib:
                        # Only store IB for current year (year index 0)
                        if ib.get("year_index") == 0:
                            data.opening_balances[ib["account"]] = ib["amount"]

                # Parse voucher start
                elif line.startswith("#VER "):
                    # Save previous voucher if exists
                    if current_voucher:
                        voucher = self._build_voucher(current_voucher)
                        if voucher:
                            data.vouchers.append(voucher)

                    current_voucher = self._parse_voucher_header(line[5:])

                # Parse voucher row
                elif line.startswith("#TRANS ") and current_voucher:
                    row = self._parse_transaction(line[7:])
                    if row:
                        current_voucher["rows"].append(row)

                # Parse voucher signature
                elif line.startswith("#SIGN ") and current_voucher:
                    current_voucher["signature"] = self._parse_string(line[6:])

            except Exception as e:
                self.errors.append(f"Line {line_num}: {str(e)}")

        # Save last voucher
        if current_voucher:
            voucher = self._build_voucher(current_voucher)
            if voucher:
                data.vouchers.append(voucher)

        return data

    def _parse_string(self, value: str) -> str:
        """Parse a quoted or unquoted string."""
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1].replace('""', '"')
        return value

    def _parse_array(self, value: str) -> List[str]:
        """Parse array of strings."""
        parts = []
        current = ""
        in_quotes = False

        for char in value:
            if char == '"':
                in_quotes = not in_quotes
            elif char == " " and not in_quotes:
                if current:
                    parts.append(self._parse_string(current))
                    current = ""
            else:
                current += char

        if current:
            parts.append(self._parse_string(current))

        return parts

    def _parse_org_number(self, value: str) -> str:
        """Parse Swedish organization number."""
        value = self._parse_string(value).replace("-", "").replace(" ", "")
        # Format: XXXXXX-XXXX
        if len(value) == 10:
            return f"{value[:6]}-{value[6:]}"
        return value

    def _parse_date(self, value: str) -> date:
        """Parse SIE date format (YYYYMMDD)."""
        value = self._parse_string(value)
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))

    def _parse_amount(self, value: str) -> int:
        """Parse amount from SIE format (with comma as decimal separator)."""
        value = self._parse_string(value).replace(",", ".")
        # Convert to öre (multiply by 100)
        amount_decimal = Decimal(value)
        return int(amount_decimal * 100)

    def _parse_account(self, line: str) -> Optional[SIEAccount]:
        """Parse account definition."""
        parts = line.split()
        if not parts:
            return None

        code = self._parse_string(parts[0])
        name = self._parse_string(" ".join(parts[1:])) if len(parts) > 1 else ""

        return SIEAccount(
            code=code,
            name=name,
            type="1",  # Default to asset
        )

    def _parse_opening_balance(self, line: str) -> Optional[Dict]:
        """Parse opening balance line (#IB).

        Format: #IB year_index account amount
        year_index: 0=current year, -1=previous year, etc.
        amount: positive=debit, negative=credit (SIE convention)
        """
        parts = line.split()
        if len(parts) < 3:
            return None

        try:
            year_index = int(parts[0])
            account = self._parse_string(parts[1])
            amount = self._parse_amount(parts[2])
            return {
                "year_index": year_index,
                "account": account,
                "amount": amount,  # In öre, positive=debit, negative=credit
            }
        except (ValueError, IndexError):
            return None

    def _parse_voucher_header(self, line: str) -> Dict:
        """Parse voucher header line (#VER)."""
        parts = self._parse_array(line)

        series = parts[0] if len(parts) > 0 else "A"
        number = 0
        date_val = date.today()
        description = ""

        if len(parts) > 1:
            try:
                number = int(parts[1])
            except ValueError:
                pass

        if len(parts) > 2:
            try:
                date_val = self._parse_date(parts[2])
            except:
                pass

        if len(parts) > 3:
            description = parts[3]

        return {
            "series": series,
            "number": number,
            "date": date_val,
            "description": description,
            "rows": [],
            "signature": None,
        }

    def _parse_transaction(self, line: str) -> Optional[SIEVoucherRow]:
        """Parse transaction row (#TRANS).

        SIE4-format: #TRANS konto objektlista belopp datum text kvantitet sign
        Objektlistan är {} för tom, eller {dimension värde} för kostnadsbärare.
        """
        # Hantera objektlistan {} speciellt - ta bort den innan parsing
        # Regex: ersätt {} eller {innehåll} med ett platshållarvärde
        # Hitta och ta bort objektlistan (andra fältet efter konto)
        cleaned = re.sub(r"\{[^}]*\}", "__OBJ__", line, count=1)
        parts = self._parse_array(cleaned)

        if len(parts) < 2:
            return None

        account = self._parse_string(parts[0])

        # Hitta beloppet - det är fältet efter objektlistan
        amount_idx = 1
        if parts[amount_idx] == "__OBJ__":
            amount_idx = 2

        if amount_idx >= len(parts):
            return None

        try:
            # SIE uses negative for credit, positive for debit
            amount = self._parse_amount(parts[amount_idx])
        except:
            return None

        # Beskrivning är fält 4 (efter datum) relativt objektlistan
        description = None
        desc_idx = amount_idx + 2  # belopp + datum + text
        if desc_idx < len(parts) and parts[desc_idx] != "__OBJ__":
            description = parts[desc_idx]

        # Kvantitet
        quantity = None
        qty_idx = amount_idx + 3
        if qty_idx < len(parts) and parts[qty_idx] != "__OBJ__":
            try:
                quantity = Decimal(self._parse_string(parts[qty_idx]).replace(",", "."))
            except:
                pass

        return SIEVoucherRow(
            account=account, amount=amount, description=description, quantity=quantity
        )

    def _build_voucher(self, data: Dict) -> Optional[SIEVoucher]:
        """Build SIEVoucher from parsed data."""
        if not data["rows"]:
            return None

        return SIEVoucher(
            series=data["series"],
            number=data["number"],
            date=data["date"],
            description=data["description"],
            rows=data["rows"],
            signature=data.get("signature"),
        )


class SIE4Importer:
    """Import SIE4 data into the bookkeeping system."""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.parser = SIE4Parser()
        self.errors: List[str] = []
        self.imported: Dict[str, int] = {
            "accounts": 0,
            "vouchers": 0,
            "periods_created": 0,
        }

    def import_file(self, filepath: str, fiscal_year_id: Optional[str] = None) -> bool:
        """Import a SIE4 file."""
        try:
            data = self.parser.parse_file(filepath)
            return self._import_data(data, fiscal_year_id)
        except Exception as e:
            self.errors.append(f"Failed to parse file: {str(e)}")
            return False

    def import_content(
        self, content: str, fiscal_year_id: Optional[str] = None
    ) -> bool:
        """Import SIE4 content from string."""
        try:
            data = self.parser.parse_content(content)
            return self._import_data(data, fiscal_year_id)
        except Exception as e:
            self.errors.append(f"Failed to parse content: {str(e)}")
            return False

    def _import_data(self, data: SIEData, fiscal_year_id: Optional[str] = None) -> bool:
        """Import parsed SIE data."""
        import requests

        success = True

        # Import accounts
        for account in data.accounts:
            if self._import_account(account):
                self.imported["accounts"] += 1

        # Import opening balances as a special voucher
        if data.opening_balances:
            if self._import_opening_balances(data, fiscal_year_id):
                self.imported["vouchers"] += 1

        # Import vouchers
        for voucher in data.vouchers:
            if self._import_voucher(voucher, fiscal_year_id):
                self.imported["vouchers"] += 1

        return success

    def _import_account(self, account: SIEAccount) -> bool:
        """Import a single account via API."""
        import requests

        # Check if account exists
        resp = requests.get(
            f"{self.api_url}/api/v1/accounts/{account.code}", headers=self.headers
        )

        if resp.status_code == 200:
            # Account exists, skip
            return True

        # Create account
        account_data = {
            "code": account.code,
            "name": account.name,
            "account_type": self._map_account_type(account.type),
        }

        resp = requests.post(
            f"{self.api_url}/api/v1/accounts", headers=self.headers, json=account_data
        )

        if resp.status_code == 201:
            return True
        else:
            self.errors.append(f"Failed to create account {account.code}: {resp.text}")
            return False

    def _import_voucher(
        self, voucher: SIEVoucher, fiscal_year_id: Optional[str] = None
    ) -> bool:
        """Import a single voucher via API."""
        import requests

        # Find or create period for this date
        period_id = self._get_or_create_period(voucher.date, fiscal_year_id)
        if not period_id:
            self.errors.append(f"No period found for date {voucher.date}")
            return False

        # Convert SIE rows to API format
        rows = []
        for row in voucher.rows:
            # SIE uses positive for debit, negative for credit
            if row.amount >= 0:
                rows.append(
                    {
                        "account": row.account,
                        "debit": row.amount,
                        "credit": 0,
                        "description": row.description or "",
                    }
                )
            else:
                rows.append(
                    {
                        "account": row.account,
                        "debit": 0,
                        "credit": abs(row.amount),
                        "description": row.description or "",
                    }
                )

        voucher_data = {
            "series": voucher.series,
            "number": voucher.number,
            "date": voucher.date.isoformat(),
            "period_id": period_id,
            "description": voucher.description,
            "rows": rows,
            "auto_post": True,
        }

        resp = requests.post(
            f"{self.api_url}/api/v1/vouchers", headers=self.headers, json=voucher_data
        )

        if resp.status_code == 201:
            return True
        else:
            self.errors.append(
                f"Failed to create voucher {voucher.series}{voucher.number}: {resp.text}"
            )
            return False

    def _import_opening_balances(
        self, data: SIEData, fiscal_year_id: Optional[str] = None
    ) -> bool:
        """Import opening balances (IB) as a special opening balance voucher.

        Creates a voucher on the first day of the fiscal year with rows
        representing the opening balances from the SIE file.
        """
        import requests

        if not data.opening_balances or not data.fiscal_year_start:
            return False

        # Find period for the first day of fiscal year
        period_id = self._get_or_create_period(data.fiscal_year_start, fiscal_year_id)
        if not period_id:
            self.errors.append(
                f"No period found for opening balance date {data.fiscal_year_start}"
            )
            return False

        # Build rows from opening balances
        rows = []
        for account, amount in data.opening_balances.items():
            if amount == 0:
                continue
            # SIE: positive = debit, negative = credit
            if amount >= 0:
                rows.append(
                    {
                        "account": account,
                        "debit": amount,
                        "credit": 0,
                        "description": "Ingående balans",
                    }
                )
            else:
                rows.append(
                    {
                        "account": account,
                        "debit": 0,
                        "credit": abs(amount),
                        "description": "Ingående balans",
                    }
                )

        if not rows:
            return False

        # Opening balance voucher uses series "A" and number 0
        # (or find the next available number)
        voucher_data = {
            "series": "A",
            "date": data.fiscal_year_start.isoformat(),
            "period_id": period_id,
            "description": "Ingående balans (IB) från SIE4-import",
            "rows": rows,
            "auto_post": True,
        }

        resp = requests.post(
            f"{self.api_url}/api/v1/vouchers", headers=self.headers, json=voucher_data
        )

        if resp.status_code == 201:
            return True
        else:
            self.errors.append(f"Failed to create opening balance voucher: {resp.text}")
            return False

    def _get_or_create_period(
        self, voucher_date: date, fiscal_year_id: Optional[str] = None
    ) -> Optional[str]:
        """Get or create period for a specific date."""
        import requests

        # Find existing period
        year = voucher_date.year
        month = voucher_date.month

        # Try to find fiscal year first
        if not fiscal_year_id:
            resp = requests.get(
                f"{self.api_url}/api/v1/fiscal-years", headers=self.headers
            )
            if resp.status_code == 200:
                fiscal_years = resp.json().get("fiscal_years", [])
                for fy in fiscal_years:
                    start = date.fromisoformat(fy["start_date"])
                    end = date.fromisoformat(fy["end_date"])
                    if start <= voucher_date <= end:
                        fiscal_year_id = fy["id"]
                        break

        if not fiscal_year_id:
            return None

        # List periods for this fiscal year
        resp = requests.get(
            f"{self.api_url}/api/v1/periods",
            headers=self.headers,
            params={"fiscal_year_id": fiscal_year_id},
        )

        if resp.status_code == 200:
            for period in resp.json().get("periods", []):
                if period["year"] == year and period["month"] == month:
                    return period["id"]

        return None

    def _map_account_type(self, sie_type: str) -> str:
        """Map SIE account type to internal type."""
        mapping = {
            "1": "asset",
            "2": "liability",
            "3": "equity",
            "4": "revenue",
            "5": "expense",
        }
        return mapping.get(sie_type, "asset")


def create_sample_sie4() -> str:
    """Create a sample SIE4 file for testing."""
    return """#FLAGGA 0
#FORMAT PC8
#GEN "Bokföringssystem" 20260115
#PROGRAM "Bokföringssystem" 1.0
#FNAMN "Demo AB"
#FORGN 5591234567
#ADRESS "Stefan Wikner" "Storgatan 1" "11122 Stockholm" "08-123456"
#RAR 0 20260101 20261231
#KPTYP EUBAS97

#KONTO 1930 "Företagskonto"
#KONTO 2013 "Eget uttag"
#KONTO 2081 "Aktieägartillskott"
#KONTO 2440 "Leverantörsskulder"
#KONTO 2610 "Utgående moms 25%"
#KONTO 2640 "Ingående moms"
#KONTO 3010 "Försäljning tjänster"
#KONTO 5010 "Lokalhyra"
#KONTO 7010 "Lön tjänstemän"

#VER A 1 20260115 "Startkapital"
{
#TRANS 1930 {} 200000.00 20260115 "Insättning"
#TRANS 2081 {} -200000.00 20260115 "Aktieägartillskott"
}

#VER A 2 20260201 "Hyra februari"
{
#TRANS 5010 {} 10000.00 20260201 "Lokalhyra"
#TRANS 2640 {} 2500.00 20260201 "Moms 25%"
#TRANS 2440 {} -12500.00 20260201 "Leverantörsskuld"
}

#VER A 3 20260215 "Försäljning"
{
#TRANS 1510 {} 125000.00 20260215 "Kundfordran"
#TRANS 3010 {} -100000.00 20260215 "Försäljning"
#TRANS 2610 {} -25000.00 20260215 "Utgående moms"
}
#SRU 1930 1940
#SRU 3010 3610
"""


if __name__ == "__main__":
    # Test parsing
    sample = create_sample_sie4()
    parser = SIE4Parser()
    data = parser.parse_content(sample)

    print("Parsed SIE4 data:")
    print(f"  Company: {data.company.name if data.company else 'N/A'}")
    print(f"  Org number: {data.company.org_number if data.company else 'N/A'}")
    print(f"  Accounts: {len(data.accounts)}")
    print(f"  Vouchers: {len(data.vouchers)}")
    print(f"  Fiscal year: {data.fiscal_year_start} - {data.fiscal_year_end}")

    for voucher in data.vouchers:
        print(f"\n  {voucher.series}{voucher.number}: {voucher.description}")
        for row in voucher.rows:
            print(f"    {row.account}: {row.amount / 100:,.2f} kr")
