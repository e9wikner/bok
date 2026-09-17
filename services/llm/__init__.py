"""LLM protocol boundary (docs/redesign/SPEC-agentruntime.md §4).

`services/llm/` is the only package in this codebase allowed to import
`anthropic` or `openai` (SPEC §4). Everything above it -- the session, the
tools, the worker, the status endpoint -- only ever sees the small,
provider-agnostic surface defined here: `LLMClient`, `LLMTurn`,
`LLMCapabilities`, and the model registry. That boundary is what keeps a
third provider a new file instead of an `if provider == ...` spreading into
bookkeeping logic.

This module (`services/llm/__init__.py`) itself imports neither `anthropic`
nor `openai` -- it is pure typing plus a data table. The two adapters live in
sibling modules: `services/llm/messages.py` (A5) and `services/llm/chat.py`
(A12).

No network calls happen here, and none of this module's tests may perform
one (SPEC §9).
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol

# ---------------------------------------------------------------------------
# Value types (SPEC §4)
# ---------------------------------------------------------------------------

#: Normalized stop reason. `refusal` only exists on the Messages protocol
#: (SPEC §2); the Chat Completions adapter never produces it -- a refusal
#: there just comes back as ordinary text with `stop == "end"`.
StopReason = Literal["tool_calls", "end", "refusal", "max_tokens"]

#: Which wire protocol a model speaks on OpenCode Zen (SPEC §2).
ProtocolName = Literal["messages", "chat"]


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation requested by the model in a turn."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    """Token accounting for a single turn, as reported by the provider.

    `cache_read_input_tokens` is always present on the type so callers don't
    need to branch on protocol, but it is only ever non-zero on the Messages
    protocol (SPEC §2, §6.6) -- the Chat Completions adapter reports 0 because
    it has no explicit, verifiable cache breakpoint.
    """

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int


@dataclass(frozen=True)
class LLMTurn:
    """One normalized model turn, independent of which protocol produced it."""

    text: str
    tool_calls: list[ToolCall]
    stop: StopReason
    usage: Usage


@dataclass(frozen=True)
class LLMCapabilities:
    """What an adapter can and cannot do (SPEC §2, §4).

    The session (A8) and cost/cache logic (A9) consult this instead of
    branching on protocol name, so a missing capability becomes an explicit
    abstention rather than a silent, wrong assumption.
    """

    #: Explicit cache breakpoint whose savings show up in
    #: `Usage.cache_read_input_tokens` (Messages only; SPEC §6.6).
    cache_breakpoint: bool
    #: Can send a PDF as a `document` block (Messages only; used only as a
    #: fallback per SPEC §6.3 -- extracted text is preferred everywhere).
    pdf_document_blocks: bool
    #: Has its own `stop`/`stop_reason` value for a refusal (Messages only;
    #: SPEC §6.7). Without it, a refusal is indistinguishable from ordinary
    #: text and must be treated as an uncategorized abstention.
    refusal_stop_reason: bool


class LLMClient(Protocol):
    """Structural protocol every adapter satisfies independently (SPEC §4).

    Deliberately narrow, and deliberately *not* a base class: `messages.py`
    and `chat.py` each implement this shape on their own terms -- neither
    inherits from anything here. That is what makes the fake client used in
    every other test in this module trivial to write.
    """

    capabilities: LLMCapabilities

    def run_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
    ) -> LLMTurn: ...


# ---------------------------------------------------------------------------
# Protocol-agnostic errors (SPEC §6.7, task A10)
# ---------------------------------------------------------------------------
#
# Real API connection failures and rate limits come back from each adapter's
# own SDK as SDK-specific exception types (`anthropic.APIConnectionError`,
# `anthropic.RateLimitError`, ...). Those types must never leak past
# `services/llm/` -- `services/agent_runtime.py` is not allowed to import
# `anthropic`/`openai` (SPEC §4/§10), so every adapter translates its own
# SDK's connectivity/rate-limit errors into these two, protocol-agnostic
# types before they leave this package. See `services/llm/messages.py`'s
# `run_turn` for the Messages-protocol translation.


class LLMConnectionError(Exception):
    """A transient network/connectivity failure talking to the LLM gateway.

    SPEC §6.7's "Gateway nere, timeout, 5xx" row, after the SDK's own retry
    policy has been exhausted. A10's worker catches this, marks the
    `agent_runs` row `status='failed'`, and stops the pass -- it never
    retries within the same pass ("håller det i sig ... passet 'failed'").
    """


class LLMRateLimitError(Exception):
    """A 429 from the LLM gateway.

    SPEC §6.7's "429" row: "Respektera retry-after, avsluta passet, ta om
    vid nästa start" -- no in-pass retry/sleep. `retry_after_seconds` is the
    value read off the real SDK exception's `retry-after` header/attribute,
    when the gateway sent one; `None` when it did not, which a caller must
    treat as "unknown", not "zero".
    """

    def __init__(
        self,
        message: str = "Rate limited by the LLM gateway (429).",
        *,
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


# ---------------------------------------------------------------------------
# Model registry: model id -> protocol + price (SPEC §2, §5)
# ---------------------------------------------------------------------------
#
# Table-driven on purpose -- adding a model is one dict entry, in either
# table below, never a new branch of logic.


class UnknownModelError(Exception):
    """Raised when a model has no price row.

    SPEC §2: "En modell utan prisrad är ett fel, inte ett standardvärde" --
    an unpriced model is a bug, not something that falls back to a default
    price. A9's budget code and A10's worker startup call `get_model_info`
    and let this propagate: the pass must refuse to start rather than run
    with a cost the daily cap cannot compute (test case 19).

    Never includes `llm_api_key` or any other secret -- only the model id.
    """

    def __init__(self, model: str) -> None:
        super().__init__(
            f"No price row for model {model!r}. "
            "Add one to services/llm/_MODEL_PRICES before this model may run."
        )
        self.model = model


@dataclass(frozen=True)
class ModelPrice:
    """Price for one model, in öre (1/100 SEK) per 1,000,000 tokens.

    Unit convention: this codebase keeps all amounts as integer öre (see
    `domain/models.py`, ledger/VAT handling). A per-token öre price would
    routinely need to be a fraction of an öre, which breaks that convention;
    per-million keeps every number here an integer while matching the
    industry-standard "price per million tokens" quoting convention. A9's
    `cost_ore` math is expected to do:

        cost_ore = tokens * price.input_ore_per_million_tokens // 1_000_000

    (and the equivalent for output / cache-read tokens), then sum and round
    at the end, not per line item.
    """

    input_ore_per_million_tokens: int
    output_ore_per_million_tokens: int
    cache_read_ore_per_million_tokens: int


@dataclass(frozen=True)
class ModelInfo:
    """What `get_model_info` returns: a model's protocol and its price."""

    model: str
    protocol: ProtocolName
    price: ModelPrice


