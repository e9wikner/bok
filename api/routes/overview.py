"""API route for the page overview (SPEC-oversikt.md §5)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from api.deps import get_current_actor
from api.schemas import (
    OverviewClosingView,
    OverviewCounters,
    OverviewFiscalYear,
    OverviewOtherYear,
    OverviewPageResponse,
    OverviewPeriodState,
    OverviewResponse,
    OverviewViewWaiting,
)
from services.overview import OverviewService

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])

overview_service = OverviewService()


@router.get("", response_model=OverviewResponse)
async def get_overview(
    fiscal_year_id: Optional[str] = Query(
        None,
        description=(
            "Count for this fiscal year; omitted, the current one. What waits "
            "in other years is listed in `other_years`. Unknown id is 404."
        ),
    ),
    actor: str = Depends(get_current_actor),
):
    """All three pages' counters in one call.

    Returns the fiscal year, the current period state, and one entry per page
    in the order the design draws them: Böcker, Fakturering och löner, Bokslut.
    Each page carries `waiting` (is there a dot?) and `meta` (what waits?),
    both decided by the server — the client counts nothing.

    The counters are for one fiscal year (`counted_fiscal_year_id`); `views`
    gives the count per view (tab), and `other_years` the years where
    something else waits. `fiscal_year` and `period_state` are always the
    current year's.

    This is a pure read. Unlike POST /compliance/check it persists nothing.
    """
    try:
        overview = overview_service.get_overview(fiscal_year_id=fiscal_year_id)
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Unknown fiscal year: {fiscal_year_id!r}",
                "code": "fiscal_year_not_found",
                "details": "fiscal_year_id must name an existing fiscal year.",
            },
        )
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
        counted_fiscal_year_id=overview.counted_fiscal_year_id,
        views=[
            OverviewViewWaiting(key=view.key, waiting=view.waiting)
            for view in overview.views
        ],
        other_years=[
            OverviewOtherYear(
                id=year.id, label=year.label, waiting=year.waiting, meta=year.meta
            )
            for year in overview.other_years
        ],
        closing_views=[
            OverviewClosingView(key=v.key, waiting=v.waiting, meta=v.meta)
            for v in overview.closing_views
        ],
    )
