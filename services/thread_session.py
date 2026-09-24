"""The thread entry point to the session (docs/redesign/SPEC-tradar.md §6.1, §6.3).

The second way into the same engine: a *message* instead of a document.
Everything that decides what the agent may do is shared with the document
path and unchanged here -- `build_system_prompt()` byte for byte (test case
12), `AGENT_TOOL_DEFINITIONS` byte for byte (test case 14), and
`services.agent_session.run_tool_loop` itself. Only three things differ, and
they are the whole of this module:

1. **The user turn** is the thread window plus today's date, the open
   periods and the new message -- not a document's metadata and content
   block.
2. **The terminal policy** is `THREAD_POLICY`: a turn that ends with no tool
   call is an *answer*, not an unresolved outcome (§11).
3. **The posting key** is `thread:{thread_id}:{post_id}`, hung on the user
   post that triggered the turn (§6.4).

What this module deliberately is *not*:

- Not a second way into the ledger. A posting from a chat reply goes the
  exact same way as one from a document: `posta_verifikation` ->
  `services/voucher_posting.py`, with an `Idempotency-Key`. The tool surface
  is not extended (§8.2, antagande 4).
- Not a renderer. It returns a `SessionOutcome`; turning that and the run's
  events into `thread_posts` is `services/thread_service.py`'s job (§8.1:
  the runtime produces events and outcomes, `tradar` decides how they are
  shown).
- Not a summarizer. A post that does not fit the window is left out. See
  `build_thread_window`.
"""

import json
import logging
from datetime import date
from typing import Any, Optional

from config import settings
from domain.models import Period, Thread, ThreadPost
from services.agent_session import (
    THREAD_POLICY,
    SessionOutcome,
    build_system_prompt,
    run_tool_loop,
)
from services.agent_tools import (
    AGENT_TOOL_DEFINITIONS,
    ProposalSequence,
    derive_thread_posting_idempotency_key,
)
from services.llm import LLMClient, StreamTextHook, StreamToolCallHook

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The thread window (SPEC §6.3)
# ---------------------------------------------------------------------------

#: Characters per token, for budgeting only. No tokenizer is used or added:
#: SPEC §3 is explicit that this module takes no new dependency, and the two
#: providers tokenize differently anyway, so an exact count for one would be
#: wrong for the other. 3 is deliberately pessimistic -- Swedish prose runs
#: closer to 4 characters per token, and JSON-ish `draft` bodies closer to 3
#: -- because the failure mode of underestimating (a window that overflows
#: the context and costs more than planned) is worse than the failure mode of
#: overestimating (a slightly shorter window than the budget allows).
_CHARS_PER_TOKEN = 3


