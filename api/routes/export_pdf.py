"""API routes for PDF export of invoices and financial reports."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from typing import Optional

from repositories.period_repo import PeriodRepository
from services.pdf_export import PDFExportService, CompanyInfo

router = APIRouter(prefix="/api/v1/export/pdf", tags=["export-pdf"])


def _get_pdf_service(
    company_name: str = Query("Mitt Företag AB", description="Företagsnamn"),
    org_number: str = Query("", description="Organisationsnummer"),
    vat_number: str = Query("", description="Momsregistreringsnummer"),
    address: str = Query("", description="Företagsadress"),
    phone: str = Query("", description="Telefon"),
    email: str = Query("", description="E-post"),
    website: str = Query("", description="Webbplats"),
    bankgiro: str = Query("", description="Bankgiro"),
    plusgiro: str = Query("", description="Plusgiro"),
    swish: str = Query("", description="Swish-nummer"),
    iban: str = Query("", description="IBAN"),
    bic: str = Query("", description="BIC/SWIFT"),
    logo_url: str = Query("", description="URL till logotyp"),
) -> PDFExportService:
    """Build PDFExportService from query params (company info)."""
    company = CompanyInfo(
        name=company_name,
        org_number=org_number,
        vat_number=vat_number,
        address=address,
        phone=phone,
        email=email,
        website=website,
        bankgiro=bankgiro,
        plusgiro=plusgiro,
        swish=swish,
        iban=iban,
        bic=bic,
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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera faktura-PDF: {str(e)}",
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
        return _pdf_response(pdf_bytes, f"resultatrakning_{fiscal_year_id}_{suffix}.pdf")
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
