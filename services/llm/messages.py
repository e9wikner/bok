"""Anthropic Messages protocol adapter (docs/redesign/SPEC-agentruntime.md §2, §4, §6.6).

This is the only module in the codebase -- besides its own tests and
fixtures -- allowed to `import anthropic` (SPEC §4, §10). Everything else
sees `MessagesClient` only through the structural `services.llm.LLMClient`
Protocol: `run_turn(system, messages, tools, model, max_tokens) -> LLMTurn`.

Per the architectural decision in SPEC §4/§10 (see `services/llm/__init__.py`),
`messages`/`tools` are already Anthropic's own Messages API wire shapes --
that is the protocol-agnostic lingua franca used everywhere above this
package -- so this adapter passes them through essentially unchanged. The
`services/llm/chat.py` adapter (A12) is the one that pays the translation
cost, in the other direction, down to OpenAI's shapes.

Two responsibilities are split into pure, independently testable functions
so the adapter tests never need a network call (SPEC §9):

- `build_request_kwargs` -- builds the `messages.stream(...)` kwargs dict.
  Tested directly against the built dict: cache_control placement, the
  presence of `thinking`/`output_config`, and the *absence* of
  `budget_tokens` anywhere in it.
- `normalize_message` -- turns an already-constructed `anthropic.types.Message`
  into an `LLMTurn`. Tested against hand-written JSON fixtures under
  `tests/fixtures/llm_messages/*.json`, loaded via
  `anthropic.types.Message.model_validate(...)` so the fixtures are checked
  against the real SDK's schema, not a guess at its shape.

`run_turn` itself is just the wiring between the two, plus the actual
`.stream()` / `get_final_message()` call -- the one thing that touches the
network, and the one thing the tests stub out.
"""

from typing import Any, Optional

import anthropic
from anthropic.types import Message

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
)

# Normalizes anthropic.types.StopReason -> services.llm.StopReason.
#
# Anthropic's Messages API can return more stop_reason values than this
# table covers ("pause_turn", "model_context_window_exceeded" as of this
# SDK version) -- those are deliberately left out. `normalize_message` raises
# on anything not in this table rather than guessing a mapping, per SPEC
# §6.7's "ett osäkert utfall är ett avstående, aldrig en postning": a stop
# reason nobody has looked at yet must never silently pass as "end" or
# "tool_calls".
_STOP_REASON_MAP: dict[str, StopReason] = {
    "tool_use": "tool_calls",
    "end_turn": "end",
    "stop_sequence": "end",
    "max_tokens": "max_tokens",
    # Confirmed against the installed `anthropic` SDK (anthropic.types.StopReason,
    # anthropic.types.RefusalStopDetails): the literal really is "refusal",
    # exactly as SPEC §2/§6.7 assumes -- not a guess.
    "refusal": "refusal",
}


class UnrecognizedStopReasonError(Exception):
    """Raised when the Messages API returns a `stop_reason` this adapter has
    no mapping for.

    Deliberately fatal rather than swallowed: a new or unhandled stop reason
    (e.g. "pause_turn", "model_context_window_exceeded") must surface as a
    loud failure, not quietly become `"end"` or `"tool_calls"` and risk a
    posting on an outcome nobody has categorized (SPEC §6.7).
    """

    def __init__(self, stop_reason: str | None) -> None:
        super().__init__(f"Unrecognized Anthropic stop_reason: {stop_reason!r}")
        self.stop_reason = stop_reason


