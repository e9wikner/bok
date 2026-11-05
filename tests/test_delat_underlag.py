"""One underlag, several vouchers (migration 044).

BFL wants an underlag behind every voucher, not each underlag behind only one:
a loan agreement supports every amortisation, an annual invoice every month it
is accrued over. The server still never links an already linked underlag on
its own -- that is how one receipt is booked twice -- so a further link needs
a human's press: a `foresla_delat_underlag` card (once, or approved for the
fiscal year), or a voucher proposal card that says the underlag is shared.

Built on `tests/test_flode_underlag.py`'s helpers; no LLM.
"""

from datetime import date

import pytest

from db.database import db
from domain.types import IntakeStatus
from repositories.intake_repo import IntakeRepository
from repositories.intake_reuse_repo import ReuseApprovalRepository
from repositories.period_repo import PeriodRepository
from services.auth import AuthService
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    a118,
    interpret,
    make_source,
    make_thread,
    posted_purchase,
)

accounts = fu.accounts
client = fu.client
period_id = fu.period_id
auth_headers = fu.auth_headers


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


def _tool(name: str, arguments: dict, thread=None):
    from services.agent_tools import execute_tool
    from services.llm import LLMCapabilities

    return execute_tool(
        name,
        arguments,
        actor="agent",
        capabilities=LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
            streaming=True,
        ),
        tool_context={"thread": thread} if thread is not None else None,
    )


def _shared(period_id: str):
    """A loan agreement linked to A-1 on an exact match, and a second posted
    voucher it should support too: `(source, first, second)`."""
    from services.intake_link import IntakeLinkService

    first = a118(period_id)
    source_id = make_source(filename="laneavtal.pdf", mime_type="image/jpeg")
    interpret(source_id, "exact")
    IntakeLinkService().link(source_id, first, actor="agent")
    second = posted_purchase(period_id, day=20)
    return source_id, first, second


def _linked_to(source_id: str) -> set:
    return {lk.voucher_id for lk in IntakeRepository.list_links_for_source(source_id)}


def _answer(client, headers, decision_id: str, option_id: str):
    return client.post(
        f"/api/v1/decisions/{decision_id}/answer",
        json={"option_id": option_id},
        headers=headers,
    )


def _card(period_id: str, source_id: str, voucher_id: str):
    from repositories.decision_repo import DecisionRepository

    thread = make_thread(period_id)
    result = _tool(
        "foresla_delat_underlag",
        {
            "source_id": source_id,
            "voucher_id": voucher_id,
            "reason": "Amortering enligt låneavtalet.",
        },
        thread,
    )
    decision = DecisionRepository.get(result["decision_id"])
    assert decision is not None
    return thread, decision


# --- the guard: never on the agent's word alone ------------------------------


def test_an_already_linked_underlag_is_not_linked_again_without_a_human(period_id):
    from services.intake_link import IntakeLinkService, LinkConflictError

    source_id, first, second = _shared(period_id)
    interpret(source_id, "exact", expected_voucher_id=second)

    with pytest.raises(LinkConflictError) as excinfo:
        IntakeLinkService().link(source_id, second, actor="agent")
    assert excinfo.value.code == "intake_already_linked"
    assert "foresla_delat_underlag" in excinfo.value.details
    assert _linked_to(source_id) == {first}


def test_posting_on_an_already_linked_underlag_is_refused(period_id):
    from services.intake import IntakeConflictError, IntakeService

    source_id, _first, _second = _shared(period_id)
    with pytest.raises(IntakeConflictError) as excinfo:
        IntakeService().ensure_source_ready_for_voucher_link(source_id)
    assert excinfo.value.code == "intake_already_linked"


def test_the_exact_match_never_links_an_underlag_that_supports_a_voucher(period_id):
    """The automatic link is for new underlag: once linked, a match is no
    longer open, so the intake pass leaves it alone."""
    from repositories.voucher_repo import VoucherRepository

    source_id, _first, second = _shared(period_id)
    assert VoucherRepository.match_still_open(second, source_id) is False


# --- the card -----------------------------------------------------------------


def test_the_card_has_once_standing_and_no(period_id):
    source_id, first, second = _shared(period_id)
    _thread, decision = _card(period_id, source_id, second)

    titles = [o.title for o in decision.options]
    assert titles[0].startswith("Koppla till A-")
    assert titles[1] == "Koppla, och godkänn för kommande verifikationer"
    assert "2026-12-31" in decision.options[1].rationale
    assert decision.options[2].is_exit
    assert _linked_to(source_id) == {first}


