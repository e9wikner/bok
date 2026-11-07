"""`flode-underlag`: the hard stop in the posting (FU7, §8, D5).

`posta_verifikation`, `POST /agent/vouchers` and `foresla_verifikation`
refuse an underlag whose latest interpretation is an exact match that is
still open: it belongs to an already posted voucher and is linked with
`koppla_underlag` instead. Test case numbers refer to
SPEC-flode-underlag.md §14.
"""

from datetime import date

import pytest

from db.database import db
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    a118,
    attach,
    interpret,
    make_source,
    make_thread,
    table_rows,
    voucher_number,
)

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
period_id = fu.period_id

#: A new purchase of A-118's amount, as the agent would post the receipt
#: if it had not seen the match.
_ROWS = [
    {"account": "5410", "debit": 358400, "credit": 0},
    {"account": "2640", "debit": 89600, "credit": 0},
    {"account": "1930", "debit": 0, "credit": 448000},
]


def _capabilities():
    from services.llm import LLMCapabilities

    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


def _posta(period_id: str, source_id: str, tool_context=None):
    from services.agent_tools import execute_tool

    return execute_tool(
        "posta_verifikation",
        {
            "date": "2026-03-15",
            "period_id": period_id,
            "description": "Kortköp Elektronikhuset",
            "rows": _ROWS,
            "intake_source_ids": [source_id],
        },
        actor="agent",
        capabilities=_capabilities(),
        tool_context=tool_context,
    )


def _foresla(period_id: str, source_id: str, thread):
    from services.agent_tools import execute_tool

    return execute_tool(
        "foresla_verifikation",
        {
            "description": "Kortköp Elektronikhuset",
            "rows": _ROWS,
            "date": "2026-03-15",
            "period_id": period_id,
            "intake_source_ids": [source_id],
        },
        actor="agent",
        capabilities=_capabilities(),
        tool_context={"thread": thread},
    )


def _keys() -> list:
    return table_rows("idempotency_keys")


def _vouchers() -> list:
    return table_rows("vouchers")


