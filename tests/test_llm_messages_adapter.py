"""Tests for `services/llm/messages.py`, the Anthropic Messages adapter (A5).

Split out from `tests/test_agent_runtime.py` because these tests are
fixture-heavy (`tests/fixtures/llm_messages/*.json`) and none of them touch
the DB (`test_db` fixture) the rest of that file uses -- keeping them here
avoids diluting that file's per-task section structure with a chunk of
tests that don't share its setup. `pytest tests/ -v` picks this file up
automatically like any other `test_*.py` module; no registration needed.

Per SPEC §9: no real network call anywhere in this file. Fixtures are
loaded and validated into the real `anthropic.types.Message` type so the
normalization tests run against the SDK's actual response schema rather
than a guess at its shape; `TestRunTurnWiring` stubs the Anthropic client
instance directly instead of hitting the network.
"""

import json
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.lib.streaming._types import TextEvent, ThinkingEvent
from anthropic.types import Message, RawContentBlockStartEvent

from services.llm import LLMCapabilities, LLMConnectionError, LLMRateLimitError
from services.llm.messages import (
    MESSAGES_MAX_TOKENS_FALLBACK,
    MessagesClient,
    UnrecognizedStopReasonError,
    dispatch_stream_event,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm_messages"


def _load_message(filename: str) -> Message:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        raw = json.load(f)
    return Message.model_validate(raw)


def _contains_key(value: Any, key: str) -> bool:
    """Recursively search a built-request-kwargs structure for `key`.

    Used to prove `budget_tokens` is absent not just at the top level of
    the kwargs dict but nested anywhere inside it (e.g. inside `thinking`).
    """
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_contains_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_contains_key(v, key) for v in value)
    return False


# --- Request building -------------------------------------------------------


class TestBuildRequestKwargs:
    def _build(self) -> dict[str, Any]:
        return MessagesClient.build_request_kwargs(
            system="du är en bokföringsagent",
            messages=[{"role": "user", "content": [{"type": "text", "text": "hej"}]}],
            tools=[{"name": "las_kontoplan", "description": "...", "input_schema": {}}],
            model="opencode/claude-opus-5",
            max_tokens=4096,
        )

    def test_system_becomes_content_block_list_with_cache_control(self):
        kwargs = self._build()

        assert isinstance(kwargs["system"], list)
        last_block = kwargs["system"][-1]
        assert last_block["type"] == "text"
        assert last_block["text"] == "du är en bokföringsagent"
        assert last_block["cache_control"] == {"type": "ephemeral"}

    def test_thinking_is_adaptive(self):
        kwargs = self._build()

        assert kwargs["thinking"] == {"type": "adaptive"}

    def test_output_config_effort_is_high(self):
        kwargs = self._build()

        assert kwargs["output_config"] == {"effort": "high"}

    def test_budget_tokens_never_appears_anywhere_in_the_built_kwargs(self):
        kwargs = self._build()

        assert not _contains_key(kwargs, "budget_tokens")

    def test_messages_and_tools_pass_through_unchanged(self):
        messages = [{"role": "user", "content": [{"type": "text", "text": "hej"}]}]
        tools = [{"name": "las_kontoplan", "description": "...", "input_schema": {}}]

        kwargs = MessagesClient.build_request_kwargs(
            system="x", messages=messages, tools=tools, model="m", max_tokens=1
        )

        assert kwargs["messages"] is messages
        assert kwargs["tools"] is tools

    def test_model_and_max_tokens_pass_through(self):
        kwargs = self._build()

        assert kwargs["model"] == "claude-opus-5"
        assert kwargs["max_tokens"] == 4096

    def test_no_cap_still_sends_the_protocols_required_max_tokens(self):
        kwargs = MessagesClient.build_request_kwargs(
            system="x", messages=[], tools=[], model="m", max_tokens=None
        )

        assert kwargs["max_tokens"] == MESSAGES_MAX_TOKENS_FALLBACK


# --- Normalization against recorded fixtures --------------------------------


