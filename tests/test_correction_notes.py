"""Tests for correction note lifecycle APIs."""

from calendar import monthrange
from datetime import date

import httpx
import pytest
import pytest_asyncio

from api.main import app
from config import settings
from repositories.account_repo import AccountRepository
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository


def _headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


def _ensure_accounts():
    for code, name, account_type in [
        ("1930", "Företagskonto", "asset"),
        ("3011", "Försäljning tjänster", "revenue"),
        ("6570", "Bankkostnader", "expense"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def _period():
    today = date.today()
    last_day = monthrange(today.year, today.month)[1]
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
    )
    return PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=today.year,
        month=today.month,
        start_date=date(today.year, today.month, 1),
        end_date=date(today.year, today.month, last_day),
    )


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _create_voucher(async_client, period_id: str, auto_post: bool = True) -> dict:
    response = await async_client.post(
        "/api/v1/vouchers",
        headers=_headers(),
        json={
            "series": "A",
            "date": date.today().isoformat(),
            "period_id": period_id,
            "description": "Test voucher",
            "auto_post": auto_post,
            "rows": [
                {"account": "1930", "debit": 12500, "credit": 0},
                {"account": "3011", "debit": 0, "credit": 12500},
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def _correction_rows():
    return [
        {"account": "1930", "debit": 0, "credit": 12500},
        {"account": "6570", "debit": 12500, "credit": 0},
    ]


@pytest.mark.asyncio
async def test_posted_voucher_can_receive_pending_correction_note(test_db, async_client):
    _ensure_accounts()
    period = _period()
    original = await _create_voucher(async_client, period.id)

    response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "Bankavgift ska bokföras på 6570"},
    )

    assert response.status_code == 201
    note = response.json()
    assert note["status"] == "pending"
    assert note["voucher_id"] == original["id"]
    assert note["note_text"] == "Bankavgift ska bokföras på 6570"


@pytest.mark.asyncio
async def test_draft_voucher_note_creation_is_rejected(test_db, async_client):
    _ensure_accounts()
    period = _period()
    draft = await _create_voucher(async_client, period.id, auto_post=False)

    response = await async_client.post(
        f"/api/v1/vouchers/{draft['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "Should not be accepted"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "voucher_not_posted"


@pytest.mark.asyncio
async def test_duplicate_active_correction_note_returns_409(test_db, async_client):
    _ensure_accounts()
    period = _period()
    original = await _create_voucher(async_client, period.id)

    first = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "First pending correction"},
    )
    assert first.status_code == 201

    duplicate = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "Second pending correction"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "correction_note_active_exists"


@pytest.mark.asyncio
async def test_correction_draft_and_suggestion_link_lifecycle(test_db, async_client):
    _ensure_accounts()
    period = _period()
    original = await _create_voucher(async_client, period.id)

    note_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "Suggest bank fee correction"},
    )
    assert note_response.status_code == 201
    note = note_response.json()

    draft_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-draft",
        headers=_headers(),
        json={"correction_rows": _correction_rows()},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["series"] == "B"
    assert draft["status"] == "draft"
    assert draft["correction_of"] == original["id"]

    suggested_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes/{note['id']}/suggest",
        headers=_headers(),
        json={"correction_rows": _correction_rows()},
    )
    assert suggested_response.status_code == 200
    suggested = suggested_response.json()
    assert suggested["note"]["status"] == "suggested"
    assert suggested["note"]["suggested_voucher_id"] == suggested["draft"]["id"]


@pytest.mark.asyncio
async def test_approving_suggested_note_posts_b_series_and_applies_note(
    test_db,
    async_client,
):
    _ensure_accounts()
    period = _period()
    original = await _create_voucher(async_client, period.id)
    note_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "Approve suggested correction"},
    )
    note = note_response.json()
    suggested_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes/{note['id']}/suggest",
        headers=_headers(),
        json={"correction_rows": _correction_rows()},
    )
    suggested_note = suggested_response.json()["note"]

    approve_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes/{note['id']}/approve",
        headers=_headers(),
        json={"rows": _correction_rows()},
    )

    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["series"] == "B"
    assert approved["status"] == "posted"
    assert approved["correction_of"] == original["id"]
    notes = await async_client.get(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
    )
    assert notes.status_code == 200
    applied_note = next(item for item in notes.json() if item["id"] == suggested_note["id"])
    assert applied_note["status"] == "applied"


@pytest.mark.asyncio
async def test_dismissing_suggested_note_deletes_draft_and_records_history(
    test_db,
    async_client,
):
    _ensure_accounts()
    period = _period()
    original = await _create_voucher(async_client, period.id)
    note_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "Dismiss suggested correction"},
    )
    note = note_response.json()
    suggested_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes/{note['id']}/suggest",
        headers=_headers(),
        json={"correction_rows": _correction_rows()},
    )
    suggested = suggested_response.json()
    draft_id = suggested["draft"]["id"]

    dismiss_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes/{note['id']}/dismiss",
        headers=_headers(),
        json={"reason": "Not the right correction"},
    )

    assert dismiss_response.status_code == 200
    assert dismiss_response.json()["status"] == "dismissed"
    assert VoucherRepository.get(draft_id) is None
    histories = AccountingCorrectionRepository.list(voucher_id=original["id"])
    assert histories[0].corrected_voucher_id is None
    assert histories[0].change_type == "suggestion_dismissed"
    response = await async_client.get(
        "/api/v1/accounting-corrections",
        headers=_headers(),
    )
    assert response.status_code == 200
    correction = response.json()["corrections"][0]
    assert correction["corrected_voucher_id"] is None
    assert correction["corrected_data"]["rows"][0]["account_code"] == "1930"


@pytest.mark.asyncio
async def test_rejecting_note_records_failure_context(test_db, async_client):
    _ensure_accounts()
    period = _period()
    original = await _create_voucher(async_client, period.id)
    note_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes",
        headers=_headers(),
        json={"note_text": "Agent cannot resolve"},
    )
    note = note_response.json()

    reject_response = await async_client.post(
        f"/api/v1/vouchers/{original['id']}/correction-notes/{note['id']}/reject",
        headers=_headers(),
        json={"rejection_reason": "Missing source context"},
    )

    assert reject_response.status_code == 200
    rejected = reject_response.json()
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "Missing source context"
    histories = AccountingCorrectionRepository.list(voucher_id=original["id"])
    assert histories[0].corrected_voucher_id is None
    assert histories[0].change_type == "suggestion_rejected"
    assert histories[0].was_successful is False
    response = await async_client.get(
        "/api/v1/accounting-corrections",
        headers=_headers(),
    )
    assert response.status_code == 200
    correction = response.json()["corrections"][0]
    assert correction["corrected_voucher_id"] is None
    assert correction["corrected_data"]["rejection_reason"] == "Missing source context"
    assert correction["was_successful"] is False
