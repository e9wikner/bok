"""One LLM session for one intake source (docs/redesign/SPEC-agentruntime.md §6.3, task A8).

"Ett anrop per underlag, inte en session som lever över hela passet" -- the
caller (A9's budget/cap logic, A10's worker) constructs one `LLMClient`, one
intake source and its bytes, and gets back exactly one `SessionOutcome`: a
posted voucher, a documented abstention, or (only for a case the manual loop
below cannot make sense of) a hard failure. This module never persists
anything itself -- no `AgentRunRepository` import here on purpose (see
`tasks/agentruntime/todo.md`'s A8 file list) -- it only returns enough
structure (`SessionOutcome.turns`) for the caller to write `agent_run_events`
rows later.

Three things this module is deliberately *not*:

- Not protocol-aware. It only ever sees `services.llm.LLMClient` and its
  `capabilities` -- no `anthropic`/`openai` import, no `if protocol == ...`.
- Not the tool executor. `services.agent_tools.execute_tool` decides what a
  tool call does and raises on failure; this module decides what a raised
  exception, or a successful `posta_verifikation`/`registrera_avstaende`
  call, means for the *session's outcome* (SPEC §6.7).
- Mostly not a cap enforcer. `max_tool_turns` is the cap A8 owns (SPEC §6.5's
  "verktygsvarv per underlag", default
  `config.settings.agent_max_tool_turns_per_item`). A9 adds the one other cap
  that has to live in this loop -- cumulative *output* tokens per item (SPEC
  §6.5's "ut-token per underlag", default
  `config.settings.agent_max_output_tokens_per_item`), since it can only be
  measured turn by turn, right here. The remaining two caps (daily cost,
  items per pass) are checked *between* sessions/items by A9/A10 in
  `services/agent_runtime.py` and the future worker -- this module has no
  notion of them.

KNOWN LIMITATION -- extended thinking across turns: Anthropic's
extended-thinking + tool-use flow can require preserving `thinking`/
`redacted_thinking` content blocks verbatim across turns in some
configurations (interleaved thinking). `LLMTurn` (A4/A5) deliberately does
not carry those blocks through -- it only has `text` and `tool_calls` -- so
`_assistant_message` below reconstructs the assistant's turn from those two
fields alone. That reconstruction may not perfectly round-trip a real
multi-turn Anthropic Messages conversation in every thinking configuration.
This is a documented risk for real (non-test) runs, not solved here --
fixing it would mean enriching `LLMTurn`'s shape, which is out of this task's
scope. No test in this module is affected: every test drives a fake
`LLMClient`, which never produces thinking blocks to lose.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Literal, Optional

from config import settings
from domain.models import Account, CorrectionHistory, IntakeSource, Period
from repositories.account_repo import AccountRepository
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.agent_instruction_repo import AgentInstructionRepository
from repositories.system_instructions import get_system_instructions
from services.agent_documents import ContentBlock, DocumentUnreadableError
from services.agent_documents import select_content_for_source as _select_content
from services.agent_tools import AGENT_TOOL_DEFINITIONS, execute_tool
from services.llm import (
    LLMClient,
    LLMTurn,
    StreamTextHook,
    StreamToolCallHook,
    ToolCall,
    Usage,
)

# ---------------------------------------------------------------------------
# System prompt (SPEC §6.3, stable/cacheable -- see SPEC §6.6)
# ---------------------------------------------------------------------------
#
# This function returns a plain string. It knows nothing about cache
# breakpoints, `cache_control`, or any protocol-specific wire shape --
# turning a plain `system: str` into the cache-breakpoint content-block form
# is `services/llm/messages.py`'s job (A5), not this module's. Keeping this
# protocol-agnostic is what makes test case 14 ("call it twice, assert
# byte-identical strings") meaningful: there is only one shape to compare.
#
# SPEC §6.6's three cache traps, and how this function avoids each:
#   - No timestamp anywhere in here or anything it calls. Today's date lives
#     in `build_user_turn`, which sits *after* the cache breakpoint.
#   - Deterministic ordering: the kontoplan is sorted by account code and the
#     corrections are sorted by (created_at, id) descending, both explicitly
#     in Python -- never relying on a dict/set's iteration order or an
#     unsorted SQL result happening to come back the same way twice.
#   - Nothing here is "verify, don't guess" on its own; that half of §6.6 is
#     test case 15, driven against a fake client in the test file.

#: How many of the most recent corrections to include (SPEC §6.3 point 4).
#: "Vad människan senast rättade är den starkaste signalen som finns" --
#: recent, not exhaustive; 20 is a small, fixed number so the section's size
#: doesn't grow unboundedly as correction history accumulates.
_CORRECTIONS_LIMIT = 20

#: Scope key for the company's own, human-editable accounting instructions
#: (`AgentInstructionRepository`), matching `GET /api/v1/agent-instructions/
#: accounting`'s `company` field (see `api/routes/agent_instructions.py`).
_ACCOUNTING_COMPANY_SCOPE = "accounting_company"


def _render_kontoplan(accounts: list[Account]) -> str:
    """One line per account, sorted by code -- never dict/set order."""
    lines = ["## Kontoplan"]
    for account in sorted(accounts, key=lambda acc: acc.code):
        lines.append(f"{account.code}  {account.name}  ({account.account_type.value})")
    return "\n".join(lines)


def _render_corrections(corrections: list[CorrectionHistory]) -> str:
    """One line per correction, newest first.

    `AccountingCorrectionRepository.list` already orders by `created_at
    DESC`, but that column has no tiebreaker for two rows created in the
    same instant -- so this re-sorts explicitly by `(created_at, id)`
    descending, a stable order for identical underlying data regardless of
    what order SQLite happened to return rows in (SPEC §6.6).
    """
    lines = ["## Senaste korrigeringarna"]
    if not corrections:
        lines.append("(inga korrigeringar ännu)")
        return "\n".join(lines)

    ordered = sorted(
        corrections, key=lambda entry: (entry.created_at, entry.id), reverse=True
    )
    for entry in ordered:
        lines.append(
            f"- {entry.created_at.isoformat()}  verifikation "
            f"{entry.original_voucher_id} ({entry.change_type or '-'}): "
            f"{entry.correction_reason or '-'}"
        )
    return "\n".join(lines)


def build_system_prompt() -> str:
    """Assemble the stable, cacheable system prompt (SPEC §6.3), in order:

    1. `repositories.system_instructions.get_system_instructions()` --
       the same four read-only files served to a human-run external agent.
    2. The company's own, editable accounting instructions.
    3. The kontoplan, sorted deterministically.
    4. The latest corrections, sorted deterministically.

    No `datetime.now()` or any other non-deterministic value anywhere in
    this function or anything it calls -- see the module-level comment above
    for why, and test case 14 for the assertion.
    """
    system_instructions = get_system_instructions()["content_markdown"]
    company_instructions = AgentInstructionRepository.get_active(
        _ACCOUNTING_COMPANY_SCOPE
    )["content_markdown"]
    kontoplan_section = _render_kontoplan(AccountRepository.list_all(active_only=True))
    corrections_section = _render_corrections(
        AccountingCorrectionRepository.list(limit=_CORRECTIONS_LIMIT)
    )
    return "\n\n---\n\n".join(
        [
            system_instructions,
            company_instructions,
            kontoplan_section,
            corrections_section,
        ]
    )


# ---------------------------------------------------------------------------
# User turn (SPEC §6.3, volatile -- after the cache breakpoint)
# ---------------------------------------------------------------------------


def _render_open_periods(open_periods: list[Period]) -> str:
    if not open_periods:
        return "(inga öppna perioder)"
    ordered = sorted(open_periods, key=lambda period: (period.year, period.month))
    return "\n".join(
        f"- {period.id}: {period.year}-{period.month:02d}" for period in ordered
    )


def build_user_turn(
    source: IntakeSource,
    content_block: ContentBlock,
    today: date,
    open_periods: list[Period],
) -> list[dict]:
    """Build the volatile user turn (SPEC §6.3): today's date, a compact open-
    periods summary, this source's own metadata, and finally `content_block`
    itself -- the text/image/document block A6's `select_content_for_source`
    produced for it.

    Returns a single Anthropic-native `{"role": "user", "content": [...]}`
    message wrapped in a list, directly usable as (part of) the `messages`
    list `LLMClient.run_turn` expects.
    """
    metadata_text = (
        f"Dagens datum: {today.isoformat()}\n\n"
        "Öppna perioder:\n"
        f"{_render_open_periods(open_periods)}\n\n"
        "Underlag:\n"
        f"- id: {source.id}\n"
        f"- filnamn: {source.original_filename}\n"
        f"- filtyp: {source.mime_type}\n"
        f"- förklaring: {source.explanation or '-'}\n"
        f"- agentvägledning: {source.agent_guidance or '-'}\n"
    )
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": metadata_text},
                content_block,
            ],
        }
    ]


# ---------------------------------------------------------------------------
# Outcome type
# ---------------------------------------------------------------------------


def _zero_usage() -> Usage:
    return Usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=0)


def _add_usage(total: Usage, turn_usage: Usage) -> Usage:
    return Usage(
        input_tokens=total.input_tokens + turn_usage.input_tokens,
        output_tokens=total.output_tokens + turn_usage.output_tokens,
        cache_read_input_tokens=(
            total.cache_read_input_tokens + turn_usage.cache_read_input_tokens
        ),
    )


@dataclass(frozen=True)
class ExecutedToolCall:
    """One tool call executed within a turn, and what happened.

    `result` is set only when `ok` is True; `error` (a human-readable
    message, see `_format_tool_error`) only when it's False. Kept alongside
    `SessionTurnRecord` purely for the caller (A9/A10) to log -- this module
    never inspects `.ok/.error` again after building the `tool_result` block.
    """

    tool_call: ToolCall
    ok: bool
    result: Any = None
    error: Optional[str] = None


@dataclass(frozen=True)
class SessionTurnRecord:
    """Everything about one LLM turn worth persisting later: the turn itself
    (what the model sent) and every tool call executed because of it (what
    ran, and what it returned or raised).

    This module does not persist these anywhere -- `run_session`'s caller
    (A9/A10) is expected to turn each one into `agent_run_events` rows.
    """

    turn: LLMTurn
    executed_tool_calls: list[ExecutedToolCall] = field(default_factory=list)


@dataclass
class SessionOutcome:
    """The result of one session, on either entry point.

    `kind` is always one of "posted" / "abstained" / "answered" / "failed" --
    there is no fifth, ambiguous state. `reason` carries the
    abstention/failure motivation or code (e.g. "agent_refusal: ...",
    "agent_output_truncated", "agent_no_outcome", "agent_turn_limit"); it is
    `None` for "posted" and for "answered". `voucher_id`/`tool_result` are
    set on a successful posting; `tool_result` is also set when the outcome
    came from a successful `registrera_avstaende` call. `usage` is
    accumulated across every LLM turn actually made in this session (zero if
    content selection aborted before any call -- SPEC §6.3 step 3).

    "answered" only ever comes from the thread entry point
    (SPEC-tradar.md §11): a turn that ends with no tool call is a *reply*
    there, and an unresolved outcome on the document path. `text` is that
    reply, and is empty on every other kind -- the document path's own
    assistant text lives in `turns`, where it always did.
    """

    kind: Literal["posted", "abstained", "answered", "failed"]
    reason: Optional[str] = None
    voucher_id: Optional[str] = None
    tool_result: Optional[dict] = None
    usage: Usage = field(default_factory=_zero_usage)
    turns: list[SessionTurnRecord] = field(default_factory=list)
    text: str = ""


# ---------------------------------------------------------------------------
# Tool-result / assistant-message reconstruction for the manual loop
# ---------------------------------------------------------------------------


def _format_tool_error(exc: Exception) -> str:
    """Render any tool-call exception as a human-readable message for an
    Anthropic `tool_result` block with `is_error: true` (SPEC §6.7: "får
    rätta sig själv inom varvtaket").

    Most domain exceptions raised through `execute_tool`
    (`domain.validation.ValidationError`, `services.intake.IntakeError`,
    `services.bank_inputs.BankInputError`,
    `services.agent_tools.PostingConflictError`) carry `.code`/`.message`/
    `.details`; `services.agent_documents.DocumentUnreadableError` carries
    `.reason` instead. Anything else falls back to `str(exc)`.
    """
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None) or getattr(exc, "reason", None) or str(exc)
    details = getattr(exc, "details", None)
    rendered = f"[{code}] {message}" if code else str(message)
    if details:
        rendered = f"{rendered} ({details})"
    return rendered


def _tool_result_content_blocks(tool_name: str, result: Any) -> list[dict]:
    """Anthropic `tool_result` content is itself a list of content blocks.

    `hamta_underlagsfil` returns exactly one content block already in
    Anthropic-native shape (text/image/document, per
    `services.agent_documents.select_content_for_source`) -- passed through
    unchanged so an image or document actually reaches the model as visual
    content, not flattened into an opaque JSON string. Every other tool
    returns a plain JSON-serializable dict/list, rendered as a single text
    block.
    """
    if (
        tool_name == "hamta_underlagsfil"
        and isinstance(result, dict)
        and "type" in result
    ):
        return [result]
    if isinstance(result, str):
        return [{"type": "text", "text": result}]
    return [
        {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
    ]


def _tool_result_block(
    tool_use_id: str, content_blocks: list[dict], *, is_error: bool = False
) -> dict:
    block: dict = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content_blocks,
    }
    if is_error:
        block["is_error"] = True
    return block


def _assistant_message(turn: LLMTurn) -> dict:
    """Reconstruct the assistant's turn as a message to append before the
    next turn -- see the module docstring's "KNOWN LIMITATION" paragraph for
    what this does *not* preserve (thinking/redacted_thinking blocks).
    """
    content: list[dict] = []
    if turn.text:
        content.append({"type": "text", "text": turn.text})
    for tool_call in turn.tool_calls:
        content.append(
            {
                "type": "tool_use",
                "id": tool_call.id,
                "name": tool_call.name,
                "input": tool_call.arguments,
            }
        )
    return {"role": "assistant", "content": content}


# ---------------------------------------------------------------------------
# The session itself
# ---------------------------------------------------------------------------

#: Per-call token limit for the LLM's response on a single `run_turn` call.
#: Distinct from SPEC §6.5's "ut-token per underlag" cap (default 32,000),
#: which is a *cumulative* limit across every turn of one session and is
#: A9's job to enforce between turns -- not this constant, and not checked
#: anywhere in this module.
DEFAULT_MAX_TOKENS_PER_TURN = 8192

#: Tool names that end a session outright on success (SPEC §6.3/§6.7): the
#: only two ways a pass over one intake source is allowed to conclude.
_POSTING_TOOL = "posta_verifikation"
_ABSTENTION_TOOL = "registrera_avstaende"


@dataclass(frozen=True)
class TerminalPolicy:
    """What a turn that reached no tool call *means* (SPEC-tradar.md §11).

    The loop below is shared by both entry points, and this is the only
    thing that differs between them. Five of §11's six rows are identical on
    both paths -- a refusal, a truncated turn, a posting, an abstention and
    the turn limit all mean the same thing whether a document or a person
    started the session -- so they are not in here. The sixth is:

        `stop == "end"` with no tool calls
          - document path: `abstained: agent_no_outcome`. SPEC-agentruntime
            §1 requires every pass over an item to end in a posting or a
            documented abstention, so a bare "end" is an unresolved outcome.
          - thread path: an **answer**. A bare "end" is precisely what an
            ordinary conversational reply looks like.

    A frozen dataclass rather than a bare string so a third entry point, if
    one ever appears, adds a named policy here instead of another `if` in
    the loop.
    """

    #: Only for logs and error text; never branched on.
    name: str
    #: What a bare `end` means: "abstain" (document) or "answer" (thread).
    bare_end: Literal["abstain", "answer"]


#: The document path's policy -- byte for byte the behaviour `run_session`
#: had before the loop was extracted (SPEC-tradar.md T4: a pure refactoring).
DOCUMENT_POLICY = TerminalPolicy(name="document", bare_end="abstain")

#: The thread path's policy (SPEC-tradar.md §11). A bare `end` is a reply.
THREAD_POLICY = TerminalPolicy(name="thread", bare_end="answer")


def run_tool_loop(
    client: LLMClient,
    *,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    model: str,
    actor: str,
    policy: TerminalPolicy,
    turn_limit: int,
    max_tokens_per_turn: int = DEFAULT_MAX_TOKENS_PER_TURN,
    max_output_tokens: Optional[int] = None,
    on_text: Optional[StreamTextHook] = None,
    on_tool_call: Optional[StreamToolCallHook] = None,
    posting_idempotency_key: Optional[str] = None,
    check_between_turns: Optional[Callable[[], Optional[str]]] = None,
) -> SessionOutcome:
    """The manual tool loop, shared by both entry points.

    Extracted from `run_session` unchanged (SPEC-tradar.md §11, task T4):
    every branch below is the one that was inline there, with `policy`
    deciding the single row of §11's table where the two paths differ. Never
    the SDK's own tool runner -- every tool call passes through
    `services.agent_tools.execute_tool`, where it can be logged and its
    result or error turned into an explicit `tool_result` block
    (SPEC-agentruntime §6.3).

    `messages` is mutated as the conversation grows, exactly as before; the
    caller owns the list it passes in.

    `max_output_tokens` defaults to
    `config.settings.agent_max_output_tokens_per_item` and is checked
    *between* turns: a turn that itself reached a terminal outcome is never
    overridden by it, and it never aborts mid-turn. `turn_limit` is the
    other per-session cap. Neither the daily budget nor the items-per-pass
    cap is known here -- both are checked between sessions, one layer up,
    and never inside a `with db.transaction():`.

    `on_text`/`on_tool_call` are forwarded to the adapter only when it says
    it can stream (`LLMCapabilities.streaming`, SPEC-tradar.md §12.1). An
    adapter that cannot is never handed a callback it would silently drop:
    the turn comes back complete, just without deltas (test case 10). The
    hooks are passed as keyword arguments only when they exist, so an
    adapter or a double written before they did is called exactly as it
    always was.

    `posting_idempotency_key` is handed to `execute_tool` and read only by
    `posta_verifikation` -- the thread path names its own key
    (`thread:{thread_id}:{post_id}`, SPEC-tradar.md §6.4), the document path
    passes nothing and lets the key be derived from the intake source. No
    tool is added by it (SPEC-tradar.md §8.2).

    `check_between_turns` is called between tool turns and returns a reason
    to stop, or `None` to continue. It exists so a caller can enforce a cap
    this module has no notion of -- the daily budget, for a thread turn that
    is a pass of its own -- at the one place where stopping is safe. It is a
    plain string rather than an exception type so that this module stays
    ignorant of `services.agent_runtime`, which imports *it*. There is no
    `with db.transaction():` anywhere in this module, so "between turns" is
    never inside one (SPEC-agentruntime §6.5, test case 30).
    """
    output_token_limit = (
        max_output_tokens
        if max_output_tokens is not None
        else settings.agent_max_output_tokens_per_item
    )
    stream_hooks: dict[str, Any] = {}
    if getattr(client.capabilities, "streaming", False):
        if on_text is not None:
            stream_hooks["on_text"] = on_text
        if on_tool_call is not None:
            stream_hooks["on_tool_call"] = on_tool_call

    usage = _zero_usage()
    turns: list[SessionTurnRecord] = []

    for _ in range(turn_limit):
        turn = client.run_turn(
            system=system_prompt,
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens_per_turn,
            **stream_hooks,
        )
        usage = _add_usage(usage, turn.usage)

        if turn.stop == "refusal":
            # Never proceed to any tool execution after a refusal.
            turns.append(SessionTurnRecord(turn=turn))
            return SessionOutcome(
                kind="abstained",
                reason=f"agent_refusal: {turn.text}",
                usage=usage,
                turns=turns,
            )

        if turn.stop == "max_tokens":
            # A truncated turn is never a decision.
            turns.append(SessionTurnRecord(turn=turn))
            return SessionOutcome(
                kind="abstained",
                reason="agent_output_truncated",
                usage=usage,
                turns=turns,
            )

        if turn.stop == "end":
            # Per `StopReason`'s contract "end" never carries tool calls.
            # The two paths part here, and only here -- see `TerminalPolicy`.
            turns.append(SessionTurnRecord(turn=turn))
            if policy.bare_end == "answer":
                return SessionOutcome(
                    kind="answered", text=turn.text, usage=usage, turns=turns
                )
            return SessionOutcome(
                kind="abstained", reason="agent_no_outcome", usage=usage, turns=turns
            )

        if turn.stop == "tool_calls":
            tool_result_blocks: list[dict] = []
            executed: list[ExecutedToolCall] = []

            for tool_call in turn.tool_calls:
                try:
                    result = execute_tool(
                        tool_call.name,
                        tool_call.arguments,
                        actor=actor,
                        capabilities=client.capabilities,
                        idempotency_key=posting_idempotency_key,
                    )
                except Exception as exc:  # noqa: BLE001 -- SPEC §6.7: any
                    # tool exception becomes an is_error tool_result and the
                    # model gets to retry within the remaining turn budget;
                    # it never aborts the session outright.
                    error_message = _format_tool_error(exc)
                    executed.append(
                        ExecutedToolCall(
                            tool_call=tool_call, ok=False, error=error_message
                        )
                    )
                    tool_result_blocks.append(
                        _tool_result_block(
                            tool_call.id,
                            [{"type": "text", "text": error_message}],
                            is_error=True,
                        )
                    )
                    continue

                executed.append(
                    ExecutedToolCall(tool_call=tool_call, ok=True, result=result)
                )

                if tool_call.name == _POSTING_TOOL:
                    # Immediately -- no further tool calls in this turn (or
                    # ever again in this session) run once a posting has
                    # happened.
                    turns.append(
                        SessionTurnRecord(turn=turn, executed_tool_calls=executed)
                    )
                    return SessionOutcome(
                        kind="posted",
                        voucher_id=str(result.get("id")),
                        tool_result=result,
                        usage=usage,
                        turns=turns,
                        text=turn.text,
                    )

                if tool_call.name == _ABSTENTION_TOOL:
                    turns.append(
                        SessionTurnRecord(turn=turn, executed_tool_calls=executed)
                    )
                    reason = (
                        result.get("summary")
                        or result.get("error_detail")
                        or "agent_abstained"
                    )
                    return SessionOutcome(
                        kind="abstained",
                        reason=reason,
                        tool_result=result,
                        usage=usage,
                        turns=turns,
                        text=turn.text,
                    )

                tool_result_blocks.append(
                    _tool_result_block(
                        tool_call.id,
                        _tool_result_content_blocks(tool_call.name, result),
                    )
                )

            turns.append(SessionTurnRecord(turn=turn, executed_tool_calls=executed))
            messages.append(_assistant_message(turn))
            messages.append({"role": "user", "content": tool_result_blocks})

            if usage.output_tokens > output_token_limit:
                # SPEC §6.5's "ut-token per underlag" cap: this turn didn't
                # itself post or abstain (handled above, before this point),
                # so nothing is overridden -- the cap only prevents the next
                # run_turn call from happening at all.
                return SessionOutcome(
                    kind="abstained",
                    reason="agent_output_limit",
                    usage=usage,
                    turns=turns,
                )

            if check_between_turns is not None:
                stop_reason = check_between_turns()
                if stop_reason is not None:
                    # Same shape and same place as the output-token cap
                    # above: this turn already reached no terminal outcome,
                    # so nothing is overridden -- only the *next* run_turn
                    # call is prevented, and never mid-turn.
                    return SessionOutcome(
                        kind="abstained",
                        reason=stop_reason,
                        usage=usage,
                        turns=turns,
                    )

            continue

        # Defensive: no other `stop` value should exist given `StopReason`'s
        # definition, but an unrecognized one must never be treated as a
        # silent success (SPEC §10: never post on an outcome the model
        # hasn't actually reached).
        turns.append(SessionTurnRecord(turn=turn))
        return SessionOutcome(
            kind="failed",
            reason=f"unknown_stop_reason: {turn.stop!r}",
            usage=usage,
            turns=turns,
        )

    # Turn budget exhausted without reaching a terminal outcome (test case 7).
    return SessionOutcome(
        kind="abstained", reason="agent_turn_limit", usage=usage, turns=turns
    )


def run_session(
    client: LLMClient,
    source: IntakeSource,
    file_bytes: bytes,
    open_periods: list[Period],
    today: date,
    model: str,
    actor: str,
    max_tool_turns: Optional[int] = None,
    max_tokens_per_turn: int = DEFAULT_MAX_TOKENS_PER_TURN,
    max_output_tokens: Optional[int] = None,
    on_text: Optional[StreamTextHook] = None,
    on_tool_call: Optional[StreamToolCallHook] = None,
) -> SessionOutcome:
    """Run one LLM session for one intake source (SPEC §6.3, §6.7).

    A thin wrapper around `run_tool_loop` since SPEC-tradar.md T4: this
    function owns what is specific to a *document* -- selecting the content
    block for the source, building the user turn out of its metadata, and
    the `DOCUMENT_POLICY` that makes a bare `end` an `agent_no_outcome`
    abstention -- and the loop itself is shared with the thread entry point.
    The behaviour is unchanged by that extraction (test case 7).

    `max_tool_turns` defaults to `config.settings.agent_max_tool_turns_per_item`
    (SPEC §6.5's "verktygsvarv per underlag" cap), `max_output_tokens` to
    `config.settings.agent_max_output_tokens_per_item` ("ut-token per
    underlag", checked between turns by the loop).
    """
    turn_limit = (
        max_tool_turns
        if max_tool_turns is not None
        else settings.agent_max_tool_turns_per_item
    )

    try:
        content_block = _select_content(
            source, file_bytes, capabilities=client.capabilities
        )
    except DocumentUnreadableError as exc:
        # SPEC §6.3 step 3: genuinely no LLM call happens here -- zero usage,
        # not a discarded call. See §2/§6.3's cost table.
        return SessionOutcome(kind="abstained", reason=exc.reason, usage=_zero_usage())

    return run_tool_loop(
        client,
        system_prompt=build_system_prompt(),
        messages=build_user_turn(source, content_block, today, open_periods),
        tools=AGENT_TOOL_DEFINITIONS,
        model=model,
        actor=actor,
        policy=DOCUMENT_POLICY,
        turn_limit=turn_limit,
        max_tokens_per_turn=max_tokens_per_turn,
        max_output_tokens=max_output_tokens,
        on_text=on_text,
        on_tool_call=on_tool_call,
    )
