"""Tests for SRU export functionality."""

import pytest
import sqlite3
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from services.sru_export import (
    SRUExportService,
    DEFAULT_SRU_MAPPINGS,
    export_sru_for_fiscal_year,
)


class TestSRUExportService:
    """Test the SRU export service."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def service(self, mock_db):
        """Create SRU export service with mocked DB."""
        with patch('services.sru_export.get_db', return_value=mock_db):
            service = SRUExportService()
            yield service

    def test_get_sru_mappings_uses_defaults(self, service, mock_db):
        """Test that default BAS2026 mappings are used when no DB mappings."""
        # Mock empty DB result
        mock_db.execute.return_value.fetchall.return_value = []

        mappings = service.get_sru_mappings("fy-123")

        # Should have many mappings from defaults
        assert len(mappings) > 100  # Default mappings cover many accounts
        
        # Check specific mappings
        assert mappings["1920"] == "7281"  # Bankkonto -> Likvida medel
        assert mappings["3010"] == "7410"  # Försäljning -> Nettoomsättning
        assert mappings["1500"] == "7251"  # Kundfordringar -> Kundfordringar
        assert mappings["1630"] == "7261"  # Skattekonto -> Övriga fordringar

    def test_get_sru_mappings_prefers_db_over_defaults(self, service, mock_db):
        """Test that DB mappings override defaults."""
        # Mock DB with custom mapping
        mock_row = Mock()
        mock_row.__getitem__ = lambda self, key: {
            "code": "1920",
            "sru_field": "9999"  # Custom field
        }[key]
        mock_db.execute.return_value.fetchall.return_value = [mock_row]

        mappings = service.get_sru_mappings("fy-123")

        # DB mapping should take precedence
        assert mappings["1920"] == "9999"

    def test_calculate_account_balances_carries_forward_opening_for_balance_accounts(self):
        """Balance accounts use closing balance, while result accounts stay in fiscal year."""
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            CREATE TABLE fiscal_years (id TEXT PRIMARY KEY, start_date DATE, end_date DATE);
            CREATE TABLE accounts (code TEXT PRIMARY KEY, name TEXT, account_type TEXT);
            CREATE TABLE vouchers (
                id TEXT PRIMARY KEY,
                series TEXT,
                date DATE,
                fiscal_year_id TEXT,
                status TEXT
            );
            CREATE TABLE voucher_rows (
                voucher_id TEXT,
                account_code TEXT,
                debit INTEGER,
                credit INTEGER
            );
            INSERT INTO fiscal_years VALUES ('fy-2026', '2026-01-01', '2026-12-31');
            INSERT INTO accounts VALUES ('1500', 'Kundfordringar', 'asset');
            INSERT INTO accounts VALUES ('3010', 'Försäljning', 'income');
            INSERT INTO vouchers VALUES ('prior', 'A', '2025-12-31', 'fy-2025', 'posted');
            INSERT INTO vouchers VALUES ('sent', 'A', '2026-02-05', 'fy-2026', 'posted');
            INSERT INTO vouchers VALUES ('paid', 'A', '2026-03-01', 'fy-2026', 'posted');
            INSERT INTO voucher_rows VALUES ('prior', '1500', 32000000, 0);
            INSERT INTO voucher_rows VALUES ('sent', '1500', 9200000, 0);
            INSERT INTO voucher_rows VALUES ('paid', '1500', 0, 4800000);
            INSERT INTO voucher_rows VALUES ('prior', '3010', 0, 10000000);
            INSERT INTO voucher_rows VALUES ('sent', '3010', 0, 9200000);
            """
        )

        with patch("services.sru_export.get_db", return_value=db):
            balances = SRUExportService().calculate_account_balances("fy-2026")

        assert balances["1500"]["balance"] == 36400000
        assert balances["3010"]["balance"] == -9200000

    def test_generate_info_sru(self, service):
        """Test INFO.SRU file generation."""
        declaration = Mock()
        declaration.company_org_number = "5568194731"
        declaration.company_name = "Test AB"

        content = service.generate_info_sru(declaration)

        assert "#DATABESKRIVNING_START" in content
        assert "#PRODUKT SRU" in content
        assert "5568194731" in content
        assert "Test AB" in content
        assert "#MEDIELEV_START" in content
        assert "\r\n" in content  # CRLF line endings

    def test_generate_blanketter_sru(self, service):
        """Test BLANKETTER.SRU file generation."""
        from services.sru_export import SRUDeclaration, SRUFieldValue

        declaration = SRUDeclaration(
            fiscal_year_id="fy-123",
            company_org_number="5568194731",
            company_name="Test AB",
            fiscal_year_start="20250101",
            fiscal_year_end="20251231",
            fields={
                "7410": SRUFieldValue("7410", "Nettoomsättning", 100000, ["3010"]),
                "7513": SRUFieldValue("7513", "Kostnader", 50000, ["5000", "6000"]),
                "7650": SRUFieldValue("7650", "Årets resultat", 25000, ["7450"]),
                "7321": SRUFieldValue("7321", "Periodiseringsfonder", 0, ["2121"]),
            }
        )

        content = service.generate_blanketter_sru(declaration)
        ink2r_part = content.split("#BLANKETT INK2R-2025P4", 1)[1].split("#BLANKETTSLUT", 1)[0]
        ink2s_part = content.split("#BLANKETT INK2S-2025P4", 1)[1].split("#BLANKETTSLUT", 1)[0]

        assert "#BLANKETT INK2-2025P4" not in content
        assert "#BLANKETT INK2R-2025P4" in content
        assert "#BLANKETT INK2S-2025P4" in content
        assert content.index("#BLANKETT INK2R-2025P4") < content.index("#BLANKETT INK2S-2025P4")
        assert "#IDENTITET 5568194731" in content
        assert "#UPPGIFT 7011 20250101" in content  # Fiscal year start
        assert "#UPPGIFT 7012 20251231" in content  # Fiscal year end
        assert "#UPPGIFT 7410 100000" in content
        assert "#UPPGIFT 7513 50000" in content
        assert "#UPPGIFT 7321 0" in ink2r_part
        assert "#UPPGIFT 7650 25000" not in ink2r_part
        assert "#UPPGIFT 7650 25000" in ink2s_part
        assert "#UPPGIFT 8041 X" in ink2s_part
        assert "#UPPGIFT 8045 X" in ink2s_part
        assert "#BLANKETTSLUT" in content
        assert "#FIL_SLUT" in content
        assert "\r\n" in content  # CRLF line endings

    def test_export_sru_zip_returns_bytes(self, service, mock_db):
        """Test that export returns ZIP bytes."""
        # Mock fiscal year
        mock_fy = Mock()
        mock_fy.__getitem__ = lambda self, key: {
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        }[key]
        
        # Mock company
        mock_company = Mock()
        mock_company.__getitem__ = lambda self, key: {
            "org_number": "556819-4731",
            "name": "Test AB",
        }[key]

        mock_ib_count = Mock()
        mock_ib_count.__getitem__ = lambda self, key: {"count": 0}[key]

        mock_db.execute.return_value.fetchone.side_effect = [mock_fy, mock_company, mock_fy, mock_ib_count]
        mock_db.execute.return_value.fetchall.return_value = []

        zip_bytes, filename, errors, warnings = service.export_sru_zip("fy-123")

        assert isinstance(zip_bytes, bytes)
        assert len(zip_bytes) > 0
        assert filename.endswith(".zip")
        assert "Test_AB" in filename or "TestAB" in filename

    def test_get_company_info_from_key_value_table(self, service, mock_db):
        """Test company info is read from the actual key/value table schema."""
        rows = []
        for key, value in [("org_number", "556819-4731"), ("name", "Test AB")]:
            row = Mock()
            row.__getitem__ = lambda self, k, key=key, value=value: {
                "key": key,
                "value": value,
            }[k]
            rows.append(row)

        mock_db.execute.return_value.fetchall.return_value = rows

        company = service._get_company_info(mock_db)

        assert company["org_number"] == "556819-4731"
        assert company["name"] == "Test AB"

    def test_default_sru_mappings_structure(self):
        """Test that default mappings have correct structure."""
        # All keys should be strings
        for field, accounts in DEFAULT_SRU_MAPPINGS.items():
            assert isinstance(field, str)
            assert all(len(part) == 4 for part in field.split("/"))  # 4-digit field codes, optionally as alternatives
            assert isinstance(accounts, list)
            assert all(isinstance(a, int) for a in accounts)

    def test_credit_balance_fields_are_exported_as_positive_values(self, service):
        """Test that credit-normal SRU fields are sign-flipped for export."""
        assert service._to_sru_value("7301", -100000) == 1000
        assert service._to_sru_value("7410", -250000) == 2500
        assert service._to_sru_value("7410", -113931946) == 1139319

    def test_expense_fields_are_exported_as_positive_values(self, service):
        """Test that cost fields are emitted as absolute values."""
        assert service._to_sru_value("7513", 100000) == 1000
        assert service._to_sru_value("7513", -100000) == 1000
        assert service._to_sru_value("7513", 13174174) == 131741
        assert service._to_sru_value("7528", 11497500) == 114975

    def test_resolve_slash_sru_mapping_uses_positive_export_side(self, service):
        """Test that imported iOrdning slash mappings resolve to real SRU fields."""
        assert service._resolve_sru_field("7416/7520", -12000000) == "7416"
        assert service._resolve_sru_field("7450/7550", 56123202) == "7450"

    def test_derived_fields_do_not_overwrite_base_sru_fields(self, service):
        """Test that derived calculations preserve mapped SRU field values."""
        from services.sru_export import SRUFieldValue

        fields = {
            "7420": SRUFieldValue("7420", "Periodiseringsfond", 190000, ["8819"]),
            "7450": SRUFieldValue("7450", "Årets resultat", 561232, ["8999"]),
            "7368": SRUFieldValue("7368", "Leverantörsskulder", 12000, ["2440"]),
            "7410": SRUFieldValue("7410", "Nettoomsättning", 100000, ["3010"]),
            "7513": SRUFieldValue("7513", "Övriga externa kostnader", 20000, ["6540"]),
            "7514": SRUFieldValue("7514", "Personalkostnader", 30000, ["7010"]),
        }

        service._calculate_derived_fields(fields)

        assert fields["7420"].value == 190000
        assert fields["7450"].value == 561232
        assert fields["7368"].description == "Leverantörsskulder"
        assert fields["7368"].value == 12000
        assert fields["7410"].description == "Nettoomsättning"
        assert fields["7410"].value == 100000
        assert fields["7513"].description == "Övriga externa kostnader"
        assert fields["7513"].value == 20000
        assert fields["7514"].description == "Personalkostnader"
        assert fields["7514"].value == 30000

    def test_ink2s_fields_are_derived_from_iordning_sru_values(self, service):
        """Test INK2S tax adjustments match the iOrdning 2025 reference logic."""
        from services.sru_export import SRUFieldValue

        fields = {
            "7450": SRUFieldValue("7450", "Årets resultat", 561232, ["8999"], [{"account": "8999", "name": "Årets resultat", "value": 561232}]),
            "7528": SRUFieldValue("7528", "Skatt på årets resultat", 114975, ["8910"], [{"account": "8910", "name": "Skatt på årets resultat", "value": 114975}]),
            "7522": SRUFieldValue("7522", "Andra ej avdragsgilla kostnader", 270, ["8423"], [{"account": "8423", "name": "Räntekostnader", "value": 270}]),
            "7416": SRUFieldValue("7416", "Skattefria intäkter", 120000, ["8226"], [{"account": "8226", "name": "Resultat värdepapper", "value": 120000}]),
            "7417": SRUFieldValue("7417", "Skattefria intäkter", 2069, ["8310", "8314"], [{"account": "8310", "name": "Ränteintäkter", "value": 2000}, {"account": "8314", "name": "Skattefri ränta", "value": 69}]),
            "7420": SRUFieldValue("7420", "Periodiseringsfond", 190000, ["8819"], [{"account": "8819", "name": "Återföring periodiseringsfond", "value": 190000}]),
        }

        service._calculate_ink2s_fields(fields)

        assert fields["7650"].value == 561232
        assert fields["7651"].value == 114975
        assert fields["7653"].value == 270
        assert fields["7754"].value == 122069
        assert fields["7654"].value == 3724
        assert fields["7670"].value == 558132
        assert fields["7651"].source_account_values == [{"account": "8910", "name": "Skatt på årets resultat", "value": 114975}]
        assert fields["7754"].source_account_values == [
            {"account": "8226", "name": "Resultat värdepapper", "value": 120000},
            {"account": "8310", "name": "Ränteintäkter", "value": 2000},
            {"account": "8314", "name": "Skattefri ränta", "value": 69},
        ]
        assert fields["7654"].source_account_values == [{"account": "8819", "name": "Återföring periodiseringsfond", "value": 3724}]
        assert {"account": "8226", "name": "Resultat värdepapper", "value": -120000} in fields["7670"].source_account_values


