"""API routes for VAT (moms) declarations."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from services.vat_report import VatReportService
from domain.validation import ValidationError

router = APIRouter(prefix="/api/v1/vat", tags=["vat"])

vat_service = VatReportService()


@router.post("/declarations/monthly")
async def generate_monthly_declaration(
    year: int = Query(..., description="Year (e.g. 2026)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
):
    """Generate a monthly VAT declaration (momsdeklaration).
    
    Collects all VAT-related transactions from posted vouchers for the
    given period and calculates the SKV 4700 form values.
    
    Returns:
    - Sales by VAT rate (25%, 12%, 6%, exempt)
    - Output VAT (utgående moms)
    - Input VAT (ingående moms)
    - Net VAT to pay/receive
    """
    try:
        decl = vat_service.generate_monthly(year, month)
        return vat_service.format_skv_summary(decl)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/declarations/quarterly")
async def generate_quarterly_declaration(
    year: int = Query(..., description="Year"),
    quarter: int = Query(..., ge=1, le=4, description="Quarter (1-4)"),
):
    """Generate a quarterly VAT declaration."""
    try:
        decl = vat_service.generate_quarterly(year, quarter)
        return vat_service.format_skv_summary(decl)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/declarations/yearly")
async def generate_yearly_declaration(
    year: int = Query(..., description="Year"),
):
    """Generate an annual VAT declaration.

    Annual eSKD declarations use period code YYYY12, matching Skatteverket's
    upload format and the iOrdning reference export.
    """
    try:
        decl = vat_service.generate_yearly(year)
        return vat_service.format_skv_summary(decl)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/declarations/yearly/{year}")
async def preview_yearly_declaration(year: int):
    """Preview an annual VAT declaration without saving a new row."""
    try:
        decl = vat_service.preview_yearly(year)
        return vat_service.format_skv_summary(decl)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/declarations")
async def list_declarations(
    year: Optional[int] = Query(None, description="Filter by year"),
):
    """List all generated VAT declarations."""
    declarations = vat_service.list_declarations(year=year)
    return {
        "count": len(declarations),
        "declarations": [vat_service.format_skv_summary(d) for d in declarations],
    }


@router.get("/declarations/{decl_id}")
async def get_declaration(decl_id: str):
    """Get a specific VAT declaration."""
    decl = vat_service.get_declaration(decl_id)
    if not decl:
        raise HTTPException(status_code=404, detail="Declaration not found")
    return vat_service.format_skv_summary(decl)


@router.get("/export/eskd/{year}")
async def export_yearly_eskd(year: int):
    """Export annual VAT declaration as Skatteverket eSKD XML."""
    try:
        decl = vat_service.preview_yearly(year)
        filename = f"Moms-{decl.period_code}.eskd"
        return Response(
            content=vat_service.export_eskd(decl),
            media_type="application/xml; charset=ISO-8859-1",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/export/pdf/{year}")
async def export_yearly_pdf(year: int):
    """Export annual VAT declaration as PDF."""
    try:
        decl = vat_service.preview_yearly(year)
        filename = f"momsdeklaration-{decl.period_code}.pdf"
        return Response(
            content=vat_service.export_pdf(decl),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
