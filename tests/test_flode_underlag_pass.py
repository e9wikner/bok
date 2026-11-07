"""`flode-underlag` and the intake pass: the thread owns its files (FU11,
D4, §11.3) and the scripted flows (FU18, testfall 39-42).

Test case numbers refer to SPEC-flode-underlag.md §14. No real LLM: the
pass and the thread turns run with `agentruntime`'s scripted client.
"""

import itertools

import pytest

from config import settings
from db.database import db
from repositories.intake_repo import IntakeRepository
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    _READS,
    a118,
    link_options,
    make_source,
    make_thread,
    table_rows,
    voucher_number,
)

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
intake_dir = fu.intake_dir
period_id = fu.period_id


def _dropped_in_thread(thread, source_id: str) -> None:
    """A `user_file` post for *source_id*, as `POST /threads/{vk}/messages`
    with an attachment writes it."""
    from services.thread_service import ThreadService

    ThreadService.record_user_file(
        thread,
        filename="kvitto.jpg",
        size_bytes=1024,
        actor="stefan",
        intake_source_id=source_id,
    )


def _counting(monkeypatch):
    from db.database import db

    calls: list = []
    original = db.execute

    def counting(sql, *args, **kwargs):
        calls.append(sql)
        return original(sql, *args, **kwargs)

    monkeypatch.setattr(db, "execute", counting)
    return calls


# ---------------------------------------------------------------------------
# FU11 — the pass skips the thread's files (D4, §11.3)
# ---------------------------------------------------------------------------


def test_38_list_pending_skips_a_source_dropped_in_a_thread(period_id, monkeypatch):
    """Testfall 38: the source with a `user_file` post is not listed, the
    other is; one query each for the list and the count."""
    in_thread = make_source()
    queued = make_source()
    _dropped_in_thread(make_thread(period_id), in_thread)

    calls = _counting(monkeypatch)
    listed = IntakeRepository.list_pending()
    counted = IntakeRepository.count_pending()

    assert [s.id for s in listed] == [queued]
    assert counted == 1
    assert len(calls) == 2
    assert all("user_file" in sql for sql in calls)


def test_38_the_intake_page_still_shows_both(client, auth_headers, period_id):
    """`GET /intake/workspace` reads `list_by_status`: the intake page's
    queue is not the pass's."""
    in_thread = make_source()
    queued = make_source()
    _dropped_in_thread(make_thread(period_id), in_thread)

    resp = client.get(
        "/api/v1/intake/workspace",
        headers=auth_headers,
        params={"status": "pending", "kind": "voucher_source"},
    )

    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert {in_thread, queued} <= ids


def test_fu11_las_underlag_and_the_agent_queue_follow(client, auth_headers, period_id):
    """Avvikelse 3: `las_underlag`, `GET /agent/intake/pending` and the
    status's `queue_depth` read the same queue -- the thread owns the file
    there too."""
    from services.agent_tools import execute_tool
    from services.llm import LLMCapabilities

    in_thread = make_source()
    queued = make_source()
    _dropped_in_thread(make_thread(period_id), in_thread)

    tool = execute_tool(
        "las_underlag",
        {},
        actor="agent",
        capabilities=LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
            streaming=True,
        ),
    )
    http = client.get("/api/v1/agent/intake/pending", headers=auth_headers)

    assert [item["id"] for item in tool["items"]] == [queued]
    assert tool["total"] == 1
    assert http.status_code == 200, http.text
    assert [item["id"] for item in http.json()["items"]] == [queued]


def test_fu11_a_user_text_post_does_not_take_the_source(period_id):
    """Only a `user_file` post naming the source takes it out."""
    from repositories.thread_repo import ThreadRepository

    source_id = make_source()
    ThreadRepository.add_post(
        thread_id=make_thread(period_id).id,
        post_type="user_text",
        actor="stefan",
        body={"text": f"Kvittot {source_id}", "intake_source_id": source_id},
    )

    assert [s.id for s in IntakeRepository.list_pending()] == [source_id]


# ---------------------------------------------------------------------------
# FU18 — the scripted flows (testfall 39-42)
# ---------------------------------------------------------------------------
#
# The instruction's path, step by step, with `agentruntime`'s scripted
# client: they show that the path holds when the model follows the
# instruction, not that a real model does (§14, criterion 7).

_ids = itertools.count(1)


def _turn(name: str, arguments: dict, text: str = ""):
    from services.llm import LLMTurn, ToolCall, Usage

    return LLMTurn(
        text=text,
        tool_calls=[ToolCall(id=f"call-{next(_ids)}", name=name, arguments=arguments)],
        stop="tool_calls",
        usage=Usage(10, 10, 0),
    )