class TestSIE4ParserSRU:
    """Test SRU parsing from SIE4 files."""

    def test_parse_sru_mapping(self):
        """Test parsing of #SRU lines."""
        from services.sie4_import import SIE4Parser

        parser = SIE4Parser()
        
        # Standard format
        result = parser._parse_sru_mapping('1920 7281')
        assert result == {"account": "1920", "field": "7281"}
        
        # Quoted format
        result = parser._parse_sru_mapping('"1920" "7281"')
        assert result == {"account": "1920", "field": "7281"}

    def test_parse_content_extracts_sru_mappings(self):
        """Test that parse_content extracts SRU mappings."""
        from services.sie4_import import SIE4Parser

        content = """#FLAGGA 0
#FORMAT PC8
#PROGRAM Test
#KONTO 1920 Bankkonto
#SRU 1920 7281
#KONTO 3010 Försäljning
#SRU 3010 7410
#SIETYP 4
"""

        parser = SIE4Parser()
        data = parser.parse_content(content)

        assert "1920" in data.sru_mappings
        assert data.sru_mappings["1920"] == "7281"
        assert "3010" in data.sru_mappings
        assert data.sru_mappings["3010"] == "7410"

    def test_parse_content_extracts_orgnr_and_adress(self):
        """Test iOrdning-style company metadata tags."""
        from services.sie4_import import SIE4Parser

        content = """#FLAGGA 0
#FORMAT PC8
#FNAMN "Stefan Wikner Consulting AB"
#ORGNR 556819-4731
#ADRESS "Stefan Wikner Consulting AB" "Planäsvägen 7" "41749 Göteborg" 070-2233674
#SIETYP 4
"""

        parser = SIE4Parser()
        data = parser.parse_content(content)

        assert data.company.name == "Stefan Wikner Consulting AB"
        assert data.company.org_number == "556819-4731"
        assert data.company.contact_name == "Stefan Wikner Consulting AB"
        assert data.company.address == "Planäsvägen 7"
        assert data.company.postnr == "41749"
        assert data.company.postort == "Göteborg"
        assert data.company.phone == "070-2233674"


