"""Decision lifecycle orchestration (SPEC-beslut.md §6.2, §4).

`DecisionService` is the API surface B4-B10 build on -- fixed once in
BRIEF.md §2 so later tasks don't each invent their own. This module
implements the lifecycle B3 owns (`create`, `answer`, `count_open`,
`supersede`), the escalation invariant (`validate_options`, B4), and the
three-source union B7 owns (`list_decisions` / `get_decision`, SPEC §5,
§6.1, §11.2). `answer()` also carries B8's synthetic-id guard (SPEC §5,
§6.2 step 1) -- `api/routes/decisions.py::answer_decision` calls it and
maps its typed errors to status codes, then starts the turn itself once
the transaction inside `answer()` has committed; this module never
imports `ThreadTurnRunner` or starts one (§7.2's boundary: a decision
answer writes a post and stops, it does not itself drive a turn). The
seven-day reminder (`due_reminders` / `send_reminders` / `mark_reminded`,
B10, SPEC §6.5) lives at the bottom of the class: an open decision at
least `REMINDER_THRESHOLD_DAYS` old that has never been reminded gets one
`agent_text` post in its own thread and `reminded_at` set, once, per
decision -- never from a schedule of its own. `services/agent_runtime.py`
calls `DecisionService().send_reminders()` once per intake pass (SPEC
§6.5: "Kontrollen sker i intagspassets befintliga cykel").

No `fastapi` import, no `HTTPException` (AGENTS.md's layering rule --
`api/routes/decisions.py` maps these to status codes). Domain errors are
typed exceptions with the same ``{code, message, details}`` shape
`PostingConflictError` (`services/agent_tools.py`) and `IntakeError`
(`services/intake.py`) already use, so a caller already branching on
`.code` doesn't need a second pattern for this module.

All SQL lives in `repositories/decision_repo.py`, `repositories/thread_repo.py`,
`repositories/intake_repo.py`, `repositories/correction_note_repo.py` and
(for `count_waiting`) `repositories/thread_draft_repo.py` -- nothing here
executes a query directly.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from db.database import db
from domain.models import (
    CorrectionNote,
    Decision,
    DecisionOption,
    IntakeProcessingAttempt,
    IntakeSource,
    Thread,
    ThreadPost,
)
from domain.types import ThreadViewKey
from domain.validation import ValidationError
from repositories.correction_note_repo import CorrectionNoteRepository
from repositories.decision_repo import DecisionRepository
from repositories.intake_repo import IntakeRepository
from repositories.thread_draft_repo import ThreadDraftRepository
from repositories.thread_repo import ThreadRepository

logger = logging.getLogger(__name__)

#: What `DecisionRepository.add_options` already accepts -- reused here so
#: `create`'s `options` argument doesn't need a third shape of its own.
OptionInput = Union[DecisionOption, Mapping[str, Any]]


# ---------------------------------------------------------------------------
# B7: the union of the three sources (SPEC §5, §6.1, §11.2)
# ---------------------------------------------------------------------------

#: The two synthetic sources' own "open" statuses (SPEC §5's table). Neither
#: has an `answered` counterpart in this module -- `list_decisions`'s
#: docstring says what that means for `status=answered` / `status=all`.
_INTAKE_OPEN_STATUSES: Tuple[str, ...] = ("failed", "needs_attention")
_CORRECTION_OPEN_STATUSES: Tuple[str, ...] = ("pending", "suggested")

_INTAKE_PREFIX = "intake:"
_CORRECTION_PREFIX = "correction:"

#: There is no `underlag` view among the seven `ThreadViewKey`s
#: (SPEC-tradar.md §5). Both synthetic sources are pinned to
#: `bocker.verifikationer` -- the view where vouchers and the material
#: behind them live -- rather than inventing an eighth view for two sources
#: that are meant to be temporary in the first place (SPEC §11.2: "Unionen
#: är övergående").
_SYNTHETIC_VIEW_KEY = ThreadViewKey.BOCKER_VERIFIKATIONER.value

#: `intake_sources` / `intake_processing_attempts` has nothing that plays
#: the role `decisions.consequence` plays for an abstention -- unlike
#: `reason` (SPEC §5: the agent's own words from the latest attempt), there
#: is no agent-authored consequence text to draw on here. This is system
#: wording, said plainly, not invented text passed off as the agent's own.
_INTAKE_CONSEQUENCE = (
    "Inget är bokfört från det här underlaget förrän felet är åtgärdat eller "
    "ny vägledning ges."
)

#: Same reasoning as `_INTAKE_CONSEQUENCE`: `correction_notes` carries no
#: consequence text of its own either.
_CORRECTION_CONSEQUENCE = (
    "Rättelsen är inte tillämpad förrän ett beslut tas om noteringen."
)

#: Testfall 8 forbids one specific stand-in (the filename) for a missing
#: agent reason; it does not forbid being honest that there is no attempt
#: at all. Whatever this says, it is not the agent's text -- there is none
#: yet -- so it must not read as if it were.
_INTAKE_NO_ATTEMPT_REASON = (
    "Inget bearbetningsförsök är registrerat för det här underlaget ännu."
)


@dataclass
class DecisionSource:
    """`source` in the §6.1 response shape -- what grounds the decision,
    when there is one. `None` is legitimate (an abstention raised
    mid-conversation has none, SPEC §2 antagande 5)."""

    kind: str
    id: str
    date: Optional[date]


@dataclass
class DecisionView:
    """One row of `GET /decisions`'s union (SPEC §5, §6.1) -- a response
    shape spanning three sources, not a domain thing in its own right,
    which is why it lives here and not in `domain/models.py` next to
    `Decision`.

    Fields are exactly SPEC §6.1's JSON sample, plus `created_at`: the
    union's own sort key ("Äldst först" over *all three* sources at once,
    not per source) -- `api/schemas.py`'s `DecisionResponse` leaves it out
    of what actually goes over the wire.
    """

    id: str
    view_key: str
    kind: str
    status: str
    title: str
    amount_ore: Optional[int]
    reason: str
    consequence: str
    source: Optional[DecisionSource]
    age_days: int
    thread_id: Optional[str]
    post_id: Optional[str]
    options: List[DecisionOption]
    created_at: datetime
    # How it was answered, when it was (chattyta open question 3). `None`
    # for an open or superseded decision, and always for the two synthetic
    # sources -- they are never answered through this module (SPEC §11.2).
    answered_at: Optional[datetime] = None
    answered_by: Optional[str] = None
    answer_option_id: Optional[str] = None
    answer_text: Optional[str] = None


def _age_days(created_at: datetime, today: Optional[date]) -> int:
    """Same rule as `Decision.age_days` (`domain/models.py`), for the two
    sources that have no domain object of their own to hang the method on.
    Counted here, never in SQL (AGENTS.md, BRIEF.md)."""
    as_of = today if today is not None else date.today()
    return max((as_of - created_at.date()).days, 0)


def _decision_to_view(decision: Decision, *, today: Optional[date]) -> DecisionView:
    """SPEC §5's `abstention` row: a straight read of `decisions`, `reason`
    verbatim as the agent wrote it."""
    source = None
    if decision.source_kind is not None and decision.source_id is not None:
        source = DecisionSource(
            kind=decision.source_kind,
            id=decision.source_id,
            date=decision.source_date,
        )
    return DecisionView(
        id=decision.id,
        view_key=decision.view_key,
        kind=decision.kind,
        status=decision.status,
        title=decision.title,
        amount_ore=decision.amount_ore,
        reason=decision.reason,
        consequence=decision.consequence,
        source=source,
        age_days=decision.age_days(today),
        thread_id=decision.thread_id,
        post_id=decision.post_id,
        options=list(decision.options),
        created_at=decision.created_at,
        answered_at=decision.answered_at,
        answered_by=decision.answered_by,
        answer_option_id=decision.answer_option_id,
        answer_text=decision.answer_text,
    )


def _intake_reason(attempt: Optional[IntakeProcessingAttempt]) -> str:
    """SPEC §5, testfall 8: the agent's own text from the **latest**
    attempt -- `error_detail` when that attempt recorded one (the sharper,
    specific explanation `IntakeService.record_failed` requires for a
    failed attempt), else `summary`. Never the filename.

    "Latest" is found by the caller (`IntakeRepository.list_latest_attempts`
    / `.list_attempts_for_source`, whichever it used) -- this only picks
    which of the two text fields on that one attempt to surface.

    No attempt at all is not backfilled with an invented reason --
    `_INTAKE_NO_ATTEMPT_REASON` says plainly that none exists rather than
    manufacturing agent-sounding text for words the agent never wrote.
    """
    if attempt is None:
        return _INTAKE_NO_ATTEMPT_REASON
    return attempt.error_detail or attempt.summary


def _intake_to_view(
    source: IntakeSource,
    latest_attempt: Optional[IntakeProcessingAttempt],
    *,
    today: Optional[date],
) -> DecisionView:
    """SPEC §5's `intake` row. `title` is the filename -- identification,
    not a formulation -- while `reason` is the agent's own text; testfall 8
    is precisely about not blurring those two."""
    return DecisionView(
        id=f"{_INTAKE_PREFIX}{source.id}",
        view_key=_SYNTHETIC_VIEW_KEY,
        kind="intake",
        status="open",
        title=source.original_filename,
        amount_ore=None,
        reason=_intake_reason(latest_attempt),
        consequence=_INTAKE_CONSEQUENCE,
        source=DecisionSource(
            kind="intake_source", id=source.id, date=source.uploaded_at.date()
        ),
        age_days=_age_days(source.uploaded_at, today),
        thread_id=None,
        post_id=None,
        options=[],
        created_at=source.uploaded_at,
    )


def _correction_to_view(note: CorrectionNote, *, today: Optional[date]) -> DecisionView:
    """SPEC §5's `correction` row -- the one source whose text is **not**
    the agent's. `reason` is set to `note.note_text` anyway, because that
    is the only text this source has; `kind="correction"` is what tells a
    reader not to mistake it for the agent's own formulation (§11.2: "hela
    priset" of the union is exactly this -- a card that carries the
    human's words under the same `reason` key an agent's words sit under
    everywhere else in this endpoint).

    `title` names the voucher rather than repeating `note_text`, so the
    list view has something short to show before the human's own text.
    """
    return DecisionView(
        id=f"{_CORRECTION_PREFIX}{note.id}",
        view_key=_SYNTHETIC_VIEW_KEY,
        kind="correction",
        status="open",
        title=f"Korrigeringsnotering, verifikation {note.voucher_id}",
        amount_ore=None,
        reason=note.note_text,
        consequence=_CORRECTION_CONSEQUENCE,
        source=DecisionSource(
            kind="voucher", id=note.voucher_id, date=note.created_at.date()
        ),
        age_days=_age_days(note.created_at, today),
        thread_id=None,
        post_id=None,
        options=[],
        created_at=note.created_at,
    )


def _decode_synthetic_id(decision_id: str) -> Optional[Tuple[str, str]]:
    """`(source_kind, raw_id)` for a prefixed id, `None` for a plain one --
    SPEC §5's `intake:{id}` / `correction:{id}` / raw `decisions.id`
    (testfall 7: "prefixade id:n som inte kolliderar")."""
    if decision_id.startswith(_INTAKE_PREFIX):
        return "intake", decision_id[len(_INTAKE_PREFIX) :]
    if decision_id.startswith(_CORRECTION_PREFIX):
        return "correction", decision_id[len(_CORRECTION_PREFIX) :]
    return None


def _existing_path_for_synthetic_source(source_kind: str, raw_id: str) -> str:
    """SPEC §5: where a synthetic-id answer is pointed instead of
    `POST /decisions/{id}/answer` -- `PUT /intake/{id}/agent-guidance` for
    an `intake:` id. For a `correction:` id it is no path but the chat
    (SPEC-flode-verifikationer §7.3, F12): the answer to a note is a posted
    correction, proposed in Verifikationer's thread with `correction_of`
    and `correction_note_id`, not a click.

    The voucher id the second form needs is looked up on
    `correction_notes` -- a different table from the `decisions` lookup
    SPEC §6.2 / testfall 16 forbids running before this check, so reading
    it here does not fall into that trap (B7's final report is what names
    it: check the prefix *before* `DecisionRepository.get`, not after).
    A `note_id` that resolves to no row still gets a path -- the prefix
    alone is what makes an id unanswerable here, not whether the source
    row happens to still exist (SPEC §5 draws no such distinction).
    """
    if source_kind == "intake":
        return f"PUT /intake/{raw_id}/agent-guidance"
    note = CorrectionNoteRepository.get(raw_id)
    voucher_id = note.voucher_id if note is not None else raw_id
    return (
        "Svaret på en korrigeringsnotering är en postad rättelse: skriv i "
        f"Verifikationers chatt (view_key={_SYNTHETIC_VIEW_KEY}), där agenten "
        f"föreslår rättelsen med correction_of={voucher_id}, "
        f"correction_note_id={raw_id}"
    )


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
    the source's own existing path (`PUT /intake/{id}/agent-guidance`) or,
    for a correction note, at Verifikationer's chat (F12).

    Defined here per the brief; B3 never raised it -- `answer()` as B3 left
    it only ever looked a `decision_id` up in `decisions` directly
    (`DecisionRepository.get`), so it never saw a synthetic id. B8 is what
    raises it: `answer()` now decodes the prefix (`_decode_synthetic_id`)
    and raises this *before* that `decisions` lookup runs at all (SPEC
    §6.2, testfall 16) -- checking after would answer `404` instead, since
    a prefixed string is never a real `decisions.id`.
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


# ---------------------------------------------------------------------------
# B10: the seven-day reminder (SPEC §6.5)
# ---------------------------------------------------------------------------

#: Flöde 1 steg 1: "Ett beslut som legat mer än sju dagar påminner agenten
#: om en gång, inte varje körning." A named constant, not a bare `7` in a
#: comparison, so the sentence it comes from stays attached to it.
REMINDER_THRESHOLD_DAYS = 7


def _reminder_text(decision: Decision, age_days: int) -> str:
    """SPEC §6.5's tone (flöde 4 steg 1): "Mycket gamla kompletteringar hör
    hemma i en påminnelse, inte i samma neutrala ton som färska." Names the
    decision's own title and how long it has sat, and says plainly what has
    *not* happened -- the same "ingenting är bokfört" stance
    `_INTAKE_CONSEQUENCE` above already takes for a source with no agent
    text of its own.

    Deliberately does **not** restate `decision.reason` in different words:
    the `decision` post one row above this one in the same thread already
    carries the agent's own formulation verbatim (SPEC §7.4, testfall 34),
    and a paraphrase here would be exactly the rewording that rule
    forbids. This reminder points at the decision; it does not speak for
    it. Kept in its own function so the wording is readable -- and
    changeable -- in one place.
    """
    return (
        f'Påminnelse: beslutet "{decision.title}" har legat obesvarat i '
        f"{age_days} dagar. Ingenting är bokfört och beslutet ligger kvar."
    )


def _reminder_post_body(decision: Decision, age_days: int) -> dict:
    """`agent_text`'s body is ordinarily just `{"text": ...}`
    (`services/thread_service.py::_render`'s `"answered"` branch). This adds
    `decision_id` alongside `text` so a client can associate the post with
    the decision it reminds about directly, the same reasoning
    `_decision_post_body`'s docstring gives for carrying `decision_id` on
    the `decision` post itself -- without it, matching a reminder to its
    decision would need a second `GET /decisions` call and a join on
    `post_id` for every reminder a thread ever shows.
    """
    return {
        "text": _reminder_text(decision, age_days),
        "decision_id": decision.id,
    }


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

        Lookup and validation happen before any write: a synthetic id
        (`intake:...` / `correction:...`, SPEC §5) is `DecisionNotAnswerable`
        -- decoded and raised **before** `DecisionRepository.get` runs,
        because that repository only ever looks inside `decisions`, and a
        prefixed string is never a row id there. Checking the other way
        round -- look up first, decode on a miss -- would answer `404` for
        a synthetic id instead of the `409` SPEC §6.2 / testfall 16 ask
        for; B7's final report names this exact trap. An unknown *plain*
        id is `DecisionNotFound`; a decision that has already left `open`
        is `DecisionAlreadyAnswered`, carrying the existing answer, so a
        second press never produces a second post -- that check also runs
        *before* the transaction below, on the same fresh read. `option_id`
        is checked against **this** decision's own options; an id from
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

        decoded = _decode_synthetic_id(decision_id)
        if decoded is not None:
            source_kind, raw_id = decoded
            raise DecisionNotAnswerable(
                decision_id,
                existing_path=_existing_path_for_synthetic_source(source_kind, raw_id),
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
        """How many open decisions there are, across **all three** sources
        (SPEC §6.6, §11.2) -- the number `GET /overview`'s `open_decisions`
        shows.

        Deliberately the same three sources, with the same status sets, as
        `list_decisions(status="open")`, so the header's number and the
        list a human opens from it can never disagree. A test asserts that
        equality directly rather than trusting these two to be kept in
        step by hand.

        This is also why the number does not jump the day the module is
        deployed (§11.2, testfall 33): `services/overview.py`'s old
        approximation summed exactly the two synthetic sources below, and
        `decisions` is empty until something writes to it -- so the first
        reading through here equals the last reading through the
        approximation, and grows from there.

        Counted, not listed: `list_decisions` builds a `DecisionView` per
        row and sorts the union to answer a different question. A header
        counter has no use for any of that.
        """
        return (
            DecisionRepository.count_open()
            + sum(
                IntakeRepository.count_by_status(status)
                for status in _INTAKE_OPEN_STATUSES
            )
            + CorrectionNoteRepository.count_open()
        )

    def count_waiting(self, view_key: Optional[str] = None) -> int:
        """Everything that waits on the human, each thing once
        (SPEC-flode-verifikationer.md §11.3) -- the number `GET /overview`'s
        `open_decisions`, the view header and the receipt's `{n} kvar` chip
        all read.

        The rule:

        1. Every open decision `count_open` would count, filtered the way
           `list_decisions(status="open", view_key=...)` filters: `decisions`
           with `status='open'` in the view (every view when `view_key` is
           `None`), plus the two synthetic sources (`intake:`,
           `correction:`) when `view_key` is `None` or the view they are
           pinned to (`_SYNTHETIC_VIEW_KEY`).
        2. Plus every `thread_drafts` row with `status='pending'` in the
           view, **except** one whose `decision_id` is an open decision
           counted in 1, or whose `correction_note_id` is an open correction
           note counted in 1: that thing already waits, once.
        3. The drafts left over count once per `decision_id` (an answered
           or superseded decision with a pending proposal is one thing
           waiting, however many pending drafts point at it), once per
           `correction_note_id`, and one each when they answer neither -- a
           plain proposal, or a correction (`correction_of` set) with no
           decision behind it.

        So an open decision with a pending proposal counts once, via the
        decision; an answered decision with a superseded and a pending
        proposal counts once, via the pending one; a posted or superseded
        proposal never counts. With no thread drafts at all this is exactly
        `count_open()` (for `view_key=None`), which is why the switch in
        `services/overview.py` moved no number the day it was made.

        Counted, not listed, like `count_open`: three counts and one
        statement over `thread_drafts` (`ThreadDraftRepository.
        count_pending_not_yet_counted`), not a list per source.
        """
        include_synthetic = view_key is None or view_key == _SYNTHETIC_VIEW_KEY
        waiting = DecisionRepository.count(status="open", view_key=view_key)
        if include_synthetic:
            waiting += sum(
                IntakeRepository.count_by_status(status)
                for status in _INTAKE_OPEN_STATUSES
            )
            waiting += CorrectionNoteRepository.count_open()
        return waiting + ThreadDraftRepository.count_pending_not_yet_counted(
            view_key=view_key,
            open_note_statuses=_CORRECTION_OPEN_STATUSES,
            notes_counted=include_synthetic,
        )

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

    # -- B7: the union of the three sources (SPEC §5, §6.1, §11.2) --------

    def list_decisions(
        self,
        *,
        status: str = "open",
        view_key: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        today: Optional[date] = None,
    ) -> Tuple[List[DecisionView], int]:
        """SPEC §6.1: the union of `decisions`, `intake_sources`
        (`failed`/`needs_attention`) and `correction_notes`
        (`pending`/`suggested`), oldest first **over the whole union** --
        Flöde 1 steg 1: "en i taget i tråden, äldst först".

        `status` is `"open"` (default), `"answered"` or `"all"`; anything
        else is `ValidationError(code="unknown_status")`, which
        `api/routes/decisions.py` maps to `400` the same way it already
        maps every other `ValidationError` (see `services/agent_tools.py`'s
        route, `api/routes/agent.py`).

        The two synthetic sources have no `answered` counterpart -- SPEC
        §5's table lists no such column for them, and there is no path in
        this module that could set one (§5: "läsbara men inte besvarbara").
        They are therefore **always `open`**, and:

        - `status="open"`: `decisions` filtered to `status='open'`, plus
          both synthetic sources.
        - `status="answered"`: `decisions` filtered to `status='answered'`
          **only** -- the synthetic rows fall out entirely, since neither
          has ever been anything but open.
        - `status="all"`: no status filter on `decisions` at all, so this
          is the one value that also surfaces `superseded` rows -- a
          deliberate reading of "all" (every status the table has), not an
          omission -- plus both synthetic sources.

        `view_key` filters `decisions` normally. The synthetic sources are
        pinned to `_SYNTHETIC_VIEW_KEY` (`bocker.verifikationer`), so they
        are included only when `view_key` is `None` or exactly that value.
        The caller (the route) validates `view_key` against the closed list
        of seven before this is ever reached, so an invalid key never
        arrives here.

        **Pagination is over the sorted union, not per source.** Each
        source is fetched in full -- `DecisionRepository.list_decisions`
        with no `limit`/`offset`, and `IntakeRepository.list_by_statuses` /
        `CorrectionNoteRepository.list_by_statuses`, which are unbounded by
        design (see their docstrings) -- converted to `DecisionView`,
        concatenated, sorted by `(created_at, id)`, and only *then* sliced
        by `[offset : offset + limit]`. A per-source `LIMIT` would answer a
        different question ("the oldest `limit` rows from each source") and
        silently produce a wrong page the moment two sources are both
        non-empty. `total` is `len(...)` of the merged, sorted list before
        slicing -- the union's true count, independent of `limit`.

        Avoiding N+1 on `intake` rows' latest attempt:
        `IntakeRepository.list_latest_attempts` fetches every matching
        source's newest attempt in a single query (a `ROW_NUMBER()` window
        function keyed by `intake_source_id`), called once per
        `list_decisions` call -- not once per intake row, which is what a
        loop calling `list_attempts_for_source` per source would do.
        """
        if status not in ("open", "answered", "all"):
            raise ValidationError(
                code="unknown_status",
                message=f"Unknown status: {status!r}",
                details="expected one of: open, answered, all",
            )

        decision_status: Optional[str] = None if status == "all" else status
        decisions = DecisionRepository.list_decisions(
            status=decision_status, view_key=view_key
        )
        views: List[DecisionView] = [
            _decision_to_view(decision, today=today) for decision in decisions
        ]

        # The synthetic sources are always "open" (see docstring above), so
        # they only ever belong in the union when the caller did not ask
        # for "answered" alone, and only under the one view they are
        # pinned to.
        include_synthetic = status != "answered" and (
            view_key is None or view_key == _SYNTHETIC_VIEW_KEY
        )
        if include_synthetic:
            sources = IntakeRepository.list_by_statuses(_INTAKE_OPEN_STATUSES)
            latest_attempts: Dict[str, IntakeProcessingAttempt] = (
                IntakeRepository.list_latest_attempts([source.id for source in sources])
            )
            views.extend(
                _intake_to_view(source, latest_attempts.get(source.id), today=today)
                for source in sources
            )

            notes = CorrectionNoteRepository.list_by_statuses(_CORRECTION_OPEN_STATUSES)
            views.extend(_correction_to_view(note, today=today) for note in notes)

        views.sort(key=lambda view: (view.created_at, view.id))
        total = len(views)
        return views[offset : offset + limit], total

    def get_decision(
        self, decision_id: str, *, today: Optional[date] = None
    ) -> Optional[DecisionView]:
        """One row of the same union `list_decisions` returns, looked up by
        its (possibly prefixed) id -- SPEC §5.

        A synthetic id decodes to `(kind, raw_id)` via
        `_decode_synthetic_id` and is looked up in its own source; a plain
        id is looked up in `decisions` directly. A synthetic source whose
        status has since moved on (an intake source reprocessed, a
        correction note applied or dismissed) is no longer a decision in
        this module's sense the moment it leaves `_INTAKE_OPEN_STATUSES` /
        `_CORRECTION_OPEN_STATUSES` -- this returns `None` for it, exactly
        like an id nothing was ever written under. `api/routes/decisions.py`
        maps both to `404` without needing to tell them apart.
        """
        decoded = _decode_synthetic_id(decision_id)
        if decoded is not None:
            source_kind, raw_id = decoded
            if source_kind == "intake":
                source = IntakeRepository.get_source(raw_id)
                if source is None or source.status.value not in _INTAKE_OPEN_STATUSES:
                    return None
                # A single decision's own attempts -- not the batched
                # `list_latest_attempts` above, which exists to avoid an
                # N+1 across a *list* of sources. One lookup for one row
                # is not the waterfall that method guards against.
                attempts = IntakeRepository.list_attempts_for_source(raw_id)
                latest = attempts[-1] if attempts else None
                return _intake_to_view(source, latest, today=today)

            note = CorrectionNoteRepository.get(raw_id)
            if note is None or note.status not in _CORRECTION_OPEN_STATUSES:
                return None
            return _correction_to_view(note, today=today)

        decision = DecisionRepository.get(decision_id)
        if decision is None:
            return None
        return _decision_to_view(decision, today=today)

    # -- B10: the seven-day reminder (SPEC §6.5) ---------------------------

    def due_reminders(
        self, *, today: Optional[date] = None, limit: Optional[int] = None
    ) -> List[Decision]:
        """Open decisions with `age_days(today) >= REMINDER_THRESHOLD_DAYS`
        and `reminded_at IS NULL`, oldest first (SPEC §6.5, testfall 31).

        `Decision.age_days` (`domain/models.py`) counts whole calendar days
        from `created_at.date()`, ignoring the time of day `created_at`
        happens to carry -- and per AGENTS.md / BRIEF.md that counting
        never happens in SQL. `DecisionRepository.list_due_reminders`
        still needs a single `before` cutoff to filter with (a plain
        `created_at <= before`), so the cutoff passed here is the *last*
        instant of `today - REMINDER_THRESHOLD_DAYS days`
        (`datetime.combine(..., time.max)`), not its first: a decision
        created at, say, 14:00 on the day exactly seven days ago must
        still be due today, and a midnight cutoff would wrongly skip it
        until the next pass. This is arithmetic on the cutoff date, not a
        second copy of `age_days`'s rule -- the rule itself stays the one
        place that decides "how many days", in the domain.

        `today` defaults to `date.today()`, exactly like `list_decisions`'s
        own `today` parameter -- a caller (a test, or `send_reminders`
        below) pins it for a deterministic boundary.
        """
        as_of = today if today is not None else date.today()
        threshold_date = as_of - timedelta(days=REMINDER_THRESHOLD_DAYS)
        before = datetime.combine(threshold_date, time.max)
        return DecisionRepository.list_due_reminders(before=before, limit=limit)

    def send_reminders(
        self, *, today: Optional[date] = None, actor: str = "agent"
    ) -> List[Decision]:
        """Write the seven-day reminder for every decision `due_reminders`
        returns, and set `reminded_at` on each one (SPEC §6.5, testfall
        31). Called once per intake pass by
        `services.agent_runtime.AgentWorker.run_pass_once`, regardless of
        whether that pass has any intake items to process.

        **One `with db.transaction():` per decision**, not one for the
        whole batch: the reminder post and `reminded_at` belong together
        -- a half failure that wrote the post but left `reminded_at` NULL
        would remind again on the very next pass, exactly the repeat SPEC
        §6.5 forbids ("Utan kolumnen påminner varje körning"). Batching
        every decision into a single transaction would also mean one
        decision's failure rolls back reminders that had already
        succeeded for the others, which is its own version of the same
        problem in reverse.

        A decision whose write raises (a broken thread, a database error)
        is logged and skipped; the loop moves on to the rest. One
        beslut that could not be reminded about is not a reason to stop
        reminding, or bookkeeping, about any other (this method's own
        docstring promise, and the reason `AgentWorker.run_pass_once`
        below is allowed to wrap the whole call in one more try/except of
        its own -- that outer guard is for a wholly unexpected failure in
        this method itself, not a substitute for the per-decision handling
        here).

        Returns the decisions that were actually reminded, oldest first,
        in `due_reminders`' own order -- a decision that raised is left
        out entirely rather than included with some placeholder state.
        """
        as_of = today if today is not None else date.today()
        reminded: List[Decision] = []
        for decision in self.due_reminders(today=as_of):
            try:
                with db.transaction():
                    ThreadRepository.add_post(
                        thread_id=decision.thread_id,
                        post_type="agent_text",
                        actor=actor,
                        body=_reminder_post_body(decision, decision.age_days(as_of)),
                        _commit=False,
                    )
                    DecisionRepository.set_reminded(
                        decision.id, datetime.now(), _commit=False
                    )
            except Exception:
                logger.exception(
                    "Could not send the seven-day reminder for decision "
                    "%s -- continuing with the rest (SPEC §6.5)",
                    decision.id,
                )
                continue
            reminded.append(decision)
        return reminded

    def mark_reminded(self, decision_id: str) -> None:
        """A standalone `reminded_at` setter, kept for BRIEF.md §2's fixed
        `DecisionService` surface.

        `send_reminders` above never calls this -- it sets `reminded_at`
        itself, inside the same transaction as the reminder post, for the
        reason its own docstring gives. This exists as a thin wrapper
        around `DecisionRepository.set_reminded` for a caller that only
        needs to silence a decision without writing a post alongside it.
        """
        DecisionRepository.set_reminded(decision_id, datetime.now())
