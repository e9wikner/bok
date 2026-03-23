"""
SIE4 export functionality for Swedish accounting data exchange.

Genererar SIE4-filer enligt standarden från SIE-gruppen.
Stödjer alla obligatoriska sektioner: #FLAGGA, #FORMAT, #GEN, #PROGRAM,
#FNAMN, #FORGN, #ADRESS, #RAR, #KPTYP, #KONTO, #SRU, #IB, #UB, #RES,
#PSALDO, #VER och #TRANS.

Filen kodas i Windows-1252 med \\r\\n radbrytningar (SIE4-standard).
"""

from datetime import date, datetime
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from collections import defaultdict

from db.database import db
from domain.models import Account, Voucher, VoucherRow, FiscalYear, Period
from domain.types import AccountType


class SIE4ExportData:
    """Samlar all data som behövs för SIE4-export."""

    def __init__(self):
        self.company_name: str = ""
        self.org_number: str = ""
        self.address_contact: str = ""
        self.address_street: str = ""
        self.address_postal: str = ""
        self.address_city: str = ""
        self.address_phone: str = ""
        self.fiscal_year: Optional[FiscalYear] = None
        self.previous_fiscal_year: Optional[FiscalYear] = None
        self.accounts: List[Account] = []
        self.vouchers: List[Voucher] = []
        self.periods: List[Period] = []
        # IB (ingående balans) per konto: {account_code: amount_in_öre}
        self.opening_balances: Dict[str, int] = {}
        # UB (utgående balans) per konto: {account_code: amount_in_öre}
        self.closing_balances: Dict[str, int] = {}
        # RES (resultat) per konto: {account_code: amount_in_öre}
        self.result_balances: Dict[str, int] = {}
        # PSALDO per period per konto: {(year, month): {account_code: amount_in_öre}}
        self.period_balances: Dict[Tuple[int, int], Dict[str, int]] = {}
        # SRU-koder: {account_code: sru_code}
        self.sru_codes: Dict[str, str] = {}