class TestNormalizeMessage:
    def test_tool_use_stop_maps_to_tool_calls_with_correct_arguments(self):
        message = _load_message("tool_use_stop.json")

        turn = MessagesClient.normalize_message(message)

        assert turn.stop == "tool_calls"
        assert len(turn.tool_calls) == 1
        call = turn.tool_calls[0]
        assert call.id == "toolu_01PostaVerifikation0001"
        assert call.name == "posta_verifikation"
        assert call.arguments["source_id"] == "src-123"
        assert len(call.arguments["rader"]) == 3

    def test_tool_use_stop_text_excludes_thinking_block(self):
        message = _load_message("tool_use_stop.json")

        turn = MessagesClient.normalize_message(message)

        assert "bokför fakturan" in turn.text
        # The fixture's thinking block reasons about VAT reconciliation --
        # if it ever leaked into `text` this substring would show up there.
        assert "momssats" not in turn.text

    def test_end_turn_maps_to_end(self):
        message = _load_message("end_turn.json")

        turn = MessagesClient.normalize_message(message)

        assert turn.stop == "end"
        assert turn.tool_calls == []
        assert "Klart" in turn.text

    def test_refusal_maps_to_refusal(self):
        message = _load_message("refusal_stop.json")

        turn = MessagesClient.normalize_message(message)

        assert turn.stop == "refusal"
        assert turn.tool_calls == []

    def test_max_tokens_maps_to_max_tokens(self):
        message = _load_message("max_tokens_stop.json")

        turn = MessagesClient.normalize_message(message)

        assert turn.stop == "max_tokens"

    def test_cache_hit_fixture_reports_positive_cache_read_tokens(self):
        message = _load_message("cache_hit.json")

        turn = MessagesClient.normalize_message(message)

        assert turn.usage.cache_read_input_tokens > 0
        assert turn.usage.cache_read_input_tokens == 8400

    def test_absent_cache_read_tokens_normalizes_to_zero_not_error(self):
        message = _load_message("end_turn.json")

        turn = MessagesClient.normalize_message(message)

        assert turn.usage.cache_read_input_tokens == 0

    def test_usage_input_and_output_tokens_map_through(self):
        message = _load_message("tool_use_stop.json")

        turn = MessagesClient.normalize_message(message)

        assert turn.usage.input_tokens == 1450
        assert turn.usage.output_tokens == 210

    def test_unrecognized_stop_reason_raises_rather_than_normalizing_silently(self):
        message = _load_message("end_turn.json")
        # "pause_turn" is a real value the installed SDK's StopReason type
        # allows but this adapter deliberately does not map (see
        # services/llm/messages.py's _STOP_REASON_MAP comment).
        object.__setattr__(message, "stop_reason", "pause_turn")

        with pytest.raises(UnrecognizedStopReasonError):
            MessagesClient.normalize_message(message)


# --- Capabilities ------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_match_spec_for_messages_protocol(self):
        assert MessagesClient.capabilities == LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
            # SPEC-tradar.md §12.1 / task T5: both adapters stream, each
            # through its own SDK's streaming helper.
            streaming=True,
        )


# --- run_turn wiring (stubbed client, no network) ---------------------------


class _FakeStreamManager:
    """Stands in for `anthropic.Anthropic(...).messages.stream(...)`'s
    context-manager return value -- a `MessageStreamManager`."""

    def __init__(self, final_message: Message) -> None:
        self._final_message = final_message
        self.entered = False

    def __enter__(self) -> "_FakeStreamManager":
        self.entered = True
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def get_final_message(self) -> Message:
        return self._final_message


class TestRunTurnWiring:
    def test_run_turn_wires_build_stream_and_normalize_without_network(self):
        client = MessagesClient(api_key="dummy-test-key", base_url="http://127.0.0.1:0")
        fake_message = _load_message("tool_use_stop.json")
        fake_stream = _FakeStreamManager(fake_message)

        received_kwargs: dict[str, Any] = {}

        def fake_stream_call(**kwargs: Any) -> _FakeStreamManager:
            received_kwargs.update(kwargs)
            return fake_stream

        # Patch the instance's bound method rather than the real transport --
        # proves run_turn calls .messages.stream(...) and never falls
        # through to an actual HTTP call (there is no real API key or
        # reachable host here, so a real call would hang or error, not
        # silently pass).
        client._client.messages.stream = fake_stream_call  # type: ignore[method-assign]

        turn = client.run_turn(
            system="systemprompt",
            messages=[{"role": "user", "content": [{"type": "text", "text": "hej"}]}],
            tools=[],
            model="opencode/claude-opus-5",
            max_tokens=1024,
        )

        assert fake_stream.entered is True
        assert received_kwargs["model"] == "claude-opus-5"
        assert received_kwargs["thinking"] == {"type": "adaptive"}
        assert turn.stop == "tool_calls"
        assert turn.tool_calls[0].name == "posta_verifikation"


