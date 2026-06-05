"""API routes for vouchers."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

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
    UpdateVoucherRequest,
    VoucherResponse,
    VoucherRowResponse,
)
from api.deps import get_ledger_service, get_current_actor
from domain.validation import ValidationError
from services.ledger import LedgerService
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.audit_repo import AuditRepository
from repositories.account_repo import AccountRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.intake_repo import IntakeRepository
from services.correction_notes import CorrectionNoteError, CorrectionNoteService

router = APIRouter(prefix="/api/v1/vouchers", tags=["vouchers"])


@router.get("/{voucher_id}/correction-notes", response_model=list[CorrectionNoteResponse])
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
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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
    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details},
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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
    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details},
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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
    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details},
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/{voucher_id}/correction-notes/{note_id}/reject", response_model=CorrectionNoteResponse)
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
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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
    try:
        rows_data = [r.model_dump() for r in request.rows]

        voucher = ledger.create_voucher(
            series=request.series,
            date=request.date,
            period_id=request.period_id,
            description=request.description,
            rows_data=rows_data,
            created_by=actor,
            number=request.number,
        )

        # Auto-post if requested
        if request.auto_post:
            voucher = ledger.post_voucher(voucher.id, actor=actor)

        return _voucher_to_response(voucher)

    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details},
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{voucher_id}/source-context", response_model=dict)
async def get_voucher_source_context(
    voucher_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """Return intake source material and correction context for voucher review."""
    voucher = ledger.vouchers.get(voucher_id)
    if not voucher:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Voucher not found",
        )

    intake_repo = IntakeRepository()
    bank_repo = BankInputRepository()
    source_material = []
    processing_notes = []

    for link in intake_repo.list_links_for_voucher(voucher_id):
        source = intake_repo.get_source(link.intake_source_id)
        if not source:
            continue
        source_material.append(
            {
                "kind": "voucher_source",
                "id": source.id,
                "source_type": source.source_type.value if source.source_type else None,
                "status": source.status.value,
                "original_filename": source.original_filename,
                "mime_type": source.mime_type,
                "size_bytes": source.size_bytes,
                "sha256": source.sha256,
                "explanation": source.explanation,
                "uploaded_by": source.uploaded_by,
                "uploaded_at": source.uploaded_at.isoformat(),
                "download_url": f"/api/v1/intake/{source.id}/file",
                "linked_at": link.linked_at.isoformat(),
                "linked_by": link.linked_by,
                "link_reason": link.link_reason,
            }
        )
        processing_notes.extend(
            _source_processing_note(attempt)
            for attempt in intake_repo.list_attempts_for_source(source.id)
            if attempt.voucher_id == voucher_id
        )

    voucher_transaction_links = bank_repo.list_transactions_for_voucher(voucher_id)
    for link in bank_repo.list_inputs_for_voucher(voucher_id):
        bank_input = bank_repo.get_bank_input(link.bank_input_id)
        if not bank_input:
            continue
        transaction_ids_for_input = set(bank_repo.list_transaction_ids_for_input(bank_input.id))
        transaction_ids = [
            tx_link.bank_transaction_id
            for tx_link in voucher_transaction_links
            if tx_link.bank_transaction_id in transaction_ids_for_input
        ]
        source_material.append(
            {
                "kind": "bank_input",
                "id": bank_input.id,
                "bank_connection_id": bank_input.bank_connection_id,
                "status": bank_input.status.value,
                "original_filename": bank_input.original_filename,
                "mime_type": bank_input.mime_type,
                "size_bytes": bank_input.size_bytes,
                "sha256": bank_input.sha256,
                "uploaded_by": bank_input.uploaded_by,
                "uploaded_at": bank_input.uploaded_at.isoformat(),
                "download_url": f"/api/v1/bank-inputs/{bank_input.id}/file",
                "linked_at": link.linked_at.isoformat(),
                "linked_by": link.linked_by,
                "link_reason": None,
                "imported_count": bank_input.imported_count,
                "skipped_count": bank_input.skipped_count,
                "detected_format": bank_input.detected_format,
                "parse_error": bank_input.parse_error,
                "transaction_ids": transaction_ids,
                "transaction_count": len(transaction_ids),
            }
        )
        processing_notes.append(
            {
                "kind": "bank_input",
                "id": bank_input.id,
                "status": bank_input.status.value,
                "summary": _bank_input_processing_summary(bank_input),
                "warnings": [],
                "error_detail": bank_input.parse_error,
                "voucher_id": voucher_id,
                "actor": bank_input.uploaded_by,
                "created_at": (
                    bank_input.processed_at or bank_input.uploaded_at
                ).isoformat(),
                "imported_count": bank_input.imported_count,
                "skipped_count": bank_input.skipped_count,
                "detected_format": bank_input.detected_format,
                "transaction_ids": transaction_ids,
            }
        )

    return {
        "voucher_id": voucher_id,
        "source_material": source_material,
        "processing_notes": sorted(
            processing_notes,
            key=lambda note: note["created_at"],
        ),
        "correction_chain": _correction_chain_for_voucher(voucher),
    }


@router.get("/{voucher_id}", response_model=VoucherResponse)
async def get_voucher(
    voucher_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Get voucher by ID."""
    try:
        voucher = ledger.vouchers.get(voucher_id)
        if not voucher:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Voucher not found"
            )
        return _voucher_to_response(voucher)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{voucher_id}/post", response_model=VoucherResponse)