class SIE4Exporter:
    """Exporterar bokföringsdata till SIE4-format.
    
    Användning:
        exporter = SIE4Exporter()
        content = exporter.export(fiscal_year_id="...")
        # content är bytes i Windows-1252 encoding
    """

    PROGRAM_NAME = "Bokföringssystem"
    PROGRAM_VERSION = "1.0"
    FORMAT_PC8 = "PC8"

    def __init__(self):
        self.errors: List[str] = []

    def export(
        self,
        fiscal_year_id: str,
        company_name: Optional[str] = None,
        org_number: Optional[str] = None,
        format_type: str = "PC8",
    ) -> bytes:
        """Exportera ett räkenskapsår till SIE4-format.
        
        Args:
            fiscal_year_id: ID för räkenskapsåret att exportera
            company_name: Företagsnamn (om None, hämtas från settings/db)
            org_number: Organisationsnummer (om None, hämtas från settings/db)
            format_type: "PC8" (Windows-1252) eller "ASCII"
            
        Returns:
            bytes: SIE4-filinnehåll kodat i Windows-1252
            
        Raises:
            ValueError: Om räkenskapsåret inte hittas
        """
        self.errors = []
        data = self._collect_data(fiscal_year_id, company_name, org_number)
        content = self._generate_content(data, format_type)

        encoding = "windows-1252" if format_type == "PC8" else "ascii"
        try:
            return content.encode(encoding)
        except UnicodeEncodeError:
            # Fallback: ersätt tecken som inte kan kodas
            return content.encode(encoding, errors="replace")

    def export_text(
        self,
        fiscal_year_id: str,
        company_name: Optional[str] = None,
        org_number: Optional[str] = None,
        format_type: str = "PC8",
    ) -> str:
        """Exportera till SIE4-format som textsträng (för testning)."""
        self.errors = []
        data = self._collect_data(fiscal_year_id, company_name, org_number)
        return self._generate_content(data, format_type)

    def _collect_data(
        self,
        fiscal_year_id: str,
        company_name: Optional[str],
        org_number: Optional[str],
    ) -> SIE4ExportData:
        """Samla in all data som behövs för exporten."""
        data = SIE4ExportData()

        # Hämta räkenskapsår
        fy = self._get_fiscal_year(fiscal_year_id)
        if not fy:
            raise ValueError(f"Räkenskapsår med id '{fiscal_year_id}' hittades inte")
        data.fiscal_year = fy

        # Hämta föregående räkenskapsår (för IB)
        data.previous_fiscal_year = self._get_previous_fiscal_year(fy)

        # Företagsinfo
        data.company_name = company_name or self._get_company_name()
        data.org_number = org_number or self._get_org_number()

        # Hämta alla konton
        data.accounts = self._get_accounts()

        # Hämta SRU-koder
        for acc in data.accounts:
            if acc.sru_code:
                data.sru_codes[acc.code] = acc.sru_code

        # Hämta perioder
        data.periods = self._get_periods(fiscal_year_id)

        # Hämta alla verifikationer för räkenskapsåret
        data.vouchers = self._get_vouchers_for_fiscal_year(fiscal_year_id)

        # Beräkna saldon
        self._calculate_balances(data)

        return data

    def _get_fiscal_year(self, fiscal_year_id: str) -> Optional[FiscalYear]:
        """Hämta räkenskapsår från databasen."""
        from repositories.period_repo import PeriodRepository
        return PeriodRepository.get_fiscal_year(fiscal_year_id)

    def _get_previous_fiscal_year(self, current_fy: FiscalYear) -> Optional[FiscalYear]:
        """Hämta föregående räkenskapsår."""
        from repositories.period_repo import PeriodRepository
        fiscal_years = PeriodRepository.list_fiscal_years()
        for fy in fiscal_years:
            if fy.end_date < current_fy.start_date:
                return fy
        return None

    def _get_company_name(self) -> str:
        """Hämta företagsnamn från company_info-tabellen om den finns."""
        try:
            cursor = db.execute(
                "SELECT value FROM company_info WHERE key = 'name' LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return row["value"]
        except Exception:
            pass
        return "Företag AB"

    def _get_org_number(self) -> str:
        """Hämta organisationsnummer."""
        try:
            cursor = db.execute(
                "SELECT value FROM company_info WHERE key = 'org_number' LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return row["value"]
        except Exception:
            pass
        return ""

    def _get_accounts(self) -> List[Account]:
        """Hämta alla aktiva konton."""
        from repositories.account_repo import AccountRepository
        return AccountRepository.list_all(active_only=False)

    def _get_periods(self, fiscal_year_id: str) -> List[Period]:
        """Hämta perioder för räkenskapsåret."""
        from repositories.period_repo import PeriodRepository
        return PeriodRepository.list_periods(fiscal_year_id)

    def _get_vouchers_for_fiscal_year(self, fiscal_year_id: str) -> List[Voucher]:
        """Hämta alla bokförda verifikationer för ett räkenskapsår.
        
        Hämtar verifikationer via perioder kopplade till räkenskapsåret.
        Batch-hämtar för prestanda.
        """
        from repositories.voucher_repo import VoucherRepository
        from repositories.period_repo import PeriodRepository

        periods = PeriodRepository.list_periods(fiscal_year_id)
        vouchers = []
        for period in periods:
            period_vouchers = VoucherRepository.list_for_period(
                period.id, status="posted"
            )
            vouchers.extend(period_vouchers)

        # Sortera på datum, serie, nummer
        vouchers.sort(key=lambda v: (v.date, v.series.value, v.number))
        return vouchers

    def _calculate_balances(self, data: SIE4ExportData) -> None:
        """Beräkna IB, UB, RES och PSALDO.
        
        Affärsregler:
        - IB (Ingående Balans): Saldo från föregående års UB, eller 0
        - UB (Utgående Balans): IB + alla transaktioner under året
          - Gäller bara balanskonton (klass 1-2)
        - RES (Resultat): Summa transaktioner för resultatkonton (klass 3-8)
        - PSALDO: Ackumulerat saldo per period per konto
        
        I SIE4 anges belopp med positivt = debet, negativt = kredit.
        """
        # Initiera saldon
        account_movements: Dict[str, int] = defaultdict(int)
        period_movements: Dict[Tuple[int, int], Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # Beräkna rörelser från verifikationer
        for voucher in data.vouchers:
            period_key = (voucher.date.year, voucher.date.month)
            for row in voucher.rows:
                # SIE4: debet = positivt, kredit = negativt
                movement = row.debit - row.credit
                account_movements[row.account_code] += movement
                period_movements[period_key][row.account_code] += movement

        # IB: Hämta från föregående års transaktioner (balansposter)
        if data.previous_fiscal_year:
            prev_vouchers = self._get_vouchers_for_fiscal_year(
                data.previous_fiscal_year.id
            )
            for voucher in prev_vouchers:
                for row in voucher.rows:
                    acc = self._find_account(data.accounts, row.account_code)
                    if acc and self._is_balance_account(acc):
                        movement = row.debit - row.credit
                        data.opening_balances[row.account_code] = (
                            data.opening_balances.get(row.account_code, 0) + movement
                        )

        # UB och RES
        for acc in data.accounts:
            movement = account_movements.get(acc.code, 0)
            if self._is_balance_account(acc):
                # UB = IB + rörelse under året
                ib = data.opening_balances.get(acc.code, 0)
                ub = ib + movement
                if ub != 0:
                    data.closing_balances[acc.code] = ub
                if ib != 0:
                    data.opening_balances[acc.code] = ib
            else:
                # RES = summa rörelse under året (resultatkonton)
                if movement != 0:
                    data.result_balances[acc.code] = movement

        # PSALDO: Ackumulerat saldo per period
        # Sorterade perioder
        sorted_periods = sorted(data.periods, key=lambda p: (p.year, p.month))
        accumulated: Dict[str, int] = {}
        # Starta med IB för balanskonton
        for code, balance in data.opening_balances.items():
            accumulated[code] = balance

        for period in sorted_periods:
            period_key = (period.year, period.month)
            movements = period_movements.get(period_key, {})
            
            # Uppdatera ackumulerat saldo
            for code, mov in movements.items():
                accumulated[code] = accumulated.get(code, 0) + mov

            # Spara periodsaldo för alla konton som har saldo
            period_data: Dict[str, int] = {}
            for code, balance in accumulated.items():
                acc = self._find_account(data.accounts, code)
                if acc and self._is_balance_account(acc) and balance != 0:
                    period_data[code] = balance
            # Lägg till resultatkonton ackumulerat
            for code, mov in movements.items():
                acc = self._find_account(data.accounts, code)
                if acc and not self._is_balance_account(acc):
                    period_data[code] = accumulated.get(code, 0)

            if period_data:
                data.period_balances[period_key] = period_data

    def _find_account(
        self, accounts: List[Account], code: str
    ) -> Optional[Account]:
        """Hitta konto i listan."""
        for acc in accounts:
            if acc.code == code:
                return acc
        return None

    def _is_balance_account(self, account: Account) -> bool:
        """Kontrollera om kontot är ett balanskonto (klass 1-2).
        
        Balansposter: Tillgångar (1xxx), Skulder (2xxx), Eget kapital (2xxx)
        Resultatposter: Intäkter (3xxx), Kostnader (4xxx-8xxx)
        """
        if account.code and len(account.code) >= 1:
            first_digit = account.code[0]
            return first_digit in ("1", "2")
        # Fallback till account_type
        return account.account_type in (
            AccountType.ASSET,
            AccountType.LIABILITY,
            AccountType.EQUITY,
            AccountType.VAT_OUT,
            AccountType.VAT_IN,
        )

    def _generate_content(self, data: SIE4ExportData, format_type: str) -> str:
        """Generera SIE4-filinnehåll som textsträng.
        
        Sektionsordning enligt SIE4-specifikationen:
        1. Flagga och format
        2. Program och generering
        3. Företagsinformation
        4. Räkenskapsår
        5. Kontoplan
        6. SRU-koder
        7. Ingående balanser (IB)
        8. Utgående balanser (UB)
        9. Resultat (RES)
        10. Periodsaldon (PSALDO)
        11. Verifikationer (VER/TRANS)
        """
        lines: List[str] = []

        # Flagga och format
        lines.append("#FLAGGA 0")
        lines.append(f"#FORMAT {format_type}")

        # Generering
        gen_date = datetime.now().strftime("%Y%m%d")
        lines.append(
            f'#GEN {gen_date} "{self.PROGRAM_NAME}" "{self.PROGRAM_VERSION}"'
        )
        lines.append(
            f'#PROGRAM "{self.PROGRAM_NAME}" "{self.PROGRAM_VERSION}"'
        )
        lines.append(f"#SIETYP 4")

        # Företagsinformation
        if data.company_name:
            lines.append(f'#FNAMN "{self._escape(data.company_name)}"')
        if data.org_number:
            lines.append(f"#FORGN {data.org_number}")

        # Adress (kontakt, gatuadress, postnr+ort, telefon)
        if any(
            [
                data.address_contact,
                data.address_street,
                data.address_postal,
                data.address_phone,
            ]
        ):
            lines.append(
                f'#ADRESS "{self._escape(data.address_contact)}" '
                f'"{self._escape(data.address_street)}" '
                f'"{self._escape(data.address_postal + " " + data.address_city).strip()}" '
                f'"{self._escape(data.address_phone)}"'
            )

        # Räkenskapsår
        if data.fiscal_year:
            fy = data.fiscal_year
            start_str = fy.start_date.strftime("%Y%m%d")
            end_str = fy.end_date.strftime("%Y%m%d")
            lines.append(f"#RAR 0 {start_str} {end_str}")

        # Föregående räkenskapsår
        if data.previous_fiscal_year:
            pfy = data.previous_fiscal_year
            start_str = pfy.start_date.strftime("%Y%m%d")
            end_str = pfy.end_date.strftime("%Y%m%d")
            lines.append(f"#RAR -1 {start_str} {end_str}")

        # Kontoplanstyp
        lines.append('#KPTYP "EUBAS97"')

        # Konton
        lines.append("")
        for acc in sorted(data.accounts, key=lambda a: a.code):
            lines.append(f'#KONTO {acc.code} "{self._escape(acc.name)}"')

        # SRU-koder
        if data.sru_codes:
            lines.append("")
            for code in sorted(data.sru_codes.keys()):
                sru = data.sru_codes[code]
                lines.append(f"#SRU {code} {sru}")

        # Ingående balanser (IB) - årsnr 0 = aktuellt år
        if data.opening_balances:
            lines.append("")
            for code in sorted(data.opening_balances.keys()):
                balance = data.opening_balances[code]
                lines.append(
                    f"#IB 0 {code} {self._format_amount(balance)}"
                )

        # Utgående balanser (UB) - årsnr 0 = aktuellt år
        if data.closing_balances:
            lines.append("")
            for code in sorted(data.closing_balances.keys()):
                balance = data.closing_balances[code]
                lines.append(
                    f"#UB 0 {code} {self._format_amount(balance)}"
                )

        # Resultat (RES) - årsnr 0 = aktuellt år
        if data.result_balances:
            lines.append("")
            for code in sorted(data.result_balances.keys()):
                balance = data.result_balances[code]
                lines.append(
                    f"#RES 0 {code} {self._format_amount(balance)}"
                )

        # Periodsaldon (PSALDO)
        if data.period_balances:
            lines.append("")
            for (year, month) in sorted(data.period_balances.keys()):
                period_str = f"{year}{month:02d}"
                for code in sorted(data.period_balances[(year, month)].keys()):
                    balance = data.period_balances[(year, month)][code]
                    lines.append(
                        f"#PSALDO 0 {period_str} {code} {self._format_amount(balance)}"
                    )

        # Verifikationer
        if data.vouchers:
            lines.append("")
            for voucher in data.vouchers:
                date_str = voucher.date.strftime("%Y%m%d")
                desc = self._escape(voucher.description)
                sign = voucher.created_by or ""
                lines.append(
                    f'#VER {voucher.series.value} {voucher.number} {date_str} "{desc}" {sign}'
                )
                lines.append("{")
                for row in voucher.rows:
                    # SIE4: #TRANS konto {} belopp datum text
                    amount = row.debit - row.credit  # debet positivt, kredit negativt
                    row_date = date_str
                    row_desc = self._escape(row.description or "")
                    lines.append(
                        f'\t#TRANS {row.account_code} {{}} {self._format_amount(amount)} {row_date} "{row_desc}"'
                    )
                lines.append("}")

        # Avslutande tom rad
        lines.append("")

        return "\r\n".join(lines)

    def _format_amount(self, amount_ore: int) -> str:
        """Formatera belopp i öre till SIE4-format (kronor med decimaler).
        
        Exempel: 12500 öre → "125.00", -50000 öre → "-500.00"
        """
        kr = amount_ore / 100
        # Formatera med punkt som decimaltecken (SIE4-standard)
        if kr == int(kr):
            return f"{int(kr)}.00"
        return f"{kr:.2f}"

    def _escape(self, text: str) -> str:
        """Escapea text för SIE4-format.
        
        Dubbla citattecken inuti strängar ersätts med dubbla citattecken.
        """
        if not text:
            return ""
        return text.replace('"', '""')

    def get_filename(
        self, company_name: str, fiscal_year: FiscalYear
    ) -> str:
        """Generera filnamn för SIE4-filen.
        
        Format: Företagsnamn_ÅÅÅÅ.si
        """
        # Rensa företagsnamn för filnamn (ASCII only)
        safe_name = "".join(
            c for c in company_name if (c.isascii() and c.isalnum()) or c in (" ", "-", "_")
        ).strip()
        safe_name = safe_name.replace(" ", "_")
        year = fiscal_year.start_date.year
        return f"{safe_name}_{year}.si"
