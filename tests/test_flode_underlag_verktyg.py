"""`flode-underlag`: `koppla_underlag` in the tool list (FU5) and
`missing_attachment`/`age_days` in `las_verifikationer` (FU12).

Test case numbers refer to SPEC-flode-underlag.md §14. The tools run
through `execute_tool` with a real thread in `tool_context`, as the thread
turn puts it there; no LLM.
"""

import hashlib
import json

import pytest

from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    SPEC,
    a118,
    interpret,
    make_decision,
    make_run,
    make_source,
    make_thread,
)

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
period_id = fu.period_id

#: sha256 of `json.dumps(AGENT_TOOL_DEFINITIONS[:12])`, taken on `a326fdf`
#: (FU4), before FU5 touched `_TOOL_SPECS`. No `sort_keys`: the key order
#: inside each definition is part of the bytes the model is sent, and so of
#: the cached prefix (SPEC-agentruntime §6.6). Re-taken for SPEC-lasbarhet
#: L6, which deliberately rewords `be_om_beslut` and `foresla_verifikation`. Re-taken again for the period lock, which rewords
#: `las_perioder` (it said locking was never the agent's) and appends
#: `stang_perioder`.
_FIRST_TWELVE_SHA256 = (
    "7a250f41c8f64fcfb80eb6c7f5e52aa0f8a04d919eb4c8208ca2e7d888a38d97"
)


def _capabilities():
    from services.llm import LLMCapabilities

    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


def _execute(name: str, arguments: dict, tool_context=None):
    from services.agent_tools import execute_tool

    return execute_tool(
        name,
        arguments,
        actor="agent",
        capabilities=_capabilities(),
        tool_context=tool_context,
    )


def _spec_6_2_description() -> str:
    """The block quote under "Beskrivning i verktygslistan:" in §6.2, its
    lines joined with a space -- read from the spec so that "verbatim" is
    checked against the spec itself, not a copy of it."""
    spec = SPEC.read_text(encoding="utf-8")
    section = spec.split("### 6.2 Argumenten", 1)[1]
    after = section.split("Beskrivning i verktygslistan:\n\n", 1)[1]
    quoted = []
    for line in after.splitlines():
        if not line.startswith("> "):
            break
        quoted.append(line[2:].strip())
    return " ".join(quoted)


# ---------------------------------------------------------------------------
# FU5 — `koppla_underlag` last in the tool list (§6.2, §6.7)
# ---------------------------------------------------------------------------


def test_36_koppla_underlag_is_last_and_the_first_twelve_are_unchanged():
    """Testfall 36: appended last, the thirteenth tool; the names catch a
    reorder, the hash an edit to a description or schema before it."""
    from services.agent_tools import AGENT_TOOL_DEFINITIONS, KopplaUnderlagArgs

    names = [t["name"] for t in AGENT_TOOL_DEFINITIONS]
    # `stang_perioder` has since been appended after it, the fourteenth,
    # and `koppla_bort_underlag` after that, the fifteenth.
    assert len(names) == 15
    assert names[11:] == [
        "tolka_underlag",
        "koppla_underlag",
        "stang_perioder",
        "koppla_bort_underlag",
    ]
    first_twelve = json.dumps(AGENT_TOOL_DEFINITIONS[:12])
    assert hashlib.sha256(first_twelve.encode()).hexdigest() == _FIRST_TWELVE_SHA256
    assert AGENT_TOOL_DEFINITIONS[12]["input_schema"] == (
        KopplaUnderlagArgs.model_json_schema()
    )


def test_36_the_description_is_section_6_2_verbatim():
    from services.agent_tools import AGENT_TOOL_DEFINITIONS

    expected = _spec_6_2_description()
    assert expected.startswith("Koppla ett underlag till en redan postad")
    assert expected.endswith("Skapar ingen verifikation och ändrar ingen.")
    assert AGENT_TOOL_DEFINITIONS[12]["description"] == expected
    # §6.2, SPEC-underlagstolkning §12.6 c: it does not name the ledger.
    assert "huvudbok" not in expected.lower()


def test_fu5_args_are_section_6_2():
    from services.agent_tools import KopplaUnderlagArgs

    assert list(KopplaUnderlagArgs.model_fields) == [
        "source_id",
        "voucher_id",
        "decision_id",
    ]
    minimal = KopplaUnderlagArgs.model_validate({"source_id": "s", "voucher_id": "v"})
    assert minimal.decision_id is None
    # No `extra="forbid"`: only `tolka_underlag` has it (the cached prefix).
    assert KopplaUnderlagArgs.model_config.get("extra") != "forbid"


def test_fu5_the_docstrings_say_thirteen_tools():
    from services import agent_tools

    assert "thirteenth" in (agent_tools.__doc__ or "")
    assert "koppla_underlag" in (agent_tools.__doc__ or "")
    # Fifteen since underlag-ersatt appended `koppla_bort_underlag`.
    assert "fifteen" in (agent_tools.execute_tool.__doc__ or "")


