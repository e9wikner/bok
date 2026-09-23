"""OpenAI Chat Completions protocol adapter (docs/redesign/SPEC-agentruntime.md §2, §4, §9).

This is the only module in the codebase -- besides its own tests -- allowed
to `import openai` (SPEC §4, §10). Everything else sees `ChatClient` only
through the structural `services.llm.LLMClient` Protocol:
`run_turn(system, messages, tools, model, max_tokens) -> LLMTurn`.

Unlike `services/llm/messages.py`, this adapter is where the real translation
cost sits (SPEC §4's architectural decision, restated in that module's
docstring): `messages`/`tools` arriving here are already Anthropic's own
Messages API wire shapes (content blocks: `text`/`image`/`document`/
`tool_use`/`tool_result`; tools: `{"name", "description", "input_schema"}`),
because that is the protocol-agnostic lingua franca used everywhere above
`services/llm/` (built by `services/agent_session.py`, `services/agent_tools.py`,
`services/agent_documents.py`). This module translates that shape DOWN into
OpenAI's Chat Completions shape, in the direction `messages.py` never has to.

Per SPEC §2's protocol-differences table, this protocol lacks, relative to
Messages:

- **Cache breakpoint**: none we control or can verify (`capabilities.
  cache_breakpoint=False`) -- `Usage.cache_read_input_tokens` is always `0`
  here, never inferred from `prompt_tokens_details.cached_tokens` (see
  `_normalize_response`'s comment on that field).
- **PDF `document` blocks**: don't exist on this protocol
  (`capabilities.pdf_document_blocks=False`) -- `services.agent_documents.
  select_content_for_source` already routes around this by raising
  `DocumentUnreadableError` before a `document` block would ever reach an
  adapter with this capability set to `False` (SPEC §6.3 step 3). A
  `document` block reaching `_translate_messages` anyway is therefore a
  defensive check on a path that should be unreachable in normal operation,
  not an expected branch -- see `UnsupportedContentBlockError`.
- **Thinking/effort**: provider-specific or absent. This adapter sends
  neither `thinking` nor `output_config` -- there is nothing in OpenAI's
  Chat Completions request shape to put them in, and OpenCode Zen's
  Chat-protocol model families each have their own (or no) reasoning-effort
  knob, which is out of this task's scope to wire up.
- **Tool loop**: `finish_reason == "tool_calls"`, and each tool call's
  `function.arguments` is a JSON *string* that must be parsed with
  `json.loads` -- never string matching (SPEC §2, §9's explicit wording).
  See `_normalize_response`/`MalformedToolArgumentsError`.
- **Refusal as its own outcome**: no dedicated code. A model refusal on
  Chat Completions comes back as ordinary text with `finish_reason ==
  "stop"`, which normalizes to `"end"`, exactly like any other completed
  response. No heuristic (e.g. scanning `content` for refusal-shaped
  prose) is implemented here to detect one -- SPEC is explicit this
  protocol has no dedicated code for it, and guessing would manufacture a
  false positive/negative rate nobody asked for. `ChatCompletionMessage`
  does carry its own `refusal: Optional[str]` field (confirmed against the
  installed `openai>=2.0` SDK -- a *structured-output* refusal field, used
  by the JSON-schema/structured-outputs feature this codebase's tool-calling
  loop does not use), which is deliberately not read here either, for the
  same reason: it is a different mechanism than SPEC's Messages-protocol
  `stop_reason == "refusal"`, and treating it as equivalent would be a
  second, undocumented refusal path this adapter's `capabilities.
  refusal_stop_reason=False` explicitly says doesn't exist.

Structured the same way as `messages.py`: pure, network-free translation
functions (`_translate_tools`, `_translate_messages`, `_normalize_response`)
plus a thin `run_turn` that wires them to the actual
`.chat.completions.create(...)` call -- the one thing that touches the
network, and the one thing the tests stub out.
"""

import json
from typing import Any, Optional

import openai
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
)

