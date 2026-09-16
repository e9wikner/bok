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

from typing import Any

import anthropic
from anthropic.types import Message

from services.llm import LLMCapabilities, LLMTurn, StopReason, ToolCall, Usage

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
    ) -> LLMTurn:
        kwargs = self.build_request_kwargs(system, messages, tools, model, max_tokens)
        with self._client.messages.stream(**kwargs) as stream:
            final_message = stream.get_final_message()
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
            "model": model,
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
