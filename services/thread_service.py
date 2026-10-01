"""Runtime events and outcomes rendered as thread posts (SPEC-tradar.md §6.2).

The boundary from `SPEC-agentruntime.md` §1, restated in SPEC-tradar.md §8.1:
**the runtime produces events and outcomes; `tradar` decides how they are
shown.** This module is that decision, and it is the only place that knows
both shapes. Nothing here is imported by `services/agent_runtime.py` or
`services/agent_session.py`, and no `thread_id` travels down into either
(test: `TestRuntimeKnowsNothingOfThreads`).

Two rules the §6.2 table does not state but the contract depends on:

- **A `tool_call` is a chip, not a post.** `komponenter.md`'s `SparChip` is
  "agentens spår: vad den läste, räknade och gjorde" -- a row under the
  answer, not a turn in the conversation. Nine tool calls are one reply with
  nine chips, never nine replies (test case 16).
- **Base64 never reaches a post.** `AgentWorker._compact_tool_result` already
  strips document/image payloads out of `agent_run_events`; the same applies
  here, and is applied again rather than assumed, because a post is what the
  client fetches on every thread load (test case 17).
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from db.database import db
from domain.models import Thread, ThreadPost
from domain.types import AuditAction
from repositories.agent_run_repo import AgentRunRepository
from repositories.audit_repo import AuditRepository
from repositories.thread_repo import ThreadRepository
from services.agent_session import SessionOutcome

logger = logging.getLogger(__name__)

#: Payload keys whose values are, or may contain, raw file bytes. Same
#: precedent as `services.agent_runtime._compact_tool_result`, applied to
#: anything on its way into `body_json`/`traces_json`.
_BINARY_BLOCK_TYPES = ("document", "image")

#: Key names that carry base64 in Anthropic's own content-block shapes.
_BINARY_KEYS = ("data", "base64", "content_bytes")

#: How long a single rendered value may be before it is truncated. A trace
#: chip is one line in the interface (`komponenter.md`: mono 12, a pill); an
#: argument dump that runs to kilobytes is not a chip and is not readable.
_MAX_TRACE_VALUE_CHARS = 200


def compact(
    value: Any, max_chars: Optional[int] = _MAX_TRACE_VALUE_CHARS, _depth: int = 0
) -> Any:
    """Strip binary payloads out of anything bound for a post.

    Mirrors `services.agent_runtime._compact_tool_result` for whole content
    blocks, and goes one step further: it also walks nested structures, since
    a tool result may carry a block inside a list or a dict rather than being
    one. A `data` field under an Anthropic `source` is the base64 itself, so
    it is replaced rather than truncated -- a truncated base64 string is not
    smaller in any way that matters and is no longer valid for anything.

    `max_chars` caps each plain string for a chip's one line. A post's body
    passes `None`: what the agent said is stored whole, never shortened to
    fit a chip.

    Depth-limited: a payload nested deeper than this is not a shape any tool
    in `AGENT_TOOL_DEFINITIONS` returns, and recursion without a floor is how
    a malformed result takes a request down with it.
    """
    if _depth > 6:
        return "<nested too deeply>"
    if isinstance(value, dict):
        if value.get("type") in _BINARY_BLOCK_TYPES:
            return {"type": value["type"], "note": "<binary content omitted>"}
        return {
            key: (
                "<binary content omitted>"
                if key in _BINARY_KEYS and isinstance(item, str)
                else compact(item, max_chars, _depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [compact(item, max_chars, _depth + 1) for item in value]
    if max_chars is not None and isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "…"
    return value


# ---------------------------------------------------------------------------
# Traces (SparChip)
# ---------------------------------------------------------------------------

#: What each tool did, in the human's words, stored as the trace's label.
#: The client no longer renders traces (SPEC-lasbarhet §4.3); the labels keep
#: stored traces readable in the audit trail. Every tool in
#: ``services/agent_tools.py`` has one (``tests/test_tradar.py`` checks).
#: `komponenter.md`'s examples are of this shape: "16 händelser lästa",
#: "kompletteringsflagga satt" -- what happened, not which function ran.
_TRACE_LABELS = {
    "las_kontoplan": "kontoplanen läst",
    "las_perioder": "perioderna lästa",
    "las_verifikationer": "verifikationer lästa",
    "las_korrigeringar": "korrigeringshistoriken läst",
    "las_underlag": "underlag lästa",
    "hamta_underlagsfil": "underlagsfilen hämtad",
    "las_bankhandelser": "bankhändelser lästa",
    "posta_verifikation": "verifikation postad",
    "registrera_avstaende": "avstående registrerat",
    "be_om_beslut": "beslut framlagt",
    "foresla_verifikation": "verifikation föreslagen",
    "tolka_underlag": "underlaget tolkat",
    "koppla_underlag": "underlaget kopplat",
    "stang_perioder": "perioder låsta",
    "koppla_bort_underlag": "underlaget bortkopplat",
    "las_okopplade_banktransaktioner": "okopplade banktransaktioner lästa",
    "koppla_banktransaktion": "kontoutdrag kopplat",
    "las_kunder": "kunder lästa",
    "las_fakturor": "fakturor lästa",
    "foresla_faktura": "faktura föreslagen",
    "andra_fakturautkast": "fakturaförslaget ändrat",
    "koppla_bort_banktransaktion": "kontoutdrag bortkopplat",
    "las_loner": "löner lästa",
    "registrera_anstalld": "anställd registrerad",
    "satt_lon": "lön satt",
    "skapa_lonekorning": "lönekörning skapad",
    "foresla_rakenskapsar": "räkenskapsår föreslaget",
}


def build_trace(event_payload: dict) -> dict:
    """One `SparChip` from one `tool_call` event's payload.

    Carries the tool's name (so a client can group or filter) and a label in
    Swedish (so it can be rendered as-is). `detail` is whatever is worth one
    line -- a voucher number for a posting, nothing for a plain read -- and
    is always compacted first.
    """
    name = event_payload.get("name", "okänt verktyg")
    trace: dict = {"tool": name, "label": _TRACE_LABELS.get(name, name)}
    result = event_payload.get("result")
    if name == "posta_verifikation" and isinstance(result, dict):
        number = result.get("number")
        series = result.get("series")
        if series and number:
            trace["detail"] = f"{series}-{number}"
        if result.get("id"):
            trace["voucher_id"] = result["id"]
    return compact(trace)


def traces_for_run(run_id: str, since_seq: Optional[int] = None) -> list[dict]:
    """Every `tool_call` event of a run, as chips, in the order they happened.

    Test case 16: these become one post's `traces[]`, never posts of their
    own.
    """
    traces: list[dict] = []
    for event in AgentRunRepository.list_events(run_id, since_seq=since_seq):
        if event.kind != "tool_call":
            continue
        try:
            payload = json.loads(event.payload_json)
        except json.JSONDecodeError:
            logger.warning(
                "Agent run %s event %s has unparsable payload -- skipped as a trace",
                run_id,
                event.id,
            )
            continue
        traces.append(build_trace(payload))
    return traces


# ---------------------------------------------------------------------------
# Outcome -> post
# ---------------------------------------------------------------------------

#: Why the agent stopped, and what that means in bookkeeping terms (§6.7:
#: "ett `error`-inlägg med orsak *och* konsekvens i bokföringstermer"). The
#: consequence is the half that matters to the reader: a reason alone says
#: what happened to the agent, not what happened to her books.
_ERROR_CONSEQUENCES = {
    "agent_output_truncated": (
        "Svaret klipptes mitt i. Ingenting bokfördes — en avhuggen tur är "
        "aldrig ett beslut."
    ),
    "agent_no_outcome": ("Agenten kom inte fram till något. Ingenting bokfördes."),
    "agent_turn_limit": (
        "Agenten nådde taket för antal verktygsvarv. Ingenting bokfördes."
    ),
    "agent_output_limit": (
        "Agenten nådde taket för hur mycket den får skriva per fråga. "
        "Ingenting bokfördes."
    ),
    "llm_connection_error": (
        "Anropet till modellen gick inte fram. Ingenting bokfördes — försök " "igen."
    ),
    "llm_rate_limit_error": (
        "Modellen är tillfälligt överbelastad. Ingenting bokfördes — försök "
        "igen om en stund."
    ),
}

_DEFAULT_ERROR_CONSEQUENCE = (
    "Ingenting bokfördes. Ett osäkert utfall är alltid ett avstående, aldrig "
    "en postning."
)


def _error_body(reason: Optional[str], retry_draft_id: Optional[str] = None) -> dict:
    """`FelKort`'s body (§6.2): cause, consequence, and the id to retry with.

    `retry_draft_id` carries **the same draft id** the failed attempt used
    (§6.7), so "Försök igen" resumes the same intent rather than minting a
    new one -- which is also what keeps the idempotency key stable across
    the retry.
    """
    code = (reason or "").split(":", 1)[0].strip()
    return {
        "cause": reason or "okänd orsak",
        "consequence": _ERROR_CONSEQUENCES.get(code, _DEFAULT_ERROR_CONSEQUENCE),
        "retry_draft_id": retry_draft_id,
    }


def _posted_fallback(tool_result: Optional[dict]) -> str:
    """What a posting says when the agent said nothing after it.

    `posta_verifikation`'s result is the voucher response, `series` and
    `number` included (`services/voucher_posting.py`); an idempotent replay
    returns the same payload.
    """
    series = (tool_result or {}).get("series")
    number = (tool_result or {}).get("number")
    if series and number is not None:
        return f"Verifikation {series}-{number} är postad."
    return "Verifikationen är postad."


def _decision_body(outcome: SessionOutcome, decision_id: str) -> dict:
    """`BeslutKort`'s body (§6.2) for a registered abstention.

    §11: `registrera_avstaende` becomes a `decision` post. The agent's own
    wording is the point -- `datakontrakt.md` §2: "`reason` är agentens text
    om varför den inte gissade". It is never rewritten here.

    `decision_id` (B6, SPEC §2) is minted by `record_outcome` before this
    runs and before the post is written -- `decisions.post_id` is a plain
    foreign key into `thread_posts(id)`, so the row can only be created once
    the post exists, and a post is never rewritten afterwards to add one in
    (`SPEC-tradar.md` §8.4). This function's only job regarding it is to
    carry it in the body it already builds -- nothing else about it
    changes. Same shape as `_decision_post_body`
    (`services/decision_service.py`), which takes the same id the same way
    for a decision raised through `be_om_beslut`, so a `BeslutKort` looks
    identical regardless of which path produced it.
    """
    tool_result = outcome.tool_result or {}
    return {
        "decision_id": decision_id,
        "title": tool_result.get("summary") or "Agenten avstod",
        "amount": None,
        "reason": outcome.reason or tool_result.get("error_detail") or "",
        "source": (
            {"kind": "intake", "id": tool_result.get("intake_source_id")}
            if tool_result.get("intake_source_id")
            else None
        ),
        "consequence": (
            "Ingenting är bokfört. Beslutet ligger kvar tills du svarar på det."
        ),
    }


class ThreadService:
    """Write a finished session's outcome into a thread (§6.2).

    One post per turn, not one per event: `agent_run_events` is the run's
    log, `thread_posts` is what the human saw. The chips are the bridge
    between them.
    """

    @staticmethod
    def record_outcome(
        thread: Thread,
        run_id: str,
        outcome: SessionOutcome,
        *,
        actor: str = "agent",
        answer_text: Optional[str] = None,
    ) -> ThreadPost:
        """Render `outcome` as the one post that closes this turn.

        `answer_text` overrides the outcome's own text -- the stream
        passes the last paragraph it sent, the text after the turn's final
        tool call, so the post matches what the human was left reading
        (SPEC §4: the client replaces its optimistic rows with this post at
        `message.completed`). What the agent wrote between tool calls is
        never stored (SPEC-lasbarhet §4.1).

        Returns the post. The mapping, per §6.2 and §11:

        | outcome                          | post         |
        |----------------------------------|--------------|
        | `answered`                       | `agent_text` |
        | `posted`                         | `agent_text` |
        | `abstained` via registrera_avstaende | `decision` |
        | `abstained` for any other reason | `error`      |
        | `failed`                         | `error`      |

        B6 (SPEC-beslut.md §2): a `decision` post alone is not the whole
        story -- without a row in `decisions` bound to it, it is the
        orphaned card the module exists to close: visible in the thread,
        but impossible to list, age or answer. So when `_render` produces a
        `decision` post, this method also binds it to a fresh `decisions`
        row, in the same transaction as the post itself (see the comment
        by the `with db.transaction():` below for why that has to be
        atomic). Every other outcome kind is unaffected -- only the
        `decision` branch does any of this.
        """
        traces = traces_for_run(run_id)
        # Minted unconditionally, before `_render` runs, and cheaply (no
        # I/O): that way `_render` stays a pure function that merely
        # *carries* the value into the decision branch's body instead of
        # `record_outcome` re-deriving `_render`'s own "is this outcome a
        # decision" condition a second time just to decide whether an id is
        # needed at all.
        decision_id = str(uuid.uuid4())
        post_type, body = ThreadService._render(outcome, answer_text, decision_id)

        if post_type != "decision":
            return ThreadRepository.add_post(
                thread_id=thread.id,
                post_type=post_type,
                actor=actor,
                body=compact(body, max_chars=None),
                traces=traces or None,
                run_id=run_id,
            )

        # A `decision` post and the `decisions` row bound to it must land
        # together. The post is written first -- `decisions.post_id` is a
        # plain foreign key into an already-existing `thread_posts` row --
        # but if the row's write then failed on its own, a half-finished
        # outcome would leave exactly the orphaned card this task exists to
        # prevent: a post the human can see, with no row to list, age or
        # answer it by. The post is written with `_commit=False`, so it is
        # still pending when `DecisionService.create` opens its own
        # `with db.transaction():` -- and since both run on the same
        # thread-local connection (`db/database.py`), that block's commit
        # or rollback settles the post along with the row. SQLite has no
        # nested transactions; the outer block below is not a second one,
        # it is the guard for everything up to the point where `create`
        # takes over.
        compacted_body = compact(body, max_chars=None)
        with db.transaction():
            post = ThreadRepository.add_post(
                thread_id=thread.id,
                post_type=post_type,
                actor=actor,
                body=compacted_body,
                traces=traces or None,
                run_id=run_id,
                _commit=False,
            )

            # Deferred import -- AGENTS.md's service-to-service rule:
            # imported inside the method rather than at module load time.
            # Matches the same deferred import of `DecisionService` already
            # done in `services/agent_tools.py`'s `_run_be_om_beslut` for
            # this same module.
            from services.decision_service import DecisionService

            DecisionService().create(
                thread,
                title=compacted_body["title"],
                reason=compacted_body["reason"],
                consequence=compacted_body["consequence"],
                amount_ore=compacted_body["amount"],
                source=compacted_body["source"],
                kind="abstention",
                actor=actor,
                post=post,
                decision_id=decision_id,
            )

        return post

    @staticmethod
    def _render(
        outcome: SessionOutcome,
        answer_text: Optional[str],
        decision_id: Optional[str] = None,
    ) -> tuple[str, dict]:
        text = answer_text if answer_text is not None else outcome.text

        if outcome.kind == "answered":
            return "agent_text", {"text": text}

        if outcome.kind == "posted":
            # The post is the agent's own words about the posting; where it
            # said nothing, a plain statement of fact rather than a
            # fabricated explanation. The client no longer shows trace chips
            # (SPEC-lasbarhet §4.3), so the fact names the voucher's number
            # whenever the posting's result carries it.
            return "agent_text", {
                "text": text or _posted_fallback(outcome.tool_result),
                "voucher_id": outcome.voucher_id,
            }

        if outcome.kind == "abstained" and outcome.tool_result is not None:
            # `decision_id` is always minted by `record_outcome` before
            # this runs (B6) -- this is the only branch that needs one, so
            # `agent_text`/`error` never see it.
            assert decision_id is not None
            return "decision", _decision_body(outcome, decision_id)

        return "error", _error_body(outcome.reason)

    @staticmethod
    def record_error(
        thread: Thread,
        reason: str,
        *,
        run_id: Optional[str] = None,
        actor: str = "agent",
        retry_draft_id: Optional[str] = None,
    ) -> ThreadPost:
        """An `error` post for a turn that never produced an outcome at all.

        §6.7: "Går LLM-anropet inte fram alls (`LLMConnectionError`,
        `LLMRateLimitError`) blir det också ett `error`-inlägg. Tråden tappar
        aldrig en tur i tysthet."
        """
        return ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="error",
            actor=actor,
            body=_error_body(reason, retry_draft_id),
            run_id=run_id,
        )

    @staticmethod
    def record_user_message(thread: Thread, text: str, actor: str) -> ThreadPost:
        """The human's own reply, written before the agent has said anything
        (§6.1 step 2)."""
        return ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor=actor,
            body={"text": text},
        )

    @staticmethod
    def record_user_file(
        thread: Thread,
        *,
        filename: str,
        size_bytes: int,
        actor: str,
        pages: Optional[int] = None,
        intake_source_id: Optional[str] = None,
    ) -> ThreadPost:
        """`FilInlagg`'s body (§6.2): the file card's metadata and a
        reference, **never the content**.

        §6.2: "Base64 kommer aldrig in i ett inlägg." The bytes live in
        intake storage, where they already have a path, a hash and an audit
        trail; a second copy inside a thread post would have none of those.
        """
        return ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_file",
            actor=actor,
            body={
                "filename": filename,
                "size_bytes": size_bytes,
                "pages": pages,
                "intake_source_id": intake_source_id,
            },
        )

    @staticmethod
    def reset_context(thread: Thread, actor: str) -> Thread:
        """Reset the view's conversation (migration 034).

        Moves the thread's context boundary to its last `seq`, so the next
        turn's window starts empty. A boundary and not a deletion: posts are
        append-only (§8.2 p.4), decisions and drafts point at them, and the
        human can still read what was said -- the client folds it away above
        a divider. Audit-logged in the same transaction as the move, with the
        boundary before and after, so a reset is as traceable as a lock.
        """
        from_seq = ThreadRepository.last_seq(thread.id)
        now = datetime.now()
        with db.transaction():
            updated = ThreadRepository.reset_context(
                thread.id, from_seq, now, _commit=False
            )
            AuditRepository.log(
                entity_type="thread",
                entity_id=thread.id,
                action=AuditAction.CONTEXT_RESET.value,
                actor=actor,
                payload={
                    "view_key": thread.view_key,
                    "fiscal_year_id": thread.fiscal_year_id,
                    "context_from_seq_before": thread.context_from_seq,
                    "context_from_seq": from_seq,
                },
                _commit=False,
            )
        assert updated is not None  # the row was just updated
        return updated
