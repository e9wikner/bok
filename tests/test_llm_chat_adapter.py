"""Tests for `services/llm/chat.py`, the OpenAI Chat Completions adapter (A12).

Split out from `tests/test_agent_runtime.py`, mirroring
`tests/test_llm_messages_adapter.py`'s own reasoning exactly: these tests are
fixture-heavy (`tests/fixtures/llm_chat/*.json`) and none of them touch the
DB (`test_db` fixture) the rest of that file uses. `pytest tests/ -v` picks
this file up automatically like any other `test_*.py` module.

Per SPEC §9: no real network call anywhere in this file. Fixtures are loaded
and validated into the real `openai.types.chat.ChatCompletion` type so the
normalization tests run against the SDK's actual response schema rather than
a guess at its shape; `TestRunTurnWiring`/`TestRunTurnErrorTranslation` stub
the OpenAI client instance directly instead of hitting the network.

SPEC §9 test case 18 ("samma pass, en gång per adapter") is covered here as
`TestCase18ProtocolParity`: the Messages-protocol fixture
(`tests/fixtures/llm_messages/tool_use_stop.json`) and this file's
`tool_calls_stop.json` encode the *same* `posta_verifikation` call (same
`source_id`, same three accounting rows) -- both adapters must normalize it
to an equal `ToolCall`, proving the protocol doesn't leak into the outcome.
"""

import json
from pathlib import Path
from typing import Any

import openai
import pytest
from openai.types.chat import ChatCompletion

