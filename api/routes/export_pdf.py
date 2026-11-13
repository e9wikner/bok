"""API routes for PDF export of invoices and financial reports."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from domain.validation import ValidationError
from services.pdf_export import CompanyInfo, PDFExportService

router = APIRouter(prefix="/api/v1/export/pdf", tags=["export-pdf"])


def _get_pdf_service(
    company_name: Optional[str] = Query(None, description="Företagsnamn"),
    org_number: Optional[str] = Query(None, description="Organisationsnummer"),
    vat_number: Optional[str] = Query(None, description="Momsregistreringsnummer"),
    address: Optional[str] = Query(None, description="Företagsadress"),
    phone: Optional[str] = Query(None, description="Telefon"),
    email: Optional[str] = Query(None, description="E-post"),
    website: Optional[str] = Query(None, description="Webbplats"),
    bankgiro: Optional[str] = Query(None, description="Bankgiro"),
    plusgiro: Optional[str] = Query(None, description="Plusgiro"),
    swish: Optional[str] = Query(None, description="Swish-nummer"),
    iban: Optional[str] = Query(None, description="IBAN"),
    bic: Optional[str] = Query(None, description="BIC/SWIFT"),
    logo_url: Optional[str] = Query(None, description="URL till logotyp"),
) -> PDFExportService:
    """Build PDFExportService with the company info for headers and footers.

    With no company query parameter at all, the details come from
    `company_info` (`CompanyInfo.load()`). As soon as one is given, the
    parameters are used as before and `company_info` is not read.
    """
    params = [
        company_name,
        org_number,
        vat_number,
        address,
        phone,
        email,
        website,
        bankgiro,
        plusgiro,
        swish,
        iban,
        bic,
        logo_url,
    ]
    if all(p is None for p in params):
        company = CompanyInfo.load()
        if not company.name:
            company.name = CompanyInfo.name
        return PDFExportService(company=company)

    company = CompanyInfo(
        name=company_name if company_name is not None else CompanyInfo.name,
        org_number=org_number or "",
        vat_number=vat_number or "",
        address=address or "",
        phone=phone or "",
        email=email or "",
        website=website or "",
        bankgiro=bankgiro or "",
        plusgiro=plusgiro or "",
        swish=swish or "",
        iban=iban or "",
        bic=bic or "",
        logo_url=logo_url or None,
        f_skatt=True,
    )
    return PDFExportService(company=company)


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    """Wrap PDF bytes in a downloadable response."""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ---- Invoice PDF ----


@router.get("/invoice/{invoice_id}")
async def export_invoice_pdf(
    invoice_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """
    Exportera faktura som PDF.

    Genererar professionell faktura-PDF med:
    - Företagslogga och information
    - Svenska termer (Fakturadatum, Förfallodatum, etc.)
    - Momsspecifikation per momskod
    - QR-kod för Swish-betalning
    - Betalningsinstruktioner (bankgiro, plusgiro, Swish)
    - Footer med organisationsnummer och F-skatt
    """
    try:
        pdf_bytes = pdf_service.export_invoice(invoice_id)
        return _pdf_response(pdf_bytes, f"faktura_{invoice_id}.pdf")
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/payslip/{payslip_id}")
async def export_payslip_pdf(
    payslip_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """Exportera lönespecifikation som PDF."""
    try:
        pdf_bytes = pdf_service.export_payslip(payslip_id)
        return _pdf_response(pdf_bytes, f"lonespecifikation_{payslip_id}.pdf")
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