class TestSRUFieldDescriptions:
    """Test SRU field descriptions."""

    def test_field_descriptions_exist(self):
        """Test that all default fields have descriptions."""
        from services.sru_export import SRUExportService

        service = SRUExportService()
        descriptions = service._get_field_descriptions()

        # Key fields should have descriptions
        assert "7410" in descriptions  # Nettoomsättning
        assert "7450" in descriptions  # Summa tillgångar
        assert "7550" in descriptions  # Summa EK och skulder

        # All descriptions should be non-empty strings
        for code, desc in descriptions.items():
            assert isinstance(desc, str)
            assert len(desc) > 0


class TestSRUValidation:
    """Test SRU validation logic."""

    def test_balance_sheet_validation_warning(self):
        """Test that imbalance generates warning."""
        from services.sru_export import SRUExportService, SRUFieldValue

        service = SRUExportService()
        fields = {
            "7450": SRUFieldValue("7450", "Summa tillgångar", 100000, []),
            "7550": SRUFieldValue("7550", "Summa EK+Skulder", 90000, []),
            "7670": SRUFieldValue("7670", "Skillnad", 10000, []),
        }

        service._validate_balance_sheet(fields)

        assert len(service.warnings) > 0
        assert any("BALANSPOSTER STÄMMER INTE" in w for w in service.warnings)

    def test_balance_sheet_validation_ok(self):
        """Test that balanced sheet shows OK."""
        from services.sru_export import SRUExportService, SRUFieldValue

        service = SRUExportService()
        fields = {
            "7450": SRUFieldValue("7450", "Summa tillgångar", 100000, []),
            "7550": SRUFieldValue("7550", "Summa EK+Skulder", 100000, []),
            "7670": SRUFieldValue("7670", "Skillnad", 0, []),
        }

        service._validate_balance_sheet(fields)

        assert any("Balansräkning OK" in w for w in service.warnings)
