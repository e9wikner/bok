"""API route for a view's thread drafts (SPEC-flode-verifikationer.md §10).

A `draft` post is never rewritten, so whether its card is posted, replaced or
still waiting has to be asked for: one call per view, looked up locally in the
client, the same pattern as `GET /decisions`.

HTTP only, per AGENTS.md's layering rule: parse, authenticate, validate
`view_key` against the closed list of seven, and map domain errors to status
codes. The list and the voucher numbers come from
`services/draft_service.py::DraftService.list_drafts`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from api.deps import get_current_actor
from api.schemas import (
    DraftVoucherNumber,
    ThreadDraftListResponse,
    ThreadDraftResponse,
)
from domain.types import ThreadViewKey
from domain.validation import ValidationError
from services.draft_service import DraftListItem, DraftService

router = APIRouter(prefix="/api/v1/drafts", tags=["drafts"])


def _validate_view_key(view_key: str) -> str:
    """Same rule and error shape as `api/routes/decisions.py` and
    `api/routes/threads.py`: an unknown key is `404`, not an empty list."""
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


def _draft_response(item: DraftListItem) -> ThreadDraftResponse:
    draft = item.draft
    voucher = (
        DraftVoucherNumber(series=item.series, number=item.number)
        if item.series is not None and item.number is not None
        else None
    )
    return ThreadDraftResponse(
        draft_id=draft.voucher_id,
        post_id=draft.post_id,
        decision_id=draft.decision_id,
        correction_of=draft.correction_of,
        correction_note_id=draft.correction_note_id,
        status=draft.status,
        replaced_by=draft.replaced_by,
        posted_at=draft.posted_at,
        voucher=voucher,
        last_error_code=draft.last_error_code,
        created_at=draft.created_at,
    )


@router.get("", response_model=ThreadDraftListResponse)
async def list_drafts(
    view_key: str = Query(..., description="One of the seven views; unknown is 404."),
    status: str = Query(
        "all",
        description="`pending`, `posted`, `superseded` or `all` (default) -- "
        "unknown value is 400.",
    ),
    limit: int = Query(200, ge=1, le=200),
    actor: str = Depends(get_current_actor),
):
    """`GET /drafts` -- one view's thread drafts, oldest first. `voucher`
    is set only when the draft is posted."""
    validated_view_key = _validate_view_key(view_key)
    try:
        items, total = DraftService().list_drafts(
            view_key=validated_view_key, status=status, limit=limit
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.message, "code": exc.code, "details": exc.details},
        )
    return ThreadDraftListResponse(
        drafts=[_draft_response(item) for item in items], total=total
    )
