"""Tests for the agent runtime module (docs/redesign/SPEC-agentruntime.md).

This file grows across tasks A3-A13 of tasks/agentruntime/todo.md. Each task
gets its own section/class so the file stays navigable as it grows:

- A3: AgentRunRepository (this file, first pass)
- A4: services/llm/ protocol layer, model registry, config
- A6: services/agent_documents.py -- underlagsläsning, textlager, avstämning
- A7: services/agent_tools.py -- verktygsytan, dispatcher, idempotensnyckel
- A8: services/agent_session.py -- systemprompt, användartur, manuell
  verktygsloop, avståenden (SPEC §9 testfall 4, 5, 7, 14, 15)

Per SPEC §9: no LLM is ever called from a test. A3 covers the storage layer
only — creating a run, sequencing events, and the "running with no live
thread" query the worker (A10) will later use to detect abandoned runs. The
liveness decision itself is out of scope here; find_running() only needs to
return what is marked 'running'.

A4 covers pure typing, a table-driven model registry, and config plumbing —
no network calls, no `anthropic`/`openai` imports. Test case 19 (a model
with no price row must refuse to start) is proven here only at the registry
level: `get_model_info` raises. The full "the pass refuses to start, no
agent_runs row" behavior is A10's job.

A6 covers SPEC §9 test cases 20-23 at the content-selection level: whether
`select_content_for_source` picks text, a document block, or abstains, and
the reconciliation heuristic that decides it, all against synthetic PDFs
built in-process (no fixture files) so the tests don't depend on any
external renderer being installed. Full end-to-end session behavior (the
`hamta_underlagsfil` tool actually calling this) is A7/A8's job.
"""

import base64
import io
import json
import uuid
from calendar import monthrange
from datetime import date
from typing import Optional

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from config import Settings, settings
from db.database import db
from domain.models import IntakeSource
from domain.types import IntakeStatus
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.agent_run_repo import AgentRunRepository
from repositories.period_repo import PeriodRepository
from services.agent_documents import (
    DocumentUnreadableError,
    ReconciliationState,
    extract_pdf_text,
    reconciliation_result,
    select_content_for_source,
)
from services.agent_session import (
    SessionOutcome,
    build_system_prompt,
    build_user_turn,
    run_session,
)
from services.agent_tools import (
    AGENT_TOOL_DEFINITIONS,
    BOK_NAMESPACE,
    derive_posting_idempotency_key,
    execute_tool,
)
from services.intake import IntakeService
from services.llm import (
    LLMCapabilities,
    LLMTurn,
    ModelInfo,
    ToolCall,
    UnknownModelError,
    Usage,
    get_model_info,
)

pytestmark = pytest.mark.usefixtures("test_db")


# --- A3: AgentRunRepository -------------------------------------------------