from services.llm import (
    LLMCapabilities,
    LLMConnectionError,
    LLMRateLimitError,
    ToolCall,
)
from services.llm.chat import (
    ChatClient,
    MalformedToolArgumentsError,
    UnrecognizedFinishReasonError,
    UnsupportedContentBlockError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm_chat"


def _load_completion(filename: str) -> ChatCompletion:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        raw = json.load(f)
    return ChatCompletion.model_validate(raw)


# --- Tool translation --------------------------------------------------------


class TestTranslateTools:
    def test_anthropic_tool_dict_becomes_openai_function_tool_dict(self):
        anthropic_tools = [
            {
                "name": "las_kontoplan",
                "description": "Läs kontoplanen.",
                "input_schema": {
                    "type": "object",
                    "properties": {"active_only": {"type": "boolean"}},
                },
            }
        ]

        translated = ChatClient.translate_tools(anthropic_tools)

        assert translated == [
            {
                "type": "function",
                "function": {
                    "name": "las_kontoplan",
                    "description": "Läs kontoplanen.",
                    "parameters": {
                        "type": "object",
                        "properties": {"active_only": {"type": "boolean"}},
                    },
                },
            }
        ]

    def test_translates_every_tool_in_order(self):
        anthropic_tools = [
            {"name": "a", "description": "A", "input_schema": {}},
            {"name": "b", "description": "B", "input_schema": {}},
        ]

        translated = ChatClient.translate_tools(anthropic_tools)

        assert [t["function"]["name"] for t in translated] == ["a", "b"]


# --- Message translation -----------------------------------------------------


class TestTranslateMessages:
    def test_system_string_becomes_prepended_system_message(self):
        translated = ChatClient.translate_messages("du är en bokföringsagent", [])

        assert translated == [{"role": "system", "content": "du är en bokföringsagent"}]

    def test_user_message_with_only_text_becomes_plain_content_string(self):
        messages = [{"role": "user", "content": [{"type": "text", "text": "hej"}]}]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1] == {"role": "user", "content": "hej"}

    def test_multiple_text_blocks_are_concatenated(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Dagens datum: 2026-09-16\n\n"},
                    {"type": "text", "text": "Underlag: faktura.pdf"},
                ],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1]["content"] == (
            "Dagens datum: 2026-09-16\n\nUnderlag: faktura.pdf"
        )

    def test_image_block_becomes_image_url_content_part(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Underlag:"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "AAAA",
                        },
                    },
                ],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1] == {
            "role": "user",
            "content": [
                {"type": "text", "text": "Underlag:"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,AAAA"},
                },
            ],
        }

    def test_assistant_message_with_only_text_becomes_plain_content_string(self):
        messages = [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Klart."}],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1] == {"role": "assistant", "content": "Klart."}

    def test_assistant_tool_use_block_becomes_tool_calls_with_json_string_arguments(
        self,
    ):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Jag bokför fakturan."},
                    {
                        "type": "tool_use",
                        "id": "toolu_0001",
                        "name": "posta_verifikation",
                        "input": {"source_id": "src-123", "rows": [1, 2]},
                    },
                ],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assistant_message = translated[1]
        assert assistant_message["role"] == "assistant"
        assert assistant_message["content"] == "Jag bokför fakturan."
        assert assistant_message["tool_calls"] == [
            {
                "id": "toolu_0001",
                "type": "function",
                "function": {
                    "name": "posta_verifikation",
                    # Arguments are a JSON *string*, unlike Anthropic's
                    # already-a-dict tool_use.input.
                    "arguments": json.dumps(
                        {"source_id": "src-123", "rows": [1, 2]}, ensure_ascii=False
                    ),
                },
            }
        ]
        # And it really is a JSON string, round-trippable with json.loads.
        parsed = json.loads(assistant_message["tool_calls"][0]["function"]["arguments"])
        assert parsed == {"source_id": "src-123", "rows": [1, 2]}

    def test_assistant_message_with_only_tool_use_has_no_content_text(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_0002",
                        "name": "las_kontoplan",
                        "input": {},
                    }
                ],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1]["content"] is None
        assert translated[1]["tool_calls"][0]["function"]["name"] == "las_kontoplan"

    def test_tool_result_with_plain_text_content_becomes_tool_role_message(self):
        """The common, expected case per `services.agent_session.
        _tool_result_content_blocks`: every tool result except an
        `hamta_underlagsfil` image/document passthrough is exactly this
        shape -- a single text block.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_0001",
                        "content": [
                            {"type": "text", "text": '{"total": 3, "items": []}'}
                        ],
                    }
                ],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1] == {
            "role": "tool",
            "tool_call_id": "toolu_0001",
            "content": '{"total": 3, "items": []}',
        }

    def test_multiple_tool_results_in_one_anthropic_message_become_separate_tool_messages(
        self,
    ):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_a",
                        "content": [{"type": "text", "text": "resultat a"}],
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_b",
                        "content": [{"type": "text", "text": "resultat b"}],
                    },
                ],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1:] == [
            {"role": "tool", "tool_call_id": "toolu_a", "content": "resultat a"},
            {"role": "tool", "tool_call_id": "toolu_b", "content": "resultat b"},
        ]

    def test_error_tool_result_content_is_plain_text_content(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_err",
                        "content": [
                            {"type": "text", "text": "[invalid_tool_arguments] ..."}
                        ],
                        "is_error": True,
                    }
                ],
            }
        ]

        translated = ChatClient.translate_messages("sys", messages)

        assert translated[1]["content"] == "[invalid_tool_arguments] ..."

    def test_a_full_representative_sequence_translates_end_to_end(self):
        """text + image (initial user turn) -> tool_use (assistant) ->
        tool_result with plain text (tool turn) -- a realistic sequence per
        `services/agent_session.py`.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Underlag: kvitto.jpg"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgo=",
                        },
                    },
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_0009",
                        "name": "las_verifikationer",
                        "input": {"limit": 5},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_0009",
                        "content": [{"type": "text", "text": "[]"}],
                    }
                ],
            },
        ]

        translated = ChatClient.translate_messages("systemprompt", messages)

        assert [m["role"] for m in translated] == [
            "system",
            "user",
            "assistant",
            "tool",
        ]
        assert translated[1]["content"][1]["type"] == "image_url"
        assert (
            translated[2]["tool_calls"][0]["function"]["name"] == "las_verifikationer"
        )
        assert translated[3] == {
            "role": "tool",
            "tool_call_id": "toolu_0009",
            "content": "[]",
        }


