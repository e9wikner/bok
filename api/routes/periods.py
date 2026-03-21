"""API routes for periods and fiscal years."""

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import date
from typing import List

from api.schemas import PeriodResponse, FiscalYearResponse
from api.deps import get_ledger_service, get_current_actor
from domain.validation import ValidationError
from services.ledger import LedgerService

router = APIRouter(prefix="/api/v1", tags=["periods"])


@router.post("/fiscal-years", response_model=FiscalYearResponse, status_code=status.HTTP_201_CREATED)
async def create_fiscal_year(
    start_date: date,
    end_date: date,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    Create fiscal year with automatic monthly periods.
    
    Example: 2026-01-01 to 2026-12-31
    """
    try:
        if start_date >= end_date:
            raise ValidationError(
                "invalid_dates",
                "start_date must be before end_date"
            )
        
        fiscal_year = ledger.periods.create_fiscal_year(start_date, end_date)
        
        # Create monthly periods
        from calendar import monthrange
        current_date = start_date
        while current_date.year < end_date.year or (current_date.year == end_date.year and current_date.month <= end_date.month):
            year = current_date.year
            month = current_date.month
            
            # Get last day of month
            _, last_day = monthrange(year, month)
            period_start = date(year, month, 1)
            period_end = date(year, month, last_day)
            
            ledger.periods.create_period(
                fiscal_year_id=fiscal_year.id,
                year=year,
                month=month,
                start_date=period_start,
                end_date=period_end
            )
            
            # Move to next month
            if month == 12:
                current_date = date(year + 1, 1, 1)
            else:
                current_date = date(year, month + 1, 1)
        
        return _fiscal_year_to_response(fiscal_year)
    
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/fiscal-years/{fy_id}", response_model=FiscalYearResponse)
async def get_fiscal_year(
    fy_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Get fiscal year by ID."""
    try:
        fy = ledger.periods.get_fiscal_year(fy_id)
        if not fy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fiscal year not found"
            )
        return _fiscal_year_to_response(fy)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/periods", response_model=dict)
async def list_periods(
    fiscal_year_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """List all periods in a fiscal year."""
    try:
        periods = ledger.periods.list_periods(fiscal_year_id)
        return {
            "fiscal_year_id": fiscal_year_id,
            "total": len(periods),
            "periods": [_period_to_response(p) for p in periods]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/periods/{period_id}", response_model=PeriodResponse)
async def get_period(
    period_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Get period by ID."""
    try:
        period = ledger.periods.get_period(period_id)
        if not period:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Period not found"
            )
        return _period_to_response(period)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/periods/{period_id}/lock", response_model=PeriodResponse)
async def lock_period(
    period_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """
    Lock period (irreversible - BFL varaktighet requirement).
    
    All draft vouchers must be posted or deleted before locking.
    Once locked, no new vouchers can be added to this period.
    """
    try:
        period = ledger.lock_period(period_id, actor=actor)
        return _period_to_response(period)
    
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _fiscal_year_to_response(fy) -> FiscalYearResponse:
    """Convert domain FiscalYear to response."""
    return FiscalYearResponse(
        id=fy.id,
        start_date=fy.start_date,
        end_date=fy.end_date,
        locked=fy.locked,
        locked_at=fy.locked_at,
        created_at=fy.created_at
    )


def _period_to_response(period) -> PeriodResponse:
    """Convert domain Period to response."""
    return PeriodResponse(
        id=period.id,
        fiscal_year_id=period.fiscal_year_id,
        year=period.year,
        month=period.month,
        start_date=period.start_date,
        end_date=period.end_date,
        locked=period.locked,
        locked_at=period.locked_at,
        created_at=period.created_at
    )
