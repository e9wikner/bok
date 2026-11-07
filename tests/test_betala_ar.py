"""`GET /invoices` och `GET /payroll/runs` tar `?fiscal_year_id=`, så att
Fakturering och Löner följer årsväljaren som Böcker gör.

En faktura hör till året för sitt fakturadatum, en lönekörning till året för
sin utbetalning -- samma år som deras verifikationer. Ett okänt år är 404
`fiscal_year_not_found`, aldrig ett tyst byte till alla år.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from repositories.invoice_repo import InvoiceRepository
from repositories.payroll_repo import PayrollRunRepository
from repositories.period_repo import PeriodRepository

pytestmark = pytest.mark.usefixtures("test_db")


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture
def years():
    y25 = PeriodRepository.create_fiscal_year(
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)
    )
    y26 = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    return y25, y26


def test_invoices_are_listed_per_fiscal_year(client, headers, years):
    y25, y26 = years
    InvoiceRepository.create("Kund 2025", date(2025, 12, 31), date(2026, 1, 30))
    InvoiceRepository.create("Kund 2026a", date(2026, 1, 1), date(2026, 1, 31))
    InvoiceRepository.create("Kund 2026b", date(2026, 6, 15), date(2026, 7, 15))
    db.commit()  # the client reads on its own thread-local connection

    def names(params):
        r = client.get("/api/v1/invoices", params=params, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == len(body["invoices"])
        return {i["customer_name"] for i in body["invoices"]}

    assert names({"fiscal_year_id": y25.id}) == {"Kund 2025"}
    assert names({"fiscal_year_id": y26.id}) == {"Kund 2026a", "Kund 2026b"}
    assert names({}) == {"Kund 2025", "Kund 2026a", "Kund 2026b"}


def test_payroll_runs_are_listed_by_payment_year(client, headers, years):
    y25, y26 = years
    # December's salary paid in January belongs to the year it is paid in.
    PayrollRunRepository.create(2025, 11, date(2025, 11, 25))
    PayrollRunRepository.create(2025, 12, date(2026, 1, 5))
    PayrollRunRepository.create(2026, 1, date(2026, 1, 25))

    def payment_dates(params):
        r = client.get("/api/v1/payroll/runs", params=params, headers=headers)
        assert r.status_code == 200, r.text
        return {run["payment_date"] for run in r.json()["payroll_runs"]}

    assert payment_dates({"fiscal_year_id": y25.id}) == {"2025-11-25"}
    assert payment_dates({"fiscal_year_id": y26.id}) == {"2026-01-05", "2026-01-25"}
    assert len(payment_dates({})) == 3


@pytest.mark.parametrize("path", ["/api/v1/invoices", "/api/v1/payroll/runs"])
def test_unknown_fiscal_year_is_404(client, headers, years, path):
    r = client.get(path, params={"fiscal_year_id": "finns-inte"}, headers=headers)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "fiscal_year_not_found"
