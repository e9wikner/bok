"""Fiscal years: creating one, `foresla_rakenskapsar`, and underlag dated in a
locked period or outside every year (migration 041,
`services/fiscal_years.py`, `services/fiscal_year_proposal.py`)."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from config import settings
from domain.types import IntakeStatus
from domain.validation import ValidationError
from repositories.audit_repo import AuditRepository
from repositories.decision_repo import DecisionRepository
from repositories.fiscal_year_proposal_repo import FiscalYearProposalRepository
from repositories.intake_repo import IntakeRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.agent_tools import execute_tool
from services.fiscal_years import FiscalYearService
from services.llm import LLMCapabilities
from services.thread_service import ThreadService

FISCAL_YEARS_URL = "/api/v1/fiscal-years"
VOUCHERS_VIEW = "bocker.verifikationer"

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
def intake_dir(tmp_path):
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    yield settings.intake_dir
    settings.intake_dir = original


@pytest.fixture
def year_2026(test_db):
    return FiscalYearService().create(
        date(2026, 1, 1), date(2026, 12, 31), actor="test"
    )


def _upload(name: str = "kvitto.png"):
    from services.intake import IntakeService

    return IntakeService().create_source_from_upload_content(
        filename=name,
        content_type="image/png",
        content=uuid.uuid4().bytes,
        explanation=None,
        source_type="receipt",
        actor="dropzone",
    )


def _interpret(source_id: str, document_date: date, thread=None) -> dict:
    return execute_tool(
        "tolka_underlag",
        {
            "source_id": source_id,
            "document_date": document_date.isoformat(),
            "total_ore": 12500,
        },
        actor="agent",
        capabilities=_CAPABILITIES,
        tool_context={"thread": thread} if thread is not None else None,
    )


def _propose(document_date: date, source_ids=(), thread=None, **extra) -> dict:
    return execute_tool(
        "foresla_rakenskapsar",
        {
            "document_date": document_date.isoformat(),
            "source_ids": list(source_ids),
            **extra,
        },
        actor="agent",
        capabilities=_CAPABILITIES,
        tool_context={"thread": thread} if thread is not None else None,
    )


def _thread(fiscal_year):
    return ThreadRepository.get_or_create(
        view_key=VOUCHERS_VIEW, fiscal_year_id=fiscal_year.id, model="test-model"
    )


def _answer(client, auth_headers, decision_id: str, **body):
    return client.post(
        f"/api/v1/decisions/{decision_id}/answer", json=body, headers=auth_headers
    )


def _pending_ids() -> set:
    return {s.id for s in IntakeRepository.list_pending()}


# --- POST /fiscal-years -------------------------------------------------------


def test_create_takes_a_json_body_and_makes_one_period_per_month(
    client, auth_headers, test_db
):
    response = client.post(
        FISCAL_YEARS_URL,
        json={"start_date": "2026-07-15", "end_date": "2027-06-30"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    fiscal_year = response.json()
    periods = PeriodRepository.list_periods(fiscal_year["id"])
    assert len(periods) == 12
    assert periods[0].start_date == date(2026, 7, 15)
    assert periods[-1].end_date == date(2027, 6, 30)
    audit = AuditRepository.get_history("fiscal_year", fiscal_year["id"])
    assert [entry.action for entry in audit] == ["created"]


def test_create_no_longer_takes_query_parameters(client, auth_headers, test_db):
    response = client.post(
        f"{FISCAL_YEARS_URL}?start_date=2026-01-01&end_date=2026-12-31",
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_overlap_is_409_and_names_the_year(client, auth_headers, year_2026):
    response = client.post(
        FISCAL_YEARS_URL,
        json={"start_date": "2026-07-01", "end_date": "2027-06-30"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "fiscal_year_overlap"
    assert detail["fiscal_year"]["id"] == year_2026.id
    assert len(PeriodRepository.list_fiscal_years()) == 1


@pytest.mark.parametrize(
    "start, end, code",
    [
        ("2027-02-01", "2028-01-31", "fiscal_year_not_adjacent"),
        ("2027-01-01", "2028-07-31", "fiscal_year_too_long"),
        ("2027-12-31", "2027-01-01", "invalid_dates"),
    ],
)
def test_refusals_are_400_and_create_nothing(
    client, auth_headers, year_2026, start, end, code
):
    response = client.post(
        FISCAL_YEARS_URL,
        json={"start_date": start, "end_date": end},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == code
    assert len(PeriodRepository.list_fiscal_years()) == 1


def test_an_eighteen_month_year_and_the_year_before_the_first_are_allowed(
    client, auth_headers, year_2026
):
    after = client.post(
        FISCAL_YEARS_URL,
        json={"start_date": "2027-01-01", "end_date": "2028-06-30"},
        headers=auth_headers,
    )
    before = client.post(
        FISCAL_YEARS_URL,
        json={"start_date": "2025-01-01", "end_date": "2025-12-31"},
        headers=auth_headers,
    )
    assert (after.status_code, before.status_code) == (201, 201)


def test_a_failure_halfway_leaves_no_year_without_periods(test_db, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(PeriodRepository, "create_period", boom)
    with pytest.raises(RuntimeError):
        FiscalYearService().create(date(2026, 1, 1), date(2026, 12, 31), actor="t")
    assert PeriodRepository.list_fiscal_years() == []


# --- suggest and placement ------------------------------------------------------


def test_suggest_is_twelve_months_next_to_the_books(year_2026):
    service = FiscalYearService()
    assert service.suggest(date(2027, 3, 4)) == (date(2027, 1, 1), date(2027, 12, 31))
    assert service.suggest(date(2025, 3, 4)) == (date(2025, 1, 1), date(2025, 12, 31))


@pytest.mark.parametrize(
    "day, code",
    [
        (date(2026, 5, 5), "fiscal_year_exists"),
        (date(2028, 2, 1), "document_date_too_far"),
    ],
)
def test_suggest_refuses(year_2026, day, code):
    with pytest.raises(ValidationError) as excinfo:
        FiscalYearService().suggest(day)
    assert excinfo.value.code == code


def test_suggest_without_any_year_is_no_fiscal_year(test_db):
    with pytest.raises(ValidationError) as excinfo:
        FiscalYearService().suggest(date(2026, 5, 5))
    assert excinfo.value.code == "no_fiscal_year"


def test_placement_open_and_outside(year_2026):
    service = FiscalYearService()
    assert service.placement(date(2026, 5, 5))["status"] == "open"
    outside = service.placement(date(2027, 1, 15))
    assert outside["status"] == "no_fiscal_year"
    assert outside["suggested_fiscal_year"] == {
        "start_date": "2027-01-01",
        "end_date": "2027-12-31",
    }


def test_placement_in_a_locked_period_names_the_first_open_one(year_2026):
    from services.ledger import LedgerService

    periods = PeriodRepository.list_periods(year_2026.id)
    LedgerService().lock_period(periods[2].id, actor="människa")  # March

    placement = FiscalYearService().placement(
        date(2026, 3, 10), today=date(2026, 4, 20)
    )

    assert placement["status"] == "period_locked"
    assert placement["locked_by"] == "människa"
    assert placement["first_open_period"]["name"] == "2026-04"
    assert placement["suggested_date"] == "2026-04-20"


def test_placement_in_a_locked_year_points_into_the_next_year(year_2026):
    from services.ledger import LedgerService

    next_year = FiscalYearService().create(
        date(2027, 1, 1), date(2027, 12, 31), actor="t"
    )
    LedgerService().lock_fiscal_year(year_2026.id, actor="människa")

    placement = FiscalYearService().placement(
        date(2026, 11, 3), today=date(2026, 12, 1)
    )

    assert placement["status"] == "fiscal_year_locked"
    assert placement["first_open_period"]["name"] == "2027-01"
    # Today is not in that period: its first day is suggested.
    assert placement["suggested_date"] == "2027-01-01"
    assert placement["fiscal_year"]["id"] == year_2026.id
    assert next_year.id != year_2026.id


def test_tolka_underlag_answers_with_the_placement(year_2026, intake_dir):
    source = _upload()
    result = _interpret(source.id, date(2027, 1, 15))
    assert result["placement"]["status"] == "no_fiscal_year"


# --- foresla_rakenskapsar ------------------------------------------------------


def test_in_a_thread_the_card_goes_in_that_thread(year_2026, intake_dir):
    thread = _thread(year_2026)
    source = _upload()

    result = _propose(date(2027, 1, 15), [source.id], thread=thread)

    assert (result["start_date"], result["end_date"]) == ("2027-01-01", "2027-12-31")
    assert result["existing_card"] is False
    decision = DecisionRepository.get(result["decision_id"])
    assert decision.thread_id == thread.id
    assert decision.kind == "approval"
    assert decision.title == "Skapa räkenskapsår 2027-01-01 – 2027-12-31?"
    assert [o.title for o in decision.options] == ["Skapa räkenskapsåret", "Inte nu"]
    assert decision.options[0].recommended and decision.options[1].is_exit
    assert "2027-01-15" in decision.reason
    # Proposing creates no year.
    assert len(PeriodRepository.list_fiscal_years()) == 1


def test_a_second_underlag_joins_the_pending_card(year_2026, intake_dir):
    first, second = _upload("a.png"), _upload("b.png")

    one = _propose(date(2027, 1, 15), [first.id])
    two = _propose(date(2027, 3, 2), [second.id])

    assert two["existing_card"] is True
    assert two["decision_id"] == one["decision_id"]
    assert set(two["waiting_source_ids"]) == {first.id, second.id}
    assert DecisionRepository.count(status="open", view_key=VOUCHERS_VIEW) == 1


def test_from_the_intake_pass_the_card_goes_in_verifikationer_and_the_file_waits(
    year_2026, intake_dir
):
    source = _upload()
    assert source.id in _pending_ids()

    result = _propose(date(2027, 1, 15), [source.id])

    thread = ThreadRepository.find(VOUCHERS_VIEW, year_2026.id)
    assert thread is not None
    assert DecisionRepository.get(result["decision_id"]).thread_id == thread.id
    # Out of the pass's queue, but still pending -- not failed, not in _Problem.
    assert source.id not in _pending_ids()
    assert IntakeRepository.count_pending() == 0
    assert IntakeRepository.get_source(source.id).status == IntakeStatus.PENDING


def test_refusals_from_the_tool(year_2026, intake_dir):
    with pytest.raises(ValidationError) as inside:
        _propose(date(2026, 6, 1))
    assert inside.value.code == "fiscal_year_exists"
    with pytest.raises(ValidationError) as unknown:
        _propose(date(2027, 1, 15), ["no-such-source"])
    assert unknown.value.code == "source_not_found"
    with pytest.raises(ValidationError) as overlapping:
        _propose(date(2027, 1, 15), start_date="2026-07-01", end_date="2027-06-30")
    assert overlapping.value.code == "fiscal_year_overlap"


def test_the_agent_may_give_other_dates_that_fit(year_2026, intake_dir):
    result = _propose(date(2027, 1, 15), start_date="2027-01-01", end_date="2028-06-30")
    assert result["end_date"] == "2028-06-30"


# --- the press -----------------------------------------------------------------


def test_pressing_create_makes_the_year_and_releases_the_underlag(
    client, auth_headers, year_2026, intake_dir
):
    source = _upload()
    result = _propose(date(2027, 1, 15), [source.id])
    decision = DecisionRepository.get(result["decision_id"])

    response = _answer(
        client, auth_headers, decision.id, option_id=decision.options[0].id
    )

    assert response.status_code == 202
    created = FiscalYearService.containing(date(2027, 1, 15))
    assert created is not None
    assert (created.start_date, created.end_date) == (
        date(2027, 1, 1),
        date(2027, 12, 31),
    )
    assert len(PeriodRepository.list_periods(created.id)) == 12
    proposal = FiscalYearProposalRepository.get(result["proposal_id"])
    assert (proposal.status, proposal.fiscal_year_id) == ("created", created.id)
    assert source.id in _pending_ids()
    receipt = ThreadRepository.list_posts(decision.thread_id)[-1]
    assert receipt.type == "receipt"
    assert receipt.body["title"] == "Räkenskapsår 2027-01-01 – 2027-12-31 skapat"


def test_declining_records_the_dropzone_file_as_failed_with_the_reason(
    client, auth_headers, year_2026, intake_dir
):
    thread = _thread(year_2026)
    dropped = _upload("dropzone.png")
    in_chat = _upload("chatt.png")
    ThreadService.record_user_file(
        thread,
        filename=in_chat.original_filename,
        size_bytes=in_chat.size_bytes,
        pages=None,
        intake_source_id=in_chat.id,
        actor="människa",
    )
    result = _propose(date(2027, 1, 15), [dropped.id, in_chat.id], thread=thread)
    decision = DecisionRepository.get(result["decision_id"])

    _answer(client, auth_headers, decision.id, option_id=decision.options[1].id)

    assert FiscalYearService.containing(date(2027, 1, 15)) is None
    assert FiscalYearProposalRepository.get(result["proposal_id"]).status == "declined"
    assert IntakeRepository.get_source(dropped.id).status == IntakeStatus.FAILED
    attempt = IntakeRepository.list_attempts_for_source(dropped.id)[-1]
    assert "valde att inte skapa" in attempt.error_detail
    # The thread's own file is the thread's to answer for.
    assert IntakeRepository.get_source(in_chat.id).status == IntakeStatus.PENDING


def test_a_free_text_answer_creates_nothing_and_a_new_card_carries_the_files(
    client, auth_headers, year_2026, intake_dir
):
    source = _upload()
    first = _propose(date(2027, 1, 15), [source.id])

    _answer(client, auth_headers, first["decision_id"], free_text="ja, gör det")

    assert FiscalYearService.containing(date(2027, 1, 15)) is None
    second = _propose(date(2027, 1, 15))
    assert second["decision_id"] != first["decision_id"]
    assert second["waiting_source_ids"] == [source.id]
    old = FiscalYearProposalRepository.get(first["proposal_id"])
    assert old.status == "superseded"
    assert source.id not in _pending_ids()


def test_a_year_created_in_between_gives_an_error_post_and_releases_the_files(
    client, auth_headers, year_2026, intake_dir
):
    source = _upload()
    result = _propose(date(2027, 1, 15), [source.id])
    decision = DecisionRepository.get(result["decision_id"])
    FiscalYearService().create(date(2027, 1, 1), date(2027, 6, 30), actor="människa")

    _answer(client, auth_headers, decision.id, option_id=decision.options[0].id)

    error = ThreadRepository.list_posts(decision.thread_id)[-1]
    assert error.type == "error"
    assert "kunde inte skapas" in error.body["cause"]
    assert FiscalYearProposalRepository.get(result["proposal_id"]).status == (
        "superseded"
    )
    assert source.id in _pending_ids()
    assert len(PeriodRepository.list_fiscal_years()) == 2


def test_another_decision_is_untouched_by_the_hook(client, auth_headers, year_2026):
    from services.decision_service import DecisionService

    decision = DecisionService().create(
        _thread(year_2026),
        title="Vilket konto?",
        reason="Oklart.",
        consequence="Inget bokfört.",
        options=[
            {"title": "5410", "rationale": "Inventarier.", "recommended": True},
            {"title": "Avstå", "rationale": "Inget.", "is_exit": True},
        ],
    )
    response = _answer(
        client, auth_headers, decision.id, option_id=decision.options[0].id
    )
    assert response.status_code == 202
    assert len(PeriodRepository.list_fiscal_years()) == 1


# --- underlag in a locked period, or outside every year --------------------------


def _locked_march(year):
    from services.ledger import LedgerService

    march = PeriodRepository.list_periods(year.id)[2]
    LedgerService().lock_period(march.id, actor="människa")
    return march


def test_the_pass_may_not_move_a_locked_period_underlag_to_another_date(
    year_2026, intake_dir
):
    _locked_march(year_2026)
    source = _upload()
    _interpret(source.id, date(2026, 3, 10))

    with pytest.raises(ValidationError) as excinfo:
        FiscalYearService().check_underlag_dates(
            [source.id], date(2026, 4, 1), decision_id=None, in_thread=False
        )
    assert excinfo.value.code == "underlag_in_locked_period"
    assert "registrera_avstaende" in excinfo.value.message


def test_in_a_thread_a_late_booking_needs_a_decision(year_2026, intake_dir):
    _locked_march(year_2026)
    source = _upload()
    _interpret(source.id, date(2026, 3, 10))
    service = FiscalYearService()

    with pytest.raises(ValidationError) as excinfo:
        service.check_underlag_dates(
            [source.id], date(2026, 4, 1), decision_id=None, in_thread=True
        )
    assert "be_om_beslut" in excinfo.value.message
    # With the user's decision behind it, the late booking may go ahead.
    service.check_underlag_dates(
        [source.id], date(2026, 4, 1), decision_id="d-1", in_thread=True
    )


def test_an_underlag_outside_every_year_is_never_dated_into_another(
    year_2026, intake_dir
):
    source = _upload()
    _interpret(source.id, date(2027, 1, 15))

    with pytest.raises(ValidationError) as excinfo:
        FiscalYearService().check_underlag_dates(
            [source.id], date(2026, 12, 31), decision_id="d-1", in_thread=True
        )
    assert excinfo.value.code == "underlag_outside_fiscal_years"
    assert "foresla_rakenskapsar" in excinfo.value.message


def test_posta_verifikation_holds_the_rule(year_2026, intake_dir):
    """The guard runs before anything is posted, through the tool itself."""
    from repositories.account_repo import AccountRepository

    for code, name, kind in [("1930", "Bank", "asset"), ("5410", "Inv", "expense")]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, kind)
    _locked_march(year_2026)
    april = PeriodRepository.list_periods(year_2026.id)[3]
    source = _upload()
    _interpret(source.id, date(2026, 3, 10))

    with pytest.raises(ValidationError) as excinfo:
        execute_tool(
            "posta_verifikation",
            {
                "date": "2026-04-01",
                "period_id": april.id,
                "description": "Kvitto",
                "rows": [
                    {"account": "5410", "debit": 12500},
                    {"account": "1930", "credit": 12500},
                ],
                "intake_source_ids": [source.id],
            },
            actor="agent",
            capabilities=_CAPABILITIES,
        )
    assert excinfo.value.code == "underlag_in_locked_period"


def test_an_uninterpreted_underlag_or_its_own_date_passes(year_2026, intake_dir):
    _locked_march(year_2026)
    source = _upload()
    FiscalYearService().check_underlag_dates(
        [source.id], date(2026, 4, 1), decision_id=None, in_thread=False
    )
    _interpret(source.id, date(2026, 3, 10))
    # Its own date: the ledger's `period_locked` answers that, as always.
    FiscalYearService().check_underlag_dates(
        [source.id], date(2026, 3, 10), decision_id=None, in_thread=False
    )


# --- warnings --------------------------------------------------------------------


def test_dropzone_status_warns_about_underlag_outside_every_year(
    client, auth_headers, year_2026, intake_dir
):
    waiting = _upload("väntar.png")
    outside = _upload("utanför.png")
    inside = _upload("innanför.png")
    _interpret(outside.id, date(2027, 2, 1))
    _interpret(inside.id, date(2026, 2, 1))
    _propose(date(2027, 1, 15), [waiting.id])

    response = client.get("/api/v1/intake/dropzone/status", headers=auth_headers)

    warnings = response.json()["date_warnings"]
    by_source = {w["source_id"]: w["code"] for w in warnings["underlag"]}
    assert by_source == {
        waiting.id: "waiting_for_fiscal_year",
        outside.id: "outside_fiscal_years",
    }
    assert warnings["bank_transactions_outside_fiscal_years"] == 0


def test_the_workspace_item_carries_the_date_warning(
    client, auth_headers, year_2026, intake_dir
):
    source = _upload()
    _interpret(source.id, date(2027, 2, 1))

    response = client.get(
        "/api/v1/intake/workspace?kind=voucher_source", headers=auth_headers
    )

    item = next(i for i in response.json()["items"] if i["id"] == source.id)
    assert item["date_warning"]["code"] == "outside_fiscal_years"
