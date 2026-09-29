"""Integrationstester för SIE4 import/export.

Testar hela flödet:
- Skapa konton → skapa verifikation → bokför → exportera SIE4
- Importera SIE4 → exportera → jämför
- API-endpoints för export
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from config import settings
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.sie4_export import SIE4Exporter
from services.sie4_import import SIE4Parser


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
        year=2026,
        month=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    p2 = PeriodRepository.create_period(
        fiscal_year_id=fy.id,
        year=2026,
        month=2,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )

    # Skapa och bokför verifikationer
    # Ver A1: Startkapital (jan)
    v1 = VoucherRepository.create(
        series="A",
        date=date(2026, 1, 15),
        period_id=p1.id,
        description="Startkapital",
        fiscal_year_id=fy.id,
    )
    VoucherRepository.add_row(v1.id, "1930", debit=20000000, credit=0)
    VoucherRepository.add_row(v1.id, "2081", debit=0, credit=20000000)
    VoucherRepository.post(v1.id, number=1)

    # Ver A2: Hyra (feb)
    v2 = VoucherRepository.create(
        series="A",
        date=date(2026, 2, 1),
        period_id=p2.id,
        description="Lokalhyra feb",
        fiscal_year_id=fy.id,
    )
    VoucherRepository.add_row(v2.id, "5010", debit=1000000, credit=0)
    VoucherRepository.add_row(v2.id, "1930", debit=0, credit=1000000)
    VoucherRepository.post(v2.id, number=2)

    # Ver A3: Försäljning (feb)
    v3 = VoucherRepository.create(
        series="A",
        date=date(2026, 2, 15),
        period_id=p2.id,
        description="Försäljning tjänster",
        fiscal_year_id=fy.id,
    )
    VoucherRepository.add_row(v3.id, "1930", debit=5000000, credit=0)
    VoucherRepository.add_row(v3.id, "3010", debit=0, credit=5000000)
    VoucherRepository.post(v3.id, number=3)

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
        assert "#RAR 0 20260101 20261231" in content

        # Verifiera konton
        assert '#KONTO 1930 "Företagskonto"' in content
        assert '#KONTO 3010 "Försäljning tjänster"' in content

        # Verifiera verifikationer
        assert "#VER A 1" in content
        assert "#VER A 2" in content
        assert "#VER A 3" in content
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
            assert (
                total == 0
            ), f"Verifikation {v.series}{v.number} balanserar inte: {total}"

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


def _ib_file(amount: int) -> str:
    return f"""#FLAGGA 0
