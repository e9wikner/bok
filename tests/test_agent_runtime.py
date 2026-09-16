"""Tests for the agent runtime module (docs/redesign/SPEC-agentruntime.md).

This file grows across tasks A3-A13 of tasks/agentruntime/todo.md. Each task
gets its own section/class so the file stays navigable as it grows:

- A3: AgentRunRepository (this file, first pass)
- A4: services/llm/ protocol layer, model registry, config
- A6: services/agent_documents.py -- underlagsläsning, textlager, avstämning

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

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from config import Settings
from domain.models import IntakeSource
from domain.types import IntakeStatus
from repositories.agent_run_repo import AgentRunRepository
from services.agent_documents import (
    DocumentUnreadableError,
    ReconciliationState,
    extract_pdf_text,
    reconciliation_result,
    select_content_for_source,
)
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
