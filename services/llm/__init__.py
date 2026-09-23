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
from typing import Any, Callable, Literal, Optional, Protocol, cast

# ---------------------------------------------------------------------------
# Value types (SPEC §4)
# ---------------------------------------------------------------------------

#: Normalized stop reason. `refusal` only exists on the Messages protocol
#: (SPEC §2); the Chat Completions adapter never produces it -- a refusal
#: there just comes back as ordinary text with `stop == "end"`.
StopReason = Literal["tool_calls", "end", "refusal", "max_tokens"]

#: Which wire protocol a model speaks on its gateway (SPEC §2).
ProtocolName = Literal["messages", "chat"]

#: Which OpenCode gateway serves a model: Zen (pay per token) or Go (the
#: subscription). Read off the model id's prefix -- `opencode/...` or
#: `opencode-go/...`, the same prefixes OpenCode's own config uses -- and
#: mapped to a base URL and key by `config.Settings.gateway_for`.
Provider = Literal["opencode", "opencode-go"]


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


#: Called with each text increment as the model produces it
#: (SPEC-tradar.md §12.1). What becomes a `message.delta` on the stream.
StreamTextHook = Callable[[str], None]

#: Called with a tool's name as the model starts asking for it
#: (SPEC-tradar.md §12.1). What lets `SkriverIndikator` say "Postar
#: verifikation A-118..." instead of being "en anonym spinner", and what
#: gives `AgentWorker.current_activity` something better than "processing".
StreamToolCallHook = Callable[[str], None]


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
    #: Delivers text/tool-call increments through `run_turn`'s `on_text` /
    #: `on_tool_call` hooks (SPEC-tradar.md §12.1). Both shipped adapters
    #: can, each through its own SDK's streaming helper. Defaulted to
    #: `False` so an adapter that has not been taught to stream says so by
    #: omission rather than by silently accepting hooks it never calls: a
    #: caller gated on this simply never passes them, and gets a complete
    #: turn without deltas (test case 10). A protocol difference that is
    #: shown, not one that is hidden.
    streaming: bool = False


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
        max_tokens: Optional[int],
        on_text: Optional[StreamTextHook] = None,
        on_tool_call: Optional[StreamToolCallHook] = None,
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
            "Add one to services/llm/_MODELS before this model may run."
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
    """What `get_model_info` returns: a model's gateway, protocol and price."""

    model: str
    protocol: ProtocolName
    price: ModelPrice
    #: Which gateway serves it -- the model id's prefix.
    provider: Provider
    #: The id the gateway expects in the request's `model` field: the stored
    #: id without its prefix. Both gateways document the bare id; the
    #: `opencode/` / `opencode-go/` prefix is OpenCode's config convention,
    #: and it is what `threads.model` / `agent_runs.model` keep, so a run
    #: still says afterwards which gateway it went to.
    api_model: str


_PROVIDERS: tuple[Provider, ...] = ("opencode", "opencode-go")


def api_model_id(model: str) -> str:
    """`model` without its gateway prefix -- what goes on the wire.

    Pure string work, no registry lookup, so the adapters' request builders
    stay callable with any id in tests. An id without a known prefix is
    passed through unchanged.
    """
    prefix, sep, bare = model.partition("/")
    if sep and prefix in _PROVIDERS:
        return bare
    return model


#: How the adapters identify themselves to the gateway. OpenCode Go refuses
#: a generic SDK user agent: it wants the client's own name
#: (https://opencode.ai/docs/go/#where-can-i-use-it).
USER_AGENT = "bok-agent/1.0"


def gateway_headers(session_id: Optional[str]) -> dict[str, str]:
    """Headers every adapter sends on every request.

    `x-opencode-session` is a stable id per conversation -- one thread, or
    one intake pass -- which Go uses for routing and prompt caching, and
    without which it answers 400 `MissingSessionID`. Zen ignores both.
    """
    headers = {"User-Agent": USER_AGENT}
    if session_id:
        headers["x-opencode-session"] = session_id
    return headers


