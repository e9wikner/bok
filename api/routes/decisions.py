"""API routes for the union of the three decision sources (SPEC-beslut.md
§5, §6.1) and for answering one (§6.2, B8).

HTTP only, per AGENTS.md's layering rule: parse, authenticate, validate
`view_key` against the closed list of seven, map domain errors to status
codes, and -- for `answer_decision` -- start the turn after
`DecisionService.answer()`'s own transaction has committed. Everything
else -- the union itself, the synthetic-id prefixes, the lifecycle -- lives
entirely in `services/decision_service.py`; nothing here decodes an
`intake:`/`correction:` id or touches `decisions`/`decision_options`/
`intake_sources`/`correction_notes` directly.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from api.deps import get_current_actor
from api.schemas import (
    DecisionAnswerRequest,
    DecisionAnswerResponse,
    DecisionListResponse,
    DecisionOptionResponse,
    DecisionResponse,
    DecisionSourceResponse,
)
from config import settings
from domain.models import DecisionOption
from domain.types import ThreadViewKey
from domain.validation import ValidationError
from repositories.thread_repo import ThreadRepository
from services.decision_service import (
    DecisionAlreadyAnswered,
    DecisionNotAnswerable,
    DecisionNotFound,
    DecisionService,
    DecisionView,
)
from services.thread_stream import ThreadTurnRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


def _validate_view_key(view_key: str) -> str:
    """Same rule, same error shape, as
    `api/routes/threads.py::_validate_view_key` (SPEC-tradar.md §5): an
    unknown key is `404`, not an empty result -- otherwise a typo in a
    client would silently ask for a view whose backlog it can never find.

    Not imported from `threads.py`: that helper is private to its own
    module, and duplicating four lines here keeps this router's HTTP
    parsing self-contained rather than reaching into another route module
    for it. The behaviour is identical on purpose (testfall 9).
    """
    try:
        return ThreadViewKey(view_key).value
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Unknown view_key: {view_key!r}",
                "code": "unknown_view_key",
                "details": "known views: "
                + ", ".join(key.value for key in ThreadViewKey),
            },
        )


def _option_response(option: DecisionOption) -> DecisionOptionResponse:
    return DecisionOptionResponse(
        id=option.id,
        position=option.position,
        title=option.title,
        rationale=option.rationale,
        account=option.account,
        amount_ore=option.amount_ore,
        recommended=option.recommended,
        is_exit=option.is_exit,
    )


def _decision_response(view: DecisionView) -> DecisionResponse:
    return DecisionResponse(
        id=view.id,
        view_key=view.view_key,
        kind=view.kind,
        status=view.status,
        title=view.title,
        amount_ore=view.amount_ore,
        reason=view.reason,
        consequence=view.consequence,
        source=(
            DecisionSourceResponse(
                kind=view.source.kind, id=view.source.id, date=view.source.date
            )
            if view.source is not None
            else None
        ),
        age_days=view.age_days,
        thread_id=view.thread_id,
        post_id=view.post_id,
        options=[_option_response(option) for option in view.options],
        answered_at=view.answered_at,
        answered_by=view.answered_by,
        answer_option_id=view.answer_option_id,
        answer_text=view.answer_text,
    )


@router.get("", response_model=DecisionListResponse)
async def list_decisions(
    status: str = Query(
        "open",
        description="`open` (default), `answered` or `all` -- unknown value is 400.",
    ),
    view_key: Optional[str] = Query(
        None,
        description="Filter to one of the seven views; unknown key is 404.",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor: str = Depends(get_current_actor),
):
    """`GET /decisions` -- the union of the three sources (SPEC §5, §6.1),
    oldest first **over the whole union**. `limit`/`offset` page the
    sorted union, not each source separately -- see
    `DecisionService.list_decisions`'s docstring for why a per-source
    `LIMIT` would silently produce a wrong page.
    """
    validated_view_key = _validate_view_key(view_key) if view_key is not None else None

    try:
        views, total = DecisionService().list_decisions(
            status=status, view_key=validated_view_key, limit=limit, offset=offset
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.message, "code": exc.code, "details": exc.details},
        )

    return DecisionListResponse(
        decisions=[_decision_response(view) for view in views], total=total
    )


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: str,
    actor: str = Depends(get_current_actor),
):
    """`GET /decisions/{id}` -- one row of the same union, looked up by its
    (possibly prefixed) id. Unknown id, or a synthetic id whose source has
    since moved on (reprocessed, applied, dismissed), is `404` (SPEC §5).
    """
    view = DecisionService().get_decision(decision_id)
    if view is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Unknown decision: {decision_id!r}",
                "code": "decision_not_found",
                "details": f"decision_id={decision_id}",
            },
        )
    return _decision_response(view)


@router.post(
    "/{decision_id}/answer",
    response_model=DecisionAnswerResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def answer_decision(
    decision_id: str,
    request: DecisionAnswerRequest,
    actor: str = Depends(get_current_actor),
):
    """`POST /decisions/{id}/answer` -- SPEC §6.2's seven steps.

    Steps 1-5 (lookup, the synthetic-id guard, the already-answered guard,
    `option_id` ownership, and the `user_text` post plus the status flip in
    one transaction) all happen inside `DecisionService.answer()` -- there
    is no business rule here, per AGENTS.md's layering rule and this
    module's own docstring. This handler only maps `answer()`'s typed
    errors to status codes and, for the success path, does step 6 itself:
    start the turn.

    **Not waited for.** Exactly `post_message`'s shape
    (`api/routes/threads.py`): the human's own reply (the `user_text` post
    `answer()` just wrote and committed) has to stand in the thread before
    the agent has said anything, and the agent's answer arrives over
    `GET /threads/{view_key}/stream` -- this request is not the one
    writing it. Gated on the same global switch as `post_message`: the
    agent being off is a *state*, not a per-answer failure, so the human's
    answer still stands and nothing about a global setting gets written as
    an `error` post under this one decision.

    `DecisionAlreadyAnswered`'s `409` carries the existing answer in the
    body -- `answered_at`, `answer_post_id`, and whichever of
    `answer_option_id`/`answer_text` was actually given -- rather than
    just a code, so a client can render the already-answered state instead
    of a bare error (SPEC §6.2 step 2, testfall 15).
    """
    try:
        decision, answer_post = DecisionService().answer(
            decision_id,
            option_id=request.option_id,
            free_text=request.free_text,
            actor=actor,
        )
    except DecisionNotFound:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Unknown decision: {decision_id!r}",
                "code": "decision_not_found",
                "details": f"decision_id={decision_id}",
            },
        )
    except DecisionNotAnswerable as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={"error": exc.message, "code": exc.code, "details": exc.details},
        )
    except DecisionAlreadyAnswered as exc:
        existing = exc.decision
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
                "answered_at": (
                    existing.answered_at.isoformat()
                    if existing.answered_at is not None
                    else None
                ),
                "answer_post_id": existing.answer_post_id,
                "answer_option_id": existing.answer_option_id,
                "answer_text": existing.answer_text,
            },
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.message, "code": exc.code, "details": exc.details},
        )

    # Step 6 (SPEC §6.2): started only after the transaction inside
    # `answer()` above has already committed -- the reply post and the
    # status flip are both durable before any turn is even considered.
    # Same gate, same logged-not-erred behaviour when the switch is off,
    # as `api/routes/threads.py::post_message`.
    thread = ThreadRepository.get(decision.thread_id)
    assert thread is not None  # decision.thread_id is a real foreign key
    if settings.agent_runtime_enabled:
        ThreadTurnRunner().start(thread, answer_post, answer_post.body["text"])
    else:
        logger.info(
            "Agent runtime disabled -- decision %s answered, no turn "
            "started (AGENT_RUNTIME_ENABLED=false)",
            decision.id,
        )

    # Step 7: the decision in its new state, read back through the same
    # union `GET /decisions/{id}` uses, so the response shape a client
    # gets here is identical to what a follow-up `GET` would show.
    view = DecisionService().get_decision(decision.id)
    assert view is not None  # just answered above; still exists
    return DecisionAnswerResponse(
        decision=_decision_response(view),
        answer_post_id=answer_post.id,
        answer_post_seq=answer_post.seq,
    )