#FORMAT PC8
#PROGRAM "Test" 1.0
#FNAMN "Test AB"
#FORGN 5566778899
#RAR 0 20260101 20261231
#KONTO 1930 "Företagskonto"
#KONTO 2081 "Aktieägartillskott"
#IB 0 1930 {amount}
#IB 0 2081 -{amount}
"""


class TestSIE4ImportOpeningBalances:
    """Testa SIE4-import av ingående balanser (IB)."""

    def test_import_states_opening_balance_without_a_voucher(
        self, client, auth_headers
    ):
        """Filens #IB blir årets angivna ingående balans — ingen verifikation."""
        fy = PeriodRepository.create_fiscal_year(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        PeriodRepository.create_period(
            fiscal_year_id=fy.id,
            year=2026,
            month=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        resp = client.post(
            "/api/v1/import/sie4",
            headers=auth_headers,
            json={"content": _ib_file(100000), "fiscal_year_id": fy.id},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["imported"]["vouchers"] == 0
        assert resp.json()["imported"]["opening_balances"] == 2

        vouchers = client.get(
            "/api/v1/vouchers",
            headers=auth_headers,
            params={"fiscal_year_id": fy.id},
        ).json()["vouchers"]
        assert vouchers == []

        opening = client.get(f"/api/v1/fiscal-years/{fy.id}/opening-balances").json()
        assert opening["source"] == "stated"
        assert opening["balanced"] is True
        assert opening["balances"] == [
            {"account": "1930", "amount": 10000000},
            {"account": "2081", "amount": -10000000},
        ]

    def test_reimport_replaces_the_stated_opening_balance(self, client, auth_headers):
        """IB är inte bokförd, så en ny import i ett olåst år ersätter den —
        och ett låst års IB går inte att ändra."""
        fy = PeriodRepository.create_fiscal_year(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        PeriodRepository.create_period(
            fiscal_year_id=fy.id,
            year=2026,
            month=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        for amount in (100000, 150000):
            resp = client.post(
                "/api/v1/import/sie4",
                headers=auth_headers,
                json={"content": _ib_file(amount), "fiscal_year_id": fy.id},
            )
            assert resp.json()["success"] is True

        opening = client.get(f"/api/v1/fiscal-years/{fy.id}/opening-balances").json()
        assert {"account": "1930", "amount": 15000000} in opening["balances"]

        lock = client.post(f"/api/v1/fiscal-years/{fy.id}/lock", headers=auth_headers)
        assert lock.status_code == 200

        resp = client.post(
            "/api/v1/import/sie4",
            headers=auth_headers,
            json={"content": _ib_file(200000), "fiscal_year_id": fy.id},
        )
        assert resp.json()["success"] is False
        opening = client.get(f"/api/v1/fiscal-years/{fy.id}/opening-balances").json()
        assert {"account": "1930", "amount": 15000000} in opening["balances"]

    def test_later_year_derives_its_ib_and_reconciles_the_file(
        self, client, auth_headers
    ):
        """Ett år med föregående år i böckerna räknar fram sin IB. Filens #IB
        sparas bara för avstämning, och en avvikelse är en varning."""
        fy_2025 = PeriodRepository.create_fiscal_year(
            start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)
        )
        PeriodRepository.create_period(
            fiscal_year_id=fy_2025.id,
            year=2025,
            month=1,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        sie_2025 = """#FLAGGA 0
#FORMAT PC8
#RAR 0 20250101 20251231
#KONTO 1930 "Företagskonto"
#KONTO 2081 "Aktieägartillskott"
#KONTO 3010 "Försäljning tjänster"
#IB 0 1930 100000
#IB 0 2081 -100000
#VER A 1 20250115 "Försäljning"
{
#TRANS 1930 {} 20000.00
#TRANS 3010 {} -20000.00
}
"""
        resp = client.post(
            "/api/v1/import/sie4",
            headers=auth_headers,
            json={"content": sie_2025, "fiscal_year_id": fy_2025.id},
        )
        assert resp.json()["success"] is True

        # The file says 2099 was never credited: it differs from what Bok
        # derives (the 2025 result carried to 2099).
        sie_2026 = """#FLAGGA 0
#FORMAT PC8
#RAR 0 20260101 20261231
#KONTO 1930 "Företagskonto"
#KONTO 2081 "Aktieägartillskott"
#IB 0 1930 120000
#IB 0 2081 -120000
"""
        resp = client.post(
            "/api/v1/import/sie4",
            headers=auth_headers,
            json={"content": sie_2026},
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["warnings"]) == 1
        assert "2099" in body["warnings"][0]

        fy_2026_id = body["fiscal_year"]["id"]
        opening = client.get(
            f"/api/v1/fiscal-years/{fy_2026_id}/opening-balances"
        ).json()
        assert opening["source"] == "derived"
        assert opening["previous_fiscal_year_id"] == fy_2025.id
        assert opening["balanced"] is True
        assert opening["balances"] == [
            {"account": "1930", "amount": 12000000},
            {"account": "2081", "amount": -10000000},
            {"account": "2099", "amount": -2000000},
        ]
        assert {d["account"] for d in opening["stated_differences"]} == {
            "2081",
            "2099",
        }

    def test_export_reflects_imported_opening_balance(self, client, auth_headers):
        """Exporten ska spegla den importerade ingående balansen — även konton
        som ingen verifikation under året rör (aktiekapital,
        periodiseringsfonder, upplupna löner ...)."""
        for code, name, acc_type in [
            ("1930", "Företagskonto", "asset"),
            ("2081", "Aktiekapital", "equity"),
            ("2890", "Övriga kortfristiga skulder", "liability"),
            ("5010", "Lokalhyra", "expense"),
        ]:
            if not AccountRepository.exists(code):
                AccountRepository.create(code, name, acc_type)

        fy = PeriodRepository.create_fiscal_year(
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        for month, last in [(1, 31), (3, 31)]:
            PeriodRepository.create_period(
                fiscal_year_id=fy.id,
                year=2026,
                month=month,
                start_date=date(2026, month, 1),
                end_date=date(2026, month, last),
            )

        # #IB har en post (2890) som ingen verifikation under året rör.
        sie4 = """#FLAGGA 0
#FORMAT PC8
#PROGRAM "Test" 1.0
#FNAMN "IB AB"
#RAR 0 20260101 20261231
#KONTO 1930 "Företagskonto"
#KONTO 2081 "Aktiekapital"
#KONTO 2890 "Övriga kortfristiga skulder"
#KONTO 5010 "Lokalhyra"
#IB 0 1930 200000
#IB 0 2081 -50000
#IB 0 2890 -150000
#VER A 1 20260315 "Hyra"
{
#TRANS 5010 {} 10000.00
#TRANS 1930 {} -10000.00
}
"""
        resp = client.post(
            "/api/v1/import/sie4",
            headers=auth_headers,
            json={"content": sie4, "fiscal_year_id": fy.id},
        )
        assert resp.status_code == 200

        content = client.get(
            "/api/v1/export/sie4",
            headers=auth_headers,
            params={"fiscal_year_id": fy.id, "download": False},
        ).json()["content"]

        # IB speglar filens #IB — även konton utan rörelse under året.
        assert "#IB 0 1930 200000.00" in content
        assert "#IB 0 2081 -50000.00" in content
        assert "#IB 0 2890 -150000.00" in content

        # UB = IB + rörelse.
        assert "#UB 0 1930 190000.00" in content  # 200000 - 10000
        assert "#UB 0 2081 -50000.00" in content  # oförändrat
        assert "#UB 0 2890 -150000.00" in content  # oförändrat
        assert "#RES 0 5010 10000.00" in content

        # IB är ingen verifikation och skrivs aldrig ut som #VER.
        assert "#VER IB" not in content
        assert "#VER A 1" in content

    def test_all_zero_opening_balance_is_not_a_failure(self, client, auth_headers):
        """En startårsexport har #IB-rader men alla är 0. Det ska inte flagga
        importen som ofullständig (och i dropzonen skicka filen till _Problem/).
        """
        for code, name, acc_type in [
            ("1930", "Företagskonto", "asset"),
            ("2081", "Aktiekapital", "equity"),
        ]:
            if not AccountRepository.exists(code):
                AccountRepository.create(code, name, acc_type)

        fy = PeriodRepository.create_fiscal_year(
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        PeriodRepository.create_period(
            fiscal_year_id=fy.id,
            year=2026,
            month=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        sie4 = """#FLAGGA 0
#FORMAT PC8
#FNAMN "Startår AB"
#RAR 0 20260101 20261231
#KONTO 1930 "Företagskonto"
#KONTO 2081 "Aktiekapital"
#IB 0 1930 0
#IB 0 2081 0
#VER A 1 20260115 "Kontantemission"
{
#TRANS 1930 {} 50000.00
#TRANS 2081 {} -50000.00
}
"""
        resp = client.post(
            "/api/v1/import/sie4",
            headers=auth_headers,
            json={"content": sie4, "fiscal_year_id": fy.id},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        vouchers = client.get(
            "/api/v1/vouchers",
            headers=auth_headers,
            params={"fiscal_year_id": fy.id},
        ).json()["vouchers"]
        assert not [v for v in vouchers if v["series"] == "IB"]
        assert len([v for v in vouchers if v["series"] == "A"]) == 1


class TestSIE4ExportAPI:
    """Testa API-endpoints för SIE4-export."""

    def test_export_endpoint_get_json(
        self, client, auth_headers, fiscal_year_with_data
    ):
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

    def test_export_endpoint_get_download(
        self, client, auth_headers, fiscal_year_with_data
    ):
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
            year=2026,
            month=3,
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
                    {
                        "account": "1930",
                        "debit": 125000,
                        "credit": 0,
                        "description": "Inbetalning",
                    },
                    {
                        "account": "3011",
                        "debit": 0,
                        "credit": 100000,
                        "description": "Försäljning",
                    },
                    {
                        "account": "2610",
                        "debit": 0,
                        "credit": 25000,
                        "description": "Moms 25%",
                    },
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