# Every model has an explicit protocol and price row -- no inference from
# the name. A substring rule ("claude" means Messages) held on Zen, but Go
# serves Qwen and MiniMax over Messages too, and a rule that is right by
# coincidence is one model away from routing a request to the wrong
# endpoint. Adding a model is still one dict entry.
#
# Models a gateway serves only over `/responses` (Go's Grok, GPT Luna and
# Muse; Zen's newer GPT/Grok) have no adapter here and are deliberately
# absent.
#
# Illustrative placeholder prices -- confirm against the gateways' actual
# price sheets (https://opencode.ai/zen, https://opencode.ai/docs/go/)
# before any real spend. Converted from USD at an illustrative ~10 SEK/USD,
# not a maintained FX rate. Go is a flat subscription, but its quotas are
# metered in these same per-token prices, and the daily cap (A9) needs a
# cost per run either way.
#
# `opencode/claude-sonnet-5`'s USD reference ($2 in / $10 out per million
# tokens) is the one figure SPEC-agentruntime.md §12.5 actually states.
_MODELS: dict[str, tuple[ProtocolName, ModelPrice]] = {
    # --- OpenCode Zen -----------------------------------------------------
    "opencode/claude-opus-5": (
        "messages",
        ModelPrice(
            input_ore_per_million_tokens=15_000,
            output_ore_per_million_tokens=75_000,
            # Anthropic-style cache reads are billed at roughly 10% of the
            # base input price.
            cache_read_ore_per_million_tokens=1_500,
        ),
    ),
    "opencode/claude-sonnet-5": (
        "messages",
        ModelPrice(
            input_ore_per_million_tokens=2_000,
            output_ore_per_million_tokens=10_000,
            cache_read_ore_per_million_tokens=200,
        ),
    ),
    "opencode/gpt-5.5": (
        "chat",
        ModelPrice(
            input_ore_per_million_tokens=1_500,
            output_ore_per_million_tokens=6_000,
            # Chat Completions has no verifiable cache-read discount
            # (capabilities.cache_breakpoint is False for this protocol), so
            # this is priced the same as a plain input token.
            cache_read_ore_per_million_tokens=1_500,
        ),
    ),
    "opencode/grok-4": (
        "chat",
        ModelPrice(
            input_ore_per_million_tokens=2_500,
            output_ore_per_million_tokens=10_000,
            cache_read_ore_per_million_tokens=2_500,
        ),
    ),
    # --- OpenCode Go ------------------------------------------------------
    # Chat-protocol rows price a cache read as a plain input token, for the
    # reason given on `opencode/gpt-5.5` above.
    "opencode-go/glm-5.3": (
        "chat",
        ModelPrice(
            input_ore_per_million_tokens=1_400,
            output_ore_per_million_tokens=4_400,
            cache_read_ore_per_million_tokens=1_400,
        ),
    ),
    "opencode-go/glm-5.3-flash": (
        "chat",
        ModelPrice(
            input_ore_per_million_tokens=150,
            output_ore_per_million_tokens=500,
            cache_read_ore_per_million_tokens=150,
        ),
    ),
    "opencode-go/kimi-k3": (
        "chat",
        ModelPrice(
            input_ore_per_million_tokens=3_000,
            output_ore_per_million_tokens=15_000,
            cache_read_ore_per_million_tokens=3_000,
        ),
    ),
    "opencode-go/deepseek-v4-pro": (
        "chat",
        ModelPrice(
            input_ore_per_million_tokens=660,
            output_ore_per_million_tokens=1_980,
            cache_read_ore_per_million_tokens=660,
        ),
    ),
    "opencode-go/deepseek-v4.1-flash": (
        "chat",
        ModelPrice(
            input_ore_per_million_tokens=150,
            output_ore_per_million_tokens=600,
            cache_read_ore_per_million_tokens=150,
        ),
    ),
    "opencode-go/qwen3.8-max": (
        "messages",
        ModelPrice(
            input_ore_per_million_tokens=2_000,
            output_ore_per_million_tokens=6_000,
            cache_read_ore_per_million_tokens=250,
        ),
    ),
    "opencode-go/minimax-m3": (
        "messages",
        ModelPrice(
            input_ore_per_million_tokens=300,
            output_ore_per_million_tokens=1_200,
            cache_read_ore_per_million_tokens=60,
        ),
    ),
}


def get_model_info(model: str) -> ModelInfo:
    """Resolve a model id to its gateway, protocol and price row.

    Raises `UnknownModelError` if the model has no row -- that is a hard
    error by design (SPEC §2), not a fallback to a default price.
    """
    row = _MODELS.get(model)
    if row is None:
        raise UnknownModelError(model)
    protocol, price = row
    # Every key in `_MODELS` carries one of `_PROVIDERS` as its prefix, so
    # this cast cannot lie; `test_every_registered_model_has_a_known_provider`
    # holds the table to that.
    provider = cast(Provider, model.partition("/")[0])
    return ModelInfo(
        model=model,
        protocol=protocol,
        price=price,
        provider=provider,
        api_model=api_model_id(model),
    )
