"""API routes for vouchers."""

import logging
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from api.deps import (
    get_current_actor,
    get_human_actor,
    get_idempotency_key,
    get_ledger_service,
)
from api.schemas import (
    ApproveCorrectionNoteRequest,
    CorrectionDraftRequest,
    CorrectionNoteResponse,
    CorrectVoucherRequest,
    CreateCorrectionNoteRequest,
    CreateVoucherRequest,
    DismissCorrectionNoteRequest,
    RejectCorrectionNoteRequest,
    SuggestCorrectionNoteRequest,
    UnderlagWaiverRequest,
    UnderlagWaiverResponse,
    UpdateVoucherRequest,
    VoucherCorrectionResponse,
    VoucherOriginResponse,
    VoucherRefResponse,
    VoucherResponse,
    VoucherRowResponse,
)
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.audit_repo import AuditRepository
from services import posting_flow
from services.correction_notes import CorrectionNoteError, CorrectionNoteService
from services.draft_service import DraftError, DraftService, SourceAlreadyBookedError
from services.idempotency import IdempotencyOutcome, IdempotencyService
from services.ledger import LedgerService
from services.underlag_waiver import UnderlagWaiverError, UnderlagWaiverService
from services.voucher_origin import voucher_origin
from services.voucher_source_context import voucher_source_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vouchers", tags=["vouchers"])


@router.get(
    "/{voucher_id}/correction-notes", response_model=list[CorrectionNoteResponse]
)
async def list_correction_notes(
    voucher_id: str,
    actor: str = Depends(get_current_actor),
):
    """List correction notes for a voucher."""
    try:
        notes = CorrectionNoteService().list_for_voucher(voucher_id)
        return [_correction_note_to_response(note) for note in notes]
    except CorrectionNoteError as e:
        _raise_correction_note_http_error(e)


