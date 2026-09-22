"""Decision lifecycle orchestration (SPEC-beslut.md §6.2, §4).

`DecisionService` is the API surface B4-B10 build on -- fixed once in
BRIEF.md §2 so later tasks don't each invent their own. This module
implements only the lifecycle B3 owns: `create`, `answer`, `count_open`,
`supersede`, plus the typed errors. The escalation invariant
(`validate_options`, B4), the three-source union (`list_decisions`/
`get_decision`, B7) and the seven-day reminder (`due_reminders`/
`mark_reminded`, B10) are deliberately not built here -- their names are
reserved in BRIEF.md §2 and their call sites are left as plain comments
below rather than implemented ahead of the task that owns them.

No `fastapi` import, no `HTTPException` (AGENTS.md's layering rule --
`api/routes/decisions.py`, B7/B8, maps these to status codes). Domain
errors are typed exceptions with the same ``{code, message, details}``
shape `PostingConflictError` (`services/agent_tools.py`) and `IntakeError`
(`services/intake.py`) already use, so a caller already branching on
`.code` doesn't need a second pattern for this module.

All SQL lives in `repositories/decision_repo.py` and
`repositories/thread_repo.py` -- nothing here executes a query directly.
"""

import uuid
from datetime import date, datetime
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from db.database import db
from domain.models import Decision, DecisionOption, Thread, ThreadPost
from domain.validation import ValidationError
from repositories.decision_repo import DecisionRepository
from repositories.thread_repo import ThreadRepository