# Claude family (Opus, Sonnet, Haiku, Fable) speaks the Anthropic Messages
# protocol; every other model OpenCode Zen lists (GPT, Grok, Qwen, DeepSeek,
# Kimi, GLM, MiniMax) speaks OpenAI Chat Completions (SPEC §2). Matched by
# substring against the model id, case-insensitively, so
# "opencode/claude-opus-5" and a bare "claude-3-7-sonnet" both resolve the
# same way without a new branch per model.
_MESSAGES_PROTOCOL_SUBSTRINGS: tuple[str, ...] = (
    "claude",
    "opus",
    "sonnet",
    "haiku",
    "fable",
)


def _infer_protocol(model: str) -> ProtocolName:
    lowered = model.lower()
    if any(substring in lowered for substring in _MESSAGES_PROTOCOL_SUBSTRINGS):
        return "messages"
    return "chat"


# Illustrative placeholder prices -- confirm against OpenCode Zen's actual
# price sheet (https://opencode.ai/zen) before any real spend. These are
# only real enough to give A9's cap/cost math and A12's chat-protocol tests
# non-zero, plausible numbers to multiply.
#
# `opencode/claude-sonnet-5`'s USD reference ($2 in / $10 out per million
# tokens) is the one figure SPEC-agentruntime.md §12.5 actually states;
# converted here at an illustrative ~10 SEK/USD rate purely to seed a
# plausible öre value -- not a maintained FX rate.
_MODEL_PRICES: dict[str, ModelPrice] = {
    "opencode/claude-opus-5": ModelPrice(
        input_ore_per_million_tokens=15_000,
        output_ore_per_million_tokens=75_000,
        # Anthropic-style cache reads are billed at roughly 10% of the base
        # input price.
        cache_read_ore_per_million_tokens=1_500,
    ),
    "opencode/claude-sonnet-5": ModelPrice(
        input_ore_per_million_tokens=2_000,
        output_ore_per_million_tokens=10_000,
        cache_read_ore_per_million_tokens=200,
    ),
    "opencode/gpt-5.5": ModelPrice(
        input_ore_per_million_tokens=1_500,
        output_ore_per_million_tokens=6_000,
        # Chat Completions has no verifiable cache-read discount
        # (capabilities.cache_breakpoint is False for this protocol), so
        # this is priced the same as a plain input token.
        cache_read_ore_per_million_tokens=1_500,
    ),
    "opencode/grok-4": ModelPrice(
        input_ore_per_million_tokens=2_500,
        output_ore_per_million_tokens=10_000,
        cache_read_ore_per_million_tokens=2_500,
    ),
}


def get_model_info(model: str) -> ModelInfo:
    """Resolve a model id to its protocol and price row.

    Raises `UnknownModelError` if the model has no price row -- that is a
    hard error by design (SPEC §2), not a fallback to a default price.
    """
    price = _MODEL_PRICES.get(model)
    if price is None:
        raise UnknownModelError(model)
    return ModelInfo(model=model, protocol=_infer_protocol(model), price=price)
