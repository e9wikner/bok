"""Locking and unlocking periods and fiscal years.

A lock stops new vouchers in a period; posted vouchers are immutable either
way (the SQL triggers). The agent may lock -- through `stang_perioder` or the
API key -- but only a logged-in human (JWT) may open a period or a year again.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from domain.validation import ValidationError
from repositories.audit_repo import AuditRepository
from services.agent_tools import AGENT_TOOL_DEFINITIONS, execute_tool
from services.auth import AuthService
from services.llm import LLMCapabilities

_ROWS = [
    {"account": "1510", "debit": 10000, "credit": 0},
    {"account": "3011", "debit": 0, "credit": 10000},
]


@pytest.fixture
def year(ledger_service, fiscal_year):
    """The 2026 fiscal year with three monthly periods."""
    periods = [
        ledger_service.periods.create_period(
            fiscal_year_id=fiscal_year.id,
            year=2026,
            month=m,
            start_date=date(2026, m, 1),
            end_date=date(2026, m, 28),
        )
        for m in (1, 2, 3)
    ]
    return fiscal_year, periods


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


def _capabilities() -> LLMCapabilities:
    return LLMCapabilities(
        cache_breakpoint=False, pdf_document_blocks=False, refusal_stop_reason=False
    )


def _audit_actions(entity_id: str) -> list:
    return [e.action for e in AuditRepository.get_history("period", entity_id)]


# --- the service ------------------------------------------------------------


def test_locking_a_fiscal_year_locks_every_period_in_it(ledger_service, year):
    fy, periods = year
    ledger_service.lock_period(periods[0].id, actor="test")

    locked = ledger_service.lock_fiscal_year(fy.id, actor="agent")

    assert locked.locked is True
    assert locked.locked_at is not None
    for p in ledger_service.periods.list_periods(fy.id):
        assert p.locked is True
    # The one locked before keeps who locked it.
    assert ledger_service.periods.get_period(periods[0].id).locked_by == "test"
    assert ledger_service.periods.get_period(periods[1].id).locked_by == "agent"


def test_a_draft_stops_the_whole_year_lock(ledger_service, year):
    fy, periods = year
    ledger_service.create_voucher(
        series="A",
        date=date(2026, 2, 10),
        period_id=periods[1].id,
        description="Utkast",
        rows_data=_ROWS,
        created_by="test",
    )

    with pytest.raises(ValidationError) as exc:
        ledger_service.lock_fiscal_year(fy.id, actor="test")

    assert exc.value.code == "draft_vouchers_exist"
    assert "2026-02" in exc.value.message
    # Nothing is half locked.
    assert ledger_service.periods.get_fiscal_year(fy.id).locked is False
    assert not any(p.locked for p in ledger_service.periods.list_periods(fy.id))


def test_unlocking_a_period_lets_vouchers_in_again(ledger_service, year):
    _, periods = year
    ledger_service.lock_period(periods[2].id, actor="test")

    opened = ledger_service.unlock_period(periods[2].id, actor="stefan")

    assert opened.locked is False
    assert opened.locked_at is None and opened.locked_by is None
    ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 10),
        period_id=periods[2].id,
        description="Efter upplåsning",
        rows_data=_ROWS,
        created_by="test",
    )
    assert _audit_actions(periods[2].id)[-2:] == ["locked", "unlocked"]


def test_a_month_in_a_locked_year_stays_locked(ledger_service, year):
    fy, periods = year
    ledger_service.lock_fiscal_year(fy.id, actor="test")

    with pytest.raises(ValidationError) as exc:
        ledger_service.unlock_period(periods[0].id, actor="stefan")

    assert exc.value.code == "fiscal_year_locked"


def test_unlocking_a_fiscal_year_opens_every_period(ledger_service, year):
    fy, _ = year
    ledger_service.lock_fiscal_year(fy.id, actor="test")

    opened = ledger_service.unlock_fiscal_year(fy.id, actor="stefan")

    assert opened.locked is False and opened.locked_at is None
    assert not any(p.locked for p in ledger_service.periods.list_periods(fy.id))
    history = AuditRepository.get_history("fiscal_year", fy.id)
    assert [e.action for e in history] == ["locked", "unlocked"]
    assert history[-1].actor == "stefan"


def test_unlocking_what_is_open_is_refused(ledger_service, year):
    fy, periods = year
    with pytest.raises(ValidationError) as exc:
        ledger_service.unlock_period(periods[0].id, actor="stefan")
    assert exc.value.code == "not_locked"
    with pytest.raises(ValidationError) as exc:
        ledger_service.unlock_fiscal_year(fy.id, actor="stefan")
    assert exc.value.code == "not_locked"


def test_posted_vouchers_are_untouched_by_lock_and_unlock(ledger_service, year):
    fy, periods = year
    voucher = ledger_service.create_voucher(
        series="A",
        date=date(2026, 1, 10),
        period_id=periods[0].id,
        description="Postad",
        rows_data=_ROWS,
        created_by="test",
    )
    posted = ledger_service.post_voucher(voucher.id, actor="test")

    ledger_service.lock_fiscal_year(fy.id, actor="test")
    ledger_service.unlock_fiscal_year(fy.id, actor="stefan")

    again = ledger_service.vouchers.get(voucher.id)
    assert again.status == posted.status
    assert again.number == posted.number
    assert [(r.account_code, r.debit, r.credit) for r in again.rows] == [
        (r.account_code, r.debit, r.credit) for r in posted.rows
    ]


# --- the API ----------------------------------------------------------------


def test_the_agents_key_may_lock_but_not_unlock(client, year, auth_headers):
    fy, periods = year

    locked = client.post(f"/api/v1/fiscal-years/{fy.id}/lock", headers=auth_headers)
    assert locked.status_code == 200, locked.text
    assert locked.json()["locked"] is True

    for url in (
        f"/api/v1/fiscal-years/{fy.id}/unlock",
        f"/api/v1/periods/{periods[0].id}/unlock",
    ):
        refused = client.post(url, headers=auth_headers)
        assert refused.status_code == 403
        assert refused.json()["detail"]["code"] == "human_only"


def test_a_logged_in_human_may_unlock(client, year, auth_headers, human_headers):
    fy, periods = year
    client.post(f"/api/v1/periods/{periods[0].id}/lock", headers=human_headers)

    opened = client.post(
        f"/api/v1/periods/{periods[0].id}/unlock", headers=human_headers
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["locked"] is False

    client.post(f"/api/v1/fiscal-years/{fy.id}/lock", headers=auth_headers)
    in_locked_year = client.post(
        f"/api/v1/periods/{periods[0].id}/unlock", headers=human_headers
    )
    assert in_locked_year.status_code == 400
    assert in_locked_year.json()["detail"]["code"] == "fiscal_year_locked"

    year_opened = client.post(
        f"/api/v1/fiscal-years/{fy.id}/unlock", headers=human_headers
    )
    assert year_opened.status_code == 200
    assert year_opened.json()["locked"] is False
    history = AuditRepository.get_history("fiscal_year", fy.id)
    assert history[-1].actor == "stefan"


def test_a_missing_year_is_404(client, test_db, auth_headers):
    response = client.post("/api/v1/fiscal-years/finns-inte/lock", headers=auth_headers)
    assert response.status_code == 404


# --- the agent's tool -------------------------------------------------------


def test_stang_perioder_locks_a_period_or_a_year(ledger_service, year):
    fy, periods = year

    period = execute_tool(
        "stang_perioder",
        {"period_id": periods[0].id},
        actor="agent",
        capabilities=_capabilities(),
    )
    assert period["locked"] is True and period["locked_by"] == "agent"

    whole = execute_tool(
        "stang_perioder",
        {"fiscal_year_id": fy.id},
        actor="agent",
        capabilities=_capabilities(),
    )
    assert whole["locked"] is True
    assert all(p["locked"] for p in whole["periods"])


@pytest.mark.parametrize("args", [{}, {"period_id": "p", "fiscal_year_id": "f"}])
def test_stang_perioder_takes_exactly_one_target(test_db, args):
    with pytest.raises(ValidationError) as exc:
        execute_tool(
            "stang_perioder", args, actor="agent", capabilities=_capabilities()
        )
    assert exc.value.code == "invalid_tool_arguments"


def test_no_tool_can_unlock():
    for tool in AGENT_TOOL_DEFINITIONS:
        assert "unlock" not in tool["name"]
        assert "las_upp" not in tool["name"] and "oppna" not in tool["name"]
    [stang] = [t for t in AGENT_TOOL_DEFINITIONS if t["name"] == "stang_perioder"]
    assert "Kan bara låsa" in stang["description"]
