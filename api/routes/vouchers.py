"""API routes for vouchers."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from datetime import datetime
from typing import List

from api.schemas import (
    CreateVoucherRequest,
    VoucherResponse,
    VoucherRowResponse,
    ErrorResponse,
)
from api.deps import get_ledger_service, get_current_actor
from domain.validation import ValidationError
from services.ledger import LedgerService

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
        rows_data = [r.dict() for r in request.rows]
        
        voucher = ledger.create_voucher(
            series=request.series,
            date=request.date,
            period_id=request.period_id,
            description=request.description,
            rows_data=rows_data,
            created_by=actor
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


@router.get("", response_model=dict)
async def list_vouchers(
    period_id: str = Query(None, description="Filter by period ID (optional)"),
    voucher_status: str = Query("all", alias="status", description="Filter: draft, posted, or all"),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    List vouchers, optionally filtered by period.
    
    Filter by status: "draft", "posted", or "all".
    If period_id is omitted, returns vouchers from all periods.
    """
    try:
        status_filter = voucher_status if voucher_status != "all" else None
        
        if period_id:
            vouchers = ledger.vouchers.list_for_period(period_id, status=status_filter)
        else:
            vouchers = ledger.vouchers.list_all(status=status_filter)
        
        return {
            "period_id": period_id,
            "status_filter": voucher_status,
            "total": len(vouchers),
            "vouchers": [_voucher_to_response(v) for v in vouchers]
        }
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _voucher_to_response(voucher) -> VoucherResponse:
    """Convert domain Voucher to response."""
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
