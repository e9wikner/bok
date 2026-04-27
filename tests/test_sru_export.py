"""Tests for SRU export functionality."""

import pytest
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
            }
        )

        content = service.generate_blanketter_sru(declaration)

        assert "#BLANKETT INK2R-2025P4" in content
        assert "#IDENTITET 5568194731" in content
        assert "#UPPGIFT 7011 20250101" in content  # Fiscal year start
        assert "#UPPGIFT 7012 20251231" in content  # Fiscal year end
        assert "#UPPGIFT 7410 100000" in content
        assert "#UPPGIFT 7513 50000" in content
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

        mock_db.execute.return_value.fetchone.side_effect = [mock_fy, mock_company]
        mock_db.execute.return_value.fetchall.return_value = []

        zip_bytes, filename, errors, warnings = service.export_sru_zip("fy-123")

        assert isinstance(zip_bytes, bytes)
        assert len(zip_bytes) > 0
        assert filename.endswith(".zip")
        assert "Test_AB" in filename or "TestAB" in filename

    def test_default_sru_mappings_structure(self):
        """Test that default mappings have correct structure."""
        # All keys should be strings
        for field, accounts in DEFAULT_SRU_MAPPINGS.items():
            assert isinstance(field, str)
            assert len(field) == 4  # 4-digit field codes
            assert isinstance(accounts, list)
            assert all(isinstance(a, int) for a in accounts)

    def test_credit_balance_fields_are_exported_as_positive_values(self, service):
        """Test that credit-normal SRU fields are sign-flipped for export."""
        assert service._to_sru_value("7301", -100000) == 1000
        assert service._to_sru_value("7410", -250000) == 2500

    def test_expense_fields_are_exported_as_positive_values(self, service):
        """Test that cost fields are emitted as absolute values."""
        assert service._to_sru_value("7513", 100000) == 1000
        assert service._to_sru_value("7513", -100000) == 1000

    def test_derived_fields_do_not_overwrite_base_sru_fields(self, service):
        """Test that derived calculations preserve mapped SRU field values."""
        from services.sru_export import SRUFieldValue

        fields = {
            "7368": SRUFieldValue("7368", "Leverantörsskulder", 12000, ["2440"]),
            "7410": SRUFieldValue("7410", "Nettoomsättning", 100000, ["3010"]),
            "7513": SRUFieldValue("7513", "Övriga externa kostnader", 20000, ["6540"]),
            "7514": SRUFieldValue("7514", "Personalkostnader", 30000, ["7010"]),
        }

        service._calculate_derived_fields(fields)

        assert fields["7368"].description == "Leverantörsskulder"
        assert fields["7368"].value == 12000
        assert fields["7410"].description == "Nettoomsättning"
        assert fields["7410"].value == 100000
        assert fields["7513"].description == "Övriga externa kostnader"
        assert fields["7513"].value == 20000
        assert fields["7514"].description == "Personalkostnader"
        assert fields["7514"].value == 30000


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
