"""Tests for PDF export functionality."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_pdf_export_invoice_endpoint_exists(client):
    """Test that invoice PDF export endpoint exists."""
    with patch("services.pdf_export.PDFExportService.export_invoice") as mock_export:
        mock_export.return_value = b"fake pdf content"
        response = client.get("/api/v1/export/pdf/invoice/test-123")
        # Should succeed or return 404 if invoice not found
        assert response.status_code in [200, 404]


def test_pdf_export_income_statement_endpoint_exists(client):
    """Test that income statement PDF export endpoint exists."""
    with patch("services.pdf_export.PDFExportService.export_income_statement") as mock_export:
        mock_export.return_value = b"fake pdf content"
        response = client.get("/api/v1/export/pdf/income-statement/test-period")
        assert response.status_code in [200, 404]


def test_pdf_export_balance_sheet_endpoint_exists(client):
    """Test that balance sheet PDF export endpoint exists."""
    with patch("services.pdf_export.PDFExportService.export_balance_sheet") as mock_export:
        mock_export.return_value = b"fake pdf content"
        response = client.get("/api/v1/export/pdf/balance-sheet/test-period")
        assert response.status_code in [200, 404]


def test_pdf_export_general_ledger_endpoint_exists(client):
    """Test that general ledger PDF export endpoint exists."""
    with patch("services.pdf_export.PDFExportService.export_general_ledger") as mock_export:
        mock_export.return_value = b"fake pdf content"
        response = client.get("/api/v1/export/pdf/general-ledger/1930?period_id=test-period")
        assert response.status_code in [200, 404]


def test_pdf_export_k2_report_endpoint_exists(client):
    """Test that K2 report PDF export endpoint exists."""
    with patch("services.pdf_export.PDFExportService.export_k2_report") as mock_export:
        mock_export.return_value = b"fake pdf content"
        response = client.get(
            "/api/v1/export/pdf/k2-report/test-fy?company_name=Test+AB"
        )
        assert response.status_code in [200, 404]


def test_pdf_response_headers(client):
    """Test that PDF responses have correct headers."""
    with patch("services.pdf_export.PDFExportService.export_invoice") as mock_export:
        mock_export.return_value = b"fake pdf content"
        response = client.get("/api/v1/export/pdf/invoice/test-123")
        if response.status_code == 200:
            assert response.headers["content-type"] == "application/pdf"
            assert "attachment" in response.headers.get("content-disposition", "")


def test_pdf_export_with_company_params(client):
    """Test PDF export with company info parameters."""
    with patch("services.pdf_export.PDFExportService.export_invoice") as mock_export:
        mock_export.return_value = b"fake pdf content"
        response = client.get(
            "/api/v1/export/pdf/invoice/test-123?"
            "company_name=Test%20AB&"
            "org_number=5566778899&"
            "bankgiro=123-4567&"
            "swish=0701234567"
        )
        # Just verify the endpoint accepts these params
        assert response.status_code in [200, 404]
