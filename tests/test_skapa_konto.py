"""`skapa_konto`: the agent adds an account to the kontoplan, never changes one."""

import pytest
from fastapi.testclient import TestClient

from db.database import db
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from services.agent_tools import execute_tool
from services.llm import LLMCapabilities


def _capabilities():
    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


def _execute(arguments: dict):
    return execute_tool(
        "skapa_konto", arguments, actor="agent", capabilities=_capabilities()
    )


def _audit_rows(code: str):
    return db.execute(
        "SELECT action, actor FROM audit_log "
        "WHERE entity_type = 'account' AND entity_id = ?",
        (code,),
    ).fetchall()


def test_creates_the_account_and_logs_it(test_db):
    result = _execute(
        {
            "code": "6981",
            "name": "Föreningsavgifter, avdragsgilla",
            "account_type": "expense",
        }
    )

    assert result["code"] == "6981" and result["account_type"] == "expense"
    account = AccountRepository.get("6981")
    assert account is not None and account.name == "Föreningsavgifter, avdragsgilla"
    assert [tuple(r) for r in _audit_rows("6981")] == [("created", "agent")]


def test_an_existing_account_is_never_changed(test_db):
    AccountRepository.create("6982", "Original", "expense")

    with pytest.raises(ValidationError) as exc:
        _execute({"code": "6982", "name": "Nytt namn", "account_type": "revenue"})

    assert exc.value.code == "account_exists"
    account = AccountRepository.get("6982")
    assert account.name == "Original" and account.account_type.value == "expense"


@pytest.mark.parametrize(
    "arguments, code",
    [
        (
            {"code": "698", "name": "X", "account_type": "expense"},
            "invalid_account_code",
        ),
        (
            {"code": "9001", "name": "X", "account_type": "expense"},
            "invalid_account_code",
        ),
        (
            {"code": "69A1", "name": "X", "account_type": "expense"},
            "invalid_account_code",
        ),
        (
            {"code": "6983", "name": "X", "account_type": "correction"},
            "invalid_tool_arguments",
        ),
        (
            {"code": "6983", "name": "X", "account_type": "expense", "vat_code": "M9"},
            "invalid_tool_arguments",
        ),
    ],
)
def test_invalid_arguments_are_refused(test_db, arguments, code):
    with pytest.raises(ValidationError) as exc:
        _execute(arguments)
    assert exc.value.code == code
    assert not AccountRepository.exists(arguments["code"])


def test_route_creates_and_refuses_a_duplicate_with_409(test_db, auth_headers):
    from api.main import app

    client = TestClient(app)
    body = {"code": "6984", "name": "Testkonto", "account_type": "expense"}

    created = client.post("/api/v1/accounts", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    again = client.post("/api/v1/accounts", json=body, headers=auth_headers)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "account_exists"
    bad = client.post(
        "/api/v1/accounts",
        json={**body, "code": "6985", "account_type": "x"},
        headers=auth_headers,
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "invalid_account_type"