from services.llm import (
    LLMCapabilities,
    LLMConnectionError,
    LLMRateLimitError,
    LLMTurn,
    StopReason,
    StreamTextHook,
    StreamToolCallHook,
    ToolCall,
    Usage,
    api_model_id,
    gateway_headers,
)

# Normalizes OpenAI's Chat Completions `finish_reason` -> services.llm.StopReason.
#
# The installed SDK's `Choice.finish_reason` type
# (`openai.types.chat.chat_completion.Choice`) is
# `Literal["stop", "length", "tool_calls", "content_filter", "function_call"]`.
# "content_filter" and the legacy "function_call" (pre-tools API) are
# deliberately left out of this table -- there is no Messages-protocol
# equivalent to map either onto, and SPEC §6.7/§10's "ett osäkert utfall är
# ett avstående, aldrig en postning" means an unhandled finish reason must
# raise, not silently become "end" or "tool_calls". See
# `UnrecognizedFinishReasonError`.
#
# Deliberately no "refusal" entry: this protocol has no such finish_reason
# value at all (confirmed against the installed SDK's `Choice.finish_reason`
# Literal above) -- a refusal here is just "stop" with refusal-shaped text,
# which correctly normalizes to "end" via this table, per the module
# docstring's "Refusal as its own outcome" section.
_FINISH_REASON_MAP: dict[str, StopReason] = {
    "tool_calls": "tool_calls",
    "stop": "end",
    "length": "max_tokens",
}


class UnrecognizedFinishReasonError(Exception):
    """Raised when the Chat Completions API returns a `finish_reason` this
    adapter has no mapping for (e.g. "content_filter", "function_call").

    Deliberately fatal rather than swallowed -- mirrors `services.llm.
    messages.UnrecognizedStopReasonError`'s reasoning exactly: a new or
    unhandled finish reason must surface as a loud failure, never quietly
    become `"end"` or `"tool_calls"` and risk a posting on an outcome nobody
    has categorized (SPEC §6.7).
    """

    def __init__(self, finish_reason: Optional[str]) -> None:
        super().__init__(
            f"Unrecognized Chat Completions finish_reason: {finish_reason!r}"
        )
        self.finish_reason = finish_reason


class UnsupportedContentBlockError(Exception):
    """Raised when an Anthropic-native content block has no representation
    on the Chat Completions protocol.

    Two cases, both defensive rather than expected (see module docstring):

    - A `document` block reaches `_translate_messages`. SPEC §2: "Finns
      inte" -- PDF `document` blocks don't exist on this protocol at all.
      This should never happen in practice: `services.agent_documents.
      select_content_for_source`, called with `ChatClient.capabilities`
      (`pdf_document_blocks=False`), already raises `DocumentUnreadableError`
      instead of ever producing a `document` block for this adapter (SPEC
      §6.3 step 3).
    - A `tool_result` block whose content is only an `image`/`document`
      block, with no plain text to fall back to (e.g. `hamta_underlagsfil`'s
      image/document passthrough, per `services.agent_session.
      _tool_result_content_blocks`). OpenAI's tool-result message content is
      plain text/string, not a list of typed content blocks -- there is
      nowhere to put an image inside a `role: "tool"` message on this
      protocol either.
    """

    def __init__(self, block_type: str, *, context: str) -> None:
        super().__init__(
            f"Content block type {block_type!r} has no Chat Completions "
            f"representation ({context}). This adapter's capabilities "
            "(pdf_document_blocks=False) should make this unreachable in "
            "normal operation -- see services.agent_documents."
            "select_content_for_source."
        )
        self.block_type = block_type


class UnsupportedToolCallTypeError(Exception):
    """Raised when a tool call in the response is not a function-tool call.

    Defensive, and expected to be unreachable: `ChatClient.translate_tools`
    only ever emits `{"type": "function", ...}` tool declarations (SPEC's
    nine-tool surface, `services.agent_tools.AGENT_TOOL_DEFINITIONS`), so a
    model returning the installed SDK's other tool-call shape (a "custom",
    freeform-input tool call -- a feature this codebase's tools never
    declare) would be answering with a tool call for a tool it was never
    offered.
    """

    def __init__(self, tool_call_type: str) -> None:
        super().__init__(
            f"Unsupported tool call type {tool_call_type!r} -- this adapter "
            "only ever declares function tools, so the model should never "
            "return this shape."
        )
        self.tool_call_type = tool_call_type