def test_01_exact_match_through_the_tool_in_a_thread(period_id):
    """Testfall 1 through `execute_tool`: the thread and the turn's run
    land on the basis; the answer is §6.6's."""
    from repositories.intake_link_repo import IntakeLinkRepository

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    thread = make_thread(period_id)
    run_id = make_run()

    result = _execute(
        "koppla_underlag",
        {"source_id": source_id, "voucher_id": voucher_id},
        tool_context={"thread": thread, "agent_run_id": run_id},
    )

    assert list(result) == [
        "source_id",
        "voucher_id",
        "voucher_number",
        "basis",
        "interpretation_id",
        "decision_id",
        "replayed",
        "missing_attachments",
    ]
    assert (result["basis"], result["replayed"]) == ("exact_match", False)
    basis = IntakeLinkRepository.get_for_source(source_id)
    assert basis is not None
    assert (basis.thread_id, basis.agent_run_id, basis.actor) == (
        thread.id,
        run_id,
        "agent",
    )
    assert json.loads(json.dumps(result)) == result


def test_04_decision_through_the_tool_in_a_thread(period_id):
    """Testfall 4 through `execute_tool`."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=1)

    result = _execute(
        "koppla_underlag",
        {"source_id": source_id, "voucher_id": voucher_id, "decision_id": decision.id},
        tool_context={"thread": thread},
    )

    assert (result["basis"], result["decision_id"]) == ("decision", decision.id)


def test_fu5_decision_in_another_thread_is_refused(period_id):
    from services.intake_link import IntakeLinkError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    decision = make_decision(make_thread(period_id), source_id, answer=1)
    other = make_thread(period_id, view_key="bocker.balans")

    with pytest.raises(IntakeLinkError) as exc:
        _execute(
            "koppla_underlag",
            {
                "source_id": source_id,
                "voucher_id": voucher_id,
                "decision_id": decision.id,
            },
            tool_context={"thread": other},
        )

    assert exc.value.code == "decision_not_in_thread"


def test_fu5_the_pass_links_on_exact_match_only(period_id):
    """§6.7: without a thread it is the intake pass -- only `exact_match`,
    a decision gives `link_requires_decision`."""
    from services.intake_link import IntakeLinkError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    decision = make_decision(make_thread(period_id), source_id, answer=1)

    with pytest.raises(IntakeLinkError) as exc:
        _execute(
            "koppla_underlag",
            {
                "source_id": source_id,
                "voucher_id": voucher_id,
                "decision_id": decision.id,
            },
            tool_context={"agent_run_id": make_run("manual")},
        )
    assert exc.value.code == "link_requires_decision"

    exact_source = make_source()
    interpret(exact_source, "exact")
    result = _execute(
        "koppla_underlag",
        {"source_id": exact_source, "voucher_id": voucher_id},
        tool_context={"agent_run_id": make_run("manual")},
    )
    assert result["basis"] == "exact_match"


# ---------------------------------------------------------------------------
# FU12 — `missing_attachment` and `age_days` in `las_verifikationer` (§11.1)
# ---------------------------------------------------------------------------

#: sha256 of `json.dumps(las_verifikationer's definition)`, taken on
#: `a326fdf` (FU4), before FU5 and FU12: only the answer grows, the
#: arguments and the description are the cached prefix.
_LAS_VERIFIKATIONER_SHA256 = (
    "4e2d241f8db4ab674b891cec41f3351eaa729fe9ff7f4e831b03cf948b4c5119"
)


def test_37_las_verifikationer_answers_missing_attachment_and_age_days(period_id):
    """Testfall 37: the same derived values as `VoucherResponse`
    (SPEC-oversikt.md §3), read from the voucher."""
    from repositories.voucher_repo import VoucherRepository
    from tests.test_flode_underlag import attach

    missing = a118(period_id)
    complete = fu.posted_purchase(period_id, day=16)
    attach(complete)

    result = _execute("las_verifikationer", {"period_id": period_id})

    by_id = {v["id"]: v for v in result["items"]}
    for voucher_id, flag in [(missing, True), (complete, False)]:
        voucher = VoucherRepository.get(voucher_id)
        assert voucher is not None
        assert by_id[voucher_id]["missing_attachment"] is flag
        assert by_id[voucher_id]["age_days"] == voucher.age_days
        assert isinstance(by_id[voucher_id]["age_days"], int)


def test_37_arguments_and_description_are_unchanged_byte_for_byte():
    from services.agent_tools import AGENT_TOOL_DEFINITIONS

    [tool] = [t for t in AGENT_TOOL_DEFINITIONS if t["name"] == "las_verifikationer"]

    assert hashlib.sha256(json.dumps(tool).encode()).hexdigest() == (
        _LAS_VERIFIKATIONER_SHA256
    )
