"""Granskning (docs/granskning.md §4): an external agent reviews a fiscal
year and uploads a report; the UI reads the reports.

`public_router` holds the entrypoint, which needs no bearer, like the
bookkeeping agent's (`/api/v1/agent-instructions/entrypoint`). Everything
else is on `router`, included behind the bearer in `api/main.py`. The review
key (`BOKFOERING_REVIEW_KEY`) may read every route and write only
`POST /api/v1/review/reports` (`api/deps.py::verify_api_key`).

The bookkeeping agent gets no tool for this: it does not review itself.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from api.deps import get_fiscal_year_filter, get_principal
from config import settings
from domain.models import FiscalYear
from services.review import ReviewError, ReviewReportIn, ReviewService

PREFIX = "/api/v1/review"

public_router = APIRouter(prefix=PREFIX, tags=["review"])
router = APIRouter(prefix=PREFIX, tags=["review"])


def _http_error(exc: ReviewError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"error": exc.message, "code": exc.code, **exc.payload},
    )


@public_router.get("/entrypoint", response_model=dict)
async def get_review_entrypoint():
    """Where a reviewing agent starts. Public: it holds no data."""
    return {
        "service": "bokfoering-api",
        "version": settings.api_version,
        "purpose": "Granska ett räkenskapsår och ladda upp en granskningsrapport.",
        "auth": {
            "type": "bearer",
            "header": "Authorization",
            "value_format": "Bearer <BOKFOERING_REVIEW_KEY>",
            "check": {
                "method": "GET",
                "path": f"{PREFIX}/instructions",
                "expected_status": 200,
                "on_401": "Stop: the bearer is missing or wrong.",
            },
        },
        "startup_sequence": [
            {
                "step": 1,
                "action": "read_instructions",
                "method": "GET",
                "path": f"{PREFIX}/instructions?fiscal_year_id={{id}}",
                "guidance": "Utan fiscal_year_id gäller det senaste räkenskapsåret.",
            },
            {
                "step": 2,
                "action": "review",
                "guidance": "Följ instruktionen. Läs bara, skriv inget.",
            },
            {
                "step": 3,
                "action": "upload_report",
                "method": "POST",
                "path": f"{PREFIX}/reports",
            },
        ],
        "links": {"openapi": "/openapi.json", "health": "/api/v1/health"},
    }


@router.get("/instructions", response_model=dict)
async def get_review_instructions(
    fiscal_year_id: Optional[str] = Query(
        None, description="The year to review; omitted, the latest"
    ),
):
    """The review instruction, its hash, where the books are for the year
    and the upload's JSON Schema."""
    try:
        return ReviewService().instructions(fiscal_year_id)
    except ReviewError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/reports",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "A replay: the report with this id was stored before"},
        409: {"description": "review_report_id_conflict"},
        422: {"description": "invalid_voucher_id, fiscal_year_not_found"},
    },
)
async def upload_review_report(
    body: ReviewReportIn,
    response: Response,
    uploaded_by: str = Depends(get_principal),
):
    """Upload a granskningsrapport. `201` when stored, `200` when the same
    id and body was stored before. Nothing is stored unless all of it is
    valid."""
    try:
        report, created = ReviewService().submit(body, uploaded_by=uploaded_by)
    except ReviewError as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return report


@router.get("/reports", response_model=dict)
async def list_review_reports(
    fiscal_year: Optional[FiscalYear] = Depends(get_fiscal_year_filter),
):
    """The reports, newest first, with findings per severity and whether
    each was made against an older instruction."""
    return ReviewService().list_reports(fiscal_year.id if fiscal_year else None)


@router.get("/reports/{report_id}", response_model=dict)
async def get_review_report(report_id: str):
    """A report with its summary, findings and the vouchers they name."""
    try:
        return ReviewService().get(report_id)
    except ReviewError as exc:
        raise _http_error(exc) from exc


@router.get("/coverage", response_model=dict)
async def get_review_coverage(
    fiscal_year_id: Optional[str] = Query(None, description="Omitted, the latest"),
):
    """Per voucher a report examined or flagged: how many reports examined
    it, and which flagged it with what severity."""
    service = ReviewService()
    try:
        return service.coverage(service.fiscal_year(fiscal_year_id))
    except ReviewError as exc:
        raise _http_error(exc) from exc