class TestCreate:
    def test_create_returns_running_run_with_zeroed_counters(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        assert run.id
        assert run.trigger == "manual"
        assert run.status == "running"
        assert run.model == "opencode/claude-opus-5"
        assert run.protocol == "messages"
        assert run.started_at is not None
        assert run.finished_at is None
        assert run.input_tokens == 0
        assert run.output_tokens == 0
        assert run.cache_read_tokens == 0
        assert run.cost_ore == 0
        assert run.items_seen == 0
        assert run.items_posted == 0
        assert run.items_abstained == 0
        assert run.last_error is None

    def test_get_round_trips_a_created_run(self):
        created = AgentRunRepository.create(
            trigger="schedule", model="opencode/gpt-5.5", protocol="chat"
        )

        fetched = AgentRunRepository.get(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.trigger == "schedule"
        assert fetched.protocol == "chat"

    def test_get_missing_run_returns_none(self):
        assert AgentRunRepository.get("does-not-exist") is None


class TestUpdateStatus:
    def test_mark_completed_sets_finished_at(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        updated = AgentRunRepository.update_status(run.id, "completed")

        assert updated is not None
        assert updated.status == "completed"
        assert updated.finished_at is not None
        assert updated.last_error is None

    def test_mark_failed_records_last_error(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        updated = AgentRunRepository.update_status(
            run.id, "failed", last_error="gateway timeout"
        )

        assert updated is not None
        assert updated.status == "failed"
        assert updated.last_error == "gateway timeout"

    def test_mark_abandoned(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        updated = AgentRunRepository.update_status(run.id, "abandoned")

        assert updated is not None
        assert updated.status == "abandoned"

    def test_cannot_transition_a_run_twice(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.update_status(run.id, "completed")

        second = AgentRunRepository.update_status(run.id, "failed", last_error="late")

        refetched = AgentRunRepository.get(run.id)
        assert refetched is not None
        assert refetched.status == "completed"
        assert refetched.last_error is None
        # update_status still returns the current row even when its guard
        # prevented the write, not None -- there was no error, just no-op.
        assert second is not None
        assert second.status == "completed"

    def test_invalid_target_status_rejected(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        with pytest.raises(ValueError):
            AgentRunRepository.update_status(run.id, "running")


class TestUsageAccumulation:
    def test_add_usage_accumulates_across_calls(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        AgentRunRepository.add_usage(
            run.id, input_tokens=100, output_tokens=50, cache_read_tokens=0, cost_ore=42
        )
        updated = AgentRunRepository.add_usage(
            run.id, input_tokens=200, output_tokens=30, cache_read_tokens=90, cost_ore=8
        )

        assert updated is not None
        assert updated.input_tokens == 300
        assert updated.output_tokens == 80
        assert updated.cache_read_tokens == 90
        assert updated.cost_ore == 50

    def test_increment_items_accumulates_across_calls(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        AgentRunRepository.increment_items(run.id, seen=1, posted=1)
        AgentRunRepository.increment_items(run.id, seen=1, abstained=1)
        updated = AgentRunRepository.increment_items(run.id, seen=1, posted=1)

        assert updated is not None
        assert updated.items_seen == 3
        assert updated.items_posted == 2
        assert updated.items_abstained == 1


class TestEvents:
    def test_first_event_gets_seq_one(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        event = AgentRunRepository.add_event(
            run.id, "item_started", json.dumps({"source_id": "src-1"})
        )

        assert event.seq == 1
        assert event.run_id == run.id
        assert event.kind == "item_started"

    def test_seq_increments_across_multiple_events(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        first = AgentRunRepository.add_event(run.id, "item_started", "{}")
        second = AgentRunRepository.add_event(run.id, "tool_call", "{}")
        third = AgentRunRepository.add_event(run.id, "posted", "{}")

        assert [first.seq, second.seq, third.seq] == [1, 2, 3]

    def test_seq_is_scoped_per_run(self):
        run_a = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        run_b = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        AgentRunRepository.add_event(run_a.id, "item_started", "{}")
        event_b = AgentRunRepository.add_event(run_b.id, "item_started", "{}")

        assert event_b.seq == 1

    def test_list_events_ordered_by_seq(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.add_event(run.id, "item_started", "{}")
        AgentRunRepository.add_event(run.id, "tool_call", "{}")
        AgentRunRepository.add_event(run.id, "posted", "{}")

        events = AgentRunRepository.list_events(run.id)

        assert [e.seq for e in events] == [1, 2, 3]
        assert [e.kind for e in events] == ["item_started", "tool_call", "posted"]

    def test_add_event_carries_source_and_voucher_ids(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        event = AgentRunRepository.add_event(
            run.id,
            "posted",
            json.dumps({"ok": True}),
            source_id="src-1",
            voucher_id="voucher-1",
        )

        assert event.source_id == "src-1"
        assert event.voucher_id == "voucher-1"

    def test_list_events_empty_for_unknown_run(self):
        assert AgentRunRepository.list_events("does-not-exist") == []


class TestFindRunning:
    def test_find_running_returns_only_running_rows(self):
        running = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        finished = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.update_status(finished.id, "completed")

        result = AgentRunRepository.find_running()

        ids = [r.id for r in result]
        assert running.id in ids
        assert finished.id not in ids

    def test_find_running_empty_when_none_running(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.update_status(run.id, "abandoned")

        assert AgentRunRepository.find_running() == []

    def test_find_running_is_the_abandoned_run_candidate_set(self):
        """A10 detects an abandoned run by intersecting this list with its own
        record of live threads (see AgentRunRepository.find_running's
        docstring) -- this repository test only proves the candidate set is
        right, not the liveness decision, which is out of scope here.
        """
        stale = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        candidates = AgentRunRepository.find_running()

        assert any(r.id == stale.id for r in candidates)
        reaped = AgentRunRepository.update_status(stale.id, "abandoned")
        assert reaped is not None
        assert reaped.status == "abandoned"
        assert AgentRunRepository.find_running() == []


class TestCurrentAndLastRun:
    def test_get_current_returns_none_when_nothing_running(self):
        assert AgentRunRepository.get_current() is None

    def test_get_current_returns_the_running_run(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        current = AgentRunRepository.get_current()

        assert current is not None
        assert current.id == run.id

    def test_get_last_completed_or_failed_returns_none_when_no_finished_runs(self):
        AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )

        assert AgentRunRepository.get_last_completed_or_failed() is None

    def test_get_last_completed_or_failed_ignores_abandoned(self):
        run = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.update_status(run.id, "abandoned")

        assert AgentRunRepository.get_last_completed_or_failed() is None

    def test_get_last_completed_or_failed_returns_most_recent(self):
        first = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.update_status(first.id, "completed")
        second = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.update_status(second.id, "failed", last_error="oops")

        last = AgentRunRepository.get_last_completed_or_failed()

        assert last is not None
        assert last.id == second.id
        assert last.status == "failed"


class TestCostToday:
    def test_sum_cost_today_ore_sums_todays_runs(self):
        run_a = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        run_b = AgentRunRepository.create(
            trigger="manual", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.add_usage(run_a.id, cost_ore=1200)
        AgentRunRepository.add_usage(run_b.id, cost_ore=340)

        assert AgentRunRepository.sum_cost_today_ore() == 1540

    def test_sum_cost_today_ore_zero_with_no_runs(self):
        assert AgentRunRepository.sum_cost_today_ore() == 0


# --- A4: services/llm/ protocol layer, model registry, config --------------


class TestValueTypes:
    def test_usage_constructs_with_expected_fields(self):
        usage = Usage(input_tokens=100, output_tokens=50, cache_read_input_tokens=10)

        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cache_read_input_tokens == 10

    def test_tool_call_constructs_with_expected_fields(self):
        call = ToolCall(id="call-1", name="posta_verifikation", arguments={"a": 1})

        assert call.id == "call-1"
        assert call.name == "posta_verifikation"
        assert call.arguments == {"a": 1}

    def test_llm_capabilities_constructs_with_expected_fields(self):
        caps = LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
        )

        assert caps.cache_breakpoint is True
        assert caps.pdf_document_blocks is True
        assert caps.refusal_stop_reason is True

    def test_llm_turn_constructs_with_expected_fields(self):
        usage = Usage(input_tokens=1, output_tokens=1, cache_read_input_tokens=0)
        call = ToolCall(id="call-1", name="hamta_kontoplan", arguments={})

        turn = LLMTurn(text="klart", tool_calls=[call], stop="tool_calls", usage=usage)

        assert turn.text == "klart"
        assert turn.tool_calls == [call]
        assert turn.stop == "tool_calls"
        assert turn.usage is usage

    def test_llm_turn_stop_accepts_each_normalized_value(self):
        usage = Usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=0)

        for stop in ("tool_calls", "end", "refusal", "max_tokens"):
            turn = LLMTurn(text="", tool_calls=[], stop=stop, usage=usage)
            assert turn.stop == stop


class TestModelRegistry:
    def test_known_claude_model_resolves_to_messages_protocol(self):
        info = get_model_info("opencode/claude-opus-5")

        assert isinstance(info, ModelInfo)
        assert info.model == "opencode/claude-opus-5"
        assert info.protocol == "messages"

    def test_known_non_claude_model_resolves_to_chat_protocol(self):
        info = get_model_info("opencode/gpt-5.5")

        assert info.protocol == "chat"

    def test_unknown_model_raises_unknown_model_error(self):
        with pytest.raises(UnknownModelError):
            get_model_info("opencode/does-not-exist")

    def test_unknown_model_error_is_not_a_bare_exception_or_keyerror(self):
        try:
            get_model_info("opencode/does-not-exist")
        except UnknownModelError as e:
            assert type(e) is not Exception
            assert not isinstance(e, KeyError)
            assert e.model == "opencode/does-not-exist"
        else:
            pytest.fail("expected UnknownModelError")

    def test_price_lookup_returns_price_row_with_expected_shape(self):
        info = get_model_info("opencode/claude-opus-5")
        price = info.price

        assert price.input_ore_per_million_tokens > 0
        assert price.output_ore_per_million_tokens > 0
        assert price.cache_read_ore_per_million_tokens > 0
        # cost_ore math (A9) depends on plausible relative magnitudes: output
        # tokens cost at least as much as input tokens, and a cache read is
        # cheaper than a fresh input token.
        assert price.output_ore_per_million_tokens >= price.input_ore_per_million_tokens
        assert (
            price.cache_read_ore_per_million_tokens
            <= price.input_ore_per_million_tokens
        )

    def test_price_lookup_for_known_chat_model_also_has_expected_shape(self):
        info = get_model_info("opencode/gpt-5.5")
        price = info.price

        assert price.input_ore_per_million_tokens > 0
        assert price.output_ore_per_million_tokens > 0
        assert price.cache_read_ore_per_million_tokens > 0


class TestAgentRuntimeConfig:
    def test_agent_runtime_enabled_defaults_to_false(self):
        assert Settings().agent_runtime_enabled is False

    def test_agent_runtime_enabled_can_be_flipped_via_env_var(self, monkeypatch):
        monkeypatch.setenv("AGENT_RUNTIME_ENABLED", "true")

        assert Settings().agent_runtime_enabled is True

    def test_llm_api_key_defaults_to_empty_string(self):
        assert Settings().llm_api_key == ""

    def test_llm_base_url_has_opencode_zen_default(self):
        assert Settings().llm_base_url == "https://opencode.ai/zen/v1"

    def test_llm_default_model_is_a_priced_claude_model(self):
        # The default must itself resolve via get_model_info -- a default
        # that isn't priced would violate SPEC §2 on day one.
        info = get_model_info(Settings().llm_default_model)
        assert info.protocol == "messages"

    def test_the_four_caps_have_specs_stated_defaults(self):
        settings = Settings()

        assert settings.agent_max_tool_turns_per_item == 25
        assert settings.agent_max_output_tokens_per_item == 32000
        assert settings.agent_daily_budget_ore == 5000  # 50 kr, per SPEC §6.5/§8
        assert settings.agent_max_items_per_pass == 20

    def test_daily_budget_ore_can_be_flipped_via_env_var(self, monkeypatch):
        monkeypatch.setenv("AGENT_DAILY_BUDGET_ORE", "1234")

        assert Settings().agent_daily_budget_ore == 1234

    def test_llm_api_key_never_appears_in_unknown_model_error(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "super-secret-key-should-never-leak")
        settings_with_key = Settings()
        assert settings_with_key.llm_api_key == "super-secret-key-should-never-leak"

        try:
            get_model_info("opencode/does-not-exist")
        except UnknownModelError as e:
            assert "super-secret-key-should-never-leak" not in repr(e)
            assert "super-secret-key-should-never-leak" not in str(e)


# --- A6: services/agent_documents.py -- underlagsläsning (SPEC §6.3) -------
#
# Synthetic PDFs are built in-process with `pypdf` alone -- no fixture files,
# no external renderer (WeasyPrint needs system libraries not guaranteed to
# be present; `services/pdf_export.py` already treats it as optional for
# that reason). `_build_text_pdf_bytes` draws real text operators with a
# base-14 Helvetica font (no embedding needed), so `pypdf.extract_text()`
# gets a genuine text layer back -- this is "pypdf's own writer" per A6's
# task note, used because it's simpler and more portable here than driving
# WeasyPrint. `_build_image_only_pdf_bytes` uses Pillow to save a rasterized
# image directly as a PDF, which has no text operators at all.


def _build_text_pdf_bytes(lines: list[str]) -> bytes:
    """Build a minimal, valid one-page PDF with `lines` as real text content
    (BT/Tj operators against the standard Helvetica font) -- a genuine text
    layer `pypdf.extract_text()` can read back, not an image of text.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)  # A4 in points

    font_dict = DictionaryObject()
    font_dict[NameObject("/Type")] = NameObject("/Font")
    font_dict[NameObject("/Subtype")] = NameObject("/Type1")
    font_dict[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_dict[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
    font_ref = writer._add_object(font_dict)

    resources = DictionaryObject()
    font_resource = DictionaryObject()
    font_resource[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = font_resource
    page[NameObject("/Resources")] = resources

    def escape(line: str) -> str:
        return line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content = ["BT", "/F1 12 Tf", "50 800 Td", "14 TL"]
    for i, line in enumerate(lines):
        if i > 0:
            content.append("T*")
        content.append(f"({escape(line)}) Tj")
    content.append("ET")

    stream = DecodedStreamObject()
    stream.set_data("\n".join(content).encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _build_image_only_pdf_bytes() -> bytes:
    """A valid PDF containing only a rasterized image, no text operators at
    all -- e.g. a scanned receipt.
    """
    image = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    image.save(buf, "PDF")
    return buf.getvalue()


_CLEAN_INVOICE_LINES = [
    "Fakturanummer: 2026-0042",
    "Nettobelopp: 1 000,00 kr",
    "Moms 25%: 250,00 kr",
    "Att betala: 1 250,00 kr",
]

_SCRAMBLED_INVOICE_LINES = [
    "Fakturanummer: 2026-0043",
    "Nettobelopp: 1 000,00 kr",
    "Moms 25%: 250,00 kr",
    # A two-column table read out of order: this total doesn't match
    # net + vat, exactly the failure mode SPEC §6.3 warns about.
    "Att betala: 5 000,00 kr",
]

_NO_LABELS_LINES = [
    "Tack för ditt köp!",
    "Kvitto #1234",
    "Kaffe och bulle",
]


def _intake_source(mime_type: str, filename: str = "underlag.pdf") -> IntakeSource:
    return IntakeSource(
        id="src-1",
        source_type=None,
        status=IntakeStatus.PENDING,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=0,
        sha256="deadbeef",
        stored_path="/tmp/does-not-matter-for-this-module",
    )


def _capabilities(pdf_document_blocks: bool) -> LLMCapabilities:
    return LLMCapabilities(
        cache_breakpoint=pdf_document_blocks,
        pdf_document_blocks=pdf_document_blocks,
        refusal_stop_reason=pdf_document_blocks,
    )


class TestPdfTextExtraction:
    def test_extracts_embedded_text(self):
        pdf_bytes = _build_text_pdf_bytes(_CLEAN_INVOICE_LINES)

        text = extract_pdf_text(pdf_bytes)

        assert "Nettobelopp: 1 000,00 kr" in text
        assert "Att betala: 1 250,00 kr" in text

    def test_returns_empty_string_for_image_only_pdf(self):
        pdf_bytes = _build_image_only_pdf_bytes()

        assert extract_pdf_text(pdf_bytes) == ""

    def test_returns_empty_string_for_unparseable_bytes_rather_than_raising(self):
        assert extract_pdf_text(b"not a pdf at all") == ""

    def test_returns_empty_string_for_whitespace_only_text(self):
        pdf_bytes = _build_text_pdf_bytes(["   ", "\t"])

        assert extract_pdf_text(pdf_bytes) == ""


class TestReconciliationHeuristic:
    """SPEC §6.3's "Avstämningen": a labeled net/VAT/total breakdown must be
    found *and* add up before extracted text is trusted -- absence of a
    recognizable breakdown is not itself a failure (see
    `ReconciliationState.NOT_APPLICABLE`'s docstring in
    `services/agent_documents.py`).
    """

    def test_clean_invoice_text_reconciles(self):
        result = reconciliation_result("\n".join(_CLEAN_INVOICE_LINES))

        assert result.state == ReconciliationState.RECONCILES
        assert result.checked is True
        assert result.reconciles is True
        assert result.net_ore == 100_000
        assert result.vat_ore == 25_000
        assert result.total_ore == 125_000

    def test_scrambled_invoice_text_does_not_reconcile(self):
        result = reconciliation_result("\n".join(_SCRAMBLED_INVOICE_LINES))

        assert result.state == ReconciliationState.DOES_NOT_RECONCILE
        assert result.checked is True
        assert result.reconciles is False

    def test_text_with_no_recognizable_labels_is_not_applicable(self):
        result = reconciliation_result("\n".join(_NO_LABELS_LINES))

        assert result.state == ReconciliationState.NOT_APPLICABLE
        assert result.checked is False
        assert result.reconciles is False
        assert result.net_ore is None
        assert result.vat_ore is None
        assert result.total_ore is None

    def test_multiple_vat_lines_are_summed(self):
        text = "\n".join(
            [
                "Nettobelopp: 1 000,00 kr",
                "Moms 12%: 60,00 kr",
                "Moms 25%: 190,00 kr",
                "Att betala: 1 250,00 kr",
            ]
        )

        result = reconciliation_result(text)

        assert result.state == ReconciliationState.RECONCILES
        assert result.vat_ore == 25_000

    def test_reconciles_within_one_ore_rounding_tolerance(self):
        text = "\n".join(
            [
                "Nettobelopp: 1 000,00 kr",
                "Moms 25%: 250,01 kr",
                "Att betala: 1 250,00 kr",
            ]
        )

        assert reconciliation_result(text).state == ReconciliationState.RECONCILES

    def test_does_not_reconcile_beyond_tolerance(self):
        text = "\n".join(
            [
                "Nettobelopp: 1 000,00 kr",
                "Moms 25%: 250,02 kr",
                "Att betala: 1 250,00 kr",
            ]
        )

        assert (
            reconciliation_result(text).state == ReconciliationState.DOES_NOT_RECONCILE
        )

    def test_empty_text_is_not_applicable(self):
        assert reconciliation_result("").state == ReconciliationState.NOT_APPLICABLE


class TestSelectContentForSource:
    """SPEC §9 test cases 20-23, at this module's level."""

    @pytest.mark.parametrize(
        "mime_type", ["image/jpeg", "image/png", "image/gif", "image/webp"]
    )
    @pytest.mark.parametrize("pdf_document_blocks", [True, False])
    def test_image_mime_types_always_return_an_image_block(
        self, mime_type, pdf_document_blocks
    ):
        source = _intake_source(mime_type, filename="kvitto.jpg")
        file_bytes = b"\xff\xd8\xff-not-real-image-bytes-but-that-is-fine-here"

        block = select_content_for_source(
            source, file_bytes, _capabilities(pdf_document_blocks)
        )

        assert block == {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.b64encode(file_bytes).decode("ascii"),
            },
        }

    def test_case_20_pdf_with_text_layer_returns_only_a_text_block(self):
        pdf_bytes = _build_text_pdf_bytes(_CLEAN_INVOICE_LINES)
        source = _intake_source("application/pdf", filename="faktura.pdf")

        block = select_content_for_source(source, pdf_bytes, _capabilities(True))

        assert block["type"] == "text"
        assert "Att betala: 1 250,00 kr" in block["text"]
        # No document block anywhere in the result -- this is the whole
        # point of §6.3's cost ordering.
        assert block.get("source") is None

    def test_case_21_pdf_without_text_layer_and_document_blocks_capability(self):
        pdf_bytes = _build_image_only_pdf_bytes()
        source = _intake_source("application/pdf", filename="skannat_kvitto.pdf")

        block = select_content_for_source(source, pdf_bytes, _capabilities(True))

        assert block["type"] == "document"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "application/pdf"
        # Byte-for-byte fidelity: what comes back must decode to exactly the
        # original PDF, not a re-encoded or lossy copy.
        assert base64.b64decode(block["source"]["data"]) == pdf_bytes

    def test_case_22_pdf_without_text_layer_and_no_document_blocks_capability(self):
        pdf_bytes = _build_image_only_pdf_bytes()
        source = _intake_source("application/pdf", filename="skannat_kvitto.pdf")

        with pytest.raises(DocumentUnreadableError) as exc_info:
            select_content_for_source(source, pdf_bytes, _capabilities(False))

        error = exc_info.value
        assert error.source_id == source.id
        assert isinstance(error.reason, str)
        assert error.reason.strip() != ""

    def test_case_23_non_reconciling_text_escalates_to_document_block_when_capable(
        self,
    ):
        pdf_bytes = _build_text_pdf_bytes(_SCRAMBLED_INVOICE_LINES)
        source = _intake_source("application/pdf", filename="skum_faktura.pdf")

        # Mirrors case 21: untrustworthy text is never sent, the document
        # block is, even though a text layer technically exists.
        block = select_content_for_source(source, pdf_bytes, _capabilities(True))

        assert block["type"] == "document"
        assert base64.b64decode(block["source"]["data"]) == pdf_bytes

    def test_case_23_non_reconciling_text_abstains_when_not_capable(self):
        pdf_bytes = _build_text_pdf_bytes(_SCRAMBLED_INVOICE_LINES)
        source = _intake_source("application/pdf", filename="skum_faktura.pdf")

        # "på Chat-vägen avstående, aldrig en postning på siffror som inte
        # stämmer" -- never pass the untrustworthy text through just because
        # there's nowhere else for it to go.
        with pytest.raises(DocumentUnreadableError) as exc_info:
            select_content_for_source(source, pdf_bytes, _capabilities(False))

        assert exc_info.value.reason.strip() != ""

    def test_case_23_reconciliation_result_on_the_scrambled_pdfs_own_text(self):
        pdf_bytes = _build_text_pdf_bytes(_SCRAMBLED_INVOICE_LINES)

        text = extract_pdf_text(pdf_bytes)

        assert (
            reconciliation_result(text).state == ReconciliationState.DOES_NOT_RECONCILE
        )

    def test_unsupported_mime_type_abstains_rather_than_guessing(self):
        source = _intake_source("application/zip", filename="oj.zip")

        with pytest.raises(DocumentUnreadableError):
            select_content_for_source(source, b"PK\x03\x04", _capabilities(True))


# --- A7: services/agent_tools.py -- verktygsytan (SPEC §6.4, §9 #1/3/6/17) -


def _ensure_agent_tool_accounts():
    for code, name, account_type in [
        ("1920", "Bankkonto", "asset"),
        ("6200", "Tele och post", "expense"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def _agent_tool_period():
    today = date.today()
    last_day = monthrange(today.year, today.month)[1]
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
    )
    return PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=today.year,
        month=today.month,
        start_date=date(today.year, today.month, 1),
        end_date=date(today.year, today.month, last_day),
    )


def _agent_tool_intake_source(tmp_path, name: str = "telefon.pdf"):
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    try:
        return IntakeService().create_source_from_upload_content(
            filename=name,
            content_type="application/pdf",
            content=f"%PDF-1.4 {name}".encode(),
            explanation="Telefonutgift Fello",
            source_type="receipt",
            actor="api",
        )
    finally:
        settings.intake_dir = original


def _agent_tool_voucher_count() -> int:
    return db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"]


def _posta_verifikation_args(
    period_id: str, source_id: str, amount: int = 12500
) -> dict:
    return {
        "date": date.today().isoformat(),
        "period_id": period_id,
        "description": "Telefonutgift Fello",
        "reasoning_summary": "Kvitto matchat mot underlag",
        "intake_source_ids": [source_id],
        "rows": [
            {"account": "1920", "debit": 0, "credit": amount},
            {"account": "6200", "debit": amount, "credit": 0},
        ],
    }


_EXPECTED_TOOL_NAMES = [
    "las_kontoplan",
    "las_perioder",
    "las_verifikationer",
    "las_korrigeringar",
    "las_underlag",
    "hamta_underlagsfil",
    "las_bankhandelser",
    "posta_verifikation",
    "registrera_avstaende",
]


class TestToolDefinitionsOrder:
    """SPEC §6.6: the tool list is built in a fixed order because it sits in
    the cached system-prompt prefix -- a reorder is a silent cache-buster.
    """

    def test_tool_order_matches_the_expected_list(self):
        assert [t["name"] for t in AGENT_TOOL_DEFINITIONS] == _EXPECTED_TOOL_NAMES

    def test_tool_order_is_stable_across_repeated_reads(self):
        """Trivially true for a module-level constant -- the point is that a
        future accidental reorder of the literal tuple in agent_tools.py is
        caught by the same expected-list assertion, not that the list
        magically changes between two reads in one process.
        """
        first_read = [t["name"] for t in AGENT_TOOL_DEFINITIONS]
        second_read = [t["name"] for t in AGENT_TOOL_DEFINITIONS]
        assert first_read == second_read == _EXPECTED_TOOL_NAMES

    def test_every_definition_has_the_anthropic_tool_shape(self):
        for tool in AGENT_TOOL_DEFINITIONS:
            assert set(tool.keys()) == {"name", "description", "input_schema"}
            assert isinstance(tool["input_schema"], dict)
            assert tool["input_schema"].get("type") == "object"


class TestAppendOnlyToolSurface:
    """SPEC §9 test case 17 -- the only automatic check that the append-only
    guarantee survives the agent's tool surface. This must break if someone
    adds a "convenient" tool that can edit or delete a posted voucher.
    """

    def test_tool_names_are_exactly_the_nine_allowed_tools(self):
        assert {t["name"] for t in AGENT_TOOL_DEFINITIONS} == set(_EXPECTED_TOOL_NAMES)
        assert len(AGENT_TOOL_DEFINITIONS) == 9

    def test_no_tool_name_contains_a_mutate_or_delete_verb(self):
        forbidden_fragments = [
            "uppdatera",
            "andra",
            "ändra",
            "redigera",
            "radera",
            "ta_bort",
            "delete",
            "update",
            "edit",
            "patch",
            "remove",
        ]
        for tool in AGENT_TOOL_DEFINITIONS:
            lowered = tool["name"].lower()
            for fragment in forbidden_fragments:
                assert (
                    fragment not in lowered
                ), f"tool name {tool['name']!r} contains {fragment!r}"

    def test_no_tool_description_implies_editing_or_deleting_a_posted_voucher(self):
        forbidden_phrases = [
            "ändra en postad",
            "ändra postad",
            "redigera en postad",
            "radera en postad",
            "radera verifikation",
            "ta bort en postad",
            "ta bort verifikation",
            "update the voucher",
            "edit the voucher",
            "delete the voucher",
            "modify a posted",
        ]
        for tool in AGENT_TOOL_DEFINITIONS:
            haystack = tool["description"].lower()
            for phrase in forbidden_phrases:
                assert (
                    phrase not in haystack
                ), f"tool {tool['name']!r} description contains {phrase!r}"

    def test_only_two_tools_are_documented_as_writing_anything(self):
        write_tool_names = {"posta_verifikation", "registrera_avstaende"}
        read_tool_names = set(_EXPECTED_TOOL_NAMES) - write_tool_names
        for tool in AGENT_TOOL_DEFINITIONS:
            if tool["name"] in read_tool_names:
                assert (
                    "skrivskyddat" in tool["description"].lower()
                ), f"read tool {tool['name']!r} should say it is read-only"

    def test_posta_verifikation_is_the_only_tool_that_touches_the_ledger(self):
        description = next(
            t["description"]
            for t in AGENT_TOOL_DEFINITIONS
            if t["name"] == "posta_verifikation"
        )
        assert "huvudboken" in description.lower()
        for tool in AGENT_TOOL_DEFINITIONS:
            if tool["name"] != "posta_verifikation":
                assert "huvudboken" not in tool["description"].lower()


class TestIdempotencyKeyDerivation:
    """SPEC §6.4: uuid5(BOK_NAMESPACE, f"intake:{source_id}"), fixed and
    deterministic -- the whole point is that a worker retry after a crash
    reproduces the exact same key for the exact same intake source.
    """

    def test_same_source_id_derives_the_identical_key_every_time(self):
        first = derive_posting_idempotency_key("src-42")
        second = derive_posting_idempotency_key("src-42")
        assert first == second

    def test_different_source_ids_derive_different_keys(self):
        assert derive_posting_idempotency_key(
            "src-1"
        ) != derive_posting_idempotency_key("src-2")

    def test_key_matches_the_spec_formula_under_bok_namespace(self):
        key = derive_posting_idempotency_key("src-1")
        assert key == str(uuid.uuid5(BOK_NAMESPACE, "intake:src-1"))

    def test_bok_namespace_is_a_fixed_uuid_constant(self):
        assert isinstance(BOK_NAMESPACE, uuid.UUID)


@pytest.mark.usefixtures("test_db")
class TestPostaVerifikationTool:
    """SPEC §9 test case 1, plus the worker-retry-after-a-crash story behind
    case 2: repeated calls for the same source_id must derive the identical
    idempotency key and replay rather than double-post.
    """

    def test_case_1_posts_a_voucher_for_a_pending_intake_source(self, tmp_path):
        _ensure_agent_tool_accounts()
        period = _agent_tool_period()
        source = _agent_tool_intake_source(tmp_path)

        result = execute_tool(
            "posta_verifikation",
            _posta_verifikation_args(period.id, source.id),
            actor="agent",
            capabilities=_capabilities(True),
        )

        assert result["status"] == "posted"
        assert result["created_by"] == "agent"
        assert _agent_tool_voucher_count() == 1

        refreshed_source = IntakeService().get_source(source.id)
        assert refreshed_source.status == IntakeStatus.PROCESSED

    def test_repeated_calls_for_the_same_source_derive_the_same_key_and_replay(
        self, tmp_path
    ):
        _ensure_agent_tool_accounts()
        period = _agent_tool_period()
        source = _agent_tool_intake_source(tmp_path)
        args = _posta_verifikation_args(period.id, source.id)

        first = execute_tool(
            "posta_verifikation", args, actor="agent", capabilities=_capabilities(True)
        )
        key_before_retry = derive_posting_idempotency_key(source.id)
        second = execute_tool(
            "posta_verifikation", args, actor="agent", capabilities=_capabilities(True)
        )
        key_after_retry = derive_posting_idempotency_key(source.id)

        assert key_before_retry == key_after_retry
        assert second.get("idempotent_replay") is True
        assert first["id"] == second["id"]
        assert _agent_tool_voucher_count() == 1

    def test_missing_traceability_raises_the_domain_validation_error(self, tmp_path):
        """A tool call with no intake/bank source at all is a bad argument at
        the domain level, not a bash-style crash -- ``ValidationError``
        propagates unconverted (post_agent_voucher's own check)."""
        _ensure_agent_tool_accounts()
        period = _agent_tool_period()

        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "posta_verifikation",
                {
                    "date": date.today().isoformat(),
                    "period_id": period.id,
                    "description": "Telefonutgift Fello",
                    "rows": [
                        {"account": "1920", "debit": 0, "credit": 12500},
                        {"account": "6200", "debit": 12500, "credit": 0},
                    ],
                },
                actor="agent",
                capabilities=_capabilities(True),
            )
        assert exc_info.value.code == "missing_source_traceability"


@pytest.mark.usefixtures("test_db")
class TestRegistreraAvstaendeTool:
    """SPEC §9 test case 3: an abstention is recorded with a motivation and
    never creates a voucher."""

    def test_records_the_abstention_without_creating_a_voucher(self, tmp_path):
        source = _agent_tool_intake_source(tmp_path)

        result = execute_tool(
            "registrera_avstaende",
            {
                "source_id": source.id,
                "summary": "Kunde inte avgöra konteringen säkert",
                "error_detail": (
                    "Beloppen i den extraherade texten går inte ihop med " "totalsumman"
                ),
                "warnings": ["lag_confidence_ocr"],
            },
            actor="agent",
            capabilities=_capabilities(True),
        )

        assert result["status"] == "failed"
        assert result["error_detail"] == (
            "Beloppen i den extraherade texten går inte ihop med totalsumman"
        )
        assert result["warnings"] == ["lag_confidence_ocr"]
        assert _agent_tool_voucher_count() == 0

        refreshed_source = IntakeService().get_source(source.id)
        assert refreshed_source.status == IntakeStatus.FAILED


@pytest.mark.usefixtures("test_db")
class TestToolArgumentValidation:
    """SPEC §9 test case 6: a malformed tool call raises a validation error
    instead of proceeding."""

    def test_missing_required_field_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "posta_verifikation",
                {
                    # "date" is missing entirely.
                    "period_id": "p1",
                    "description": "desc",
                    "intake_source_ids": ["src-1"],
                    "rows": [
                        {"account": "1920", "debit": 0, "credit": 100},
                        {"account": "6200", "debit": 100, "credit": 0},
                    ],
                },
                actor="agent",
                capabilities=_capabilities(True),
            )
        assert exc_info.value.code == "invalid_tool_arguments"

    def test_wrong_type_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "las_kontoplan",
                {"active_only": "not-a-recognizable-boolean"},
                actor="agent",
                capabilities=_capabilities(True),
            )
        assert exc_info.value.code == "invalid_tool_arguments"

    def test_too_few_rows_raises_validation_error(self):
        with pytest.raises(ValidationError):
            execute_tool(
                "posta_verifikation",
                {
                    "date": date.today().isoformat(),
                    "period_id": "p1",
                    "description": "desc",
                    "intake_source_ids": ["src-1"],
                    "rows": [{"account": "1920", "debit": 0, "credit": 100}],
                },
                actor="agent",
                capabilities=_capabilities(True),
            )

    def test_unknown_tool_name_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "radera_verifikation",
                {},
                actor="agent",
                capabilities=_capabilities(True),
            )
        assert exc_info.value.code == "unknown_tool"


@pytest.mark.usefixtures("test_db")
class TestHamtaUnderlagsfilTool:
    """`hamta_underlagsfil` wired correctly to
    ``services/agent_documents.select_content_for_source`` -- resolving the
    stored file and reading its bytes itself, then delegating the actual
    content-selection decision.
    """

    def test_wired_to_select_content_for_source_for_a_pdf_with_text_layer(
        self, tmp_path
    ):
        original_intake_dir = settings.intake_dir
        settings.intake_dir = str(tmp_path / "intake")
        try:
            pdf_bytes = _build_text_pdf_bytes(_CLEAN_INVOICE_LINES)
            source = IntakeService().create_source_from_upload_content(
                filename="faktura.pdf",
                content_type="application/pdf",
                content=pdf_bytes,
                explanation="Faktura",
                source_type="supplier_invoice",
                actor="api",
            )

            block = execute_tool(
                "hamta_underlagsfil",
                {"source_id": source.id},
                actor="agent",
                capabilities=_capabilities(True),
            )
        finally:
            settings.intake_dir = original_intake_dir

        assert block["type"] == "text"
        assert "Att betala: 1 250,00 kr" in block["text"]

    def test_document_unreadable_error_propagates_rather_than_being_swallowed(
        self, tmp_path
    ):
        original_intake_dir = settings.intake_dir
        settings.intake_dir = str(tmp_path / "intake")
        try:
            pdf_bytes = _build_image_only_pdf_bytes()
            source = IntakeService().create_source_from_upload_content(
                filename="skannat_kvitto.pdf",
                content_type="application/pdf",
                content=pdf_bytes,
                explanation="Skannat kvitto",
                source_type="receipt",
                actor="api",
            )

            with pytest.raises(DocumentUnreadableError) as exc_info:
                execute_tool(
                    "hamta_underlagsfil",
                    {"source_id": source.id},
                    actor="agent",
                    capabilities=_capabilities(False),
                )
        finally:
            settings.intake_dir = original_intake_dir

        assert exc_info.value.source_id == source.id


@pytest.mark.usefixtures("test_db")
class TestReadOnlyTools:
    """Light coverage for the remaining read tools -- each just needs to
    prove it reaches its backing repository/service and returns a
    JSON-serializable shape.
    """

    def test_las_kontoplan_returns_seeded_accounts(self):
        _ensure_agent_tool_accounts()

        result = execute_tool(
            "las_kontoplan", {}, actor="agent", capabilities=_capabilities(True)
        )

        codes = {account["code"] for account in result}
        assert {"1920", "6200"} <= codes

    def test_las_perioder_returns_the_created_period_with_lock_fields(self):
        period = _agent_tool_period()

        result = execute_tool(
            "las_perioder", {}, actor="agent", capabilities=_capabilities(True)
        )

        matching = next(p for p in result if p["id"] == period.id)
        assert matching["locked"] is False
        assert matching["locked_by"] is None

    def test_las_verifikationer_filters_by_period(self, tmp_path):
        _ensure_agent_tool_accounts()
        period = _agent_tool_period()
        source = _agent_tool_intake_source(tmp_path)
        execute_tool(
            "posta_verifikation",
            _posta_verifikation_args(period.id, source.id),
            actor="agent",
            capabilities=_capabilities(True),
        )

        result = execute_tool(
            "las_verifikationer",
            {"period_id": period.id},
            actor="agent",
            capabilities=_capabilities(True),
        )

        assert result["total"] == 1
        assert result["items"][0]["status"] == "posted"

    def test_las_korrigeringar_returns_a_list(self):
        result = execute_tool(
            "las_korrigeringar", {}, actor="agent", capabilities=_capabilities(True)
        )
        assert isinstance(result, list)

    def test_las_underlag_returns_the_pending_queue(self, tmp_path):
        source = _agent_tool_intake_source(tmp_path)

        result = execute_tool(
            "las_underlag", {}, actor="agent", capabilities=_capabilities(True)
        )

        ids = {item["id"] for item in result["items"]}
        assert source.id in ids

    def test_las_underlag_returns_a_single_sources_metadata(self, tmp_path):
        source = _agent_tool_intake_source(tmp_path)

        result = execute_tool(
            "las_underlag",
            {"source_id": source.id},
            actor="agent",
            capabilities=_capabilities(True),
        )

        assert result["id"] == source.id
        assert result["status"] == "pending"

    def test_las_bankhandelser_returns_a_queue_shape(self):
        result = execute_tool(
            "las_bankhandelser", {}, actor="agent", capabilities=_capabilities(True)
        )
        assert "items" in result
        assert "total" in result


# --- A8: services/agent_session.py -- sessionen (SPEC §6.3, §6.7, §9 #4/5/7/14/15)


class FakeLLMClient:
    """Structural `LLMClient` test double (SPEC §9): returns pre-programmed
    `LLMTurn`s from a queue, never touching a network.

    If more than one turn is queued, each call pops the next one off the
    front; once only one is left, that same turn is returned forever -- this
    is what lets `TestSessionTurnLimit` simulate a model that loops without
    ever deciding anything, by queueing exactly one repeating turn.
    """

    def __init__(self, turns: list[LLMTurn], capabilities: LLMCapabilities):
        self._turns = list(turns)
        self.capabilities = capabilities
        self.calls: list[dict] = []

    def run_turn(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        max_tokens: int,
    ) -> LLMTurn:
        self.calls.append(
            {
                "system": system,
                "messages": messages,
                "tools": tools,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        if len(self._turns) > 1:
            return self._turns.pop(0)
        return self._turns[0]


def _run_test_session(
    client: FakeLLMClient,
    source: IntakeSource,
    open_periods: Optional[list] = None,
    max_tool_turns: Optional[int] = None,
) -> SessionOutcome:
    return run_session(
        client=client,
        source=source,
        file_bytes=b"%PDF-1.4 fake, no real text layer",
        open_periods=open_periods or [],
        today=date.today(),
        model="opencode/claude-opus-5",
        actor="agent",
        max_tool_turns=max_tool_turns,
    )


class TestBuildSystemPrompt:
    """SPEC §9 test case 14, plus the deterministic-ordering half of §6.6."""

    def test_case_14_identical_across_two_calls(self):
        _ensure_agent_tool_accounts()

        first = build_system_prompt()
        second = build_system_prompt()

        assert first == second

    def test_kontoplan_section_is_sorted_by_code_not_creation_order(self):
        AccountRepository.create("9999", "Sista kontot", "expense")
        AccountRepository.create("1000", "Första kontot", "asset")

        prompt = build_system_prompt()

        assert prompt.index("1000  Första kontot") < prompt.index("9999  Sista kontot")

    def test_includes_company_instructions_and_system_instructions(self):
        prompt = build_system_prompt()

        # The company's editable accounting instructions (default content,
        # AgentInstructionRepository) and the read-only system instructions
        # both land in the prompt, in that fixed order (SPEC §6.3).
        assert "Bokföringsinstruktioner" in prompt
        system_pos = prompt.find("Bokföringsprocess")
        company_pos = prompt.find("Bokföringsinstruktioner")
        assert system_pos != -1
        assert company_pos != -1
        assert system_pos < company_pos


class TestBuildUserTurn:
    def test_contains_todays_date_source_metadata_and_the_content_block(self, tmp_path):
        source = _agent_tool_intake_source(tmp_path, name="kvitto.pdf")
        content_block = {"type": "text", "text": "Nettobelopp: 100,00 kr"}
        today = date(2026, 9, 16)

        messages = build_user_turn(source, content_block, today, [])

        assert len(messages) == 1
        message = messages[0]
        assert message["role"] == "user"
        text_block = message["content"][0]
        assert "2026-09-16" in text_block["text"]
        assert source.original_filename in text_block["text"]
        assert message["content"][-1] == content_block


class TestSessionRefusal:
    """SPEC §9 test case 4."""

    def test_case_4_refusal_is_abstained_with_no_voucher(self, tmp_path):
        _ensure_agent_tool_accounts()
        source = _agent_tool_intake_source(tmp_path)
        client = FakeLLMClient(
            [
                LLMTurn(
                    text="Jag kan inte hjälpa till med det här.",
                    tool_calls=[],
                    stop="refusal",
                    usage=Usage(10, 5, 0),
                )
            ],
            capabilities=_capabilities(True),
        )

        outcome = _run_test_session(client, source)

        assert outcome.kind == "abstained"
        assert outcome.reason is not None
        assert outcome.reason.startswith("agent_refusal:")
        assert "kan inte hjälpa" in outcome.reason
        assert outcome.voucher_id is None
        assert _agent_tool_voucher_count() == 0
        assert len(client.calls) == 1
        assert outcome.usage == Usage(10, 5, 0)


class TestSessionMaxTokens:
    """SPEC §9 test case 5."""

    def test_case_5_truncated_turn_is_abstained_with_no_voucher(self, tmp_path):
        _ensure_agent_tool_accounts()
        source = _agent_tool_intake_source(tmp_path)
        client = FakeLLMClient(
            [
                LLMTurn(
                    text="Jag börjar analysera under...",
                    tool_calls=[],
                    stop="max_tokens",
                    usage=Usage(20, 32000, 0),
                )
            ],
            capabilities=_capabilities(True),
        )

        outcome = _run_test_session(client, source)

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_output_truncated"
        assert outcome.voucher_id is None
        assert _agent_tool_voucher_count() == 0
        assert len(client.calls) == 1


class TestSessionNoOutcome:
    """`stop == "end"` with no tool calls -- the model finished without ever
    posting or abstaining. SPEC §1 requires every pass to end in one of
    those two outcomes, so this must be its own explicit abstention, never a
    silent no-op.
    """

    def test_end_with_no_tool_calls_is_an_explicit_abstention(self, tmp_path):
        _ensure_agent_tool_accounts()
        source = _agent_tool_intake_source(tmp_path)
        client = FakeLLMClient(
            [LLMTurn(text="Klart.", tool_calls=[], stop="end", usage=Usage(5, 5, 0))],
            capabilities=_capabilities(True),
        )

        outcome = _run_test_session(client, source)

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_no_outcome"
        assert _agent_tool_voucher_count() == 0


class TestSessionTurnLimit:
    """SPEC §9 test case 7."""

    def test_case_7_turn_limit_reached_without_an_outcome(self, tmp_path):
        _ensure_agent_tool_accounts()
        source = _agent_tool_intake_source(tmp_path)
        harmless_call = ToolCall(id="call-1", name="las_kontoplan", arguments={})
        client = FakeLLMClient(
            [
                LLMTurn(
                    text="",
                    tool_calls=[harmless_call],
                    stop="tool_calls",
                    usage=Usage(5, 5, 0),
                )
            ],
            capabilities=_capabilities(True),
        )

        outcome = _run_test_session(client, source, max_tool_turns=3)

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_turn_limit"
        assert len(client.calls) == 3
        assert _agent_tool_voucher_count() == 0
        assert outcome.usage == Usage(15, 15, 0)


class TestSessionPostingEndsImmediately:
    """Edge case worth locking down: a successful `posta_verifikation` call
    ends the session immediately, even if the same turn queued other tool
    calls alongside it.
    """

    def test_posting_ends_the_session_with_no_further_tool_calls_executed(
        self, tmp_path
    ):
        _ensure_agent_tool_accounts()
        period = _agent_tool_period()
        source = _agent_tool_intake_source(tmp_path)
        posting_call = ToolCall(
            id="call-1",
            name="posta_verifikation",
            arguments=_posta_verifikation_args(period.id, source.id),
        )
        harmless_call = ToolCall(id="call-2", name="las_kontoplan", arguments={})
        client = FakeLLMClient(
            [
                LLMTurn(
                    text="",
                    tool_calls=[posting_call, harmless_call],
                    stop="tool_calls",
                    usage=Usage(1, 1, 0),
                )
            ],
            capabilities=_capabilities(True),
        )

        outcome = _run_test_session(client, source, open_periods=[period])

        assert outcome.kind == "posted"
        assert outcome.voucher_id
        assert outcome.tool_result is not None
        assert outcome.tool_result["status"] == "posted"
        assert _agent_tool_voucher_count() == 1
        assert len(client.calls) == 1

        assert len(outcome.turns) == 1
        executed = outcome.turns[0].executed_tool_calls
        assert len(executed) == 1
        assert executed[0].tool_call.name == "posta_verifikation"
        assert executed[0].ok is True


class TestSessionToolErrorRetriesWithinBudget:
    """A tool error is fed back as `is_error: true` and the loop continues --
    confirms retries work within budget, per SPEC §6.7's "får rätta sig
    själv inom varvtaket".
    """

    def test_tool_error_is_retried_and_the_second_attempt_succeeds(self, tmp_path):
        _ensure_agent_tool_accounts()
        period = _agent_tool_period()
        source = _agent_tool_intake_source(tmp_path)

        # No intake_source_ids/bank_input_ids/bank_transaction_ids at all ->
        # post_agent_voucher raises ValidationError("missing_source_traceability")
        # before anything is written (see TestPostaVerifikationTool above).
        failing_call = ToolCall(
            id="call-1",
            name="posta_verifikation",
            arguments={
                "date": date.today().isoformat(),
                "period_id": period.id,
                "description": "Telefonutgift Fello",
                "rows": [
                    {"account": "1920", "debit": 0, "credit": 12500},
                    {"account": "6200", "debit": 12500, "credit": 0},
                ],
            },
        )
        recovering_call = ToolCall(
            id="call-2",
            name="registrera_avstaende",
            arguments={
                "source_id": source.id,
                "summary": "Kunde inte bokföra automatiskt",
                "error_detail": "Underlaget saknar spårbarhet till en postning",
            },
        )
        client = FakeLLMClient(
            [
                LLMTurn(
                    text="",
                    tool_calls=[failing_call],
                    stop="tool_calls",
                    usage=Usage(1, 1, 0),
                ),
                LLMTurn(
                    text="",
                    tool_calls=[recovering_call],
                    stop="tool_calls",
                    usage=Usage(1, 1, 0),
                ),
            ],
            capabilities=_capabilities(True),
        )

        outcome = _run_test_session(
            client, source, open_periods=[period], max_tool_turns=5
        )

        assert outcome.kind == "abstained"
        assert outcome.reason == "Kunde inte bokföra automatiskt"
        assert _agent_tool_voucher_count() == 0
        assert len(client.calls) == 2

        # The first turn's failure was fed back as an is_error tool_result,
        # not swallowed or used to abort the session.
        second_call_messages = client.calls[1]["messages"]
        tool_result_message = second_call_messages[-1]
        assert tool_result_message["role"] == "user"
        assert tool_result_message["content"][0]["is_error"] is True

        assert len(outcome.turns) == 2
        assert outcome.turns[0].executed_tool_calls[0].ok is False
        assert (
            "missing_source_traceability"
            in outcome.turns[0].executed_tool_calls[0].error
        )
        assert outcome.turns[1].executed_tool_calls[0].ok is True


class TestSessionDocumentUnreadableShortCircuits:
    """`DocumentUnreadableError` from content selection must short-circuit
    before any `run_turn` call -- SPEC §6.3 step 3 costs zero tokens because
    there is genuinely no API call, not a discarded one.
    """

    def test_no_run_turn_call_is_made_when_the_source_is_unreadable(self, tmp_path):
        # `_agent_tool_intake_source` writes a fake, textless PDF body, and
        # capabilities without pdf_document_blocks means there is no
        # fallback -- select_content_for_source must raise.
        source = _agent_tool_intake_source(tmp_path)
        client = FakeLLMClient(
            [
                LLMTurn(
                    text="should never be reached",
                    tool_calls=[],
                    stop="end",
                    usage=Usage(999, 999, 0),
                )
            ],
            capabilities=_capabilities(False),
        )

        outcome = _run_test_session(client, source)

        assert outcome.kind == "abstained"
        assert outcome.reason
        assert outcome.usage == Usage(0, 0, 0)
        assert client.calls == []
        assert outcome.turns == []


class TestSessionUsageAccumulationAndCachePrompt:
    """SPEC §9 test case 15, at the session level: the exact same system
    string must be sent on every call given the same underlying data, and
    `usage.cache_read_input_tokens` must be reported/accumulated verbatim,
    never recomputed or discarded.
    """

    def test_case_15_same_system_prompt_and_accumulated_cache_usage_per_item(
        self, tmp_path
    ):
        _ensure_agent_tool_accounts()
        period = _agent_tool_period()

        systems_sent = []
        cache_read_seen = []
        for index, cache_read in enumerate([0, 120, 130, 140, 150]):
            source = _agent_tool_intake_source(tmp_path, name=f"kvitto-{index}.pdf")
            recovering_call = ToolCall(
                id="call-1",
                name="registrera_avstaende",
                arguments={
                    "source_id": source.id,
                    "summary": "test",
                    "error_detail": "test",
                },
            )
            client = FakeLLMClient(
                [
                    LLMTurn(
                        text="",
                        tool_calls=[recovering_call],
                        stop="tool_calls",
                        usage=Usage(
                            input_tokens=1000,
                            output_tokens=50,
                            cache_read_input_tokens=cache_read,
                        ),
                    )
                ],
                capabilities=_capabilities(True),
            )

            outcome = _run_test_session(client, source, open_periods=[period])

            systems_sent.append(client.calls[0]["system"])
            cache_read_seen.append(outcome.usage.cache_read_input_tokens)

        # Same underlying DB state across every item in the pass -> byte
        # for byte the same system string sent every single time.
        assert len(set(systems_sent)) == 1

        # Reported verbatim, never recomputed: exactly what the fake queued.
        assert cache_read_seen[0] == 0
        assert cache_read_seen[1:] == [120, 130, 140, 150]
        assert all(value > 0 for value in cache_read_seen[1:])
