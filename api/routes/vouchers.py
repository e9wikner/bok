"""API routes for vouchers."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from api.schemas import (
    CreateVoucherRequest,
    UpdateVoucherRequest,
    VoucherResponse,
    VoucherRowResponse,
)
from api.deps import get_ledger_service, get_current_actor
from domain.validation import ValidationError
from services.ledger import LedgerService
from repositories.audit_repo import AuditRepository
from repositories.account_repo import AccountRepository

router = APIRouter(prefix="/api/v1/vouchers", tags=["vouchers"])


@router.post("", response_model=VoucherResponse, status_code=http_status.HTTP_201_CREATED)
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
            detail={
                "error": e.message,
                "code": e.code,
                "details": e.details
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


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
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Voucher not found"
            )
        return _voucher_to_response(voucher)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
            detail={
                "error": e.message,
                "code": e.code,
                "details": e.details
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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

    Changes are recorded in the audit trail with before/after snapshots.
    """
    try:
        rows_data = [r.model_dump() for r in request.rows]

        # Capture original before update for AI learning
        original = ledger.vouchers.get(voucher_id) if request.teach_ai else None

        voucher = ledger.update_voucher(
            voucher_id=voucher_id,
            rows_data=rows_data,
            description=request.description,
            reason=request.reason,
            actor=actor,
        )

        # Optionally teach AI
        if request.teach_ai:
            try:
                from services.learning import LearningService
                learning = LearningService()
                if original:
                    learning.learn_from_correction(
                        original_voucher=original,
                        corrected_voucher=voucher,
                        correction_reason=request.reason,
                        corrected_by=actor,
                    )
            except Exception:
                pass  # AI learning is best-effort

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
    fiscal_year_id: str = Query(None, description="Filter by fiscal year ID (optional)"),
    voucher_status: str = Query("all", alias="status", description="Filter: draft, posted, or all"),
    search: str = Query(None, description="Search in description or voucher number"),
    limit: int = Query(None, description="Max vouchers to return (pagination)"),
    offset: int = Query(0, description="Number of vouchers to skip (pagination)"),
    sort_by: str = Query(None, description="Sort by: date or number"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    List vouchers, optionally filtered by period.
    
    Filter by status: "draft", "posted", or "all".
    If period_id is omitted, returns vouchers from all periods.
    Supports server-side search on description and voucher number.
    """
    try:
        status_filter = voucher_status if voucher_status != "all" else None
        
        if period_id:
            vouchers = ledger.vouchers.list_for_period(period_id, status=status_filter)
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
            )
        
        return {
            "period_id": period_id,
            "status_filter": voucher_status,
            "total": total,
            "vouchers": [_voucher_to_response(v) for v in vouchers]
        }
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Voucher not found"
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
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _voucher_to_response(voucher) -> VoucherResponse:
    """Convert domain Voucher to response."""
    # Look up account names
    account_names = AccountRepository.get_all_as_dict()
    
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
                account_code=row.account_code,
                account_name=account_names[row.account_code].name if row.account_code in account_names else None,
                debit=row.debit,
                credit=row.credit,
                description=row.description
            )
            for row in voucher.rows
        ],
        correction_of=voucher.correction_of,
        created_at=voucher.created_at,
        created_by=voucher.created_by,
        posted_at=voucher.posted_at
    )