class MessagesClient:
    """`LLMClient` adapter for Anthropic's Messages API (SPEC §2).

    Structurally satisfies `services.llm.LLMClient` -- no inheritance, per
    A4's Protocol design (see that module's docstring on why that matters
    for testability).
    """

    #: SPEC §2's capability table for the Messages protocol: explicit cache
    #: breakpoint, PDF `document` blocks as the §6.3 fallback, and its own
    #: stop reason for a refusal.
    capabilities = LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        # The stream was always there -- `.stream()` below has been the call
        # since A5; what was missing was anything listening. See `run_turn`.
        streaming=True,
    )

    def __init__(self, api_key: str, base_url: str) -> None:
        # Plain constructor args, not `config.settings` read here directly --
        # the factory that wires this to `settings.llm_api_key` /
        # `settings.llm_base_url` lives elsewhere (A8/A10), so this class
        # stays trivial to construct with a dummy key in tests.
        self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    def run_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        on_text: Optional[StreamTextHook] = None,
        on_tool_call: Optional[StreamToolCallHook] = None,
    ) -> LLMTurn:
        """One turn, optionally reporting increments as they arrive.

        This adapter has always streamed -- `.stream()` is the call A5 wrote
        -- and always thrown every increment away, because
        `get_final_message()` on its own silently drains the iterator. The
        hooks (SPEC-tradar.md §12.1, task T5) pick up what was already
        passing through: with either one given, the events are iterated
        first and dispatched through `dispatch_stream_event`, and
        `get_final_message()` then returns the same assembled message it
        would have returned anyway.

        With neither hook given, nothing is iterated and the call is byte
        for byte what it was before -- there is no reason to walk a stream
        no one is listening to, and it keeps the unstreamed path (and its
        tests) untouched.
        """
        kwargs = self.build_request_kwargs(system, messages, tools, model, max_tokens)
        try:
            with self._client.messages.stream(**kwargs) as stream:
                if on_text is not None or on_tool_call is not None:
                    for event in stream:
                        dispatch_stream_event(
                            event, on_text=on_text, on_tool_call=on_tool_call
                        )
                final_message = stream.get_final_message()
        except anthropic.RateLimitError as exc:
            # Checked before APIConnectionError: RateLimitError is an
            # APIStatusError (a real HTTP response came back, just a 429),
            # a wholly separate branch of the SDK's exception hierarchy from
            # APIConnectionError -- but ordering it first here keeps the
            # more specific SPEC §6.7 row ("429") visibly distinct from the
            # generic connectivity row it's checked alongside.
            raise LLMRateLimitError(
                f"Rate limited by the Messages API (429): {exc.message}",
                retry_after_seconds=_retry_after_seconds(exc),
            ) from exc
        except anthropic.APIConnectionError as exc:
            # SPEC §6.7: "Gateway nere, timeout, 5xx" -- after the SDK's own
            # retry policy (httpx-level) is exhausted, this is what surfaces.
            raise LLMConnectionError(
                f"Connection error talking to the Messages API: {exc.message}"
            ) from exc
        return self.normalize_message(final_message)

    @staticmethod
    def build_request_kwargs(
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Build the kwargs for `anthropic.Anthropic(...).messages.stream(...)`.

        Pure and network-free -- exists so the request shape (cache
        breakpoint placement, `thinking`, `output_config`, and the absence
        of `budget_tokens`) can be asserted on directly in tests.
        """
        # The plain-string `system` argument becomes the cache-breakpoint
        # form: a one-block system content list with `cache_control` on its
        # last (here, only) block. This is what makes the systemprompt
        # (instructions + kontoplan + corrections, built by A8) cacheable
        # per SPEC §6.6 -- the breakpoint has to be a content block, a bare
        # string can't carry one.
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        return {
            # The bare id: the gateway prefix is config, not wire.
            "model": api_model_id(model),
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
            "tools": tools,
            # Adaptive thinking + high effort, per SPEC §2/§6.3's table
            # ("Tänkande / effort"). Deliberately no `budget_tokens` key
            # anywhere in this dict: SPEC-agentruntime.md §2 states plainly
            # that it "ger 400 på Opus 5" (a 400 error) -- it is not a style
            # choice one could "helpfully" add back for finer cost control,
            # it breaks the call outright. If you're reading this because
            # you were about to add one back: don't.
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
        }

    @staticmethod
    def normalize_message(message: Message) -> LLMTurn:
        """Normalize a real `anthropic.types.Message` into an `LLMTurn`.

        Pure and network-free -- exists so it can be tested against
        hand-written fixtures (`tests/fixtures/llm_messages/*.json`) loaded
        via `Message.model_validate(...)`, instead of only via a live call.
        """
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in message.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                )
            # `thinking` and `redacted_thinking` blocks (adaptive thinking,
            # SPEC §2) are deliberately not concatenated into `text` -- they
            # are the model's internal reasoning, not its answer. Any other
            # block type (server tool use/results, container uploads, ...)
            # is likewise ignored here; none of those are part of the
            # session's contract with this adapter.

        if message.stop_reason not in _STOP_REASON_MAP:
            raise UnrecognizedStopReasonError(message.stop_reason)
        stop = _STOP_REASON_MAP[message.stop_reason]

        usage = message.usage
        normalized_usage = Usage(
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            # `cache_read_input_tokens` is `Optional[int]` on the real SDK
            # type (None, not 0, when the request had no cache hit at all --
            # e.g. the very first call in a pass, before anything is cached).
            # Treated as 0 here, never as an error -- but this is exactly
            # the field SPEC §6.6/test case 15 checks is > 0 from the second
            # document onward, so a silent cache invalidator would show up
            # as this staying 0 past the first call.
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
        )

        return LLMTurn(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop=stop,
            usage=normalized_usage,
        )


def dispatch_stream_event(
    event: Any,
    *,
    on_text: Optional[StreamTextHook] = None,
    on_tool_call: Optional[StreamToolCallHook] = None,
) -> None:
    """Route one `MessageStream` event to the hooks that want it.

    Pure in the sense that matters here -- it touches no network and holds
    no state -- so it can be tested against recorded raw events built with
    `model_validate(...)`, the same way `normalize_message` is tested
    against recorded messages (SPEC-tradar.md §9: "adaptertester mot
    inspelade råsvar").

    Two of the SDK's event types carry what the thread needs, confirmed
    against the installed `anthropic` SDK:

    - `TextEvent` (`type == "text"`): `.text` is the *delta*, `.snapshot`
      the accumulated text so far. The delta is what goes out, because
      `message.delta` on the wire is an increment, not a growing prefix.
    - `RawContentBlockStartEvent` (`type == "content_block_start"`) whose
      `content_block` is a `tool_use` block: fires once per tool call, as
      the model starts asking for it, which is the earliest point a
      `SkriverIndikator` can name what is happening.

    Every other event -- `thinking`, `signature`, `input_json`, the message
    start/delta/stop frames -- is ignored. `thinking` deliberately so: it is
    the model's internal reasoning, not its answer, exactly as
    `normalize_message` refuses to concatenate it into `text`.
    """
    event_type = getattr(event, "type", None)
    if event_type == "text":
        if on_text is not None:
            on_text(event.text)
        return
    if event_type == "content_block_start" and on_tool_call is not None:
        block = event.content_block
        if getattr(block, "type", None) == "tool_use":
            on_tool_call(block.name)


def _retry_after_seconds(exc: "anthropic.RateLimitError") -> Optional[float]:
    """Read a `retry-after` value off a real `anthropic.RateLimitError`.

    The SDK's exception carries the raw HTTP `response`, not a parsed
    convenience field, so this reads the header directly. Confirmed against
    the installed SDK: `RateLimitError.response` is the underlying
    `httpx2.Response`, and its `headers` mapping is case-insensitive per
    `httpx2`'s own contract, so `"retry-after"` matches the wire header
    regardless of casing.

    Anthropic sends this header as a plain integer/float number of seconds
    (never an HTTP-date), but this parses defensively anyway: an absent or
    unparseable header returns `None` -- "unknown", never a guessed `0` that
    would look like "retry immediately".
    """
    header = exc.response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except (TypeError, ValueError):
        return None