class MalformedToolArgumentsError(Exception):
    """Raised when a tool call's `function.arguments` string is not valid JSON.

    SPEC §9: "JSON-strängargument parsas med json.loads -- aldrig
    strängmatchning." A model that returns malformed JSON in a tool call's
    arguments is a real, if rare, failure mode -- this adapter raises rather
    than silently passing the raw string through as if it were a valid
    arguments dict, or swallowing the error (SPEC §10: "ett osäkert utfall är
    ett avstående, aldrig en postning"). `services/agent_session.py` (A8) is
    not touched by this task, so there is no path today that turns this into
    an `is_error` tool_result and lets the model retry -- it is simply an
    exception that propagates out of `run_turn`, same as any other
    unrecoverable adapter failure.
    """

    def __init__(self, tool_call_id: str, name: str, raw_arguments: str) -> None:
        super().__init__(
            f"Tool call {tool_call_id!r} ({name!r}) returned arguments that "
            f"are not valid JSON: {raw_arguments!r}"
        )
        self.tool_call_id = tool_call_id
        self.name = name
        self.raw_arguments = raw_arguments


class ChatClient:
    """`LLMClient` adapter for OpenAI's Chat Completions API (SPEC §2).

    Structurally satisfies `services.llm.LLMClient` -- no inheritance, same
    as `services.llm.messages.MessagesClient` (see A4's Protocol design).
    """

    #: SPEC §2's capability table for the Chat Completions protocol: no
    #: verifiable cache breakpoint, no `document` blocks, no dedicated
    #: refusal outcome. All three `False`, exactly as SPEC §2 states.
    capabilities = LLMCapabilities(
        cache_breakpoint=False,
        pdf_document_blocks=False,
        refusal_stop_reason=False,
        # This one it *can* do (SPEC-tradar.md §12.1): the SDK's own
        # `chat.completions.stream(...)` helper yields the raw chunks, and
        # a chunk carries both the content delta and -- on the first chunk
        # of each tool call -- that call's name. See `run_turn`.
        streaming=True,
    )

    def __init__(
        self, api_key: str, base_url: str, session_id: Optional[str] = None
    ) -> None:
        # Plain constructor args, not `config.settings` read here directly --
        # matches `MessagesClient`'s constructor exactly, for the same
        # reason: the factory (`services/agent_runtime.py::build_llm_client`)
        # wires this to `settings.llm_api_key`/`settings.llm_base_url`, and
        # this class stays trivial to construct with a dummy key in tests.
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=gateway_headers(session_id),
        )

    def run_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: Optional[int],
        on_text: Optional[StreamTextHook] = None,
        on_tool_call: Optional[StreamToolCallHook] = None,
    ) -> LLMTurn:
        """One turn, optionally reporting increments as they arrive.

        With either hook given this goes through the installed SDK's
        `chat.completions.stream(...)` helper, dispatching each event
        through `dispatch_stream_event` and then taking
        `get_final_completion()` -- the same `ChatCompletion` shape
        `normalize_response` already handles, so nothing downstream learns
        that a stream happened.

        With neither hook given it stays on plain `.create(...)`: the
        unstreamed path is unchanged, and this protocol's streaming mode
        reports usage only when asked to, which is a difference not worth
        taking on for a caller that isn't listening anyway.
        """
        translated_tools = self.translate_tools(tools)
        translated_messages = self.translate_messages(system, messages)
        # Built as a plain `dict[str, Any]` and passed via `**kwargs`, not as
        # inline keyword arguments -- mirrors `MessagesClient.run_turn`'s
        # `**kwargs` call exactly, and for the same practical reason: the
        # installed SDK's `.create(...)` overloads type `messages`/`tools`
        # against a closed union of specific `TypedDict` shapes
        # (`ChatCompletionSystemMessageParam` and friends), which a plain
        # `list[dict[str, Any]]` built at runtime from Anthropic-native input
        # cannot satisfy statically even though it is shaped correctly at
        # runtime. `**kwargs: dict[str, Any]` unpacks as `Any` per key, which
        # is what keeps `mypy .` clean here without a `cast` per argument.
        kwargs: dict[str, Any] = {
            # The bare id: the gateway prefix is config, not wire.
            "model": api_model_id(model),
            "messages": translated_messages,
            "tools": translated_tools,
        }
        if max_tokens is not None:
            # `max_completion_tokens`, not the deprecated `max_tokens`:
            # confirmed against the installed `openai>=2.0` SDK's
            # `CompletionCreateParamsBase` (`completion_create_params.py`)
            # -- `max_tokens`'s own docstring there states it "is now
            # deprecated in favor of max_completion_tokens, and is not
            # compatible with o-series [reasoning] models". OpenCode Zen's
            # Chat-protocol model families (SPEC §2: GPT, Grok, Qwen,
            # DeepSeek, Kimi, GLM, MiniMax) include reasoning models, so the
            # deprecated parameter is the wrong default to reach for here
            # even though both still exist on the installed SDK.
            kwargs["max_completion_tokens"] = max_tokens
        try:
            if on_text is not None or on_tool_call is not None:
                response = self._stream_completion(kwargs, on_text, on_tool_call)
            else:
                response = self._client.chat.completions.create(**kwargs)
        except openai.RateLimitError as exc:
            # Checked before APIConnectionError, mirroring
            # `MessagesClient.run_turn`: RateLimitError is an
            # APIStatusError (a real HTTP response came back, just a 429),
            # a wholly separate branch of the SDK's exception hierarchy from
            # APIConnectionError -- ordering it first keeps SPEC §6.7's
            # "429" row visibly distinct from the generic connectivity row.
            raise LLMRateLimitError(
                f"Rate limited by the Chat Completions API (429): {exc.message}",
                retry_after_seconds=_retry_after_seconds(exc),
            ) from exc
        except openai.APIConnectionError as exc:
            # SPEC §6.7: "Gateway nere, timeout, 5xx" -- after the SDK's own
            # retry policy (httpx-level) is exhausted, this is what surfaces.
            raise LLMConnectionError(
                f"Connection error talking to the Chat Completions API: {exc.message}"
            ) from exc
        return self.normalize_response(response)

    def _stream_completion(
        self,
        kwargs: dict[str, Any],
        on_text: Optional[StreamTextHook],
        on_tool_call: Optional[StreamToolCallHook],
    ) -> ChatCompletion:
        """Run the request through the SDK's streaming helper and return the
        assembled `ChatCompletion`.

        `stream_options={"include_usage": True}` is what keeps
        `response.usage` populated: on this protocol a streamed completion
        reports no usage at all unless it is asked to, and
        `normalize_response` treating a missing `usage` as zero would make
        every streamed thread turn free in `compute_cost_ore` -- a daily cap
        that silently stops counting is worse than no cap.

        Tool-call names are announced once each, as the first chunk of each
        call arrives: `_ChatStreamDispatcher` keeps the small amount of
        per-turn state that requires, since a name repeats across the
        argument chunks that follow it.
        """
        dispatcher = _ChatStreamDispatcher(on_text=on_text, on_tool_call=on_tool_call)
        stream_kwargs = dict(kwargs)
        stream_kwargs["stream_options"] = {"include_usage": True}
        with self._client.chat.completions.stream(**stream_kwargs) as stream:
            for event in stream:
                dispatcher.dispatch(event)
            try:
                return stream.get_final_completion()
            except openai.LengthFinishReasonError as exc:
                # The helper refuses to hand back a completion cut off by
                # `finish_reason == "length"`, but the exception carries it.
                # Returned as is, it normalizes to `stop="max_tokens"` -- a
                # truncated turn the session abstains on -- exactly as the
                # unstreamed `.create(...)` path already does, and its usage
                # still reaches the daily cap.
                return exc.completion

    # -----------------------------------------------------------------
    # Translation: Anthropic tool-definition shape -> OpenAI function-tool
    # -----------------------------------------------------------------

    @staticmethod
    def translate_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate `AGENT_TOOL_DEFINITIONS`-shaped tool dicts
        (`{"name", "description", "input_schema"}`, `services/agent_tools.py`)
        into OpenAI's Chat Completions function-tool shape
        (`{"type": "function", "function": {"name", "description",
        "parameters"}}`, confirmed against the installed SDK's
        `openai.types.shared_params.function_definition.FunctionDefinition`).

        `input_schema` becomes `parameters` unchanged -- same JSON Schema
        dict, no other transformation. Pure and network-free.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

    # -----------------------------------------------------------------
    # Translation: Anthropic messages/content-blocks -> OpenAI messages
    # -----------------------------------------------------------------

    @staticmethod
    def translate_messages(
        system: str, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Translate a plain `system` string plus an Anthropic-native
        `messages` list (as built by `services/agent_session.py`) into
        OpenAI's Chat Completions message list.

        `system` becomes `{"role": "system", "content": system}`, prepended.
        No cache-breakpoint content block wrapping it -- unlike
        `MessagesClient.build_request_kwargs`, `capabilities.
        cache_breakpoint` is `False` here, so there is nothing to mark and a
        plain string is the whole story.

        Each Anthropic message is translated per its `content` shape:

        - A list of only `text` blocks -> `{"role": ..., "content":
          "<concatenated text>"}` (concatenated with no separator, matching
          `MessagesClient.normalize_message`'s `"".join(text_parts)` -- in
          practice there is usually exactly one text block, per
          `services.agent_session.build_user_turn`/`_assistant_message`).
        - An `image` block -> an OpenAI `image_url` content-list entry.
        - A `document` block -> raises `UnsupportedContentBlockError` (see
          that class's docstring; this should be unreachable in practice).
        - An assistant `tool_use` block -> accumulated into that message's
          `tool_calls` array (OpenAI puts every tool call for a turn on the
          assistant message itself, not as separate content blocks).
        - A `tool_result` block -> its own `{"role": "tool", "tool_call_id":
          ..., "content": <string>}` message (Chat Completions has no
          concept of a tool result embedded inside a user turn the way
          Anthropic's `{"role": "user", "content": [tool_result, ...]}`
          does -- each tool_result block becomes its own top-level message).
        """
        translated: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for message in messages:
            translated.extend(_translate_one_message(message))
        return translated

    # -----------------------------------------------------------------
    # Normalization: OpenAI ChatCompletion -> LLMTurn
    # -----------------------------------------------------------------

    @staticmethod
    def normalize_response(response: ChatCompletion) -> LLMTurn:
        """Normalize a real `openai.types.chat.ChatCompletion` into an
        `LLMTurn`. Pure and network-free -- exists so it can be tested
        against hand-built response objects without a live call.
        """
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        for raw_call in message.tool_calls or []:
            if not isinstance(raw_call, ChatCompletionMessageFunctionToolCall):
                # The installed SDK's `tool_calls` type is a union of
                # function-tool and "custom" (freeform-input) tool calls
                # (`ChatCompletionMessageCustomToolCall`). `translate_tools`
                # above only ever emits `{"type": "function", ...}`
                # declarations (SPEC's tool surface, `AGENT_TOOL_DEFINITIONS`,
                # has none of OpenAI's newer custom-tool shape), so a model
                # returning a custom-tool call back would be responding to a
                # tool it was never offered -- an adapter-level failure, not
                # a shape this adapter can translate.
                raise UnsupportedToolCallTypeError(raw_call.type)
            try:
                arguments = json.loads(raw_call.function.arguments)
            except json.JSONDecodeError as exc:
                raise MalformedToolArgumentsError(
                    tool_call_id=raw_call.id,
                    name=raw_call.function.name,
                    raw_arguments=raw_call.function.arguments,
                ) from exc
            tool_calls.append(
                ToolCall(
                    id=raw_call.id, name=raw_call.function.name, arguments=arguments
                )
            )

        if choice.finish_reason not in _FINISH_REASON_MAP:
            raise UnrecognizedFinishReasonError(choice.finish_reason)
        stop = _FINISH_REASON_MAP[choice.finish_reason]

        usage = response.usage
        normalized_usage = Usage(
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            # Always exactly 0 on this protocol -- capabilities.
            # cache_breakpoint is False (SPEC §2/§6.6: no cache accounting
            # we can verify on the Chat path). Deliberately NOT read from
            # `usage.prompt_tokens_details.cached_tokens`, which does exist
            # on the installed SDK's `CompletionUsage` type: that field is
            # not confirmed to mean the same thing as Anthropic's verified,
            # explicit cache-breakpoint mechanism (whether it reflects a
            # provider-side implicit prefix cache at all is
            # provider-dependent and unverifiable through this gateway), so
            # wiring it up here would be exactly the "guess" SPEC §6.6 rules
            # out. If this is ever revisited, it needs its own SPEC decision
            # first, not a quiet field mapping.
            cache_read_input_tokens=0,
        )

        return LLMTurn(
            text=message.content or "",
            tool_calls=tool_calls,
            stop=stop,
            usage=normalized_usage,
        )


# ---------------------------------------------------------------------------
# Message translation helpers (module-level, pure)
# ---------------------------------------------------------------------------


class _ChatStreamDispatcher:
    """Routes this protocol's stream events to the hooks (task T5).

    Reads the *raw chunk* events (`type == "chunk"`) rather than the SDK's
    synthesized higher-level ones, because a chunk carries both things the
    thread needs in one place: `delta.content` (the text increment) and
    `delta.tool_calls[].function.name`, which the wire only sends on the
    first chunk of each tool call. The synthesized
    `tool_calls.function.arguments.delta` event repeats the name on every
    argument fragment, which would make `SkriverIndikator` flicker through
    the same name a dozen times per call.

    The `_announced` set is still kept: a provider that repeated the name
    on a later chunk would otherwise announce the same call twice, and one
    tool call is one activity, however the gateway chooses to frame it.
    """

    def __init__(
        self,
        on_text: Optional[StreamTextHook] = None,
        on_tool_call: Optional[StreamToolCallHook] = None,
    ) -> None:
        self._on_text = on_text
        self._on_tool_call = on_tool_call
        self._announced: set[int] = set()

    def dispatch(self, event: Any) -> None:
        if getattr(event, "type", None) != "chunk":
            return
        choices = getattr(event.chunk, "choices", None) or []
        if not choices:
            # The final usage-only chunk that `include_usage` adds has no
            # choices at all.
            return
        delta = choices[0].delta
        if delta is None:
            return
        content = getattr(delta, "content", None)
        if content and self._on_text is not None:
            self._on_text(content)
        if self._on_tool_call is None:
            return
        for tool_call in getattr(delta, "tool_calls", None) or []:
            function = getattr(tool_call, "function", None)
            name = getattr(function, "name", None)
            if not name or tool_call.index in self._announced:
                continue
            self._announced.add(tool_call.index)
            self._on_tool_call(name)


def _translate_one_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    role = message["role"]
    content = message["content"]

    if isinstance(content, str):
        # Already-flat content (not produced by services/agent_session.py
        # today, which always builds a content-block list, but a valid
        # Anthropic message shape in general) -- pass through unchanged.
        return [{"role": role, "content": content}]

    if role == "assistant":
        return [_translate_assistant_message(content)]

    # role == "user": a list of blocks that may mix plain text with one or
    # more tool_result blocks (services.agent_session.run_session appends
    # exactly one such message per tool-call turn: {"role": "user",
    # "content": [tool_result, tool_result, ...]}), or be the initial
    # metadata+content_block user turn from build_user_turn (text + at most
    # one image/document block, never a tool_result).
    out: list[dict[str, Any]] = []
    text_parts: list[str] = []
    image_parts: list[dict[str, Any]] = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(block["text"])
        elif block_type == "image":
            image_parts.append(_translate_image_block(block))
        elif block_type == "document":
            raise UnsupportedContentBlockError(
                "document", context="in a user message content block"
            )
        elif block_type == "tool_result":
            out.append(_translate_tool_result_block(block))
        else:
            raise UnsupportedContentBlockError(
                block_type or "<unknown>", context="in a user message content block"
            )

    if text_parts or image_parts:
        if image_parts:
            user_content: Any = [
                {"type": "text", "text": "".join(text_parts)},
                *image_parts,
            ]
        else:
            user_content = "".join(text_parts)
        # Preserve message order: the plain text/image user content goes
        # before any tool_result messages extracted from the same Anthropic
        # message, matching the order blocks appeared in `content`.
        out.insert(0, {"role": "user", "content": user_content})

    return out


def _translate_assistant_message(content: list[dict[str, Any]]) -> dict[str, Any]:
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(block["text"])
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        # OpenAI wants the arguments as a JSON *string*,
                        # unlike Anthropic's tool_use.input, which is
                        # already a dict (SPEC's own wording on this
                        # asymmetry).
                        "arguments": json.dumps(block["input"], ensure_ascii=False),
                    },
                }
            )
        elif block_type == "document":
            raise UnsupportedContentBlockError(
                "document", context="in an assistant message content block"
            )
        else:
            raise UnsupportedContentBlockError(
                block_type or "<unknown>",
                context="in an assistant message content block",
            )

    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(text_parts) or None,
    }
    if tool_calls:
        assistant_message["tool_calls"] = tool_calls
    return assistant_message


def _translate_image_block(block: dict[str, Any]) -> dict[str, Any]:
    source = block["source"]
    media_type = source["media_type"]
    data = source["data"]
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{data}"},
    }


def _translate_tool_result_block(block: dict[str, Any]) -> dict[str, Any]:
    """Translate one Anthropic `tool_result` block into an OpenAI `role:
    "tool"` message.

    `services.agent_session._tool_result_content_blocks` produces exactly
    one of two shapes for `content`: a list with a single plain `text`
    block (every tool except `hamta_underlagsfil`, and `hamta_underlagsfil`
    itself whenever the underlying source resolved to a `text` content
    block) -- the common, expected case, handled plainly below -- or a
    single `image`/`document` block with no text alongside it
    (`hamta_underlagsfil`'s image/document passthrough). OpenAI's
    tool-result content is plain text/string, not a list of typed content
    blocks, so the latter has no representation here: any plain text found
    is extracted and used, and `UnsupportedContentBlockError` is raised only
    when there is truly nothing textual to fall back to.
    """
    tool_use_id = block["tool_use_id"]
    content = block["content"]

    text_parts: list[str] = []
    unsupported_type: Optional[str] = None
    for item in content:
        item_type = item.get("type")
        if item_type == "text":
            text_parts.append(item["text"])
        else:
            unsupported_type = item_type or "<unknown>"

    if not text_parts:
        raise UnsupportedContentBlockError(
            unsupported_type or "<empty>",
            context="a tool_result with no plain-text content to fall back to",
        )

    return {
        "role": "tool",
        "tool_call_id": tool_use_id,
        "content": "".join(text_parts),
    }


def _retry_after_seconds(exc: "openai.RateLimitError") -> Optional[float]:
    """Read a `retry-after` value off a real `openai.RateLimitError`.

    Mirrors `services.llm.messages._retry_after_seconds` exactly: the SDK's
    exception carries the raw HTTP `response`, not a parsed convenience
    field (confirmed against the installed SDK -- `openai.APIStatusError`,
    which `RateLimitError` subclasses, stores it as `.response`, an
    `httpx2.Response` whose `.headers` mapping is case-insensitive per
    `httpx2`'s own contract).

    An absent or unparseable header returns `None` -- "unknown", never a
    guessed `0` that would look like "retry immediately".
    """
    header = exc.response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except (TypeError, ValueError):
        return None
