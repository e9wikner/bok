"""Tests for the agent runtime module (docs/redesign/SPEC-agentruntime.md).

This file grows across tasks A3-A13 of tasks/agentruntime/todo.md. Each task
gets its own section/class so the file stays navigable as it grows:

- A3: AgentRunRepository (this file, first pass)
- A4: services/llm/ protocol layer, model registry, config

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
"""

import json

import pytest

from config import Settings
from repositories.agent_run_repo import AgentRunRepository
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