@router.post(
    "/{voucher_id}/correction-notes",
    response_model=CorrectionNoteResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_correction_note(
    voucher_id: str,
    request: CreateCorrectionNoteRequest,
    actor: str = Depends(get_current_actor),
):
    """Create a correction note for a posted voucher."""
    try:
        note = CorrectionNoteService().create_note(
            voucher_id=voucher_id,
            note_text=request.note_text,
            actor=actor,
        )
        return _correction_note_to_response(note)
    except CorrectionNoteError as e:
        _raise_correction_note_http_error(e)


@router.post("/{voucher_id}/correction-draft", response_model=VoucherResponse)
async def create_correction_draft(
    voucher_id: str,
    request: CorrectionDraftRequest,
    actor: str = Depends(get_current_actor),
):
    """Create a draft B-series correction voucher for later approval."""
    try:
        draft = CorrectionNoteService().create_draft(
            voucher_id=voucher_id,
            correction_rows=[row.model_dump() for row in request.correction_rows],
            actor=actor,
        )
        return _voucher_to_response(draft)
    except CorrectionNoteError as e:
        _raise_correction_note_http_error(e)


@router.post("/{voucher_id}/correction-notes/{note_id}/suggest", response_model=dict)
async def suggest_correction_note(
    voucher_id: str,
    note_id: str,
    request: SuggestCorrectionNoteRequest,
    actor: str = Depends(get_current_actor),
):
    """Create and link a draft B-series suggestion for a correction note."""
    try:
        note, draft = CorrectionNoteService().suggest(
            voucher_id=voucher_id,
            note_id=note_id,
            correction_rows=[row.model_dump() for row in request.correction_rows],
            actor=actor,
        )
        return {
            "note": _correction_note_to_response(note),
            "draft": _voucher_to_response(draft),
        }
    except CorrectionNoteError as e:
        _raise_correction_note_http_error(e)


@router.post(
    "/{voucher_id}/correction-notes/{note_id}/approve",
    response_model=VoucherResponse,
)
async def approve_correction_note(
    voucher_id: str,
    note_id: str,
    request: ApproveCorrectionNoteRequest,
    actor: str = Depends(get_current_actor),
):
    """Approve and post a suggested B-series correction voucher."""
    try:
        rows = (
            [row.model_dump() for row in request.rows]
            if request.rows is not None
            else None
        )
        voucher = CorrectionNoteService().approve(
            voucher_id=voucher_id,
            note_id=note_id,
            rows_data=rows,
            actor=actor,
        )
        return _voucher_to_response(voucher)
    except CorrectionNoteError as e:
        _raise_correction_note_http_error(e)


@router.post(
    "/{voucher_id}/correction-notes/{note_id}/dismiss",
    response_model=CorrectionNoteResponse,
)
async def dismiss_correction_note(
    voucher_id: str,
    note_id: str,
    request: DismissCorrectionNoteRequest,
    actor: str = Depends(get_current_actor),
):
    """Dismiss a pending or suggested correction note."""
    try:
        note = CorrectionNoteService().dismiss(
            voucher_id=voucher_id,
            note_id=note_id,
            reason=request.reason,
            actor=actor,
        )
        return _correction_note_to_response(note)
    except CorrectionNoteError as e:
        _raise_correction_note_http_error(e)


@router.post(
    "/{voucher_id}/correction-notes/{note_id}/reject",
    response_model=CorrectionNoteResponse,
)
async def reject_correction_note(
    voucher_id: str,
    note_id: str,
    request: RejectCorrectionNoteRequest,
    actor: str = Depends(get_current_actor),
):
    """Reject a correction note when an agent cannot produce a useful suggestion."""
    try:
        note = CorrectionNoteService().reject(
            voucher_id=voucher_id,
            note_id=note_id,
            rejection_reason=request.rejection_reason,
            actor=actor,
        )
        return _correction_note_to_response(note)
    except CorrectionNoteError as e:
        _raise_correction_note_http_error(e)


@router.post(
    "", response_model=VoucherResponse, status_code=http_status.HTTP_201_CREATED
)
async def create_voucher(
    request: CreateVoucherRequest,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """
    Create new voucher (Verifikation).

    All amounts must be in öre (1 kr = 100).

    Example:
    ```json
    {
      "series": "A",
      "date": "2026-03-20",
      "period_id": "...",
      "description": "Konsultfaktura #1042",
      "auto_post": false,
      "rows": [
        {"account": "1510", "debit": 12500000, "credit": 0},
        {"account": "3011", "debit": 0, "credit": 10000000},
        {"account": "2610", "debit": 0, "credit": 2500000}
      ]
    }
    ```
    """
    rows_data = [r.model_dump() for r in request.rows]

    # A draft has no number, so an
    # explicit one can only be honoured when the voucher is posted now.
    if request.number is not None and not request.auto_post:
        raise ValidationError(
            "number_requires_auto_post",
            "An explicit voucher number is set at posting",
            "pass auto_post=true together with number",
        )

    voucher = ledger.create_voucher(
        series=request.series,
        date=request.date,
        period_id=request.period_id,
        description=request.description,
        rows_data=rows_data,
        created_by=actor,
    )

    # Auto-post if requested
    if request.auto_post:
        voucher = ledger.post_voucher(voucher.id, actor=actor, number=request.number)

    return _voucher_to_response(voucher)


@router.get("/{voucher_id}/source-context", response_model=dict)
async def get_voucher_source_context(
    voucher_id: str,
    actor: str = Depends(get_current_actor),
):
    """Return intake source material and correction context for voucher review."""
    context = voucher_source_context(voucher_id)
    if context is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Voucher not found",
        )
    return context


@router.get("/{voucher_id}", response_model=VoucherResponse)
async def get_voucher(
    voucher_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Get voucher by ID."""
    voucher = ledger.vouchers.get(voucher_id)
    if not voucher:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Voucher not found"
        )
    response = _voucher_to_response(voucher)
    _attach_corrections([voucher], [response])
    origin = voucher_origin(voucher_id)
    if origin is not None:
        response.origin = VoucherOriginResponse(**origin)
    return response


@router.post("/{voucher_id}/post", response_model=VoucherResponse)
async def post_voucher(
    voucher_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    """
    Post voucher (make immutable - BFL varaktighet requirement).

    Once posted, a voucher can only be corrected via a correction voucher (B-series),
    never edited directly.

    The key is what the chat's Posta button sends. Posting
    only flips the draft's own status, so a second request cannot make a
    second voucher -- but two requests arriving at the same instant could both
    pass validation and both write a `posted` audit row. Under a key the
    second is `request_in_flight` or a replay instead.
    """
    idempotency = IdempotencyService()
    endpoint = _post_endpoint(voucher_id)
    replay = _begin_idempotent(idempotency, idempotency_key, endpoint, {}, actor)
    if replay is not None:
        # A replay of a completed posting: the receipt may be what the first
        # request never got to.
        posting_flow.after_posting(voucher_id, actor)
        return replay

    try:
        return _post_and_record(
            voucher_id=voucher_id,
            ledger=ledger,
            actor=actor,
            idempotency=idempotency,
            idempotency_key=idempotency_key,
            endpoint=endpoint,
        )
    except Exception:
        # A refusal (locked period, already posted) is an answer, not a
        # completed posting: free the key so the caller can act on it.
        if idempotency_key:
            idempotency.release(idempotency_key, endpoint)
        raise


def _post_endpoint(voucher_id: str) -> str:
    """Scoped to the voucher, like `_correct_endpoint`: the body is empty."""
    return f"POST /api/v1/vouchers/{voucher_id}/post"


def _record_posting(
    idempotency: IdempotencyService,
    idempotency_key: Optional[str],
    endpoint: str,
    responses: list,
):
    """What the route records inside a posting's transaction: the response,
    and the key row that replays it. The response is built there, so that it
    shows the voucher exactly as committed."""

    def record(voucher) -> None:
        response = _voucher_to_response(voucher)
        responses.append(response)
        if idempotency_key:
            idempotency.complete(
                key=idempotency_key,
                endpoint=endpoint,
                response_status=http_status.HTTP_200_OK,
                response_payload=jsonable_encoder(response),
                entity_type="voucher",
                entity_id=voucher.id,
                _commit=False,
            )

    return record


def _post_and_record(
    voucher_id: str,
    ledger: LedgerService,
    actor: str,
    idempotency: IdempotencyService,
    idempotency_key: Optional[str],
    endpoint: str,
) -> VoucherResponse:
    """The posting, a thread draft's hooks and the key row, in one
    transaction (`services/posting_flow.post`)."""
    responses: list[VoucherResponse] = []
    try:
        posting_flow.post(
            voucher_id,
            actor=actor,
            record=_record_posting(idempotency, idempotency_key, endpoint, responses),
        )
    except ValidationError as e:
        raise _posting_http_error(e, ledger, voucher_id)
    return responses[0]


def _begin_idempotent(
    idempotency: IdempotencyService,
    idempotency_key: Optional[str],
    endpoint: str,
    body: dict,
    actor: str,
) -> Optional[JSONResponse]:
    """Reserve the key, or answer for it.

    Returns the stored response to replay, raises for a mismatch or a request
    still in flight, and returns `None` when the caller should go ahead --
    with the key reserved, or with no key at all.
    """
    if not idempotency_key:
        return None
    outcome = idempotency.begin(
        key=idempotency_key, endpoint=endpoint, body=body, actor=actor
    )
    if outcome.kind == IdempotencyOutcome.REPLAY:
        return JSONResponse(
            status_code=outcome.response_status or http_status.HTTP_200_OK,
            content=outcome.response_payload,
            headers={"Idempotent-Replay": "true"},
        )
    if outcome.kind == IdempotencyOutcome.MISMATCH:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "Idempotency-Key already used for a different request",
                "code": "idempotency_key_reuse",
                "details": "The same key must carry the same request body",
                "original_fingerprint": outcome.original_fingerprint,
            },
        )
    if outcome.kind == IdempotencyOutcome.IN_FLIGHT:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "error": "A request with this Idempotency-Key is in flight",
                "code": "request_in_flight",
                "details": "Retry with the same key to get the stored response",
                "retry_after_ms": 500,
            },
        )
    return None


def _posting_http_error(
    exc: ValidationError,
    ledger: LedgerService,
    voucher_id: str,
) -> HTTPException:
    """Map a posting failure onto a status code.

    Two of them are conflicts, not bad requests: the request was valid and the
    ledger is simply already in a state that settles it. A client retrying
    after a timeout has to be able to render the done state, not an error.
    """
    detail: dict[str, Any] = {
        "error": exc.message,
        "code": exc.code,
        "details": exc.details,
    }

    if exc.code == "already_posted":
        voucher = ledger.vouchers.get(voucher_id)
        if voucher:
            detail["voucher"] = jsonable_encoder(_voucher_to_response(voucher))
        return HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=detail)

    if isinstance(exc, SourceAlreadyBookedError):
        # F6's open risk: the intake flow booked the same underlag while the
        # proposal waited. Nothing was posted; say which voucher has it.
        detail["booked_by"] = exc.booked_by()
        return HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=detail)

    if exc.code == "source_not_linkable":
        return HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=detail)

    if exc.code == "period_locked":
        voucher = ledger.vouchers.get(voucher_id)
        period = ledger.periods.get_period(voucher.period_id) if voucher else None
        if period:
            detail["period_id"] = period.id
            detail["locked_at"] = (
                period.locked_at.isoformat() if period.locked_at else None
            )
            # A lock from before migration 023 has no recorded actor. The API
            # says so rather than guessing who it was.
            detail["locked_by"] = period.locked_by or "okänd"
        return HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=detail)

    return HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


@router.post("/{voucher_id}/correct", response_model=VoucherResponse)
async def correct_voucher(
    voucher_id: str,
    request: CorrectVoucherRequest,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    """Correct a posted voucher by creating and posting a B-series correction.

    A correction is exactly what a caller repeats after a timeout, so the same
    key twice must leave one B-series voucher behind.
    """
    idempotency = IdempotencyService()
    endpoint = _correct_endpoint(voucher_id)
    replay = _begin_idempotent(
        idempotency, idempotency_key, endpoint, jsonable_encoder(request), actor
    )
    if replay is not None:
        return replay

    try:
        return _correct_and_record(
            voucher_id=voucher_id,
            request=request,
            ledger=ledger,
            actor=actor,
            idempotency=idempotency,
            idempotency_key=idempotency_key,
            endpoint=endpoint,
        )
    except Exception:
        if idempotency_key:
            idempotency.release(idempotency_key, endpoint)
        raise


def _correct_endpoint(voucher_id: str) -> str:
    """The key is scoped to the voucher being corrected.

    Two vouchers corrected under the same key are two intents, and the
    fingerprint covers the body only — so the voucher id lives in the endpoint.
    """
    return f"POST /api/v1/vouchers/{voucher_id}/correct"


def _correct_and_record(
    voucher_id: str,
    request: CorrectVoucherRequest,
    ledger: LedgerService,
    actor: str,
    idempotency: IdempotencyService,
    idempotency_key: Optional[str],
    endpoint: str,
) -> VoucherResponse:
    """B-series voucher, correction history and key row, in one transaction
    (`services/posting_flow.post_correction`). The key row commits with the
    correction: written afterwards it would leave a window where the B-series
    voucher exists but the key does not."""
    responses: list[VoucherResponse] = []
    posting_flow.post_correction(
        voucher_id,
        corrected_rows=[r.model_dump() for r in request.corrected_rows],
        reason=request.reason,
        actor=actor,
        record=_record_posting(idempotency, idempotency_key, endpoint, responses),
    )
    return responses[0]


@router.put("/{voucher_id}", response_model=VoucherResponse)
async def update_voucher(
    voucher_id: str,
    request: UpdateVoucherRequest,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """
    Update voucher rows and/or description in-place.

    Only draft vouchers can be updated in place. Posted vouchers must be
    corrected with POST /api/v1/vouchers/{id}/correct.
    """
    rows_data = [r.model_dump() for r in request.rows]

    voucher = ledger.update_voucher(
        voucher_id=voucher_id,
        rows_data=rows_data,
        description=request.description,
        reason=request.reason,
        actor=actor,
    )

    return _voucher_to_response(voucher)


@router.get("", response_model=dict)
async def list_vouchers(
    period_id: str = Query(None, description="Filter by period ID (optional)"),
    fiscal_year_id: str = Query(
        None, description="Filter by fiscal year ID (optional)"
    ),
    voucher_status: str = Query(
        "all", alias="status", description="Filter: draft, posted, or all"
    ),
    search: str = Query(None, description="Search in description or voucher number"),
    limit: int = Query(None, description="Max vouchers to return (pagination)"),
    offset: int = Query(0, description="Number of vouchers to skip (pagination)"),
    sort_by: str = Query(None, description="Sort by: date, number or age"),
    sort_order: str = Query(
        None, description="Sort direction: asc or desc (age defaults to asc)"
    ),
    missing_attachment: bool = Query(
        None,
        description="true: only posted vouchers without attachment, false: only with",
    ),
    exclude_series: str = Query(
        None, description="Comma-separated list of series to exclude (e.g., 'IB')"
    ),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    List vouchers, optionally filtered by period.

    Filter by status: "draft", "posted", or "all".
    If period_id is omitted, returns vouchers from all periods.
    Supports server-side search on description and voucher number.
    Use exclude_series to hide special vouchers like opening balances (IB).
    Use missing_attachment=true with sort_by=age for the vouchers that still
    need a receipt, oldest first.
    """
    status_filter = voucher_status if voucher_status != "all" else None

    # Parse exclude_series
    exclude_series_list = None
    if exclude_series:
        exclude_series_list = [s.strip() for s in exclude_series.split(",")]

    if period_id:
        vouchers = ledger.vouchers.list_for_period(period_id, status=status_filter)
        # Filter out excluded series
        if exclude_series_list:
            vouchers = [
                v for v in vouchers if v.series.value not in exclude_series_list
            ]
        # Same meaning as the SQL branch below: the flag only applies to
        # posted vouchers. Silently ignoring it here would hand a view that
        # asked for "missing attachment" the whole ledger back.
        if missing_attachment is not None:
            vouchers = [
                v
                for v in vouchers
                if v.status.value == "posted"
                and bool(v.missing_attachment) is missing_attachment
            ]
        total = len(vouchers)
    else:
        vouchers, total = ledger.vouchers.list_all(
            status=status_filter,
            search=search,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            fiscal_year_id=fiscal_year_id,
            exclude_series=exclude_series_list,
            missing_attachment=missing_attachment,
        )

    # Read once for the page, not once per voucher.
    account_names = AccountRepository.get_all_as_dict()
    responses = [_voucher_to_response(v, account_names) for v in vouchers]
    _attach_corrections(vouchers, responses, account_names)
    return {
        "period_id": period_id,
        "status_filter": voucher_status,
        "total": total,
        "vouchers": responses,
    }


def _waiver_error(exc: UnderlagWaiverError) -> HTTPException:
    return HTTPException(
        status_code=exc.status, detail={"error": exc.message, "code": exc.code}
    )


@router.post("/{voucher_id}/underlag-waiver", response_model=UnderlagWaiverResponse)
async def waive_underlag(
    voucher_id: str,
    request: UnderlagWaiverRequest,
    actor: str = Depends(get_human_actor),
):
    """Approve a posted voucher without underlag (migration 051): it leaves
    `missing_attachment`. `later` keeps it matchable when the underlag comes;
    `none` says the voucher is its own document (an accrual). A logged-in
    user only: the API key gets `403 human_only`. The voucher is not changed.
    `200` also on a replay with the same reason; `409 waiver_exists` for
    another reason, `409 not_missing_underlag` when it has its underlag."""
    try:
        waiver = UnderlagWaiverService().waive(
            voucher_id, reason=request.reason, note=request.note, actor=actor
        )
    except UnderlagWaiverError as exc:
        raise _waiver_error(exc) from exc
    return UnderlagWaiverResponse(**waiver.__dict__)


@router.post(
    "/{voucher_id}/underlag-waiver/revoke",
    response_model=Optional[UnderlagWaiverResponse],
)
async def revoke_underlag_waiver(
    voucher_id: str,
    actor: str = Depends(get_human_actor),
):
    """Undo the approval without underlag: the voucher is back in
    `missing_attachment` unless it has got its underlag. A logged-in user
    only. `null` when there was nothing to undo."""
    try:
        waiver = UnderlagWaiverService().revoke(voucher_id, actor=actor)
    except UnderlagWaiverError as exc:
        raise _waiver_error(exc) from exc
    return UnderlagWaiverResponse(**waiver.__dict__) if waiver else None


@router.get("/{voucher_id}/audit", response_model=dict)
async def get_voucher_audit(
    voucher_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    Get audit trail (ändringshistorik) for a voucher.

    Returns all changes made to a voucher, including who changed it,
    when, and what was changed (before/after values).
    """
    voucher = ledger.vouchers.get(voucher_id)
    if not voucher:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Voucher not found"
        )

    entries = AuditRepository.get_history("voucher", voucher_id)

    return {
        "voucher_id": voucher_id,
        "total": len(entries),
        "entries": [
            {
                "id": e.id,
                "action": e.action.value,
                "actor": e.actor,
                "timestamp": e.timestamp.isoformat(),
                "payload": e.payload,
            }
            for e in entries
        ],
    }


def _correction_note_to_response(note) -> CorrectionNoteResponse:
    return CorrectionNoteResponse(
        id=note.id,
        voucher_id=note.voucher_id,
        note_text=note.note_text,
        status=note.status,
        suggested_voucher_id=note.suggested_voucher_id,
        rejection_reason=note.rejection_reason,
        created_at=note.created_at,
        created_by=note.created_by,
        updated_at=note.updated_at,
        resolved_at=note.resolved_at,
    )


@router.post("/{voucher_id}/discard", status_code=http_status.HTTP_204_NO_CONTENT)
async def discard_draft(voucher_id: str, actor: str = Depends(get_human_actor)):
    """`Kasta utkast`: a draft voucher is deleted -- it never took a number,
    so no gap is left. A thread's draft becomes `rejected` as with the card's
    `Kasta`. A logged-in human only; the API key gets `403 human_only`.
    `404 draft_not_found`; `409` for a posted voucher (`draft_not_pending`),
    attached files (`draft_has_attachments`) or another row pointing at it
    (`draft_referenced`)."""
    try:
        DraftService().discard(voucher_id, actor=actor)
    except DraftError as exc:
        raise HTTPException(
            status_code=(
                http_status.HTTP_404_NOT_FOUND
                if exc.code == "draft_not_found"
                else http_status.HTTP_409_CONFLICT
            ),
            detail={"error": exc.message, "code": exc.code, "details": exc.details},
        )


def _raise_correction_note_http_error(error: CorrectionNoteError) -> None:
    status_code = http_status.HTTP_400_BAD_REQUEST
    if error.code in {"voucher_not_found", "correction_note_not_found"}:
        status_code = http_status.HTTP_404_NOT_FOUND
    elif error.code in {
        "correction_note_active_exists",
        "invalid_lifecycle_transition",
    }:
        status_code = http_status.HTTP_409_CONFLICT
    raise HTTPException(
        status_code=status_code,
        detail={
            "error": error.message,
            "code": error.code,
            "details": error.details,
        },
    )


def _voucher_to_response(voucher, account_names=None) -> VoucherResponse:
    """Convert domain Voucher to response. A list passes *account_names*,
    read once for the page."""
    if account_names is None:
        account_names = AccountRepository.get_all_as_dict()
    total_debit = sum(row.debit for row in voucher.rows)
    total_credit = sum(row.credit for row in voucher.rows)

    # Derived, never stored. A voucher read back from the
    # repository carries both; one just built in memory does not, and a voucher
    # that has only just been created has no attachment and no age.
    missing_attachment = (
        True if voucher.missing_attachment is None else voucher.missing_attachment
    )
    age_days = (
        max((date.today() - voucher.date).days, 0)
        if voucher.age_days is None
        else voucher.age_days
    )

    return VoucherResponse(
        id=voucher.id,
        series=voucher.series.value,
        number=voucher.number,
        date=voucher.date,
        period_id=voucher.period_id,
        description=voucher.description,
        comment=voucher.comment,
        status=voucher.status.value,
        rows=[
            VoucherRowResponse(
                id=row.id,
                voucher_id=row.voucher_id,
                account=row.account_code,
                account_code=row.account_code,
                account_name=(
                    account_names[row.account_code].name
                    if row.account_code in account_names
                    else None
                ),
                debit=row.debit,
                credit=row.credit,
                description=row.description,
            )
            for row in voucher.rows
        ],
        total_debit=total_debit,
        total_credit=total_credit,
        balanced=total_debit == total_credit,
        row_count=len(voucher.rows),
        correction_of=voucher.correction_of,
        created_at=voucher.created_at,
        created_by=voucher.created_by,
        posted_at=voucher.posted_at,
        missing_attachment=missing_attachment,
        age_days=age_days,
        missing_statement_accounts=list(voucher.missing_statement_accounts),
        corrected_by=_ref_response(voucher.corrected_by),
        corrects=_ref_response(voucher.corrects),
        referenced_by=_ref_response(voucher.referenced_by),
        underlag_waiver=(
            UnderlagWaiverResponse(**voucher.underlag_waiver.__dict__)
            if voucher.underlag_waiver
            else None
        ),
    )


def _attach_corrections(vouchers, responses, account_names=None) -> None:
    """`correction` on every corrected voucher and every correction of the
    page (`services/correction_view.py`), read once for the page."""
    from services.correction_view import correction_summaries

    summaries = correction_summaries(vouchers, account_names)
    for response in responses:
        summary = summaries.get(response.id)
        if summary is not None:
            response.correction = VoucherCorrectionResponse(**summary)


def _ref_response(ref) -> Optional[VoucherRefResponse]:
    if ref is None:
        return None
    return VoucherRefResponse(id=ref.id, series=ref.series, number=ref.number)