def _stopped(period_id: str, kind: str = "exact"):
    """A-118 and a source interpreted as *kind* against it."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, kind)
    return voucher_id, source_id


# ---------------------------------------------------------------------------
# FU7 — the stop (§8)
# ---------------------------------------------------------------------------


def test_20_posta_verifikation_is_stopped(period_id):
    """Testfall 20: `source_matches_posted_voucher`, no voucher, and no
    key left reserved (the tool's derived key is released)."""
    from services.agent_tools import derive_posting_idempotency_key
    from services.intake import IntakeError
    from services.intake_link import LinkConflictError

    voucher_id, source_id = _stopped(period_id)
    vouchers, keys = _vouchers(), _keys()

    with pytest.raises(IntakeError) as exc:
        _posta(period_id, source_id)

    assert isinstance(exc.value, LinkConflictError)
    assert exc.value.code == "source_matches_posted_voucher"
    assert exc.value.details == (
        f"source_id={source_id}, voucher={voucher_number(voucher_id)}, diff_ore=0 "
        "-- underlaget hör till en redan postad verifikation. Koppla det med "
        "koppla_underlag i stället."
    )
    assert _vouchers() == vouchers
    assert _keys() == keys
    key = derive_posting_idempotency_key(source_id)
    assert (
        db.execute("SELECT 1 FROM idempotency_keys WHERE key = ?", (key,)).fetchone()
        is None
    )


def test_21_post_agent_vouchers_is_409(client, auth_headers, period_id):
    """Testfall 21: the same over `POST /agent/vouchers`, with an
    `Idempotency-Key` that is not held afterwards."""
    _voucher_id, source_id = _stopped(period_id)
    vouchers = _vouchers()
    body = {
        "date": "2026-03-15",
        "period_id": period_id,
        "description": "Kortköp Elektronikhuset",
        "rows": _ROWS,
        "intake_source_ids": [source_id],
    }
    key = "5f1d3c2a-9b8e-4c7d-a6f5-0e1d2c3b4a59"
    headers = {**auth_headers, "Idempotency-Key": key}

    resp = client.post("/api/v1/agent/vouchers", headers=headers, json=body)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "source_matches_posted_voucher"
    assert _vouchers() == vouchers
    assert (
        db.execute("SELECT 1 FROM idempotency_keys WHERE key = ?", (key,)).fetchone()
        is None
    )


def test_22_foresla_verifikation_is_stopped(period_id):
    """Testfall 22: the same error, and no draft."""
    from services.intake import IntakeError

    _voucher_id, source_id = _stopped(period_id)
    thread = make_thread(period_id)
    vouchers, drafts, posts = (
        _vouchers(),
        table_rows("thread_drafts"),
        table_rows("thread_posts"),
    )

    with pytest.raises(IntakeError) as exc:
        _foresla(period_id, source_id, thread)

    assert exc.value.code == "source_matches_posted_voucher"
    assert _vouchers() == vouchers
    assert table_rows("thread_drafts") == drafts
    assert table_rows("thread_posts") == posts


@pytest.mark.parametrize("kind", ["amount_diff", "exact_no_date", None])
def test_23_no_stop_without_an_exact_match(period_id, kind):
    """Testfall 23: `amount_diff`, `exact_no_date` or no interpretation --
    the stop is what the server knows, not what the agent should have
    done (§8)."""
    a118(period_id)
    source_id = make_source()
    if kind is not None:
        interpret(source_id, kind)

    result = _posta(period_id, source_id)

    assert result["status"] == "posted"


def test_24_no_stop_when_the_match_is_no_longer_open(period_id):
    """Testfall 24: exact, but A-118 has got an underlag since."""
    voucher_id, source_id = _stopped(period_id)
    attach(voucher_id)

    result = _posta(period_id, source_id)

    assert result["status"] == "posted"


def test_fu7_proposal_is_stopped_but_its_posting_is_not(
    client, auth_headers, period_id
):
    """§8: posting a thread proposal (`POST /vouchers/{id}/post`) does not
    run the stop again. A proposal made before the interpretation posts
    even when the interpretation turned out exact."""
    voucher_id = a118(period_id)
    source_id = make_source()
    thread = make_thread(period_id)
    proposal = _foresla(period_id, source_id, thread)
    interpret(source_id, "exact")

    resp = client.post(
        f"/api/v1/vouchers/{proposal['draft_id']}/post", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "posted"
    assert voucher_id != proposal["draft_id"]


def test_fu7_the_stop_is_one_function_in_the_link_service():
    """§8: the same check, one function in `IntakeLinkService`, called from
    the posting service and the draft service -- not from a tool or a
    route."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    posting = (root / "services" / "voucher_posting.py").read_text(encoding="utf-8")
    drafts = (root / "services" / "draft_service.py").read_text(encoding="utf-8")
    tools = (root / "services" / "agent_tools.py").read_text(encoding="utf-8")
    route = (root / "api" / "routes" / "agent.py").read_text(encoding="utf-8")

    assert "ensure_not_matching_posted" in posting
    assert "ensure_not_matching_posted" in drafts
    assert "ensure_not_matching_posted" not in tools
    assert "ensure_not_matching_posted" not in route


def test_fu7_several_sources_the_matching_one_stops(period_id):
    """Every source is checked, not only the first."""
    from services.intake import IntakeError

    voucher_id, matching = _stopped(period_id)
    other = make_source()

    from services.idempotency import IdempotencyService
    from services.voucher_posting import VoucherPostingRequest, post_agent_voucher

    request = VoucherPostingRequest(
        date=date(2026, 3, 15),
        period_id=period_id,
        description="Kortköp",
        rows=_ROWS,
        intake_source_ids=[other, matching],
    )
    with pytest.raises(IntakeError) as exc:
        post_agent_voucher(request, "agent", IdempotencyService(), None, "test")

    assert exc.value.code == "source_matches_posted_voucher"
    assert f"source_id={matching}" in (exc.value.details or "")
