"""API routes for PDF export of invoices and financial reports."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from typing import Optional

from api.deps import get_current_actor
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


# ---- Trial Balance PDF ----

@router.get("/trial-balance/{period_id}")
async def export_trial_balance_pdf(
    period_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """
    Exportera råbalans som PDF.
    
    Visar alla konton med debet/kredit/saldo för given period.
    """
    try:
        pdf_bytes = pdf_service.export_trial_balance(period_id)
        return _pdf_response(pdf_bytes, f"rabalans_{period_id}.pdf")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera råbalans-PDF: {str(e)}",
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


@router.get("/trial-balance/{period_id}/html")
async def export_trial_balance_html(
    period_id: str,
    pdf_service: PDFExportService = Depends(_get_pdf_service),
):
    """Exportera råbalans som HTML (fallback när PDF inte fungerar)."""
    try:
        html_str = pdf_service.export_trial_balance_html(period_id)
        return _html_response(html_str, f"rabalans_{period_id}.html")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera råbalans-HTML: {str(e)}",
        )
