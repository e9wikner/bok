"""The agent's payroll tools: las_loner, registrera_anstalld, satt_lon and
skapa_lonekorning (services/agent_tools.py). They call PayrollService, the
same code as /payroll; the three that write refuse outside a thread."""

from types import SimpleNamespace

import pytest

from db.database import db
from domain.payroll_models import mask_trailing, normalize_personal_number
from domain.validation import ValidationError
from services.agent_tools import execute_tool
from services.llm import LLMCapabilities
from services.payroll import PayrollService

CAPABILITIES = LLMCapabilities(
    cache_breakpoint=False, pdf_document_blocks=False, refusal_stop_reason=False
)
THREAD = {"thread": SimpleNamespace(id="thread-1")}


def _tool(name, arguments, tool_context=THREAD):
    return execute_tool(
        name,
        arguments,
        actor="agent",
        capabilities=CAPABILITIES,
        tool_context=tool_context,
    )


def _register(ledger_service, **overrides):
    arguments = {
        "name": "Stefan Wikner",
        "personal_number": "198112189876",
        "bank_account": "8327-9123456789",
        "email": "stefan@example.com",
        **overrides,
    }
    return _tool("registrera_anstalld", arguments)


def _voucher_count():
    return db.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0]


def test_personal_number_is_normalized_and_checked():
    assert normalize_personal_number("198112189876") == "19811218-9876"
    assert normalize_personal_number("19811218+9876") == "19811218-9876"
    # A samordningsnummer: the day plus 60.
    assert normalize_personal_number("19811278-9873") == "19811278-9873"
    for wrong in ["8112189876", "19811218-9875", "19811318-9876", "abc"]:
        with pytest.raises(ValidationError) as error:
            normalize_personal_number(wrong)
        assert error.value.code == "invalid_personal_number"


def test_mask_trailing():
    assert mask_trailing("19811218-9876") == "*********9876"
    assert mask_trailing(None) is None


def test_registrera_anstalld_stores_the_full_number_and_returns_it_masked(
    ledger_service,
):
    employee = _register(ledger_service)

    assert employee["personal_number"] == "*********9876"
    assert employee["bank_account"] == "***********6789"
    assert employee["salary"] is None
    stored = PayrollService().employees.get(employee["id"])
    assert stored.personal_number == "19811218-9876"
    assert stored.bank_account == "8327-9123456789"


def test_registrera_anstalld_with_id_keeps_the_fields_left_out(ledger_service):
    employee = _register(ledger_service)

    _tool(
        "registrera_anstalld",
        {"employee_id": employee["id"], "bank_account": "8327-1111111111"},
    )

    stored = PayrollService().employees.get(employee["id"])
    assert stored.name == "Stefan Wikner"
    assert stored.personal_number == "19811218-9876"
    assert stored.bank_account == "8327-1111111111"


def test_registrera_anstalld_refuses_a_wrong_check_digit(ledger_service):
    with pytest.raises(ValidationError) as error:
        _register(ledger_service, personal_number="19811218-9875")
    assert error.value.code == "invalid_personal_number"
    assert PayrollService().employees.list_all() == []


@pytest.mark.parametrize(
    "name, arguments",
    [
        ("registrera_anstalld", {"name": "Stefan Wikner"}),
        (
            "satt_lon",
            {"employee_id": "x", "gross_monthly_salary": 1, "preliminary_tax": 0},
        ),
        ("skapa_lonekorning", {"year": 2026, "month": 10}),
    ],
)
def test_the_writing_tools_refuse_outside_a_thread(ledger_service, name, arguments):
    """An underlag in the intake queue must not be able to set up payroll."""
    for context in (None, {"agent_run_id": "run-1"}):
        with pytest.raises(ValidationError) as error:
            _tool(name, arguments, tool_context=context)
        assert error.value.code == "payroll_requires_thread"


def test_satt_lon_defaults_to_the_full_employer_fee(ledger_service):
    employee = _register(ledger_service)

    result = _tool(
        "satt_lon",
        {
            "employee_id": employee["id"],
            "gross_monthly_salary": 4_000_000,
            "preliminary_tax": 1_000_000,
        },
    )

    assert result["salary"]["employer_fee_rate_bp"] == 3142
    assert result["salary"]["employer_fee"] == 1_256_800
    assert result["salary"]["payment_day"] == 25


def test_skapa_lonekorning_creates_payslips_and_books_nothing(ledger_service):
    employee = _register(ledger_service)
    _tool(
        "satt_lon",
        {
            "employee_id": employee["id"],
            "gross_monthly_salary": 4_000_000,
            "preliminary_tax": 1_000_000,
        },
    )
    vouchers_before = _voucher_count()

    run = _tool("skapa_lonekorning", {"year": 2026, "month": 10})

    assert run["payment_date"] == "2026-10-25"
    assert run["status"] == "generated"
    [payslip] = run["payslips"]
    assert payslip["gross_salary"] == 4_000_000
    assert payslip["net_salary"] == 3_000_000
    assert payslip["employer_fee"] == 1_256_800
    assert payslip["voucher_id"] is None
    assert payslip["pdf_path"] == f"/api/v1/export/pdf/payslip/{payslip['id']}"
    assert _voucher_count() == vouchers_before

    with pytest.raises(ValidationError) as error:
        _tool("skapa_lonekorning", {"year": 2026, "month": 10})
    assert error.value.code == "payroll_run_already_exists"


def test_skapa_lonekorning_without_a_salary_leaves_no_run(ledger_service):
    _register(ledger_service)

    with pytest.raises(ValidationError) as error:
        _tool("skapa_lonekorning", {"year": 2026, "month": 10})

    assert error.value.code == "no_active_salary_settings"
    assert PayrollService().runs.list_all() == []


def test_las_loner_reads_employees_runs_and_the_agi(ledger_service):
    employee = _register(ledger_service)
    _tool(
        "satt_lon",
        {
            "employee_id": employee["id"],
            "gross_monthly_salary": 4_000_000,
            "preliminary_tax": 1_000_000,
        },
    )
    _tool("skapa_lonekorning", {"year": 2026, "month": 10})

    # Read-only, so it works without a thread too.
    result = _tool("las_loner", {"year": 2026, "month": 10}, tool_context=None)

    [read_employee] = result["employees"]
    assert read_employee["personal_number"] == "*********9876"
    assert read_employee["salary"]["gross_monthly_salary"] == 4_000_000
    [run] = result["payroll_runs"]
    assert len(run["payslips"]) == 1
    agi = result["agi"]
    assert agi["due_date"] == "2026-11-12"
    assert agi["total_preliminary_tax"] == 1_000_000
    assert agi["unbooked_payslips"] == 1
    assert "personal_number" not in agi["individuals"][0]

    assert "agi" not in _tool("las_loner", {})
    with pytest.raises(ValidationError):
        _tool("las_loner", {"year": 2026})
