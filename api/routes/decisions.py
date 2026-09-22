"""API routes for the union of the three decision sources (SPEC-beslut.md
§5, §6.1).

HTTP only, per AGENTS.md's layering rule: parse, authenticate, validate
`view_key` against the closed list of seven, and map domain errors to
status codes. The union itself -- `decisions`, `intake_sources`
(`failed`/`needs_attention`) and `correction_notes`
(`pending`/`suggested`) -- lives entirely in
`services/decision_service.py::DecisionService.list_decisions` /
`.get_decision`; nothing here touches those three tables.

`POST /decisions/{id}/answer` is B8's. This router is deliberately
read-only so that task has a clean place to land.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from api.deps import get_current_actor
from api.schemas import (
    DecisionListResponse,
    DecisionOptionResponse,
    DecisionResponse,
    DecisionSourceResponse,
)
from domain.models import DecisionOption
from domain.types import ThreadViewKey
from domain.validation import ValidationError
from services.decision_service import DecisionService, DecisionView

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