def _end(text: str):
    from services.llm import LLMTurn, Usage

    return LLMTurn(text=text, tool_calls=[], stop="end", usage=Usage(10, 10, 0))


def _client(turns: list):
    from services.llm import LLMCapabilities
    from tests.test_agent_runtime import FakeLLMClient

    return FakeLLMClient(
        turns,
        LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
            streaming=True,
        ),
    )


def _upload_receipt(content: bytes = b"\x89PNG\r\n\x1a\n kvitto") -> str:
    """A receipt image in the intake root, as `POST /intake` stores it."""
    from services.intake import IntakeService

    return (
        IntakeService()
        .create_source_from_upload_content(
            filename="kvitto.png",
            content_type="image/png",
            content=content,
            explanation=None,
            source_type="receipt",
            actor="stefan",
        )
        .id
    )


def _tolka_args(source_id: str, kind: str) -> dict:
    return {**_READS[kind], "source_id": source_id}


def _vouchers() -> list:
    return table_rows("vouchers")


def _source_status(source_id: str) -> str:
    source = IntakeRepository.get_source(source_id)
    assert source is not None
    return source.status.value


def test_39_scripted_pass_links_an_exact_match(period_id, intake_dir):
    """Testfall 39: the pass reads the receipt, interprets it -- exact on
    A-118 -- and links it: no new voucher, no abstention."""
    from repositories.intake_link_repo import IntakeLinkRepository
    from services.agent_runtime import AgentWorker

    voucher_id = a118(period_id)
    source_id = _upload_receipt()
    vouchers = _vouchers()
    client = _client(
        [
            _turn("tolka_underlag", _tolka_args(source_id, "exact")),
            _turn(
                "koppla_underlag", {"source_id": source_id, "voucher_id": voucher_id}
            ),
            _end(f"Kopplat till {voucher_number(voucher_id)}."),
        ]
    )

    run = AgentWorker().run_pass_once(client_factory=lambda model: client)

    assert run is not None
    assert _vouchers() == vouchers
    basis = IntakeLinkRepository.get_for_source(source_id)
    assert basis is not None
    assert (basis.basis, basis.voucher_id, basis.agent_run_id) == (
        "exact_match",
        voucher_id,
        run.id,
    )
    assert basis.thread_id is None
    assert _source_status(source_id) == "processed"
    statuses = [
        a.status.value for a in IntakeRepository.list_attempts_for_source(source_id)
    ]
    assert "failed" not in statuses
    # The tool is not terminal (§6.1): the pass's session ends on the bare
    # `end` after it, which the pass counts as `agent_no_outcome`. The
    # source is linked and not abstained from.
    events = db.execute(
        "SELECT kind FROM agent_run_events WHERE run_id = ? ORDER BY seq", (run.id,)
    ).fetchall()
    assert [e["kind"] for e in events][-1] == "abstained"


def test_40_scripted_pass_abstains_on_a_difference(period_id, intake_dir):
    """Testfall 40: a difference in the pass -- nobody to ask -- is an
    abstention with A-118 in the reason; no link."""
    from services.agent_runtime import AgentWorker

    voucher_id = a118(period_id)
    number = voucher_number(voucher_id)
    source_id = _upload_receipt()
    client = _client(
        [
            _turn("tolka_underlag", _tolka_args(source_id, "amount_diff")),
            _turn(
                "registrera_avstaende",
                {
                    "source_id": source_id,
                    "summary": f"Hör sannolikt till {number}, differens 120,00 kr",
                    "error_detail": f"{number}: 4 600,00 kr mot 4 480,00 kr",
                },
            ),
        ]
    )

    run = AgentWorker().run_pass_once(client_factory=lambda model: client)

    assert run is not None
    assert IntakeRepository.get_link_by_source_id(source_id) is None
    assert _source_status(source_id) == "failed"
    [failed] = [
        a
        for a in IntakeRepository.list_attempts_for_source(source_id)
        if a.status.value == "failed"
    ]
    assert number in failed.summary


def _drop_in_thread(client, auth_headers, source_id: str, monkeypatch):
    """`ChattFalt` without text (D8): the file post, and no turn started by
    the route -- the test runs the turn itself."""
    from repositories.thread_repo import ThreadRepository

    monkeypatch.setattr(settings, "agent_runtime_enabled", False)
    resp = client.post(
        "/api/v1/threads/bocker.verifikationer/messages",
        headers=auth_headers,
        json={"text": "", "attachments": [source_id]},
    )
    assert resp.status_code == 201, resp.text
    thread = ThreadRepository.get(resp.json()["thread_id"])
    assert thread is not None
    trigger = ThreadRepository.get_post(resp.json()["posts"][0]["id"])
    assert trigger is not None and trigger.type == "user_file"
    return thread, trigger


