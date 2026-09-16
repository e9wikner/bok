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
from typing import Any, Literal, Optional

from config import settings
from domain.models import Account, CorrectionHistory, IntakeSource, Period
from repositories.account_repo import AccountRepository
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.agent_instruction_repo import AgentInstructionRepository
from repositories.system_instructions import get_system_instructions
from services.agent_documents import ContentBlock, DocumentUnreadableError
from services.agent_documents import select_content_for_source as _select_content
from services.agent_tools import AGENT_TOOL_DEFINITIONS, execute_tool
from services.llm import LLMClient, LLMTurn, ToolCall, Usage

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
    """The result of one `run_session` call.

    `kind` is always one of "posted" / "abstained" / "failed" -- there is no
    fourth, ambiguous state. `reason` carries the abstention/failure
    motivation or code (e.g. "agent_refusal: ...", "agent_output_truncated",
    "agent_no_outcome", "agent_turn_limit"); it is `None` only for "posted".
    `voucher_id`/`tool_result` are set on a successful posting;
    `tool_result` is also set when the outcome came from a successful
    `registrera_avstaende` call. `usage` is accumulated across every LLM
    turn actually made in this session (zero if content selection aborted
    before any call -- SPEC §6.3 step 3).
    """

    kind: Literal["posted", "abstained", "failed"]
    reason: Optional[str] = None
    voucher_id: Optional[str] = None
    tool_result: Optional[dict] = None
    usage: Usage = field(default_factory=_zero_usage)
    turns: list[SessionTurnRecord] = field(default_factory=list)


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
) -> SessionOutcome:
    """Run one LLM session for one intake source (SPEC §6.3, §6.7).

    Manual loop on `LLMTurn.stop == "tool_calls"` -- never the SDK's own tool
    runner -- so every tool call passes through `services.agent_tools.
    execute_tool` where it can be logged and its result or error turned into
    an explicit `tool_result` block (SPEC §6.3: "varje verktygsanrop ska
    passera en punkt där vi kan neka, logga...").

    `max_tool_turns` defaults to `config.settings.agent_max_tool_turns_per_item`
    (SPEC §6.5's "verktygsvarv per underlag" cap).

    `max_output_tokens` defaults to
    `config.settings.agent_max_output_tokens_per_item` (SPEC §6.5's "ut-token
    per underlag" cap, task A9). It is checked *between* turns -- once the
    cumulative `usage.output_tokens` across every turn so far exceeds this
    limit, the loop stops before requesting another turn and the session
    returns `SessionOutcome(kind="abstained", reason="agent_output_limit")`.
    A turn that itself reaches a terminal outcome (posts, abstains via
    `registrera_avstaende`, refuses, is truncated, or ends with no tool
    calls) is never overridden by this check -- the cap only ever cuts off
    the *next* `run_turn` call, exactly like `max_tool_turns`, and it never
    aborts mid-turn.
    """
    turn_limit = (
        max_tool_turns
        if max_tool_turns is not None
        else settings.agent_max_tool_turns_per_item
    )
    output_token_limit = (
        max_output_tokens
        if max_output_tokens is not None
        else settings.agent_max_output_tokens_per_item
    )

    try:
        content_block = _select_content(
            source, file_bytes, capabilities=client.capabilities
        )
    except DocumentUnreadableError as exc:
        # SPEC §6.3 step 3: genuinely no LLM call happens here -- zero usage,
        # not a discarded call. See §2/§6.3's cost table.
        return SessionOutcome(kind="abstained", reason=exc.reason, usage=_zero_usage())

    system_prompt = build_system_prompt()
    messages: list[dict] = build_user_turn(source, content_block, today, open_periods)

    usage = _zero_usage()
    turns: list[SessionTurnRecord] = []

    for _ in range(turn_limit):
        turn = client.run_turn(
            system=system_prompt,
            messages=messages,
            tools=AGENT_TOOL_DEFINITIONS,
            model=model,
            max_tokens=max_tokens_per_turn,
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
            # Per `StopReason`'s contract "end" never carries tool calls; the
            # model finished without ever calling posta_verifikation or
            # registrera_avstaende. SPEC §1 requires every pass over an item
            # to end in one of those two outcomes, so a bare "end" is itself
            # an unresolved outcome, never a silent no-op.
            turns.append(SessionTurnRecord(turn=turn))
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

    # Turn budget exhausted without reaching posted/abstained (test case 7).
    return SessionOutcome(
        kind="abstained", reason="agent_turn_limit", usage=usage, turns=turns
    )