#: What `DecisionRepository.add_options` already accepts -- reused here so
#: `create`'s `options` argument doesn't need a third shape of its own.
OptionInput = Union[DecisionOption, Mapping[str, Any]]


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class DecisionError(Exception):
    """Base for this module's domain errors.

    Same ``{code, message, details}`` shape as ``PostingConflictError``
    (`services/agent_tools.py`) and ``IntakeError`` (`services/intake.py`)
    -- one pattern for a caller to branch on across the whole backend, not
    a new one per module.
    """

    def __init__(self, code: str, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class DecisionNotFound(DecisionError):
    """No row in `decisions` has this id.

    B8 maps this to `404` (BRIEF.md §2). `answer()` raises it before
    touching anything else -- an unknown id never reaches the transaction.
    """

    def __init__(self, decision_id: str):
        super().__init__(
            "decision_not_found",
            f"No decision with id {decision_id}",
            details=f"decision_id={decision_id}",
        )
        self.decision_id = decision_id


class DecisionNotAnswerable(DecisionError):
    """A synthetic id (`intake:...` / `correction:...`, SPEC §5) that has no
    row in `decisions` -- B8's `409 decision_not_answerable`, pointing at
    the source's own existing path (`PUT /intake/{id}/agent-guidance` or
    `POST /vouchers/{id}/correction-notes/{note_id}/suggest`).

    Defined here per the brief; nothing in B3 raises it. `DecisionService`
    as built in B3 only ever looks a `decision_id` up in `decisions`
    directly (`DecisionRepository.get`), so it never sees a synthetic id --
    that only happens once B7's union exists and hands one to `answer()`.
    """

    def __init__(self, decision_id: str, existing_path: Optional[str] = None):
        super().__init__(
            "decision_not_answerable",
            f"Decision {decision_id} is not answerable through this module",
            details=existing_path,
        )
        self.decision_id = decision_id


class DecisionAlreadyAnswered(DecisionError):
    """A second answer to a decision that has already left `open` (SPEC
    §6.2 step 2: "Inte 400: klienten ska kunna visa klart-läget").

    Carries the whole `Decision` so a caller can show `answered_at`,
    `answer_post_id` and the answer that was given instead of just an
    error code.
    """

    def __init__(self, decision: Decision):
        super().__init__(
            "decision_already_answered",
            f"Decision {decision.id} was already answered at {decision.answered_at}",
            details=f"answer_post_id={decision.answer_post_id}",
        )
        self.decision = decision


# ---------------------------------------------------------------------------
# Post bodies
# ---------------------------------------------------------------------------


def _decision_post_body(
    decision_id: str,
    title: str,
    amount_ore: Optional[int],
    reason: str,
    source: Optional[Mapping[str, Any]],
    consequence: str,
) -> dict:
    """`BeslutKort`'s body -- the same key set `_decision_body`
    (`services/thread_service.py`) already produces for a registered
    abstention: `title`, `amount`, `reason`, `source`, `consequence`, plus
    the `decision_id` the card needs to be answerable.

    Without that key a `BeslutKort` rendered from
    `GET /threads/{view_key}` could only find its decision by fetching
    `GET /decisions` and joining on `post_id` -- the second call per card
    that §6.1 refuses for the same reason it puts `options` in the list
    response.

    `reason` and `consequence` are stored exactly as given -- no
    rewording, no truncation (SPEC §7.4, testfall 34; `_decision_body`'s
    own comment makes the same promise for the abstention path).
    """
    return {
        "decision_id": decision_id,
        "title": title,
        "amount": amount_ore,
        "reason": reason,
        "source": (
            {"kind": source.get("kind"), "id": source.get("id")} if source else None
        ),
        "consequence": consequence,
    }


def _options_post_body(
    decision_id: str, options: Sequence[DecisionOption], footnote: Optional[str]
) -> dict:
    """`AlternativLista`'s body, exactly the shape SPEC-beslut.md §4 gives:
    ``{"decision_id", "options": [...], "footnote"}``. `rationale` and
    `footnote` are the agent's own words, stored verbatim (SPEC §7.4).
    """
    return {
        "decision_id": decision_id,
        "options": [
            {
                "option_id": option.id,
                "title": option.title,
                "account": option.account,
                "amount_ore": option.amount_ore,
                "rationale": option.rationale,
                "recommended": option.recommended,
                "is_exit": option.is_exit,
            }
            for option in options
        ],
        "footnote": footnote,
    }


def _option_answer_text(option: DecisionOption) -> str:
    """SPEC §6.2 step 4: "alternativets titel och konto" -- the reply
    written into the thread when a decision is answered by picking an
    option. Matches the style already fixed by `tests/test_beslut.py`'s
    B2 fixtures (`"Förbrukningsinventarier, 5410."`).
    """
    if option.account:
        return f"{option.title}, {option.account}."
    return f"{option.title}."


def _split_source(
    source: Optional[Mapping[str, Any]],
) -> Tuple[Optional[str], Optional[str], Optional[date]]:
    """`decisions.source_kind` / `.source_id` / `.source_date` from the
    `source` argument's `kind` / `id` / `date` keys. `None` throughout when
    no source was given -- a decision raised mid-conversation has none
    (SPEC §2 antagande 5)."""
    if not source:
        return None, None, None
    return source.get("kind"), source.get("id"), source.get("date")


class DecisionService:
    """Orchestrates `decisions` / `decision_options` / thread posts.

    Every method here is a thin transaction wrapper around
    `DecisionRepository` and `ThreadRepository` -- no SQL (AGENTS.md's
    layering rule): all of it lives in `repositories/decision_repo.py` and
    `repositories/thread_repo.py`.
    """

    # -- B3: the lifecycle -------------------------------------------------

    def create(
        self,
        thread: Thread,
        *,
        title: str,
        reason: str,
        consequence: str,
        kind: str = "abstention",
        amount_ore: Optional[int] = None,
        source: Optional[Mapping[str, Any]] = None,
        options: Optional[Sequence[OptionInput]] = None,
        footnote: Optional[str] = None,
        actor: str = "agent",
        post: Optional[ThreadPost] = None,
        decision_id: Optional[str] = None,
    ) -> Decision:
        """Write a decision, and the post(s) that show it, in one transaction.

        Three writes, all with `_commit=False` inside a single
        `with db.transaction():` (AGENTS.md, BRIEF.md "kodbasens former"):

        1. a `decision` post in the thread, via `ThreadRepository.add_post`
           -- unless `post` is already given (B6's path: an already-written
           post is bound to a new row instead of a second post being
           written).
        2. a `decisions` row, via `DecisionRepository.create`, with
           `view_key` taken from `thread.view_key` (SPEC §2: the thread
           already knows its view; the column exists only so the list can
           filter without a join).
        3. when `options` is given: rows via `DecisionRepository.add_options`
           and an `options` post in the thread.

        **The id ordering.** Both posts carry `decision_id`, and the write
        order looks like it forbids that: `decisions.post_id` is a plain
        (non-deferred) foreign key into `thread_posts(id)`, so the
        `decision` post has to exist before the row does -- and a post is
        never rewritten afterwards (`SPEC-tradar.md` §8.4), so there is no
        patching the id in later. The id is therefore **minted here**,
        before either write, and handed to `DecisionRepository.create`.
        That is the whole reason that parameter exists. Letting the row
        mint its own id and leaving the card without one would push a
        second request and a join on `post_id` onto every `BeslutKort` the
        thread renders.

        When `post` is given (B6's path) the caller has already written a
        post carrying the same minted id, and no second post is written.

        `reason`, `consequence`, and each option's `rationale` are stored
        exactly as given -- no rewording, no truncation, no normalisation
        (SPEC §7.4, testfall 34).

        B4's escalation invariant (`validate_options`) is not enforced
        here -- this is its hook point, immediately before
        `DecisionRepository.add_options` is called below, once B4 exists.
        """
        # Minted before the transaction opens, so the `decision` post can
        # carry it and the row can be created with it -- see the docstring.
        # A caller that wrote the post itself (B6) passes the id it used.
        new_id = decision_id or str(uuid.uuid4())

        with db.transaction():
            decision_post = post
            if decision_post is None:
                decision_post = ThreadRepository.add_post(
                    thread_id=thread.id,
                    post_type="decision",
                    actor=actor,
                    body=_decision_post_body(
                        new_id, title, amount_ore, reason, source, consequence
                    ),
                    _commit=False,
                )

            source_kind, source_id, source_date = _split_source(source)
            decision = DecisionRepository.create(
                decision_id=new_id,
                thread_id=thread.id,
                post_id=decision_post.id,
                view_key=thread.view_key,
                kind=kind,
                title=title,
                reason=reason,
                consequence=consequence,
                amount_ore=amount_ore,
                source_kind=source_kind,
                source_id=source_id,
                source_date=source_date,
                _commit=False,
            )

            if options:
                # B4's escalation invariant goes here, before the write:
                # `self.validate_options(options, under_open_decision=...)`.
                created_options = DecisionRepository.add_options(
                    decision.id, options, _commit=False
                )
                decision.options = created_options
                ThreadRepository.add_post(
                    thread_id=thread.id,
                    post_type="options",
                    actor=actor,
                    body=_options_post_body(decision.id, created_options, footnote),
                    _commit=False,
                )

        return decision

    def answer(
        self,
        decision_id: str,
        *,
        option_id: Optional[str] = None,
        free_text: Optional[str] = None,
        actor: str,
    ) -> Tuple[Decision, ThreadPost]:
        """SPEC §6.2 steps 3-5: validate, write the reply, flip status.

        Exactly one of `option_id` / `free_text` is required -- both or
        neither is `ValidationError(code="invalid_answer")`, mapped to
        `400` by B8.

        Lookup and validation happen before any write: an unknown id is
        `DecisionNotFound`; a decision that has already left `open` is
        `DecisionAlreadyAnswered`, carrying the existing answer, so a
        second press never produces a second post -- the check runs
        *before* the transaction below, on a fresh read. `option_id` is
        checked against **this** decision's own options; an id from
        another decision is `ValidationError`, never a silent lookup that
        happens to match.

        Steps 4 and 5 of SPEC §6.2 -- the `user_text` post with the answer
        and the status change (`status='open' -> 'answered'`, plus the
        answer columns) -- happen in **one** `with db.transaction():`,
        each repository call with `_commit=False`. That is what makes a
        double answer structurally impossible: if the post and the status
        change were two separate transactions, two overlapping calls could
        each write their own post before either had managed to flip
        status, leaving two replies under one decision. Sharing a
        transaction means either both happen or neither does (testfall
        17: an error raised inside the `with` block, e.g. from
        `DecisionRepository.set_answer`, rolls back the post as well --
        proven by counting posts and re-reading status afterwards).

        The reply text is the option's title and account when `option_id`
        was given, or `free_text` **verbatim** when it was -- never
        reworded (SPEC §7.4).

        Never starts a turn. `ThreadTurnRunner.start(thread,
        trigger_post=answer_post, message=...)` is B8's job, called after
        this method returns and its transaction has already committed.

        No `Idempotency-Key` here (SPEC §11.4) -- `decisions.status` is
        already the one resource that can only move `open -> answered`
        once; the posting a turn may go on to make keeps the usual
        `thread:{thread_id}:{post_id}` key, derived from the answer post
        this method returns.
        """
        if (option_id is None) == (free_text is None):
            raise ValidationError(
                code="invalid_answer",
                message="Exactly one of option_id or free_text is required",
                details=f"option_id={option_id!r} free_text={free_text!r}",
            )

        decision = DecisionRepository.get(decision_id)
        if decision is None:
            raise DecisionNotFound(decision_id)

        if decision.status != "open":
            raise DecisionAlreadyAnswered(decision)

        if option_id is not None:
            option = next((o for o in decision.options if o.id == option_id), None)
            if option is None:
                raise ValidationError(
                    code="invalid_answer",
                    message=(
                        f"Option {option_id} does not belong to decision "
                        f"{decision_id}"
                    ),
                    details=f"decision_id={decision_id} option_id={option_id}",
                )
            reply_text = _option_answer_text(option)
        else:
            # The exactly-one-of check above guarantees `free_text` is set
            # here; this only narrows the type for mypy.
            assert free_text is not None
            reply_text = free_text

        with db.transaction():
            answer_post = ThreadRepository.add_post(
                thread_id=decision.thread_id,
                post_type="user_text",
                actor=actor,
                body={"text": reply_text},
                _commit=False,
            )
            updated = DecisionRepository.set_answer(
                decision_id,
                answered_at=datetime.now(),
                answered_by=actor,
                answer_post_id=answer_post.id,
                option_id=option_id,
                answer_text=free_text,
                _commit=False,
            )

        assert updated is not None  # the row was just read above; it exists
        return updated, answer_post

    def count_open(self) -> int:
        """`decisions` table's own `status='open'` count.

        B9 points `services/overview.py`'s `_count_open_decisions()` at
        this method once B7's union exists -- until then this is *only*
        the table's own count, not "the union's number of open decisions"
        BRIEF.md §2 describes for the final version. Switching
        `OverviewService` over is B9's job, not B3's.
        """
        return DecisionRepository.count_open()

    def supersede(self, decision_id: str) -> Decision:
        """`status='superseded'` -- out of the queue, post left untouched
        in the thread (SPEC §4: "lämnar kortet i tråden och tar bort det
        ur kön").

        Unknown id -> `DecisionNotFound`. *Who* calls this and *when* is
        an open question the SPEC leaves for `flode-verifikationer`
        (§12.2) -- B3 only provides the mechanism.
        """
        decision = DecisionRepository.get(decision_id)
        if decision is None:
            raise DecisionNotFound(decision_id)
        updated = DecisionRepository.set_status(decision_id, "superseded")
        assert updated is not None  # the row was just read above; it exists
        return updated