def _decision_turn(source_id: str, voucher_id: str) -> list:
    """Turn 1 of the thread: read, interpret, lay out §9.2's decision."""
    number = voucher_number(voucher_id)
    return [
        _turn("tolka_underlag", _tolka_args(source_id, "amount_diff")),
        _turn(
            "be_om_beslut",
            {
                "title": f"Kvitto Elektronikhuset mot {number}",
                "reason": f"Kvittot är 4 600,00 kr, {number} är 4 480,00 kr.",
                "consequence": "Ingenting kopplas förrän du valt.",
                "source": {"kind": "intake_source", "id": source_id},
                "options": link_options(),
            },
        ),
        _end("Skillnaden ser ut att motsvara pantraden. Vad vill du göra?"),
    ]


def _answer(client, auth_headers, decision_id: str, position: int):
    from repositories.decision_repo import DecisionRepository
    from repositories.thread_repo import ThreadRepository

    decision = DecisionRepository.get(decision_id)
    assert decision is not None
    option = next(o for o in decision.options if o.position == position)
    resp = client.post(
        f"/api/v1/decisions/{decision_id}/answer",
        headers=auth_headers,
        json={"option_id": option.id},
    )
    assert resp.status_code == 202, resp.text
    answer_post = ThreadRepository.get_post(resp.json()["answer_post_id"])
    assert answer_post is not None
    return answer_post


def _run_turn(thread, trigger, message: str, turns: list):
    from services.thread_stream import ThreadTurnRunner

    client = _client(turns)
    outcome = ThreadTurnRunner().run(
        thread, trigger, message, client_factory=lambda model: client
    )
    assert outcome is not None, "the turn raised"
    return outcome


def _the_decision(thread) -> str:
    from repositories.decision_repo import DecisionRepository

    [decision] = DecisionRepository.list_decisions(status="open")
    assert decision.thread_id == thread.id
    return decision.id


def _receipt_for(thread, source_id: str):
    from repositories.thread_repo import ThreadRepository

    return ThreadRepository.receipt_for_source(thread.id, source_id)


def test_41_scripted_thread_option_2_links_on_the_decision(
    client, auth_headers, period_id, intake_dir, monkeypatch
):
    """Testfall 41: file -> interpretation -> decision -> answer option 2
    -> link -> receipt. Linked, no new voucher, the decision in the basis."""
    from repositories.intake_link_repo import IntakeLinkRepository
    from repositories.thread_repo import ThreadRepository

    voucher_id = a118(period_id)
    source_id = _upload_receipt()
    thread, trigger = _drop_in_thread(client, auth_headers, source_id, monkeypatch)
    vouchers = _vouchers()

    _run_turn(
        thread, trigger, "(bifogade 1 filer)", _decision_turn(source_id, voucher_id)
    )
    decision_id = _the_decision(thread)
    comparison = [
        p for p in ThreadRepository.list_posts(thread.id) if p.type == "receipt"
    ]
    assert [p.body["voucher_id"] for p in comparison] == [voucher_id]
    assert IntakeRepository.get_link_by_source_id(source_id) is None

    answer = _answer(client, auth_headers, decision_id, 2)
    outcome = _run_turn(
        thread,
        answer,
        answer.body["text"],
        [
            _turn(
                "koppla_underlag",
                {
                    "source_id": source_id,
                    "voucher_id": voucher_id,
                    "decision_id": decision_id,
                },
            ),
            _end("Kvittot är kopplat till A-118."),
        ],
    )

    assert outcome.kind == "answered"
    assert _vouchers() == vouchers
    basis = IntakeLinkRepository.get_for_source(source_id)
    assert basis is not None
    assert (basis.basis, basis.decision_id, basis.thread_id) == (
        "decision",
        decision_id,
        thread.id,
    )
    receipt = _receipt_for(thread, source_id)
    assert receipt is not None
    assert receipt.actor == answer.actor
    assert _source_status(source_id) == "processed"


