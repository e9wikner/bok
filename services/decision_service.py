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


# ---------------------------------------------------------------------------
# B4: option-list validation helpers
# ---------------------------------------------------------------------------


def _option_field(item: OptionInput, name: str, *, default: Any = None) -> Any:
    """Read `name` off either a mapping or a `DecisionOption` -- the same
    dual-shape read `DecisionRepository._field` does, duplicated rather
    than imported: that helper is private to `repositories/decision_repo.py`
    (AGENTS.md's layering rule keeps SQL-side helpers there), and
    `validate_options` has to run on the raw `options` argument *before*
    any `decision_options` row -- and therefore no real `DecisionOption`
    with a settled `.account`/`.amount_ore` -- necessarily exists yet."""
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _option_changes_the_books(item: OptionInput) -> bool:
    """SPEC §6.3's predicate -- `account` set **and** `amount_ore != 0` --
    evaluated on a plain `OptionInput` instead of a `DecisionOption`.

    `DecisionOption.changes_the_books` (`domain/models.py`) is reused
    directly when `item` already is one; a dict gets the identical
    comparison via `_option_field`, so a caller that validates dicts (as
    `create()` does, since `add_options` accepts either shape) sees
    exactly the same rule the domain property documents, not a
    second definition that could drift from it."""
    if isinstance(item, DecisionOption):
        return item.changes_the_books
    account = _option_field(item, "account")
    amount_ore = _option_field(item, "amount_ore")
    return account is not None and amount_ore is not None and bool(amount_ore)


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

        A non-empty `options` is checked against `validate_options`
        (SPEC §6.3, §11.1) immediately before `DecisionRepository.add_options`
        runs below, inside this same transaction -- a broken list raises
        before either the options rows or the `options` post are written,
        so a rejected list leaves no partial trace (testfall 19, 23). An
        empty list skips the check entirely: there is nothing to have a
        `recommended` mark or an exit row in.
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
                # SPEC §11.1: the `decisions` row above always lands with
                # `status='open'` (DecisionRepository.create's column
                # default), so a list written here is always the "Flöde 1
                # steg 2" row of the table in validate_options's docstring
                # -- under_open_decision is derived from the row just
                # created, not hardcoded, so this call site keeps meaning
                # the same thing if that ever stops being true.
                self.validate_options(
                    options, under_open_decision=decision.status == "open"
                )
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

    # -- B4: the rules -------------------------------------------------

    def validate_options(
        self,
        options: Sequence[OptionInput],
        *,
        under_open_decision: bool,
    ) -> None:
        """The escalation invariant plus `AlternativLista`'s two contract
        rules (SPEC §6.3, §11.1) -- server rules, not client rules: a
        client that skipped them, or got them wrong, must not be able to
        put a bad list into `decision_options` by calling the API
        directly. `create()` is this module's only caller today, but the
        check lives here, independent of `create()`'s transaction, so B5's
        tool and any later caller ask the same question the same way.

        Called only for a non-empty `options` -- an empty list has no
        alternative to carry a `recommended` mark or an exit row, so
        `create()` never calls this for one (SPEC §6.3: "En tom lista
        valideras inte").

        Three rules, checked in this order:

        1. **The escalation invariant** (§11.1). If any option
           `changes_the_books` (`DecisionOption.changes_the_books` /
           `_option_changes_the_books`, SPEC §6.3: `account` set and
           `amount_ore != 0`) and this list is not `under_open_decision`,
           the whole list is rejected with
           `code="options_require_open_decision"`. This runs first
           because it answers a different question than the two rules
           below it -- not "is this list well-formed" but "is this list
           allowed to be an `options` list at all, or should it have been
           raised as a `decision` instead" (§11.1's forbidden case). A
           list that fails this check may also happen to have two
           `recommended` marks or no exit row, but the escalation error is
           the one that tells the agent what to do about it ("lägg fram
           beslutet först"), so it must not be shadowed by a shape error
           that leaves the caller trying to fix a list that should not
           exist in this form in the first place.
        2. **At most one `recommended`** (`komponenter.md`, via §6.3).
           `code="multiple_recommended_options"`. Zero is allowed --
           `recommended: true` is a mark, not a required pre-selection;
           `AlternativRad` renders an empty ring when none is set.
        3. **The last option has `is_exit`** (§6.3: "sista alternativet är
           alltid en väg ut"). `code="options_without_exit"`. Checked last
           because it is the cheapest, most purely structural of the
           three -- a single index lookup -- and because a list that is
           already wrong for either reason above does not need a second,
           unrelated complaint about its last row.

           SPEC §6.3 only asserts that the *last* option is a way out; it
           never says a way out may not also appear earlier (a list can
           reasonably offer more than one door -- e.g. "Annat konto" and,
           after it, "Det är inte alls detta köp"). This method therefore
           checks only `options[-1]`; `is_exit=True` on a non-last row is
           deliberately **not** an error.

        `under_open_decision`: true exactly when this `options` list sits
        under a `decision` whose status is (or is about to become, inside
        the same transaction) `open`. `create()` always passes
        `decision.status == "open"` -- true unconditionally there, since
        `DecisionRepository.create` always returns a fresh row with
        `status='open'` -- which is precisely SPEC §11.1's first table
        row: "Flöde 1 steg 2 -- 5410 mot 1250: öppet beslut ja, ändrar
        böckerna ja -> `options`, tillåtet". The parameter stays public,
        rather than this method hardcoding `True` for its only caller
        today, because a future caller may lay out options with no open
        decision behind them at all (flöde 4's "koppla utan att ändra" --
        SPEC §11.1's third row, `options` allowed precisely because
        nothing there changes the books) and needs to ask this rule
        without first writing anything to find out which world it is in.

        `options` items are `DecisionOption` or a mapping -- whatever
        `DecisionRepository.add_options` accepts (`OptionInput`) -- read
        through `_option_field` / `_option_changes_the_books` so both
        shapes are checked identically.

        An empty `options` never raises, under either value of
        `under_open_decision` -- there is no alternative to carry a
        `recommended` mark or an exit row, and nothing in it can change
        the books either. `create()` never calls this method for an
        empty list in the first place (see `create()`'s docstring), but
        the method itself stays a no-op for one rather than raising
        `IndexError` on rule 3's `options[-1]`, so a future caller that
        does ask does not need to special-case "empty" before calling.
        """
        if not options:
            return

        if any(_option_changes_the_books(option) for option in options):
            if not under_open_decision:
                raise ValidationError(
                    code="options_require_open_decision",
                    message=(
                        "An options list with an option that changes the "
                        "books must be laid out under an already-open "
                        "decision -- raise the decision first "
                        "(SPEC-beslut.md §11.1)."
                    ),
                    details=f"option_count={len(options)}",
                )

        recommended_count = sum(
            1
            for option in options
            if _option_field(option, "recommended", default=False)
        )
        if recommended_count > 1:
            raise ValidationError(
                code="multiple_recommended_options",
                message=(
                    "At most one option may be recommended, got " f"{recommended_count}"
                ),
                details=f"recommended_count={recommended_count}",
            )

        last_option = options[-1]
        if not _option_field(last_option, "is_exit", default=False):
            raise ValidationError(
                code="options_without_exit",
                message="The last option must be a way out (is_exit=True)",
                details=f"option_count={len(options)}",
            )
