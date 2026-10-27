"""API routes for periods and fiscal years."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_current_actor, get_human_actor, get_ledger_service
from api.schemas import (
    FiscalYearCreateRequest,
    FiscalYearResponse,
    OpeningBalanceDifference,
    OpeningBalanceRequest,
    OpeningBalanceResponse,
    OpeningBalanceRow,
    PeriodResponse,
)
from domain.validation import ValidationError
from services.fiscal_years import FiscalYearService
from services.ledger import LedgerService
from services.opening_balance import OpeningBalance, OpeningBalanceService

router = APIRouter(prefix="/api/v1", tags=["periods"])


@router.post(
    "/fiscal-years",
    response_model=FiscalYearResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_fiscal_year(
    request: FiscalYearCreateRequest,
    actor: str = Depends(get_current_actor),
):
    """
    Create a fiscal year with one period per calendar month, in one
    transaction. Audit-logged.

    Body: `{"start_date": "2027-01-01", "end_date": "2027-12-31"}`.

    - `409 fiscal_year_overlap`: the dates overlap a year in the books
      (`detail.fiscal_year` is that year).
    - `400 fiscal_year_not_adjacent`: years follow one another without a gap
      -- the new year starts the day after the last one ends, or ends the day
      before the first one starts.
    - `400 fiscal_year_too_long`: more than 18 months (BFL 3 kap. 1 §).
    - `400 invalid_dates`: `start_date` is not before `end_date`.
    """
    try:
        fiscal_year = FiscalYearService().create(
            request.start_date, request.end_date, actor=actor
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if e.code == "fiscal_year_overlap"
                else status.HTTP_400_BAD_REQUEST
            ),
            detail={
                "error": e.message,
                "code": e.code,
                "details": e.details,
                **e.payload,
            },
        )
    return _fiscal_year_to_response(fiscal_year)


@router.get("/fiscal-years", response_model=dict)
async def list_fiscal_years(
    ledger: LedgerService = Depends(get_ledger_service),
):
    """List all fiscal years."""
    fiscal_years = ledger.periods.list_fiscal_years()
    return {
        "total": len(fiscal_years),
        "fiscal_years": [_fiscal_year_to_response(fy) for fy in fiscal_years],
    }


@router.get("/fiscal-years/{fy_id}", response_model=FiscalYearResponse)
async def get_fiscal_year(
    fy_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Get fiscal year by ID."""
    fy = ledger.periods.get_fiscal_year(fy_id)
    if not fy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found"
        )
    return _fiscal_year_to_response(fy)


