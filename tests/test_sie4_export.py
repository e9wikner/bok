"""Tester för SIE4 export-funktionalitet.

Testar:
- Generering av alla SIE4-sektioner
- Beräkning av IB, UB, RES, PSALDO
- Windows-1252 encoding och \\r\\n radbrytningar
- Export → Import roundtrip (verifierar att data bevaras)
- Felhantering
"""

import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from services.sie4_export import SIE4Exporter, SIE4ExportData
from services.sie4_import import SIE4Parser
from domain.models import (
    Account, Voucher, VoucherRow, FiscalYear, Period,
)
from domain.types import AccountType, VoucherStatus, VoucherSeries


def _make_fiscal_year(
    fy_id="fy-2026",
    start=date(2026, 1, 1),
    end=date(2026, 12, 31),
) -> FiscalYear:
    return FiscalYear(
        id=fy_id, start_date=start, end_date=end, created_at=datetime.now()
    )


def _make_period(
    period_id, fiscal_year_id, year, month, start_d, end_d
) -> Period:
    return Period(
        id=period_id,
        fiscal_year_id=fiscal_year_id,
        year=year,
        month=month,
        start_date=start_d,
        end_date=end_d,
        created_at=datetime.now(),
    )


def _make_account(code, name, account_type, sru_code=None) -> Account:
    return Account(
        code=code,
        name=name,
        account_type=account_type,
        sru_code=sru_code,
        created_at=datetime.now(),
    )


def _make_voucher(
    voucher_id, series, number, voucher_date, period_id, description, rows
) -> Voucher:
    return Voucher(
        id=voucher_id,
        series=VoucherSeries(series),
        number=number,
        date=voucher_date,
        period_id=period_id,
        description=description,
        status=VoucherStatus.POSTED,
        rows=rows,
        created_at=datetime.now(),
        created_by="test",
    )


def _make_row(row_id, voucher_id, account_code, debit=0, credit=0, desc=None) -> VoucherRow:
    return VoucherRow(
        id=row_id,
        voucher_id=voucher_id,
        account_code=account_code,
        debit=debit,
        credit=credit,
        description=desc,
        created_at=datetime.now(),
    )