def estimate_tokens(text: str) -> int:
    """A deliberately rough, pessimistic token estimate for `text`.

    Used only to decide where the thread window is cut. Never used for cost:
    `compute_cost_ore` prices the provider's own reported `Usage`, which is
    the real number.
    """
    return -(-len(text) // _CHARS_PER_TOKEN)  # ceil division


def render_post(post: ThreadPost) -> str:
    """One post as one line of context.

    `agent_text`/`user_text` render as their text; every other type renders
    as compact JSON of its body, which is what the client was shown and is
    therefore what the model should see it as having said. Base64 never
    appears here because it never reaches `body_json` in the first place
    (§6.2, task T7) -- this function does not need to strip what cannot
    arrive.
    """
    if post.type in ("agent_text", "user_text"):
        body = post.body.get("text", "")
    else:
        body = json.dumps(post.body, ensure_ascii=False, sort_keys=True, default=str)
    return f"[{post.seq}] {post.actor} ({post.type}): {body}"


def build_thread_window(
    posts: list[ThreadPost], budget_tokens: Optional[int] = None
) -> list[ThreadPost]:
    """The most recent posts that fit inside `budget_tokens`, oldest first.

    SPEC §6.3: within the fiscal year's thread, the whole thread does **not**
    go into the context -- that would let the cost grow unbounded until the
    daily cap stopped it by itself, which looks like a bug rather than a
    budget.

    What does not fit is **left out. It is never summarized.** An LLM summary
    of earlier bookkeeping conversation, which then forms the basis for a
    posting, is precisely the second-hand text `ANALYS.md` §7 warns about,
    sitting in something that looks like an audit trail. A gap the human can
    see is honest; a paraphrase she cannot check is not.

    Newest posts win, because a conversation's most recent turns are the ones
    the next turn answers.
    """
    budget = (
        budget_tokens
        if budget_tokens is not None
        else settings.agent_thread_window_tokens
    )
    kept: list[ThreadPost] = []
    spent = 0
    for post in reversed(posts):
        cost = estimate_tokens(render_post(post))
        if spent + cost > budget:
            # Stop at the first post that does not fit rather than skipping
            # it and trying the next, older one: a window with a hole in the
            # middle would read as a conversation that never happened that
            # way.
            break
        kept.append(post)
        spent += cost
    kept.reverse()
    return kept


def _render_open_periods(open_periods: list[Period]) -> str:
    if not open_periods:
        return "(inga öppna perioder)"
    ordered = sorted(open_periods, key=lambda period: (period.year, period.month))
    return "\n".join(
        f"- {period.id}: {period.year}-{period.month:02d}" for period in ordered
    )


def build_thread_user_turn(
    thread: Thread,
    window: list[ThreadPost],
    message: str,
    today: date,
    open_periods: list[Period],
    *,
    omitted_posts: int = 0,
) -> list[dict]:
    """Build the volatile user turn for a thread reply (SPEC §6.1 step 4).

    Everything here sits *after* the cache breakpoint, exactly as
    `build_user_turn` does for a document: today's date is in here and never
    in the system prompt, so the cached prefix stays byte-identical between a
    document turn and a thread turn (test case 12, SPEC-agentruntime §6.6).

    When the window left posts out, that is stated plainly rather than
    hidden. The model is told the conversation is older than what it can see
    -- it is not shown a summary of the missing part, and not left to assume
    it has the whole thread.
    """
    lines = [
        f"Dagens datum: {today.isoformat()}",
        "",
        "Öppna perioder:",
        _render_open_periods(open_periods),
        "",
        f"Tråd: {thread.view_key} (räkenskapsår {thread.fiscal_year_id})",
        "",
    ]
    if omitted_posts:
        lines.append(
            f"(Tidigare i tråden: {omitted_posts} inlägg som inte fick plats i "
            "kontextfönstret. De är utelämnade, inte sammanfattade — fråga om "
            "du behöver veta vad som sades.)"
        )
        lines.append("")
    if window:
        lines.append("Tidigare inlägg i tråden:")
        lines.extend(render_post(post) for post in window)
        lines.append("")
    lines.append("Nytt meddelande:")
    lines.append(message)
    return [{"role": "user", "content": [{"type": "text", "text": "\n".join(lines)}]}]


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------


def run_thread_session(
    client: LLMClient,
    thread: Thread,
    trigger_post: ThreadPost,
    message: str,
    history: list[ThreadPost],
    open_periods: list[Period],
    today: date,
    model: str,
    actor: str,
    max_tool_turns: Optional[int] = None,
    max_tokens_per_turn: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    window_budget_tokens: Optional[int] = None,
    on_text: Optional[StreamTextHook] = None,
    on_tool_call: Optional[StreamToolCallHook] = None,
    check_between_turns: Optional[Any] = None,
) -> SessionOutcome:
    """Run one LLM session for one message in one thread (SPEC §6.1).

    `trigger_post` is the human's own post -- the one already written to the
    thread before this was called, per §6.1 step 2 -- and it is what the
    posting key hangs on. `history` is the thread's posts to consider for the
    window; `build_thread_window` decides how many of them fit.

    The caps: `max_tool_turns` and `max_output_tokens` are the same two the
    loop always enforced, per session. `check_between_turns` is where the
    caller puts the daily budget -- checked between tool turns, never inside
    a transaction (§6.1, test case 30).

    Returns a `SessionOutcome`, which for this path may also be `"answered"`
    (§11). Writing any of it to the thread is the caller's job.
    """
    turn_limit = (
        max_tool_turns
        if max_tool_turns is not None
        else settings.agent_max_tool_turns_per_item
    )
    window = build_thread_window(history, window_budget_tokens)

    return run_tool_loop(
        client,
        # Byte for byte the document path's prompt: the cache breakpoint sits
        # at the end of it, and moving it for the thread's sake would throw
        # away the cache economy for both paths (SPEC-agentruntime §6.6).
        system_prompt=build_system_prompt(),
        messages=build_thread_user_turn(
            thread,
            window,
            message,
            today,
            open_periods,
            omitted_posts=len(history) - len(window),
        ),
        # Unchanged, in `_TOOL_SPECS`' unchanged order -- the tool list is
        # part of the cached prefix, and the thread gets no tool of its own
        # (SPEC §6.4, §8.2; test case 14).
        tools=AGENT_TOOL_DEFINITIONS,
        model=model,
        actor=actor,
        policy=THREAD_POLICY,
        turn_limit=turn_limit,
        max_tokens_per_turn=max_tokens_per_turn,
        max_output_tokens=max_output_tokens,
        on_text=on_text,
        on_tool_call=on_tool_call,
        posting_idempotency_key=derive_thread_posting_idempotency_key(
            thread.id, trigger_post.id
        ),
        check_between_turns=check_between_turns,
        # `be_om_beslut` cannot exist without knowing which thread it was
        # raised in (SPEC-beslut.md §6.4). It travels in an unread mapping,
        # the same opaque handoff `posting_idempotency_key` already makes
        # above: `run_tool_loop` forwards it without looking inside, so
        # SPEC-tradar.md §8.1's boundary -- the runtime does not know what a
        # thread is -- survives the tenth tool. Only `execute_tool` ->
        # `be_om_beslut` opens it.
        #
        # `proposals` is `foresla_verifikation`'s (SPEC-flode-verifikationer
        # §5.5): the `{post_id}:{n}` of its key, fresh per turn and hung on
        # the same trigger post as the posting key. It rides in the same
        # unread mapping for the same reason, and only
        # `_run_foresla_verifikation` opens it.
        tool_context={
            "thread": thread,
            "proposals": ProposalSequence(thread.id, trigger_post.id),
        },
    )