# --- Error translation (SPEC §6.7, task A10) --------------------------------
#
# Real `anthropic` SDK exception types must never leak past this adapter --
# `services/agent_runtime.py` isn't allowed to import `anthropic` (SPEC
# §4/§10). These stub the SDK client to raise the *real* exception types
# (constructed directly, no network) and assert `run_turn` translates them
# into the protocol-agnostic `LLMConnectionError`/`LLMRateLimitError`.


def _raise(exc: Exception):
    def _fake_stream_call(**kwargs: Any):
        raise exc

    return _fake_stream_call


class TestRunTurnErrorTranslation:
    def _client(self) -> MessagesClient:
        return MessagesClient(api_key="dummy-test-key", base_url="http://127.0.0.1:0")

    def _call_run_turn(self, client: MessagesClient) -> None:
        client.run_turn(
            system="systemprompt",
            messages=[{"role": "user", "content": [{"type": "text", "text": "hej"}]}],
            tools=[],
            model="opencode/claude-opus-5",
            max_tokens=1024,
        )

    def test_api_connection_error_becomes_llm_connection_error(self):
        client = self._client()
        request = httpx2.Request("POST", "https://opencode.ai/zen/v1/messages")
        sdk_exc = anthropic.APIConnectionError(request=request)
        client._client.messages.stream = _raise(sdk_exc)  # type: ignore[method-assign]

        with pytest.raises(LLMConnectionError):
            self._call_run_turn(client)

    def test_rate_limit_error_becomes_llm_rate_limit_error_with_retry_after(self):
        client = self._client()
        request = httpx2.Request("POST", "https://opencode.ai/zen/v1/messages")
        response = httpx2.Response(429, request=request, headers={"retry-after": "12"})
        sdk_exc = anthropic.RateLimitError("rate limited", response=response, body=None)
        client._client.messages.stream = _raise(sdk_exc)  # type: ignore[method-assign]

        with pytest.raises(LLMRateLimitError) as exc_info:
            self._call_run_turn(client)

        assert exc_info.value.retry_after_seconds == 12.0

    def test_rate_limit_error_without_retry_after_header_carries_none(self):
        client = self._client()
        request = httpx2.Request("POST", "https://opencode.ai/zen/v1/messages")
        response = httpx2.Response(429, request=request, headers={})
        sdk_exc = anthropic.RateLimitError("rate limited", response=response, body=None)
        client._client.messages.stream = _raise(sdk_exc)  # type: ignore[method-assign]

        with pytest.raises(LLMRateLimitError) as exc_info:
            self._call_run_turn(client)

        assert exc_info.value.retry_after_seconds is None


# --- T5 (SPEC-tradar.md §12.1): streaming hooks ------------------------------
#
# `on_text`/`on_tool_call` on `run_turn`, and the pure dispatcher behind
# them. These live here rather than in `tests/test_tradar.py` because they
# assert against this SDK's own event types, and SPEC §4/§10's import
# boundary allows that in this file alone (see `TestOpenaiImportBoundary`
# for the check that enforces it).


