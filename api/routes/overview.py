"""API route for the page overview (SPEC-oversikt.md §5)."""

from fastapi import APIRouter, Depends

from api.deps import get_current_actor
from api.schemas import (
    OverviewCounters,
    OverviewFiscalYear,
    OverviewPageResponse,
    OverviewPeriodState,
    OverviewResponse,
)
from services.overview import OverviewService

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])

overview_service = OverviewService()


@router.get("", response_model=OverviewResponse)
async def get_overview(actor: str = Depends(get_current_actor)):
    """All three pages' counters in one call.

    Returns the fiscal year, the current period state, and one entry per page
    in the order the design draws them: Böcker, Fakturering och löner, Bokslut.
    Each page carries `waiting` (is there a dot?) and `meta` (what waits?),
    both decided by the server — the client counts nothing.

    This is a pure read. Unlike POST /compliance/check it persists nothing.
    """
    overview = overview_service.get_overview()
    fiscal_year = overview.fiscal_year
    period_state = overview.period_state
    return OverviewResponse(
        fiscal_year=(
            OverviewFiscalYear(
                id=fiscal_year.id,
                label=fiscal_year.label,
                start=fiscal_year.start,
                end=fiscal_year.end,
            )
            if fiscal_year
            else None
        ),
        period_state=(
            OverviewPeriodState(
                current_period_id=period_state.current_period_id,
                label=period_state.label,
                locked=period_state.locked,
            )
            if period_state
            else None
        ),
        pages=[
            OverviewPageResponse(
                key=page.key,
                title=page.title,
                waiting=page.waiting,
                meta=page.meta,
                counters=OverviewCounters(**page.counters),
            )
            for page in overview.pages
        ],
    )
