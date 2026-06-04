"""Tests for separated system and company agent instructions.

This test suite verifies:
1. System instructions are read-only and loaded from files
2. Company instructions can be updated via API
3. API returns both system and company instructions separately
4. Legacy endpoints still work for backward compatibility
"""

import pytest
import httpx
import pytest_asyncio

from api.main import app
from repositories.system_instructions import (
    get_system_instructions,
    get_accounting_system_instructions,
    list_available_files,
)


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestSystemInstructions:
    """Test system instructions loader."""

    def test_get_system_instructions_returns_structure(self):
        """System instructions should return proper structure."""
        result = get_system_instructions()
        
        assert result["scope"] == "system"
        assert result["is_editable"] is False
        assert "content_markdown" in result
        assert "source" in result
        assert "files" in result
        assert "description" in result
    
    def test_get_accounting_system_instructions(self):
        """Accounting system instructions should include all docs."""
        result = get_accounting_system_instructions()
        
        assert result["scope"] == "system"
        assert "drift_och_atkomst" in result["content_markdown"].lower() or \
               "miljö" in result["content_markdown"].lower()
        assert "bokföringsprocess" in result["content_markdown"].lower() or \
               "verifikation" in result["content_markdown"].lower()
        assert "sie4" in result["content_markdown"].lower() or \
               "import" in result["content_markdown"].lower()
    
    def test_list_available_files(self):
        """Should list all expected files."""
        files = list_available_files()
        
        assert len(files) >= 4
        
        filenames = [f["filename"] for f in files]
        assert "01_drift_och_atkomst.md" in filenames
        assert "02_bokforingsprocess.md" in filenames
        assert "03_bokforingsinstruktion.md" in filenames
        assert "04_sie4_import_och_rakenskapsar.md" in filenames
        
        # All files should exist
        for f in files:
            assert f["exists"] is True, f"File {f['filename']} should exist"


class TestAgentInstructionsAPI:
    """Test agent instructions API endpoints."""

    @pytest.mark.asyncio
    async def test_get_accounting_instructions_structure(self, test_db, async_client, auth_headers):
        """GET /accounting should return both system and company."""
        response = await async_client.get(
            "/api/v1/agent-instructions/accounting",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["scope"] == "accounting"
        assert "system" in data
        assert "company" in data
        assert "note" in data
        
        # System should be read-only
        assert data["system"]["is_editable"] is False
        assert data["system"]["scope"] == "system"
        
        # Company should have version info
        assert "version" in data["company"]
        assert "content_markdown" in data["company"]
    
    @pytest.mark.asyncio
    async def test_get_invoicing_instructions_structure(self, test_db, async_client, auth_headers):
        """GET /invoicing should return both system and company."""
        response = await async_client.get(
            "/api/v1/agent-instructions/invoicing",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["scope"] == "invoicing"
        assert "system" in data
        assert "company" in data
    
    @pytest.mark.asyncio
    async def test_update_accounting_company_instructions(
        self,
        test_db,
        async_client,
        auth_headers,
    ):
        """PUT /accounting should update company instructions."""
        new_content = "# Företagsspecifika instruktioner\n\nVi använder konto 1930 istället för 1920."
        
        response = await async_client.put(
            "/api/v1/agent-instructions/accounting",
            headers=auth_headers,
            json={
                "content_markdown": new_content,
                "change_summary": "Uppdaterat bankkontonummer"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["scope"] == "accounting_company"
        assert data["content_markdown"] == new_content
        assert data["change_summary"] == "Uppdaterat bankkontonummer"
        assert "version" in data
        assert "version_id" in data
    
    @pytest.mark.asyncio
    async def test_update_invoicing_company_instructions(
        self,
        test_db,
        async_client,
        auth_headers,
    ):
        """PUT /invoicing should update company instructions."""
        new_content = "# Faktureringsregler\n\nAlla fakturor ska ha ordernummer."
        
        response = await async_client.put(
            "/api/v1/agent-instructions/invoicing",
            headers=auth_headers,
            json={
                "content_markdown": new_content,
                "change_summary": "Lagt till ordernummerkrav"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["scope"] == "invoicing_company"
        assert "version" in data
    
    @pytest.mark.asyncio
    async def test_accounting_versions_endpoint(self, test_db, async_client, auth_headers):
        """GET /accounting/versions should list company versions."""
        response = await async_client.get(
            "/api/v1/agent-instructions/accounting/versions",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["scope"] == "accounting_company"
        assert "versions" in data
        assert "total" in data
        assert "note" in data
    
    @pytest.mark.asyncio
    async def test_system_only_endpoints(self, async_client, auth_headers):
        """System-only endpoints should return read-only instructions."""
        response = await async_client.get(
            "/api/v1/agent-instructions/system/accounting",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["is_editable"] is False
        assert data["scope"] == "system"
        assert "SIE4" in data["content_markdown"] or "import" in data["content_markdown"].lower()


class TestSIE4Documentation:
    """Test that SIE4 documentation is properly included."""

    def test_sie4_documentation_in_system_instructions(self):
        """SIE4 documentation should be part of system instructions."""
        result = get_system_instructions()
        content = result["content_markdown"]
        
        # Should contain key SIE4 concepts
        assert "SIE4" in content
        assert "#RAR" in content
        assert "#IB" in content
        assert "#UB" in content
        assert "räkenskapsår" in content.lower()
        assert "multi-period" in content.lower() or "multiperiod" in content.lower()
    
    @pytest.mark.asyncio
    async def test_sie4_documentation_via_api(self, async_client, auth_headers):
        """SIE4 documentation should be accessible via API."""
        response = await async_client.get(
            "/api/v1/agent-instructions/system/accounting",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        content = data["content_markdown"]
        assert "SIE4" in content
        assert "#RAR" in content
        assert "ingående balans" in content.lower() or "IB" in content


class TestBackwardCompatibility:
    """Test that legacy endpoints still work."""

    @pytest.mark.asyncio
    async def test_legacy_accounting_endpoint(self, test_db, async_client, auth_headers):
        """Legacy endpoint should still work."""
        response = await async_client.get(
            "/api/v1/agent-instructions/accounting/legacy",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have old format
        assert "content_markdown" in data
        assert "version" in data
        assert data.get("deprecated") is True
        assert "note" in data