class TestMessagesAdapterStreamDispatch:
    """Test case 9 — against recorded raw events, validated through the real
    SDK's own schema, so the fixtures are checked rather than guessed. No
    network call (SPEC §9)."""

    @staticmethod
    def _text_event(text: str, snapshot: str):
        return TextEvent.model_validate(
            {"type": "text", "text": text, "snapshot": snapshot}
        )

    @staticmethod
    def _tool_use_start_event(name: str):
        return RawContentBlockStartEvent.model_validate(
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_01PostaVerifikation0001",
                    "name": name,
                    "input": {},
                },
            }
        )

    @staticmethod
    def _text_block_start_event():
        return RawContentBlockStartEvent.model_validate(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }
        )

    def test_case_9_on_text_is_called_once_per_increment(self):
        seen: list = []

        for text, snapshot in (
            ("Jag ", "Jag "),
            ("bokför ", "Jag bokför "),
            ("den.", "Jag bokför den."),
        ):
            dispatch_stream_event(self._text_event(text, snapshot), on_text=seen.append)

        assert seen == ["Jag ", "bokför ", "den."]

    def test_the_delta_is_sent_not_the_accumulated_snapshot(self):
        """`message.delta` on the wire is an increment. Sending the snapshot
        would make the client render the whole answer once per character."""
        seen: list = []

        dispatch_stream_event(
            self._text_event("den.", "Jag bokför den."), on_text=seen.append
        )

        assert seen == ["den."]

    def test_a_tool_use_block_start_announces_the_tool_name(self):
        seen: list = []

        dispatch_stream_event(
            self._tool_use_start_event("posta_verifikation"), on_tool_call=seen.append
        )

        assert seen == ["posta_verifikation"]

    def test_a_text_block_start_is_not_a_tool_call(self):
        seen: list = []

        dispatch_stream_event(self._text_block_start_event(), on_tool_call=seen.append)

        assert seen == []

    def test_a_missing_hook_is_not_an_error(self):
        """Either hook may be absent; dispatching must not care."""
        dispatch_stream_event(self._text_event("hej", "hej"))
        dispatch_stream_event(self._tool_use_start_event("las_kontoplan"))

    def test_thinking_is_never_delivered_as_text(self):
        """The model's internal reasoning is not its answer — the same line
        `normalize_message` already draws."""
        seen: list = []
        event = ThinkingEvent.model_validate(
            {
                "type": "thinking",
                "thinking": "momsen är 25%",
                "snapshot": "momsen är 25%",
            }
        )

        dispatch_stream_event(event, on_text=seen.append)

        assert seen == []


class TestMessagesAdapterRunTurnStreams:
    """The wiring between the hooks and the stream, with the SDK stubbed —
    the pattern `tests/test_llm_messages_adapter.py` already uses."""

    @staticmethod
    def _client_with_events(events: list, final_message_fixture: str = "end_turn.json"):
        final_message = _load_message(final_message_fixture)

        class _FakeStream:
            def __init__(self):
                self.iterated = False

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return None

            def __iter__(self):
                self.iterated = True
                return iter(events)

            def get_final_message(self):
                return final_message

        fake = _FakeStream()
        client = MessagesClient(api_key="dummy-test-key", base_url="http://127.0.0.1:0")

        def _stream(**kwargs: Any) -> "_FakeStream":
            return fake

        # Patching the instance's bound method, exactly as
        # `TestRunTurnWiring` above does -- a named function rather than a
        # lambda so the one `type: ignore` sits on the assignment itself.
        client._client.messages.stream = _stream  # type: ignore[method-assign,assignment]
        return client, fake

    def test_case_9_hooks_receive_increments_during_the_turn(self):
        events = [
            TestMessagesAdapterStreamDispatch._text_event("Jag ", "Jag "),
            TestMessagesAdapterStreamDispatch._text_event("bokför.", "Jag bokför."),
            TestMessagesAdapterStreamDispatch._tool_use_start_event("las_kontoplan"),
        ]
        client, fake = self._client_with_events(events)
        text_seen: list = []
        tools_seen: list = []

        turn = client.run_turn(
            system="s",
            messages=[],
            tools=[],
            model="opencode/claude-opus-5",
            max_tokens=1024,
            on_text=text_seen.append,
            on_tool_call=tools_seen.append,
        )

        assert fake.iterated is True
        assert text_seen == ["Jag ", "bokför."]
        assert tools_seen == ["las_kontoplan"]
        # The complete turn still comes back, unchanged by the streaming.
        assert turn.stop == "end"

    def test_without_hooks_the_stream_is_not_iterated(self):
        """No reason to walk a stream nobody is listening to — and it keeps
        the unstreamed path exactly as it was."""
        client, fake = self._client_with_events([])

        turn = client.run_turn(
            system="s",
            messages=[],
            tools=[],
            model="opencode/claude-opus-5",
            max_tokens=1024,
        )

        assert fake.iterated is False
        assert turn.stop == "end"