def test_the_card_is_for_a_shared_underlag_only(period_id):
    from domain.validation import ValidationError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    with pytest.raises(ValidationError) as excinfo:
        _card(period_id, source_id, voucher_id)
    assert excinfo.value.code == "source_not_shared"


def test_the_api_key_cannot_answer_the_card(client, auth_headers, period_id):
    source_id, first, second = _shared(period_id)
    _thread, decision = _card(period_id, source_id, second)

    response = _answer(client, auth_headers, decision.id, decision.options[0].id)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_only"
    assert _linked_to(source_id) == {first}


def test_once_links_and_approves_nothing(client, human_headers, period_id):
    source_id, first, second = _shared(period_id)
    _thread, decision = _card(period_id, source_id, second)

    response = _answer(client, human_headers, decision.id, decision.options[0].id)
    assert response.status_code == 202, response.text
    assert _linked_to(source_id) == {first, second}
    assert IntakeRepository.get_source(source_id).status == IntakeStatus.PROCESSED
    assert ReuseApprovalRepository.list_for_source(source_id) == []

    # A third voucher is asked for again.
    from services.intake_link import IntakeLinkService, LinkConflictError

    third = posted_purchase(period_id, day=25)
    with pytest.raises(LinkConflictError):
        IntakeLinkService().link(source_id, third, actor="agent")


def test_no_links_nothing(client, human_headers, period_id):
    source_id, first, second = _shared(period_id)
    _thread, decision = _card(period_id, source_id, second)

    response = _answer(client, human_headers, decision.id, decision.options[2].id)
    assert response.status_code == 202
    assert _linked_to(source_id) == {first}


# --- the standing approval ----------------------------------------------------


def _approved(client, human_headers, period_id):
    source_id, first, second = _shared(period_id)
    _thread, decision = _card(period_id, source_id, second)
    response = _answer(client, human_headers, decision.id, decision.options[1].id)
    assert response.status_code == 202, response.text
    return source_id, first, second, decision


def test_standing_approval_lets_the_agent_link_within_the_fiscal_year(
    client, human_headers, period_id
):
    from repositories.intake_link_repo import IntakeLinkRepository
    from services.intake_link import IntakeLinkService

    source_id, first, second, decision = _approved(client, human_headers, period_id)
    [approval] = ReuseApprovalRepository.list_for_source(source_id)
    assert approval.is_active and approval.decision_id == decision.id

    third = posted_purchase(period_id, day=25)
    result = IntakeLinkService().link(source_id, third, actor="agent")
    assert result.basis == "decision" and result.decision_id == decision.id
    assert _linked_to(source_id) == {first, second, third}
    link = IntakeRepository.current_link(source_id, third)
    assert IntakeLinkRepository.get_for_link(link.id).decision_id == decision.id


def test_standing_approval_lets_the_agent_post_within_the_fiscal_year(
    client, human_headers, period_id
):
    from services.idempotency import IdempotencyService
    from services.voucher_posting import VoucherPostingRequest, post_agent_voucher

    source_id, first, second, _decision = _approved(client, human_headers, period_id)
    request = VoucherPostingRequest(
        series="A",
        date=date(2026, 3, 28),
        period_id=period_id,
        description="Amortering mars",
        rows=[
            {"account": "5410", "debit": 500000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 500000},
        ],
        intake_source_ids=[source_id],
    )
    response = post_agent_voucher(
        request,
        actor="agent",
        idempotency=IdempotencyService(),
        idempotency_key=None,
        endpoint="/agent/vouchers",
    )
    assert _linked_to(source_id) == {first, second, response["id"]}


def test_the_approval_ends_with_the_fiscal_year(client, human_headers, period_id):
    from services.intake_link import IntakeLinkService, LinkConflictError

    source_id, _first, _second, _decision = _approved(client, human_headers, period_id)
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2027, 1, 1), end_date=date(2027, 12, 31)
    )
    next_period = PeriodRepository.create_period(
        fiscal_year_id=fy.id,
        year=2027,
        month=3,
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 31),
    )
    db.commit()
    from services.ledger import LedgerService

    ledger = LedgerService()
    draft = ledger.create_voucher(
        series="A",
        date=date(2027, 3, 20),
        period_id=next_period.id,
        description="Amortering mars 2027",
        rows_data=[
            {"account": "5410", "debit": 500000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 500000},
        ],
        created_by="agent",
    )
    next_year = ledger.post_voucher(draft.id, actor="agent").id

    with pytest.raises(LinkConflictError) as excinfo:
        IntakeLinkService().link(source_id, next_year, actor="agent")
    assert excinfo.value.code == "intake_already_linked"


