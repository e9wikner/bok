"""API routes for PDF export of invoices and financial reports."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from domain.validation import ValidationError
from repositories.period_repo import PeriodRepository
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


def _resolve_period_id(fiscal_year_id: str, month: Optional[int] = None) -> str:
    periods = PeriodRepository.list_periods(fiscal_year_id)
    if not periods:
        raise ValueError(f"Inga perioder hittades för räkenskapsår {fiscal_year_id}")

    if month:
        for period in periods:
            if period.month == month:
                return period.id
        raise ValueError(f"Ingen period hittades för månad {month}")

    return periods[0].id


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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera faktura-PDF: {str(e)}",
        )


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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera lönespecifikation-PDF: {str(e)}",
        )


@router.get("/payslip/{payslip_id}/html")
async def export_payslip_html(
    payslip_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """Exportera lönespecifikation som HTML."""
    try:
        return Response(
            content=pdf_service.export_payslip_html(payslip_id),
            media_type="text/html; charset=utf-8",
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera lönespecifikation-HTML: {str(e)}",
        )


# ---- General Ledger PDF ----


@router.get("/general-ledger/{account_code}")
async def export_general_ledger_pdf(
    account_code: str,
    period_id: str = Query(..., description="Period-ID"),
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """
    Exportera huvudbok per konto som PDF.

    Visar alla transaktioner för ett specifikt konto under given period.
    """
    try:
        pdf_bytes = pdf_service.export_general_ledger(account_code, period_id)
        return _pdf_response(pdf_bytes, f"huvudbok_{account_code}_{period_id}.pdf")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera huvudbok-PDF: {str(e)}",
        )


# ---- Income Statement PDF ----


@router.get("/income-statement/{period_id}")
async def export_income_statement_pdf(
    period_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """
    Exportera resultaträkning som PDF.

    Visar intäkter, kostnader och resultat för given period.
    """
    try:
        pdf_bytes = pdf_service.export_income_statement(period_id)
        return _pdf_response(pdf_bytes, f"resultatrakning_{period_id}.pdf")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera resultaträkning-PDF: {str(e)}",
        )


@router.get("/income-statement")
async def export_income_statement_pdf_for_fiscal_year(
    fiscal_year_id: str = Query(..., description="Räkenskapsår-ID"),
    month: Optional[int] = Query(None, description="Månad 1-12, tomt för helår"),
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """Exportera resultaträkning genom att ange räkenskapsår och valfri månad."""
    try:
        period_id = _resolve_period_id(fiscal_year_id, month)
        pdf_bytes = pdf_service.export_income_statement(period_id)
        suffix = f"{month:02d}" if month else "helaar"
        return _pdf_response(
            pdf_bytes, f"resultatrakning_{fiscal_year_id}_{suffix}.pdf"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera resultaträkning-PDF: {str(e)}",
        )


# ---- Balance Sheet PDF ----


@router.get("/balance-sheet/{period_id}")
async def export_balance_sheet_pdf(
    period_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """
    Exportera balansräkning som PDF.

    Visar tillgångar, eget kapital och skulder per balansdatum.
    """
    try:
        pdf_bytes = pdf_service.export_balance_sheet(period_id)
        return _pdf_response(pdf_bytes, f"balansrakning_{period_id}.pdf")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera balansräkning-PDF: {str(e)}",
        )


@router.get("/balance-sheet")
async def export_balance_sheet_pdf_for_fiscal_year(
    fiscal_year_id: str = Query(..., description="Räkenskapsår-ID"),
    month: Optional[int] = Query(None, description="Månad 1-12, tomt för helår"),
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """Exportera balansräkning genom att ange räkenskapsår och valfri månad."""
    try:
        period_id = _resolve_period_id(fiscal_year_id, month)
        pdf_bytes = pdf_service.export_balance_sheet(period_id)
        suffix = f"{month:02d}" if month else "helaar"
        return _pdf_response(pdf_bytes, f"balansrakning_{fiscal_year_id}_{suffix}.pdf")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera balansräkning-PDF: {str(e)}",
        )


# ---- K2 Report PDF ----


@router.get("/k2-report/{fiscal_year_id}")
async def export_k2_report_pdf(
    fiscal_year_id: str,
    company_name: str = Query(..., description="Företagsnamn"),
    org_number: str = Query("", description="Organisationsnummer"),
    managing_director: str = Query("", description="Styrelse/VD"),
    average_employees: Optional[int] = Query(None, description="Medelantal anställda"),
    significant_events: str = Query("", description="Väsentliga händelser"),
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """
    Exportera K2-årsredovisning som PDF.

    Komplett årsredovisning enligt K2-regelverket med:
    - Förvaltningsberättelse
    - Resultaträkning
    - Balansräkning
    - Noter
    """
    try:
        pdf_bytes = pdf_service.export_k2_report(
            fiscal_year_id=fiscal_year_id,
            company_name=company_name,
            org_number=org_number,
            managing_director=managing_director,
            average_employees=average_employees,
            significant_events=significant_events,
        )
        return _pdf_response(pdf_bytes, f"k2_arsredovisning_{fiscal_year_id}.pdf")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera K2-rapport-PDF: {str(e)}",
        )


# ---- HTML Export (Fallback) ----


def _html_response(html_str: str, filename: str) -> Response:
    """Wrap HTML in a downloadable response."""
    return Response(
        content=html_str,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/invoice/{invoice_id}/html")
async def export_invoice_html(
    invoice_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """Exportera faktura som HTML (fallback när PDF inte fungerar)."""
    try:
        html_str = pdf_service.export_invoice_html(invoice_id)
        return _html_response(html_str, f"faktura_{invoice_id}.html")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera faktura-HTML: {str(e)}",
        )
