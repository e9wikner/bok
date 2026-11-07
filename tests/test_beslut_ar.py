"""`GET /decisions?fiscal_year_id=`: Verifikationers Väntar på beslut visar
bara det som hör till valt räkenskapsår.

Ett beslut hör till året som innehåller underlagets datum (`source_date`),
annars trådens år; en korrigeringsnotering till verifikationens år; ett
misslyckat underlag till uppladdningsdagens år.
"""

import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.decision_service import DecisionService

pytestmark = pytest.mark.usefixtures("test_db")

VIEW = "bocker.verifikationer"


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


def _thread(fiscal_year_id: str, view_key: str = VIEW):
    return ThreadRepository.get_or_create(
        view_key=view_key, fiscal_year_id=fiscal_year_id, model="test"
    )


def _decision(thread, title: str, source_date=None):
    source = (
        {"kind": "intake_source", "id": str(uuid.uuid4()), "date": source_date}
        if source_date
        else None
    )
    return DecisionService().create(
        thread,
        title=title,
        reason="Agenten avstod.",
        consequence="Ingenting är bokfört.",
        source=source,
    )


def _ids(client, headers, fiscal_year_id=None):
    params = {"view_key": VIEW, "status": "open", "limit": 200}
    if fiscal_year_id:
        params["fiscal_year_id"] = fiscal_year_id
    response = client.get("/api/v1/decisions", params=params, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return {d["title"] for d in body["decisions"]}, body["total"]


def test_source_date_wins_over_the_thread_year(client, headers, years):
    y25, y26 = years
    thread26 = _thread(y26.id)
    _decision(thread26, "kvitto 2026", source_date=date(2026, 3, 1))
    # Höjt i 2026 års tråd (som allt före årsväljaren), men underlaget är från 2025.
    _decision(thread26, "kvitto 2025", source_date=date(2025, 11, 30))
    _decision(thread26, "utan underlag")

    titles25, total25 = _ids(client, headers, y25.id)
    titles26, total26 = _ids(client, headers, y26.id)

    assert titles25 == {"kvitto 2025"} and total25 == 1
    assert titles26 == {"kvitto 2026", "utan underlag"} and total26 == 2


def test_without_fiscal_year_every_year_is_listed(client, headers, years):
    _, y26 = years
    thread26 = _thread(y26.id)
    _decision(thread26, "a", source_date=date(2026, 3, 1))
    _decision(thread26, "b", source_date=date(2025, 3, 1))

    titles, total = _ids(client, headers)
    assert titles == {"a", "b"} and total == 2


def test_synthetic_rows_follow_their_dates(client, headers, years):
    y25, y26 = years
    period25 = PeriodRepository.create_period(
        fiscal_year_id=y25.id,
        year=2025,
        month=6,
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
    )
    voucher = VoucherRepository.create(
        series="A",
        date=date(2025, 6, 15),
        period_id=period25.id,
        description="Juni",
        fiscal_year_id=y25.id,
    )
    # Noteringen skrivs 2026 men gäller en verifikation från 2025.
    db.execute(
        "INSERT INTO correction_notes (id, voucher_id, note_text, status, "
        "created_at, created_by) VALUES (?, ?, ?, 'pending', ?, 'stefan')",
        (str(uuid.uuid4()), voucher.id, "Fel konto", datetime(2026, 2, 1)),
    )
    db.execute(
        "INSERT INTO intake_sources (id, source_type, status, original_filename, "
        "mime_type, size_bytes, sha256, stored_path, uploaded_by, uploaded_at) "
        "VALUES (?, 'receipt', 'failed', 'kvitto.pdf', 'application/pdf', 1, ?, "
        "'/tmp/k.pdf', 'api', ?)",
        (str(uuid.uuid4()), uuid.uuid4().hex, datetime(2026, 4, 1)),
    )
    db.commit()

    titles25, _ = _ids(client, headers, y25.id)
    titles26, _ = _ids(client, headers, y26.id)

    assert titles25 == {f"Korrigeringsnotering, verifikation {voucher.id}"}
    assert titles26 == {"kvitto.pdf"}


def test_unknown_fiscal_year_is_404(client, headers, years):
    response = client.get(
        "/api/v1/decisions",
        params={"fiscal_year_id": "finns-inte"},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "fiscal_year_not_found"
