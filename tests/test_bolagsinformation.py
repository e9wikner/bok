"""`foresla_bolagsinformation`: company details proposed as a decision card
(migration 042, `services/company_info_proposal.py`)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from domain.validation import ValidationError
from repositories.company_info_proposal_repo import CompanyInfoProposalRepository
from repositories.company_info_repo import CompanyInfoRepository
from repositories.decision_repo import DecisionRepository
from repositories.thread_repo import ThreadRepository
from services.agent_tools import execute_tool
from services.fiscal_years import FiscalYearService
from services.llm import LLMCapabilities

_CAPABILITIES = LLMCapabilities(
    cache_breakpoint=True,
    pdf_document_blocks=True,
    refusal_stop_reason=True,
    streaming=False,
)


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def thread(test_db):
    year = FiscalYearService().create(date(2026, 1, 1), date(2026, 12, 31), actor="t")
    return ThreadRepository.get_or_create(
        view_key="bocker.verifikationer", fiscal_year_id=year.id, model="test-model"
    )


def _propose(thread, **fields) -> dict:
    return execute_tool(
        "foresla_bolagsinformation",
        fields,
        actor="agent",
        capabilities=_CAPABILITIES,
        tool_context={"thread": thread} if thread is not None else None,
    )


def _answer(client, auth_headers, decision_id: str, **body):
    return client.post(
        f"/api/v1/decisions/{decision_id}/answer", json=body, headers=auth_headers
    )


def _set(**values) -> None:
    """Stored details, committed so that the request's own connection sees them."""
    from db.database import db

    CompanyInfoRepository.set_values(values)
    db.commit()


def _stored() -> dict:
    return CompanyInfoRepository.get_all()


def test_proposing_writes_nothing_and_raises_one_card(thread):
    result = _propose(thread, seat="Göteborg", bankgiro="679-9423", f_skatt=True)

    assert result["status"] == "pending"
    assert result["fill"] == {
        "seat": "Göteborg",
        "bankgiro": "679-9423",
        "f_skatt": "true",
    }
    assert result["overwrite"] == {}
    assert "seat" not in _stored()
    decision = DecisionRepository.get(result["decision_id"])
    assert decision.thread_id == thread.id
    assert [o.title for o in decision.options] == ["Fyll i uppgifterna", "Inte nu"]
    assert "Säte Göteborg" in decision.reason


def test_it_refuses_outside_a_thread_and_with_no_fields(thread):
    with pytest.raises(ValidationError) as no_thread:
        _propose(None, seat="Göteborg")
    assert no_thread.value.code == "company_info_requires_thread"
    with pytest.raises(ValidationError) as empty:
        _propose(thread)
    assert empty.value.code == "no_company_fields"


def test_the_fill_press_writes_the_values_and_a_receipt(client, auth_headers, thread):
    result = _propose(thread, seat="Göteborg", vat_number="SE556819473101")
    decision = DecisionRepository.get(result["decision_id"])

    response = _answer(
        client, auth_headers, decision.id, option_id=decision.options[0].id
    )

    assert response.status_code == 202
    assert _stored()["seat"] == "Göteborg"
    assert _stored()["vat_number"] == "SE556819473101"
    proposal = CompanyInfoProposalRepository.get(result["proposal_id"])
    assert proposal.status == "applied"
    receipt = ThreadRepository.list_posts(thread.id)[-1]
    assert receipt.type == "receipt"
    assert receipt.body["title"] == "Bolagsuppgifterna sparade"


def test_declining_writes_nothing(client, auth_headers, thread):
    result = _propose(thread, seat="Göteborg")
    decision = DecisionRepository.get(result["decision_id"])

    _answer(client, auth_headers, decision.id, option_id=decision.options[1].id)

    assert "seat" not in _stored()
    assert CompanyInfoProposalRepository.get(result["proposal_id"]).status == (
        "declined"
    )


def test_a_differing_stored_value_is_only_replaced_on_the_overwrite_option(
    client, auth_headers, thread
):
    _set(seat="Stockholm")
    result = _propose(thread, seat="Göteborg", bankgiro="679-9423")
    assert result["fill"] == {"bankgiro": "679-9423"}
    assert result["overwrite"] == {"seat": "Göteborg"}
    decision = DecisionRepository.get(result["decision_id"])
    assert [o.title for o in decision.options] == [
        "Fyll i tomma fält",
        "Fyll i och skriv över",
        "Inte nu",
    ]
    assert "Stockholm → Göteborg" in decision.reason

    _answer(client, auth_headers, decision.id, option_id=decision.options[0].id)

    assert _stored()["seat"] == "Stockholm"
    assert _stored()["bankgiro"] == "679-9423"


def test_the_overwrite_option_replaces(client, auth_headers, thread):
    _set(seat="Stockholm")
    result = _propose(thread, seat="Göteborg")
    decision = DecisionRepository.get(result["decision_id"])
    assert [o.title for o in decision.options] == ["Fyll i och skriv över", "Inte nu"]

    _answer(client, auth_headers, decision.id, option_id=decision.options[0].id)

    assert _stored()["seat"] == "Göteborg"


def test_a_field_filled_meanwhile_is_not_overwritten_by_the_fill_press(
    client, auth_headers, thread
):
    result = _propose(thread, seat="Göteborg", bankgiro="679-9423")
    _set(seat="Malmö")
    decision = DecisionRepository.get(result["decision_id"])

    _answer(client, auth_headers, decision.id, option_id=decision.options[0].id)

    assert _stored()["seat"] == "Malmö"
    assert _stored()["bankgiro"] == "679-9423"
    receipt = ThreadRepository.list_posts(thread.id)[-1]
    assert "Hoppade över Säte" in receipt.body["note"]


def test_nothing_new_raises_no_card(thread):
    _set(seat="Göteborg")
    assert _propose(thread, seat="Göteborg")["status"] == "unchanged"


def test_a_new_proposal_supersedes_the_pending_one(thread):
    first = _propose(thread, seat="Göteborg")
    second = _propose(thread, seat="Göteborg", bankgiro="679-9423")

    assert CompanyInfoProposalRepository.get(first["proposal_id"]).status == (
        "superseded"
    )
    assert DecisionRepository.get(first["decision_id"]).status == "superseded"
    assert DecisionRepository.get(second["decision_id"]).status == "open"