@router.post(
    "/periods", response_model=PeriodResponse, status_code=status.HTTP_201_CREATED
)
async def create_period(
    fiscal_year_id: str,
    year: int,
    month: int,
    start_date: date,
    end_date: date,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    Create a single period for a fiscal year.

    Used by SIE4 import when importing vouchers for months that don't have periods yet.
    """
    try:
        period = ledger.periods.create_period(
            fiscal_year_id=fiscal_year_id,
            year=year,
            month=month,
            start_date=start_date,
            end_date=end_date,
        )
        return _period_to_response(period)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/periods", response_model=dict)
async def list_periods(
    fiscal_year_id: str = None,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """List periods, optionally filtered by fiscal year. If no fiscal_year_id, returns all periods."""
    try:
        if fiscal_year_id:
            periods = ledger.periods.list_periods(fiscal_year_id)
        else:
            periods = ledger.periods.list_all_periods()
        return {
            "fiscal_year_id": fiscal_year_id,
            "total": len(periods),
            "periods": [_period_to_response(p) for p in periods],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
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
                status_code=status.HTTP_404_NOT_FOUND, detail="Period not found"
            )
        return _period_to_response(period)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/fiscal-years/{fy_id}/lock", response_model=FiscalYearResponse)
async def lock_fiscal_year(
    fy_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """
    Lock a fiscal year and every period in it that is still open.

    One transaction: a period with draft vouchers (other than a thread's
    pending proposals, which are marked `period_locked`) stops the whole lock
    with `400 draft_vouchers_exist`. The agent may lock; only a human may
    unlock.
    """
    try:
        return _fiscal_year_to_response(ledger.lock_fiscal_year(fy_id, actor=actor))
    except ValidationError as e:
        raise _lock_error(e)


@router.post("/fiscal-years/{fy_id}/unlock", response_model=FiscalYearResponse)
async def unlock_fiscal_year(
    fy_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_human_actor),
):
    """
    Open a locked fiscal year again, and every period in it.

    Logged-in users only (JWT): the agent's API key gets `403 human_only`.
    Posted vouchers stay immutable; the audit log keeps who locked and who
    unlocked.
    """
    try:
        return _fiscal_year_to_response(ledger.unlock_fiscal_year(fy_id, actor=actor))
    except ValidationError as e:
        raise _lock_error(e)


@router.get(
    "/fiscal-years/{fy_id}/opening-balances",
    response_model=OpeningBalanceResponse,
)
async def get_opening_balances(fy_id: str):
    """
    The fiscal year's opening balance (ingående balans, IB).

    IB is not a voucher. A year with a previous fiscal year in the books
    derives it from that year's closing position, the unclosed result on
    2099 (`source: derived`), so it follows every change until the previous
    year is locked. The first year's is stated (`source: stated`). A stated
    IB kept for a derived year -- an SIE4 file's -- is reconciled in
    `stated_differences`.
    """
    try:
        return _opening_balance_response(OpeningBalanceService().get(fy_id))
    except ValidationError as e:
        raise _lock_error(e)


@router.put(
    "/fiscal-years/{fy_id}/opening-balances",
    response_model=OpeningBalanceResponse,
)
async def put_opening_balances(
    fy_id: str,
    request: OpeningBalanceRequest,
    actor: str = Depends(get_current_actor),
):
    """
    Replace the first fiscal year's stated opening balance.

    Only the first fiscal year in the books has one: a later year's is
    derived (`400 opening_balance_derived`). Balance accounts only, and it
    must balance (`opening_balance_unbalanced`). Refused while the year is
    locked (`fiscal_year_locked`). Audit-logged with before and after.
    """
    balances: dict = {}
    for row in request.balances:
        balances[row.account] = balances.get(row.account, 0) + row.amount
    try:
        return _opening_balance_response(
            OpeningBalanceService().state(fy_id, balances, actor=actor)
        )
    except ValidationError as e:
        raise _lock_error(e)


def _opening_balance_response(opening: OpeningBalance) -> OpeningBalanceResponse:
    return OpeningBalanceResponse(
        fiscal_year_id=opening.fiscal_year_id,
        source=opening.source,
        previous_fiscal_year_id=opening.previous_fiscal_year_id,
        balanced=opening.balanced,
        balances=[
            OpeningBalanceRow(account=code, amount=amount)
            for code, amount in sorted(opening.balances.items())
        ],
        stated_differences=[
            OpeningBalanceDifference(account=code, stated=stated, derived=derived)
            for code, (stated, derived) in opening.stated_differences.items()
        ],
    )


@router.post("/periods/{period_id}/lock", response_model=PeriodResponse)
async def lock_period(
    period_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """
    Lock period: no new vouchers can be posted in it.

    All draft vouchers must be posted or deleted before locking
    (`400 draft_vouchers_exist`) -- except a thread's pending proposals: the
    lock goes through and marks them `period_locked`, with an error post in
    their thread (SPEC-flode-verifikationer §9, F16). Only a human can open
    the period again (`/unlock`).
    """
    try:
        return _period_to_response(ledger.lock_period(period_id, actor=actor))
    except ValidationError as e:
        raise _lock_error(e)


@router.post("/periods/{period_id}/unlock", response_model=PeriodResponse)
async def unlock_period(
    period_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_human_actor),
):
    """
    Open a locked period again.

    Logged-in users only (JWT): the agent's API key gets `403 human_only`.
    A period in a locked fiscal year stays locked (`400 fiscal_year_locked`)
    until the year is opened.
    """
    try:
        return _period_to_response(ledger.unlock_period(period_id, actor=actor))
    except ValidationError as e:
        raise _lock_error(e)


def _lock_error(e: ValidationError) -> HTTPException:
    """`404` for a missing period or year, `400` for every other refusal."""
    not_found = e.code in ("period_not_found", "fiscal_year_not_found")
    return HTTPException(
        status_code=(
            status.HTTP_404_NOT_FOUND if not_found else status.HTTP_400_BAD_REQUEST
        ),
        detail={"error": e.message, "code": e.code, "details": e.details},
    )


def _fiscal_year_to_response(fy) -> FiscalYearResponse:
    """Convert domain FiscalYear to response."""
    return FiscalYearResponse(
        id=fy.id,
        start_date=fy.start_date,
        end_date=fy.end_date,
        locked=fy.locked,
        locked_at=fy.locked_at,
        created_at=fy.created_at,
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
        locked_by=period.locked_by,
        created_at=period.created_at,
    )
