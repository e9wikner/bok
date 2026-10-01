"""`flode-underlag`: the reference in the posting's transaction (FU10, §5,
D2, §9.2).

When a thread proposal is posted whose `decision_id` based a link, the
server writes a row in `voucher_source_references`: the difference voucher
(A-121) refers to the receipt through the voucher that carries the link
(A-118). The agent states nothing; the server looks it up. Test case
numbers refer to SPEC-flode-underlag.md §14.
"""

from repositories.intake_link_repo import VoucherSourceReferenceRepository
from repositories.voucher_repo import VoucherRepository
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    a118,
    interpret,
    make_decision,
    make_source,
    make_thread,
    table_rows,
)

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
period_id = fu.period_id

#: Alternative 1's difference: the pant, 120 kr, on 5410 against the bank.
_DIFFERENCE_ROWS = [
    {"account": "5410", "debit": 12000, "credit": 0},
    {"account": "1930", "debit": 0, "credit": 12000},
]


def _propose(thread, period_id: str, decision_id: str) -> str:
    """`foresla_verifikation` with the decision's id, as the turn after
    alternative 1 makes it (§9.2). Returns the draft's id."""
    from datetime import date

    from services.draft_service import DraftService

    result = DraftService().propose(
        thread,
        description="Korrigering pantavgift",
        rows=_DIFFERENCE_ROWS,
        date=date(2026, 3, 15),
        period_id=period_id,
        decision_id=decision_id,
    )
    return result["draft_id"]


def _post(client, auth_headers, draft_id: str):
    return client.post(f"/api/v1/vouchers/{draft_id}/post", headers=auth_headers)


def _linked_on_alternative_1(period_id: str):
    """A-118, the receipt linked to it on an answered decision (option 1)
    in the thread; returns (a118, source, thread, decision)."""
    from services.intake_link import IntakeLinkService

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=1)
    IntakeLinkService().link(
        source_id,
        voucher_id,
        decision_id=decision.id,
        actor="agent",
        thread_id=thread.id,
    )
    return voucher_id, source_id, thread, decision


# ---------------------------------------------------------------------------
# FU10 — the reference (§5, D2)
# ---------------------------------------------------------------------------


def test_42_posting_the_difference_writes_the_reference(
    client, auth_headers, period_id
):
    """The backend part of testfall 42: link first, then the proposal with
    the decision's id; `Posta` gives A-121 and a row in
    `voucher_source_references`, and A-121 does not lack underlag."""
    voucher_id, source_id, thread, decision = _linked_on_alternative_1(period_id)
    draft_id = _propose(thread, period_id, decision.id)

    resp = _post(client, auth_headers, draft_id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "posted"
    ref = VoucherSourceReferenceRepository.get_for_voucher(draft_id)
    assert ref is not None
    assert (ref.intake_source_id, ref.via_voucher_id, ref.decision_id) == (
        source_id,
        voucher_id,
        decision.id,
    )
    # Read again: the route's answer is built from the voucher as
    # `post_voucher` returned it, before `on_posting`'s hooks ran.
    posted = VoucherRepository.get(draft_id)
    assert posted is not None and posted.missing_attachment is False


def test_42b_a_decision_without_a_link_posts_as_usual(client, auth_headers, period_id):
    """Testfall 42b: a proposal whose decision based no link is posted as
    usual, without a reference."""
    a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=1)
    draft_id = _propose(thread, period_id, decision.id)

    resp = _post(client, auth_headers, draft_id)

    assert resp.status_code == 200, resp.text
    assert VoucherSourceReferenceRepository.get_for_voucher(draft_id) is None
    assert table_rows("voucher_source_references") == []


def test_fu10_a_proposal_without_a_decision_writes_no_reference(
    client, auth_headers, period_id
):
    from datetime import date

    from services.draft_service import DraftService

    _linked_on_alternative_1(period_id)
    thread = make_thread(period_id)
    draft_id = DraftService().propose(
        thread,
        description="Annat köp",
        rows=_DIFFERENCE_ROWS,
        date=date(2026, 3, 15),
        period_id=period_id,
    )["draft_id"]

    assert _post(client, auth_headers, draft_id).status_code == 200
    assert table_rows("voucher_source_references") == []


def test_fu10_reference_fails_the_whole_posting_rolls_back(
    client, auth_headers, period_id, monkeypatch
):
    """The insert fails -> no number taken, the draft is still a draft and
    its row `pending`: the reference is in the posting's transaction."""
    from repositories.thread_draft_repo import ThreadDraftRepository

    _voucher_id, _source_id, thread, decision = _linked_on_alternative_1(period_id)
    draft_id = _propose(thread, period_id, decision.id)

    def boom(*args, **kwargs):
        raise RuntimeError("reference insert failed")

    monkeypatch.setattr(VoucherSourceReferenceRepository, "insert", staticmethod(boom))
    resp = _post(client, auth_headers, draft_id)

    # An unexpected error is the route's 500 (`_post_and_record`).
    assert resp.status_code == 500
    assert "reference insert failed" in resp.text

    draft = VoucherRepository.get(draft_id)
    assert draft is not None
    assert (draft.status.value, draft.number) == ("draft", None)
    row = ThreadDraftRepository.get(draft_id)
    assert row is not None and row.status == "pending"
    assert table_rows("voucher_source_references") == []


def test_fu10_the_reference_is_the_servers_lookup_not_an_argument():
    """§9.2: `foresla_verifikation`'s arguments are unchanged -- nothing in
    them names a source or a reference."""
    from services.agent_tools import ForeslaVerifikationArgs

    assert "reference" not in " ".join(ForeslaVerifikationArgs.model_fields)
    assert "via_voucher_id" not in ForeslaVerifikationArgs.model_fields
