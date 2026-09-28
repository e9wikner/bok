"""`flode-underlag` in the thread: the comparison post (FU8, §9.1, D6) and
the receipt after a link (FU9, §9.3).

Test case numbers refer to SPEC-flode-underlag.md §14. The tools run
through `execute_tool` with a real thread in `tool_context`; events are
captured from the process-wide broker.
"""

import pytest

from repositories.thread_repo import ThreadRepository
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    _READS,
    A118_TOTAL,
    A118_VAT,
    a118,
    make_source,
    make_thread,
    posted_purchase,
    table_rows,
    voucher_number,
)

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
period_id = fu.period_id

HYPOTHESIS = "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget."


@pytest.fixture
def events(monkeypatch):
    """Every event published on the broker, as `(thread_id, event, data)`."""
    from services.thread_stream import get_broker

    seen: list = []
    broker = get_broker()
    original = broker.publish

    def capture(thread_id, event, data):
        seen.append((thread_id, event, data))
        original(thread_id, event, data)

    monkeypatch.setattr(broker, "publish", capture)
    return seen


def _capabilities():
    from services.llm import LLMCapabilities

    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


def _tolka(source_id: str, kind: str, tool_context=None, **overrides) -> dict:
    """`tolka_underlag` through `execute_tool`, with the read giving *kind*
    against A-118."""
    from services.agent_tools import execute_tool

    read = {**_READS[kind], "source_id": source_id, **overrides}
    return execute_tool(
        "tolka_underlag",
        read,
        actor="agent",
        capabilities=_capabilities(),
        tool_context=tool_context,
    )


def _receipts(thread) -> list:
    return [p for p in ThreadRepository.list_posts(thread.id) if p.type == "receipt"]


# ---------------------------------------------------------------------------
# FU8 — the comparison post (§9.1, D6)
# ---------------------------------------------------------------------------


def test_25_amount_diff_in_a_thread_writes_the_comparison(period_id, events):
    """Testfall 25: one `receipt` with `labels ["kvitto", "A-118"]`, the
    amount and the VAT, `note` = the server's hypothesis verbatim --
    and `message.completed` for it."""
    voucher_id = a118(period_id)
    number = voucher_number(voucher_id)
    source_id = make_source()
    thread = make_thread(period_id)

    result = _tolka(source_id, "amount_diff", tool_context={"thread": thread})

    assert result["match"]["hypothesis"]["text"] == HYPOTHESIS
    [post] = _receipts(thread)
    assert post.body == {
        "title": f"Kvitto Elektronikhuset 2026-03-15 mot {number}",
        "labels": ["kvitto", number],
        "rows": [
            {
                "key": "Belopp",
                "text": "inklusive moms",
                "left_ore": 460000,
                "right_ore": A118_TOTAL,
            },
            {
                "key": "Moms",
                "text": "ingående moms",
                "left_ore": A118_VAT,
                "right_ore": A118_VAT,
            },
        ],
        "note": HYPOTHESIS,
        "voucher_id": voucher_id,
    }
    assert post.actor == "agent"
    completed = [e for e in events if e[1] == "message.completed"]
    assert [(e[0], e[2]["id"], e[2]["type"]) for e in completed] == [
        (thread.id, post.id, "receipt")
    ]


def test_26_exact_in_a_thread_writes_no_comparison(period_id, events):
    """Testfall 26: the step is skipped; the receipt after the link carries
    the same rows (§9.3)."""
    a118(period_id)
    thread = make_thread(period_id)

    _tolka(make_source(), "exact", tool_context={"thread": thread})

    assert _receipts(thread) == []
    assert events == []


def test_27_without_a_thread_no_post(period_id, client, auth_headers):
    """Testfall 27: in the pass, and over `POST …/interpretation`."""
    a118(period_id)
    thread = make_thread(period_id)
    posts = table_rows("thread_posts")

    _tolka(make_source(), "amount_diff", tool_context={"agent_run_id": None})
    body = {k: v for k, v in _READS["amount_diff"].items()}
    resp = client.post(
        f"/api/v1/intake/{make_source()}/interpretation",
        headers=auth_headers,
        json=body,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["match"]["kind"] == "amount_diff"
    assert table_rows("thread_posts") == posts
    assert _receipts(thread) == []


def test_28_match_and_expected_on_different_vouchers_give_two_expected_first(
    period_id,
):
    """Testfall 28: two posts, the one the agent asked for first."""
    match_id = a118(period_id)
    expected_id = posted_purchase(period_id, total=500000, vat=100000, day=2)
    thread = make_thread(period_id)

    result = _tolka(
        make_source(),
        "amount_diff",
        tool_context={"thread": thread},
        expected_voucher_id=expected_id,
    )

    assert result["match"]["voucher_id"] == match_id
    assert result["expected"]["voucher_id"] == expected_id
    first, second = _receipts(thread)
    assert first.body["voucher_id"] == expected_id
    assert first.body["labels"] == ["kvitto", voucher_number(expected_id)]
    assert first.body["rows"][0]["right_ore"] == 500000
    assert second.body["voucher_id"] == match_id


def test_fu8_expected_that_is_the_match_gives_one_post(period_id):
    voucher_id = a118(period_id)
    thread = make_thread(period_id)

    _tolka(
        make_source(),
        "amount_diff",
        tool_context={"thread": thread},
        expected_voucher_id=voucher_id,
    )

    [post] = _receipts(thread)
    assert post.body["voucher_id"] == voucher_id


def test_fu8_without_vat_on_one_side_no_vat_row_and_without_hypothesis_no_note(
    period_id,
):
    """The VAT row needs both sides; `note` is only the server's
    hypothesis, never absent-but-empty."""
    posted_purchase(period_id, total=A118_TOTAL, vat=0)
    thread = make_thread(period_id)

    _tolka(
        make_source(),
        "amount_diff",
        tool_context={"thread": thread},
        lines=[],
    )

    [post] = _receipts(thread)
    assert [r["key"] for r in post.body["rows"]] == ["Belopp"]
    assert "note" not in post.body


def test_fu8_comparison_and_interpretation_share_a_transaction(period_id, monkeypatch):
    """The post fails -> the interpretation is not saved either."""
    a118(period_id)
    thread = make_thread(period_id)
    source_id = make_source()
    before = table_rows("intake_interpretations")

    def boom(*args, **kwargs):
        raise RuntimeError("post failed")

    monkeypatch.setattr(ThreadRepository, "add_post", staticmethod(boom))
    with pytest.raises(RuntimeError, match="post failed"):
        _tolka(source_id, "amount_diff", tool_context={"thread": thread})

    assert table_rows("intake_interpretations") == before


def test_fu8_comparison_body_is_pure():
    """The row builder takes a match or an expected, reads no database."""
    from domain.interpretation import Match
    from services.interpretation import comparison_body

    part = Match(
        kind="amount_diff",
        voucher_id="v",
        voucher_number="A-118",
        voucher_date="2026-03-15",
        voucher_description="x",
        amounts={"document_ore": 460000, "voucher_ore": 448000},
        diff_ore=12000,
        date_diff_days=0,
        vat={"document_ore": None, "voucher_ore": 89600, "equal": False},
        hypothesis=None,
    )

    body = comparison_body(part, vendor=None, document_date=None)

    assert body == {
        "title": "Kvitto mot A-118",
        "labels": ["kvitto", "A-118"],
        "rows": [
            {
                "key": "Belopp",
                "text": "inklusive moms",
                "left_ore": 460000,
                "right_ore": 448000,
            }
        ],
        "voucher_id": "v",
    }
