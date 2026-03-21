"""Integrationstester för SIE4 import/export.

Testar hela flödet:
- Skapa konton → skapa verifikation → bokför → exportera SIE4
- Importera SIE4 → exportera → jämför
- API-endpoints för export
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.sie4_export import SIE4Exporter
from services.sie4_import import SIE4Parser, create_sample_sie4
from config import settings


@pytest.fixture
def client(test_db):
    """Skapa testklient med initierad databas."""
    accounts = [
        ("1510", "Kundfordringar", "asset"),
        ("1930", "Företagskonto", "asset"),
        ("2081", "Aktieägartillskott", "equity"),
        ("2440", "Leverantörsskulder", "liability"),
        ("2610", "Utgående moms 25%", "vat_out"),
        ("2640", "Ingående moms", "vat_in"),
        ("3010", "Försäljning tjänster", "revenue"),
        ("3011", "Försäljning tjänster 25%", "revenue"),
        ("5010", "Lokalhyra", "expense"),
        ("7010", "Lön tjänstemän", "expense"),
    ]
    for code, name, acc_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)

    from api.main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture
def fiscal_year_with_data(test_db):
    """Skapa räkenskapsår med perioder och verifikationer."""
    # Skapa konton
    accounts = [
        ("1930", "Företagskonto", "asset"),
        ("2081", "Aktieägartillskott", "equity"),
        ("3010", "Försäljning tjänster", "revenue"),
        ("5010", "Lokalhyra", "expense"),
    ]
    for code, name, acc_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)

    # Skapa räkenskapsår
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )

    # Skapa perioder
    p1 = PeriodRepository.create_period(
        fiscal_year_id=fy.id,
        year=2026, month=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    p2 = PeriodRepository.create_period(
        fiscal_year_id=fy.id,
        year=2026, month=2,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )

    # Skapa och bokför verifikationer
    # Ver A1: Startkapital (jan)
    v1 = VoucherRepository.create(
        series="A", number=1, date=date(2026, 1, 15),
        period_id=p1.id, description="Startkapital",
    )
    VoucherRepository.add_row(v1.id, "1930", debit=20000000, credit=0)
    VoucherRepository.add_row(v1.id, "2081", debit=0, credit=20000000)
    VoucherRepository.post(v1.id)

    # Ver A2: Hyra (feb)
    v2 = VoucherRepository.create(
        series="A", number=2, date=date(2026, 2, 1),
        period_id=p2.id, description="Lokalhyra feb",
    )
    VoucherRepository.add_row(v2.id, "5010", debit=1000000, credit=0)
    VoucherRepository.add_row(v2.id, "1930", debit=0, credit=1000000)
    VoucherRepository.post(v2.id)

    # Ver A3: Försäljning (feb)
    v3 = VoucherRepository.create(
        series="A", number=3, date=date(2026, 2, 15),
        period_id=p2.id, description="Försäljning tjänster",
    )
    VoucherRepository.add_row(v3.id, "1930", debit=5000000, credit=0)
    VoucherRepository.add_row(v3.id, "3010", debit=0, credit=5000000)
    VoucherRepository.post(v3.id)

    return fy


class TestSIE4ExportIntegration:
    """Integrationstester mot databasen."""

    def test_export_with_real_data(self, fiscal_year_with_data):
        """Testa export med riktig data från databasen."""
        fy = fiscal_year_with_data
        exporter = SIE4Exporter()
        content = exporter.export_text(
            fiscal_year_id=fy.id,
            company_name="Testföretag AB",
            org_number="556677-8899",
        )

        # Verifiera grundläggande sektioner
        assert "#FLAGGA 0" in content
        assert "#FORMAT PC8" in content
        assert '#FNAMN "Testföretag AB"' in content
        assert "#FORGN 556677-8899" in content
        assert f"#RAR 0 20260101 20261231" in content

        # Verifiera konton
        assert '#KONTO 1930 "Företagskonto"' in content
        assert '#KONTO 3010 "Försäljning tjänster"' in content

        # Verifiera verifikationer
        assert '#VER A 1' in content
        assert '#VER A 2' in content
        assert '#VER A 3' in content
        assert '"Startkapital"' in content

        # Verifiera UB (utgående balans)
        # 1930: 200000 - 10000 + 50000 = 240000 kr = 24000000 öre
        assert "#UB 0 1930 240000.00" in content
        # 2081: -200000 kr
        assert "#UB 0 2081 -200000.00" in content

        # Verifiera RES
        assert "#RES 0 3010 -50000.00" in content
        assert "#RES 0 5010 10000.00" in content

    def test_export_import_roundtrip_with_db(self, fiscal_year_with_data):
        """Testa export → import roundtrip med riktig data."""
        fy = fiscal_year_with_data
        exporter = SIE4Exporter()
        content = exporter.export_text(
            fiscal_year_id=fy.id,
            company_name="Roundtrip AB",
            org_number="556677-8899",
        )

        # Importera tillbaka
        parser = SIE4Parser()
        parsed = parser.parse_content(content)

        assert parsed.company.name == "Roundtrip AB"
        assert parsed.company.org_number == "556677-8899"
        assert len(parsed.vouchers) == 3
        assert parsed.fiscal_year_start == date(2026, 1, 1)
        assert parsed.fiscal_year_end == date(2026, 12, 31)

        # Kontrollera att alla verifikationer balanserar
        for v in parsed.vouchers:
            total = sum(r.amount for r in v.rows)
            assert total == 0, f"Verifikation {v.series}{v.number} balanserar inte: {total}"

    def test_export_bytes_encoding(self, fiscal_year_with_data):
        """Testa att export genererar korrekt Windows-1252 bytes."""
        fy = fiscal_year_with_data
        exporter = SIE4Exporter()
        content_bytes = exporter.export(
            fiscal_year_id=fy.id,
            company_name="Testföretag AB",
        )

        assert isinstance(content_bytes, bytes)
        # Verifiera att det kan dekodas som Windows-1252
        decoded = content_bytes.decode("windows-1252")
        assert "Testföretag AB" in decoded
        # Verifiera CRLF
        assert b"\r\n" in content_bytes

    def test_export_nonexistent_fiscal_year(self, test_db):
        """Testa felhantering vid icke-existerande räkenskapsår."""
        exporter = SIE4Exporter()
        with pytest.raises(ValueError, match="hittades inte"):
            exporter.export(fiscal_year_id="nonexistent")


class TestSIE4ExportAPI:
    """Testa API-endpoints för SIE4-export."""

    def test_export_endpoint_get_json(self, client, auth_headers, fiscal_year_with_data):
        """Testa GET /api/v1/export/sie4 med JSON-svar."""
        fy = fiscal_year_with_data
        resp = client.get(
            "/api/v1/export/sie4",
            headers=auth_headers,
            params={
                "fiscal_year_id": fy.id,
                "company_name": "API Test AB",
                "download": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert data["format"] == "SIE4"
        assert "#FLAGGA 0" in data["content"]
        assert '#FNAMN "API Test AB"' in data["content"]

    def test_export_endpoint_get_download(self, client, auth_headers, fiscal_year_with_data):
        """Testa GET /api/v1/export/sie4 med filnedladdning."""
        fy = fiscal_year_with_data
        resp = client.get(
            "/api/v1/export/sie4",
            headers=auth_headers,
            params={
                "fiscal_year_id": fy.id,
                "company_name": "Download AB",
                "download": True,
            },
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert resp.headers.get("content-type") == "application/x-sie"
        # Verifiera att innehållet är giltigt SIE4
        content = resp.content.decode("windows-1252")
        assert "#FLAGGA 0" in content

    def test_export_endpoint_post(self, client, auth_headers, fiscal_year_with_data):
        """Testa POST /api/v1/export/sie4."""
        fy = fiscal_year_with_data
        resp = client.post(
            "/api/v1/export/sie4",
            headers=auth_headers,
            params={
                "fiscal_year_id": fy.id,
                "company_name": "POST Test AB",
            },
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_export_endpoint_not_found(self, client, auth_headers):
        """Testa 404 vid icke-existerande räkenskapsår."""
        resp = client.get(
            "/api/v1/export/sie4",
            headers=auth_headers,
            params={"fiscal_year_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_full_flow_create_post_export(self, client, auth_headers):
        """Testa hela flödet: skapa verifikation → bokför → exportera SIE4."""
        # 1. Skapa räkenskapsår och period via repo (direkt)
        fy = PeriodRepository.create_fiscal_year(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        period = PeriodRepository.create_period(
            fiscal_year_id=fy.id,
            year=2026, month=3,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        # 2. Skapa verifikation via API
        resp = client.post(
            "/api/v1/vouchers",
            headers=auth_headers,
            json={
                "series": "A",
                "date": "2026-03-15",
                "period_id": period.id,
                "description": "Kundbetalning",
                "rows": [
                    {"account": "1930", "debit": 125000, "credit": 0, "description": "Inbetalning"},
                    {"account": "3011", "debit": 0, "credit": 100000, "description": "Försäljning"},
                    {"account": "2610", "debit": 0, "credit": 25000, "description": "Moms 25%"},
                ],
            },
        )
        assert resp.status_code == 201
        voucher_id = resp.json()["id"]

        # 3. Bokför verifikationen
        resp = client.post(
            f"/api/v1/vouchers/{voucher_id}/post",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 4. Exportera till SIE4
        resp = client.get(
            "/api/v1/export/sie4",
            headers=auth_headers,
            params={
                "fiscal_year_id": fy.id,
                "company_name": "Fullflöde AB",
                "download": False,
            },
        )
        assert resp.status_code == 200
        content = resp.json()["content"]

        # 5. Verifiera exporten
        assert '#FNAMN "Fullflöde AB"' in content
        assert "#VER A" in content
        assert '"Kundbetalning"' in content

        # 6. Verifiera att importern kan läsa exporten
        parser = SIE4Parser()
        parsed = parser.parse_content(content)
        assert len(parsed.vouchers) == 1
        v = parsed.vouchers[0]
        assert len(v.rows) == 3
        assert sum(r.amount for r in v.rows) == 0