class TestUnsupportedContentBlocks:
    """SPEC §2: a `document` block "finns inte" on this protocol. Reaching
    this translator at all should be unreachable in normal operation (see
    `UnsupportedContentBlockError`'s docstring) -- these tests only prove
    the defensive check fires rather than silently dropping or mis-sending
    the block.
    """

    def test_document_block_in_a_user_message_raises(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Underlag:"},
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": "AAAA",
                        },
                    },
                ],
            }
        ]

        with pytest.raises(UnsupportedContentBlockError) as exc_info:
            ChatClient.translate_messages("sys", messages)

        assert exc_info.value.block_type == "document"

    def test_tool_result_with_only_an_image_block_raises(self):
        """`hamta_underlagsfil`'s image/document passthrough, per
        `services.agent_session._tool_result_content_blocks` -- there is
        nowhere to put an image inside a `role: "tool"` message's plain
        string content, and no text to fall back to here.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_underlag",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": "AAAA",
                                },
                            }
                        ],
                    }
                ],
            }
        ]

        with pytest.raises(UnsupportedContentBlockError):
            ChatClient.translate_messages("sys", messages)

    def test_tool_result_with_only_a_document_block_raises(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_underlag",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": "AAAA",
                                },
                            }
                        ],
                    }
                ],
            }
        ]

        with pytest.raises(UnsupportedContentBlockError):
            ChatClient.translate_messages("sys", messages)


# --- Capabilities -------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_match_spec_for_chat_protocol(self):
        assert ChatClient.capabilities == LLMCapabilities(
            cache_breakpoint=False,
            pdf_document_blocks=False,
            refusal_stop_reason=False,
        )


# --- Response normalization against recorded fixtures ------------------------


class TestNormalizeResponse:
    def test_tool_calls_finish_maps_to_tool_calls_with_parsed_arguments(self):
        response = _load_completion("tool_calls_stop.json")

        turn = ChatClient.normalize_response(response)

        assert turn.stop == "tool_calls"
        assert len(turn.tool_calls) == 1
        call = turn.tool_calls[0]
        assert call.id == "call_PostaVerifikation0001"
        assert call.name == "posta_verifikation"
        # A real dict, parsed via json.loads -- not a raw string.
        assert isinstance(call.arguments, dict)
        assert call.arguments["source_id"] == "src-123"
        assert len(call.arguments["rader"]) == 3

    def test_stop_finish_maps_to_end(self):
        response = _load_completion("stop_finish.json")

        turn = ChatClient.normalize_response(response)

        assert turn.stop == "end"
        assert turn.tool_calls == []

    def test_refusal_shaped_prose_still_normalizes_to_end_not_a_refusal_category(self):
        """Locks down the "no heuristic" decision (SPEC §2/§9): this
        protocol has no dedicated refusal outcome. Text that reads like a
        refusal in prose, with finish_reason == "stop", must still come back
        as an ordinary "end" -- never scanned for refusal-shaped language.
        """
        response = _load_completion("stop_finish.json")

        turn = ChatClient.normalize_response(response)

        assert "inte hjälpa till" in turn.text
        assert turn.stop == "end"

    def test_length_finish_maps_to_max_tokens(self):
        response = _load_completion("length_finish.json")

        turn = ChatClient.normalize_response(response)

        assert turn.stop == "max_tokens"

    def test_unrecognized_finish_reason_raises_rather_than_normalizing_silently(self):
        response = _load_completion("stop_finish.json")
        # "content_filter" is a real value the installed SDK's
        # Choice.finish_reason Literal allows but this adapter deliberately
        # does not map (see services/llm/chat.py's _FINISH_REASON_MAP
        # comment).
        response.choices[0].finish_reason = "content_filter"

        with pytest.raises(UnrecognizedFinishReasonError):
            ChatClient.normalize_response(response)

    def test_malformed_tool_call_arguments_raise_rather_than_passing_through(self):
        response = _load_completion("malformed_tool_call.json")

        with pytest.raises(MalformedToolArgumentsError) as exc_info:
            ChatClient.normalize_response(response)

        assert exc_info.value.tool_call_id == "call_Malformed0001"

    def test_usage_input_and_output_tokens_map_through(self):
        response = _load_completion("tool_calls_stop.json")

        turn = ChatClient.normalize_response(response)

        assert turn.usage.input_tokens == 1450
        assert turn.usage.output_tokens == 210

    def test_cache_read_input_tokens_is_always_zero_even_when_the_fixture_has_cached_tokens(
        self,
    ):
        """`tool_calls_stop.json` deliberately carries a non-zero
        `usage.prompt_tokens_details.cached_tokens` (900) to prove this
        adapter never reads it -- SPEC §2/§6.6: no cache accounting this
        protocol can verify, so this must be a hard 0, never inferred.
        """
        response = _load_completion("tool_calls_stop.json")
        assert (
            response.usage.prompt_tokens_details.cached_tokens == 900
        )  # fixture sanity

        turn = ChatClient.normalize_response(response)

        assert turn.usage.cache_read_input_tokens == 0

    def test_cache_read_input_tokens_is_zero_with_no_details_at_all(self):
        response = _load_completion("stop_finish.json")

        turn = ChatClient.normalize_response(response)

        assert turn.usage.cache_read_input_tokens == 0


# --- run_turn wiring (stubbed client, no network) ----------------------------


class TestRunTurnWiring:
    def test_run_turn_wires_translate_call_and_normalize_without_network(self):
        client = ChatClient(api_key="dummy-test-key", base_url="http://127.0.0.1:0")
        fake_response = _load_completion("tool_calls_stop.json")

        received_kwargs: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> ChatCompletion:
            received_kwargs.update(kwargs)
            return fake_response

        # Patch the instance's bound method rather than the real transport --
        # proves run_turn calls .chat.completions.create(...) and never
        # falls through to an actual HTTP call.
        client._client.chat.completions.create = fake_create  # type: ignore[method-assign]

        turn = client.run_turn(
            system="systemprompt",
            messages=[{"role": "user", "content": [{"type": "text", "text": "hej"}]}],
            tools=[{"name": "las_kontoplan", "description": "...", "input_schema": {}}],
            model="opencode/gpt-5.5",
            max_tokens=1024,
        )

        assert received_kwargs["model"] == "opencode/gpt-5.5"
        assert received_kwargs["messages"][0] == {
            "role": "system",
            "content": "systemprompt",
        }
        assert received_kwargs["tools"][0]["type"] == "function"
        assert received_kwargs["max_completion_tokens"] == 1024
        assert "max_tokens" not in received_kwargs
        assert turn.stop == "tool_calls"
        assert turn.tool_calls[0].name == "posta_verifikation"


# --- Error translation (SPEC §6.7) -------------------------------------------
#
# Real `openai` SDK exception types must never leak past this adapter --
# `services/agent_runtime.py` isn't allowed to import `openai` (SPEC §4/§10).
# These stub the SDK client to raise the *real* exception types (constructed
# directly, no network) and assert `run_turn` translates them into the
# protocol-agnostic `LLMConnectionError`/`LLMRateLimitError`, exactly
# mirroring `tests/test_llm_messages_adapter.py`'s `TestRunTurnErrorTranslation`.


def _raise(exc: Exception):
    def _fake_create(**kwargs: Any):
        raise exc

    return _fake_create


class TestRunTurnErrorTranslation:
    def _client(self) -> ChatClient:
        return ChatClient(api_key="dummy-test-key", base_url="http://127.0.0.1:0")

    def _call_run_turn(self, client: ChatClient) -> None:
        client.run_turn(
            system="systemprompt",
            messages=[{"role": "user", "content": [{"type": "text", "text": "hej"}]}],
            tools=[],
            model="opencode/gpt-5.5",
            max_tokens=1024,
        )

    def test_api_connection_error_becomes_llm_connection_error(self):
        import httpx2

        client = self._client()
        request = httpx2.Request("POST", "https://opencode.ai/zen/v1/chat/completions")
        sdk_exc = openai.APIConnectionError(request=request)
        client._client.chat.completions.create = _raise(sdk_exc)  # type: ignore[method-assign]

        with pytest.raises(LLMConnectionError):
            self._call_run_turn(client)

    def test_rate_limit_error_becomes_llm_rate_limit_error_with_retry_after(self):
        import httpx2

        client = self._client()
        request = httpx2.Request("POST", "https://opencode.ai/zen/v1/chat/completions")
        response = httpx2.Response(429, request=request, headers={"retry-after": "7"})
        sdk_exc = openai.RateLimitError("rate limited", response=response, body=None)
        client._client.chat.completions.create = _raise(sdk_exc)  # type: ignore[method-assign]

        with pytest.raises(LLMRateLimitError) as exc_info:
            self._call_run_turn(client)

        assert exc_info.value.retry_after_seconds == 7.0

    def test_rate_limit_error_without_retry_after_header_carries_none(self):
        import httpx2

        client = self._client()
        request = httpx2.Request("POST", "https://opencode.ai/zen/v1/chat/completions")
        response = httpx2.Response(429, request=request, headers={})
        sdk_exc = openai.RateLimitError("rate limited", response=response, body=None)
        client._client.chat.completions.create = _raise(sdk_exc)  # type: ignore[method-assign]

        with pytest.raises(LLMRateLimitError) as exc_info:
            self._call_run_turn(client)

        assert exc_info.value.retry_after_seconds is None


# --- SPEC §9 test case 18: protocol parity -----------------------------------


class TestCase18ProtocolParity:
    """ "Samma verktygsanrop ger samma postning. Protokollet syns inte i
    utfallet." `tests/fixtures/llm_messages/tool_use_stop.json` (Messages)
    and `tests/fixtures/llm_chat/tool_calls_stop.json` (Chat) encode the same
    underlying model decision -- call `posta_verifikation` with the same
    `source_id` and the same three accounting rows. Both adapters must
    normalize that into an equal `ToolCall`, which is what lets
    `services.agent_session.run_session` drive the same posting regardless
    of which adapter produced the turn.
    """

    def test_both_adapters_normalize_the_same_tool_call_identically(self):
        from anthropic.types import Message

        from services.llm.messages import MessagesClient

        messages_fixture_path = (
            Path(__file__).parent / "fixtures" / "llm_messages" / "tool_use_stop.json"
        )
        with open(messages_fixture_path, encoding="utf-8") as f:
            messages_raw = json.load(f)
        messages_turn = MessagesClient.normalize_message(
            Message.model_validate(messages_raw)
        )

        chat_turn = ChatClient.normalize_response(
            _load_completion("tool_calls_stop.json")
        )

        assert messages_turn.stop == "tool_calls"
        assert chat_turn.stop == "tool_calls"
        assert len(messages_turn.tool_calls) == len(chat_turn.tool_calls) == 1

        messages_call = messages_turn.tool_calls[0]
        chat_call = chat_turn.tool_calls[0]
        assert messages_call.name == chat_call.name == "posta_verifikation"
        # Same arguments -- the id differs (each protocol mints its own
        # call id), which is expected and irrelevant to the posting outcome.
        assert messages_call.arguments == chat_call.arguments
        assert isinstance(messages_call, ToolCall)
        assert isinstance(chat_call, ToolCall)


# --- SPEC §4/§10: import boundary --------------------------------------------


class TestOpenaiImportBoundary:
    def test_openai_is_imported_only_in_services_llm_chat_and_its_own_tests(self):
        """SPEC §4/§10: "anthropic/openai importeras bara i services/llm/".
        A structural regression check, mirroring test case 17's own
        reasoning: this should break loudly if a future change adds an
        `import openai`/`from openai` anywhere it doesn't belong.
        """
        repo_root = Path(__file__).parent.parent
        allowed = {
            (repo_root / "services" / "llm" / "chat.py").resolve(),
            Path(__file__).resolve(),
        }
        offenders = []
        for path in repo_root.rglob("*.py"):
            resolved = path.resolve()
            if resolved in allowed:
                continue
            parts = resolved.parts
            if any(
                segment in {"venv", ".git", "node_modules", "__pycache__"}
                for segment in parts
            ):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(
                line.strip().startswith(("import openai", "from openai"))
                for line in text.splitlines()
            ):
                offenders.append(str(path.relative_to(repo_root)))

        assert offenders == []