class TestSIE4ExporterContent:
    """Testa generering av SIE4-filinnehåll."""

    def _build_test_data(self) -> SIE4ExportData:
        """Bygg testdata med konton och verifikationer."""
        data = SIE4ExportData()
        data.company_name = "Test AB"
        data.org_number = "556677-8899"
        data.fiscal_year = _make_fiscal_year()
        data.accounts = [
            _make_account("1930", "Företagskonto", AccountType.ASSET, sru_code="1940"),
            _make_account("2081", "Aktieägartillskott", AccountType.EQUITY),
            _make_account("3010", "Försäljning tjänster", AccountType.REVENUE, sru_code="3610"),
            _make_account("5010", "Lokalhyra", AccountType.EXPENSE),
        ]
        data.sru_codes = {"1930": "1940", "3010": "3610"}
        data.periods = [
            _make_period("p1", "fy-2026", 2026, 1, date(2026, 1, 1), date(2026, 1, 31)),
            _make_period("p2", "fy-2026", 2026, 2, date(2026, 2, 1), date(2026, 2, 28)),
        ]

        # Verifikation 1: Startkapital (jan)
        v1_rows = [
            _make_row("r1", "v1", "1930", debit=20000000, credit=0, desc="Insättning"),
            _make_row("r2", "v1", "2081", debit=0, credit=20000000, desc="Aktieägartillskott"),
        ]
        v1 = _make_voucher("v1", "A", 1, date(2026, 1, 15), "p1", "Startkapital", v1_rows)

        # Verifikation 2: Försäljning (feb)
        v2_rows = [
            _make_row("r3", "v2", "1930", debit=10000000, credit=0, desc="Betalning"),
            _make_row("r4", "v2", "3010", debit=0, credit=10000000, desc="Försäljning"),
        ]
        v2 = _make_voucher("v2", "A", 2, date(2026, 2, 1), "p2", "Försäljning feb", v2_rows)

        data.vouchers = [v1, v2]

        # Beräkna saldon manuellt
        # UB: 1930 = 200000 + 100000 = 300000 kr = 30000000 öre
        data.closing_balances = {"1930": 30000000, "2081": -20000000}
        # RES: 3010 = -100000 kr (kredit)
        data.result_balances = {"3010": -10000000}
        # PSALDO
        data.period_balances = {
            (2026, 1): {"1930": 20000000, "2081": -20000000},
            (2026, 2): {"1930": 30000000, "2081": -20000000, "3010": -10000000},
        }

        return data

    def test_flagga_and_format(self):
        """Testa att #FLAGGA och #FORMAT genereras korrekt."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        lines = content.split("\r\n")
        assert lines[0] == "#FLAGGA 0"
        assert lines[1] == "#FORMAT PC8"

    def test_program_and_gen(self):
        """Testa att #PROGRAM och #GEN genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert "#GEN " in content
        assert '#PROGRAM "Bokföringssystem"' in content
        assert "#SIETYP 4" in content

    def test_company_info(self):
        """Testa att företagsinformation genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert '#FNAMN "Test AB"' in content
        assert "#FORGN 556677-8899" in content

    def test_fiscal_year(self):
        """Testa att räkenskapsår genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert "#RAR 0 20260101 20261231" in content

    def test_accounts(self):
        """Testa att konton genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert '#KONTO 1930 "Företagskonto"' in content
        assert '#KONTO 3010 "Försäljning tjänster"' in content

    def test_sru_codes(self):
        """Testa att SRU-koder genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert "#SRU 1930 1940" in content
        assert "#SRU 3010 3610" in content

    def test_closing_balances(self):
        """Testa att UB (utgående balans) genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert "#UB 0 1930 300000.00" in content
        assert "#UB 0 2081 -200000.00" in content

    def test_result_balances(self):
        """Testa att RES (resultat) genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert "#RES 0 3010 -100000.00" in content

    def test_period_balances(self):
        """Testa att PSALDO genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert "#PSALDO 0 202601 1930 200000.00" in content
        assert "#PSALDO 0 202602 1930 300000.00" in content

    def test_vouchers(self):
        """Testa att verifikationer genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert '#VER A 1 20260115 "Startkapital"' in content
        assert "#TRANS 1930 {} 200000.00" in content
        assert "#TRANS 2081 {} -200000.00" in content

    def test_crlf_line_endings(self):
        """Testa att filen använder \\r\\n radbrytningar."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert "\r\n" in content
        # Ska inte ha bara \n utan \r\n
        lines_with_crlf = content.count("\r\n")
        lines_with_lf = content.count("\n")
        assert lines_with_crlf == lines_with_lf  # Alla \n ska vara \r\n

    def test_windows_1252_encoding(self):
        """Testa att export genererar Windows-1252 encoding."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        # Lägg till svenska tecken
        data.accounts.append(
            _make_account("6010", "Kontorsmöbler (åäö)", AccountType.EXPENSE)
        )
        content = exporter._generate_content(data, "PC8")
        encoded = content.encode("windows-1252")
        assert isinstance(encoded, bytes)
        # Verifiera att ö, ä, å kodas korrekt
        assert "åäö" in content

    def test_kptyp(self):
        """Testa att kontoplanstyp (#KPTYP) genereras."""
        exporter = SIE4Exporter()
        data = self._build_test_data()
        content = exporter._generate_content(data, "PC8")
        assert '#KPTYP "EUBAS97"' in content

    def test_amount_formatting(self):
        """Testa formatering av belopp."""
        exporter = SIE4Exporter()
        assert exporter._format_amount(12500) == "125.00"
        assert exporter._format_amount(-50000) == "-500.00"
        assert exporter._format_amount(0) == "0.00"
        assert exporter._format_amount(99) == "0.99"
        assert exporter._format_amount(100) == "1.00"
        assert exporter._format_amount(-1) == "-0.01"

    def test_escape_quotes(self):
        """Testa att citattecken escapeas."""
        exporter = SIE4Exporter()
        assert exporter._escape('Test "AB"') == 'Test ""AB""'
        assert exporter._escape("Normal text") == "Normal text"
        assert exporter._escape("") == ""

    def test_filename_generation(self):
        """Testa generering av filnamn."""
        exporter = SIE4Exporter()
        fy = _make_fiscal_year()
        assert exporter.get_filename("Test AB", fy) == "Test_AB_2026.si"
        assert exporter.get_filename("Företag & Co", fy) == "Fretag__Co_2026.si"