def test_a_human_revokes_the_approval(client, auth_headers, human_headers, period_id):
    from services.intake_link import IntakeLinkService, LinkConflictError

    source_id, first, second, _decision = _approved(client, human_headers, period_id)
    [approval] = ReuseApprovalRepository.list_for_source(source_id)
    url = f"/api/v1/intake/{source_id}/reuse-approvals/{approval.id}/revoke"

    refused = client.post(url, json={"reason": "Lånet är löst."}, headers=auth_headers)
    assert refused.status_code == 403

    response = client.post(
        url, json={"reason": "Lånet är löst."}, headers=human_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is False

    third = posted_purchase(period_id, day=25)
    with pytest.raises(LinkConflictError):
        IntakeLinkService().link(source_id, third, actor="agent")
    # Links made under it stay.
    assert _linked_to(source_id) == {first, second}

    detail = client.get(
        f"/api/v1/intake/workspace/voucher_source/{source_id}", headers=human_headers
    ).json()
    assert detail["reuse_approvals"][0]["revoke_reason"] == "Lånet är löst."


def test_approvals_are_append_only(client, human_headers, period_id):
    import sqlite3

    source_id, _first, _second, _decision = _approved(client, human_headers, period_id)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "UPDATE intake_reuse_approvals SET fiscal_year_id = 'x' "
            "WHERE intake_source_id = ?",
            (source_id,),
        )
    db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM intake_reuse_approvals")
    db.rollback()


# --- unlinking one of several -------------------------------------------------


def test_unlinking_one_of_two_keeps_the_source_processed(
    client, human_headers, period_id
):
    from services.intake_link import IntakeLinkService

    source_id, first, second = _shared(period_id)
    _thread, decision = _card(period_id, source_id, second)
    _answer(client, human_headers, decision.id, decision.options[0].id)

    IntakeLinkService().unlink(
        source_id, second, reason="Fel lån.", actor="stefan", human=True
    )
    assert _linked_to(source_id) == {first}
    assert IntakeRepository.get_source(source_id).status == IntakeStatus.PROCESSED

    IntakeLinkService().unlink(
        source_id, first, reason="Fel lån.", actor="stefan", human=True
    )
    assert _linked_to(source_id) == set()
    assert IntakeRepository.get_source(source_id).status == IntakeStatus.NEEDS_ATTENTION


# --- a voucher proposal on a shared underlag ----------------------------------


def test_a_proposal_card_names_what_the_underlag_supports_and_the_press_links(
    client, auth_headers, period_id
):
    from repositories.thread_draft_repo import ThreadDraftRepository
    from services.draft_service import DraftService

    source_id, first, _second = _shared(period_id)
    thread = make_thread(period_id)
    result = DraftService().propose(
        thread,
        description="Amortering mars",
        rows=[
            {"account": "5410", "debit": 500000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 500000},
        ],
        date=date(2026, 3, 28),
        period_id=period_id,
        intake_source_ids=[source_id],
    )
    draft = ThreadDraftRepository.get(result["draft_id"])
    assert draft.shared_intake_sources == {source_id: [first]}
    from repositories.thread_repo import ThreadRepository

    post = next(
        p for p in ThreadRepository.list_posts(thread.id) if p.id == draft.post_id
    )
    assert "laneavtal.pdf styrker redan A-" in post.body["footnote"]

    response = client.post(
        f"/api/v1/vouchers/{result['draft_id']}/post", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert _linked_to(source_id) == {first, result["draft_id"]}


def test_a_link_made_after_the_proposal_is_not_covered_by_its_press(
    client, auth_headers, human_headers, period_id
):
    from services.draft_service import DraftService

    source_id, first, second = _shared(period_id)
    thread = make_thread(period_id)
    result = DraftService().propose(
        thread,
        description="Amortering mars",
        rows=[
            {"account": "5410", "debit": 500000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 500000},
        ],
        date=date(2026, 3, 28),
        period_id=period_id,
        intake_source_ids=[source_id],
    )
    # Meanwhile the underlag is linked to another voucher on a card.
    _t, decision = _card(period_id, source_id, second)
    _answer(client, human_headers, decision.id, decision.options[0].id)

    response = client.post(
        f"/api/v1/vouchers/{result['draft_id']}/post", headers=auth_headers
    )
    assert response.status_code == 409, response.text
    assert _linked_to(source_id) == {first, second}