def test_42_scripted_thread_option_1_links_proposes_and_posts_a121(
    client, auth_headers, period_id, intake_dir, monkeypatch
):
    """Testfall 42: option 1 -- link, then the difference proposed with the
    decision's id; `Posta` gives A-121 and a reference in the posting's
    transaction; A-121 does not lack underlag."""
    from repositories.intake_link_repo import VoucherSourceReferenceRepository
    from repositories.voucher_repo import VoucherRepository

    voucher_id = a118(period_id)
    source_id = _upload_receipt()
    thread, trigger = _drop_in_thread(client, auth_headers, source_id, monkeypatch)

    _run_turn(
        thread, trigger, "(bifogade 1 filer)", _decision_turn(source_id, voucher_id)
    )
    decision_id = _the_decision(thread)
    answer = _answer(client, auth_headers, decision_id, 1)
    _run_turn(
        thread,
        answer,
        answer.body["text"],
        [
            _turn(
                "koppla_underlag",
                {
                    "source_id": source_id,
                    "voucher_id": voucher_id,
                    "decision_id": decision_id,
                },
            ),
            _turn(
                "foresla_verifikation",
                {
                    "description": "Korrigering pantavgift",
                    "rows": [
                        {"account": "5410", "debit": 12000, "credit": 0},
                        {"account": "1930", "debit": 0, "credit": 12000},
                    ],
                    "date": "2026-03-15",
                    "period_id": period_id,
                    "decision_id": decision_id,
                },
            ),
            _end("Kopplat. Skillnaden ligger som förslag."),
        ],
    )
    [draft] = [
        row
        for row in db.execute(
            "SELECT voucher_id FROM thread_drafts WHERE decision_id = ?",
            (decision_id,),
        )
    ]
    draft_id = draft["voucher_id"]
    assert IntakeRepository.get_link_by_source_id(source_id) is not None

    posted = client.post(f"/api/v1/vouchers/{draft_id}/post", headers=auth_headers)

    assert posted.status_code == 200, posted.text
    a121 = VoucherRepository.get(draft_id)
    assert a121 is not None and a121.status.value == "posted"
    ref = VoucherSourceReferenceRepository.get_for_voucher(draft_id)
    assert ref is not None
    assert (ref.intake_source_id, ref.via_voucher_id, ref.decision_id) == (
        source_id,
        voucher_id,
        decision_id,
    )
    assert a121.missing_attachment is False
    a118_after = VoucherRepository.get(voucher_id)
    assert a118_after is not None and a118_after.missing_attachment is False
    assert a118_after.referenced_by is not None
    assert a118_after.referenced_by.id == draft_id


def test_fu18_scripted_thread_exact_skips_the_decision(
    client, auth_headers, period_id, intake_dir, monkeypatch
):
    """§1 Framgång: with a receipt of exactly 4 480 kr the same day the
    decision is skipped -- the agent links directly and the receipt stands
    in the thread, with no comparison before it."""
    from repositories.thread_repo import ThreadRepository

    voucher_id = a118(period_id)
    source_id = _upload_receipt()
    thread, trigger = _drop_in_thread(client, auth_headers, source_id, monkeypatch)

    _run_turn(
        thread,
        trigger,
        "(bifogade 1 filer)",
        [
            _turn("tolka_underlag", _tolka_args(source_id, "exact")),
            _turn(
                "koppla_underlag", {"source_id": source_id, "voucher_id": voucher_id}
            ),
            _end("Kvittot är kopplat till A-118."),
        ],
    )

    receipts = [
        p for p in ThreadRepository.list_posts(thread.id) if p.type == "receipt"
    ]
    assert [p.body.get("source_id") for p in receipts] == [source_id]
    assert receipts[0].actor == "agent"
    assert [p.type for p in ThreadRepository.list_posts(thread.id)].count(
        "decision"
    ) == 0


@pytest.mark.parametrize("tool", ["posta_verifikation", "foresla_verifikation"])
def test_fu18_scripted_thread_posting_an_exact_match_is_stopped(
    client, auth_headers, period_id, intake_dir, monkeypatch, tool
):
    """§1 Framgång's last sentence: a model that posts the receipt anyway
    is refused with `source_matches_posted_voucher` -- an error result in
    the turn, and no voucher."""
    a118(period_id)
    source_id = _upload_receipt()
    thread, trigger = _drop_in_thread(client, auth_headers, source_id, monkeypatch)
    vouchers = _vouchers()
    rows = [
        {"account": "5410", "debit": 358400, "credit": 0},
        {"account": "2640", "debit": 89600, "credit": 0},
        {"account": "1930", "debit": 0, "credit": 448000},
    ]
    posting = {
        "description": "Kortköp Elektronikhuset",
        "rows": rows,
        "date": "2026-03-15",
        "period_id": period_id,
        "intake_source_ids": [source_id],
    }

    outcome = _run_turn(
        thread,
        trigger,
        "(bifogade 1 filer)",
        [
            _turn("tolka_underlag", _tolka_args(source_id, "exact")),
            _turn(tool, posting),
            _end("Det gick inte att bokföra."),
        ],
    )

    assert outcome.kind == "answered"
    [refused] = [
        call
        for record in outcome.turns
        for call in record.executed_tool_calls
        if call.tool_call.name == tool
    ]
    assert refused.ok is False
    assert "source_matches_posted_voucher" in (refused.error or "")
    assert _vouchers() == vouchers