class TestSIE4ExportImportRoundtrip:
    """Testa export → import roundtrip."""

    def test_roundtrip_accounts(self):
        """Testa att konton bevaras vid export → import."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.company_name = "Roundtrip AB"
        data.org_number = "556677-8899"
        data.fiscal_year = _make_fiscal_year()
        data.accounts = [
            _make_account("1930", "Företagskonto", AccountType.ASSET),
            _make_account("2081", "Aktieägartillskott", AccountType.EQUITY),
            _make_account("3010", "Försäljning", AccountType.REVENUE),
        ]
        data.periods = []
        data.vouchers = []

        content = exporter._generate_content(data, "PC8")

        # Importera tillbaka
        parser = SIE4Parser()
        parsed = parser.parse_content(content)

        assert len(parsed.accounts) == 3
        account_codes = {a.code for a in parsed.accounts}
        assert "1930" in account_codes
        assert "2081" in account_codes
        assert "3010" in account_codes

    def test_roundtrip_vouchers(self):
        """Testa att verifikationer bevaras vid export → import."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.company_name = "Roundtrip AB"
        data.org_number = "556677-8899"
        data.fiscal_year = _make_fiscal_year()
        data.accounts = [
            _make_account("1930", "Företagskonto", AccountType.ASSET),
            _make_account("2081", "Aktieägartillskott", AccountType.EQUITY),
        ]
        data.periods = []

        rows = [
            _make_row("r1", "v1", "1930", debit=10000000, credit=0),
            _make_row("r2", "v1", "2081", debit=0, credit=10000000),
        ]
        data.vouchers = [
            _make_voucher("v1", "A", 1, date(2026, 1, 15), "p1", "Test ver", rows)
        ]

        content = exporter._generate_content(data, "PC8")

        # Importera tillbaka
        parser = SIE4Parser()
        parsed = parser.parse_content(content)

        assert len(parsed.vouchers) == 1
        v = parsed.vouchers[0]
        assert v.series == "A"
        assert v.number == 1
        assert v.date == date(2026, 1, 15)
        assert len(v.rows) == 2

        # Kontrollera belopp (100000 kr = 10000000 öre)
        debit_row = [r for r in v.rows if r.amount > 0][0]
        credit_row = [r for r in v.rows if r.amount < 0][0]
        assert debit_row.account == "1930"
        assert debit_row.amount == 10000000  # 100000.00 kr i öre
        assert credit_row.account == "2081"
        assert credit_row.amount == -10000000

    def test_roundtrip_company_info(self):
        """Testa att företagsinformation bevaras."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.company_name = "Test & Åäö AB"
        data.org_number = "556677-8899"
        data.fiscal_year = _make_fiscal_year()
        data.accounts = []
        data.periods = []
        data.vouchers = []

        content = exporter._generate_content(data, "PC8")

        parser = SIE4Parser()
        parsed = parser.parse_content(content)

        assert parsed.company is not None
        assert parsed.company.name == "Test & Åäö AB"
        assert parsed.company.org_number == "556677-8899"

    def test_roundtrip_fiscal_year(self):
        """Testa att räkenskapsår bevaras."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.company_name = "Test AB"
        data.fiscal_year = _make_fiscal_year(
            start=date(2026, 7, 1), end=date(2027, 6, 30)
        )
        data.accounts = []
        data.periods = []
        data.vouchers = []

        content = exporter._generate_content(data, "PC8")

        parser = SIE4Parser()
        parsed = parser.parse_content(content)

        assert parsed.fiscal_year_start == date(2026, 7, 1)
        assert parsed.fiscal_year_end == date(2027, 6, 30)


class TestSIE4ExporterEdgeCases:
    """Testa edge cases."""

    def test_empty_data(self):
        """Testa export utan verifikationer."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.company_name = "Tom AB"
        data.fiscal_year = _make_fiscal_year()
        data.accounts = []
        data.periods = []
        data.vouchers = []

        content = exporter._generate_content(data, "PC8")
        assert "#FLAGGA 0" in content
        assert '#FNAMN "Tom AB"' in content
        assert "#VER" not in content

    def test_negative_amounts(self):
        """Testa med negativa belopp."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.fiscal_year = _make_fiscal_year()
        data.company_name = "Test AB"
        data.accounts = [
            _make_account("3010", "Försäljning", AccountType.REVENUE),
        ]
        data.periods = []
        data.result_balances = {"3010": -5000000}  # -50000 kr
        data.vouchers = []

        content = exporter._generate_content(data, "PC8")
        assert "#RES 0 3010 -50000.00" in content

    def test_ascii_format(self):
        """Testa ASCII-format (ingen Windows-1252)."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.company_name = "ASCII Test"
        data.fiscal_year = _make_fiscal_year()
        data.accounts = []
        data.periods = []
        data.vouchers = []

        content = exporter._generate_content(data, "ASCII")
        assert "#FORMAT ASCII" in content

    def test_is_balance_account(self):
        """Testa klassificering av balansposter."""
        exporter = SIE4Exporter()
        assert exporter._is_balance_account(
            _make_account("1930", "Kassa", AccountType.ASSET)
        )
        assert exporter._is_balance_account(
            _make_account("2440", "Skuld", AccountType.LIABILITY)
        )
        assert not exporter._is_balance_account(
            _make_account("3010", "Försäljning", AccountType.REVENUE)
        )
        assert not exporter._is_balance_account(
            _make_account("5010", "Hyra", AccountType.EXPENSE)
        )

    def test_many_vouchers(self):
        """Testa med många verifikationer."""
        exporter = SIE4Exporter()
        data = SIE4ExportData()
        data.company_name = "Stor AB"
        data.fiscal_year = _make_fiscal_year()
        data.accounts = [
            _make_account("1930", "Kassa", AccountType.ASSET),
            _make_account("3010", "Försäljning", AccountType.REVENUE),
        ]
        data.periods = []

        vouchers = []
        for i in range(100):
            rows = [
                _make_row(f"r{i}a", f"v{i}", "1930", debit=100000, credit=0),
                _make_row(f"r{i}b", f"v{i}", "3010", debit=0, credit=100000),
            ]
            v = _make_voucher(
                f"v{i}", "A", i + 1, date(2026, 1, 15), "p1", f"Ver {i+1}", rows
            )
            vouchers.append(v)
        data.vouchers = vouchers

        content = exporter._generate_content(data, "PC8")
        assert content.count("#VER ") == 100