async def post_voucher(
    voucher_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """
    Post voucher (make immutable - BFL varaktighet requirement).

    Once posted, a voucher can only be corrected via a correction voucher (B-series),
    never edited directly.
    """
    try:
        voucher = ledger.post_voucher(voucher_id, actor=actor)
        return _voucher_to_response(voucher)

    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details},
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{voucher_id}/correct", response_model=VoucherResponse)
async def correct_voucher(
    voucher_id: str,
    request: CorrectVoucherRequest,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """Correct a posted voucher by creating and posting a B-series correction."""
    try:
        rows_data = [r.model_dump() for r in request.corrected_rows]
        correction = ledger.create_posted_correction(
            original_voucher_id=voucher_id,
            corrected_rows=rows_data,
            reason=request.reason,
            actor=actor,
        )
        return _voucher_to_response(correction)
    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details},
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


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
    try:
        rows_data = [r.model_dump() for r in request.rows]

        voucher = ledger.update_voucher(
            voucher_id=voucher_id,
            rows_data=rows_data,
            description=request.description,
            reason=request.reason,
            actor=actor,
        )

        return _voucher_to_response(voucher)

    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "error": e.message,
                "code": e.code,
                "details": e.details,
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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
    sort_by: str = Query(None, description="Sort by: date or number"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
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
    """
    try:
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
            )

        return {
            "period_id": period_id,
            "status_filter": voucher_status,
            "total": total,
            "vouchers": [_voucher_to_response(v) for v in vouchers],
        }
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


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
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


def _source_processing_note(attempt) -> dict:
    return {
        "kind": "voucher_source",
        "id": attempt.id,
        "intake_source_id": attempt.intake_source_id,
        "status": attempt.status.value,
        "summary": attempt.summary,
        "warnings": attempt.warnings or [],
        "error_detail": attempt.error_detail,
        "voucher_id": attempt.voucher_id,
        "actor": attempt.actor,
        "created_at": attempt.created_at.isoformat(),
    }


def _bank_input_processing_summary(bank_input) -> str:
    if bank_input.parse_error:
        return "Bank input parsing failed"
    return (
        f"Bank input processed: {bank_input.imported_count} imported, "
        f"{bank_input.skipped_count} skipped"
    )


def _correction_chain_for_voucher(voucher) -> list[dict]:
    voucher_ids = {voucher.id}
    if voucher.correction_of:
        voucher_ids.add(voucher.correction_of)

    chain = []
    seen = set()
    for voucher_id in voucher_ids:
        for history in AccountingCorrectionRepository.list(voucher_id=voucher_id):
            if history.id in seen:
                continue
            seen.add(history.id)
            chain.append(
                {
                    "id": history.id,
                    "original_voucher_id": history.original_voucher_id,
                    "correction_voucher_id": history.corrected_voucher_id,
                    "correction_reason": history.correction_reason,
                    "actor": history.corrected_by,
                    "timestamp": history.created_at.isoformat(),
                    "change_type": history.change_type,
                }
            )
    return sorted(chain, key=lambda item: item["timestamp"])


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


def _voucher_to_response(voucher) -> VoucherResponse:
    """Convert domain Voucher to response."""
    # Look up account names
    account_names = AccountRepository.get_all_as_dict()
    total_debit = sum(row.debit for row in voucher.rows)
    total_credit = sum(row.credit for row in voucher.rows)

    return VoucherResponse(
        id=voucher.id,
        series=voucher.series.value,
        number=voucher.number,
        date=voucher.date,
        period_id=voucher.period_id,
        description=voucher.description,
        status=voucher.status.value,
        rows=[
            VoucherRowResponse(
                id=row.id,
                voucher_id=row.voucher_id,
                account=row.account_code,
                account_code=row.account_code,
                account_name=account_names[row.account_code].name
                if row.account_code in account_names
                else None,
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
    )
