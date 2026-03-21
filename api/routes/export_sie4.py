"""API routes for SIE4 export.

Exporterar bokföringsdata till SIE4-format som kan importeras
i andra bokföringsprogram (Fortnox, Visma, etc.).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from typing import Optional

from api.deps import get_current_actor
from services.sie4_export import SIE4Exporter

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/sie4", status_code=status.HTTP_200_OK)
async def export_sie4(
    fiscal_year_id: str = Query(
        ..., description="ID för räkenskapsåret att exportera"
    ),
    company_name: Optional[str] = Query(
        None, description="Företagsnamn (valfritt, hämtas annars från systemet)"
    ),
    org_number: Optional[str] = Query(
        None, description="Organisationsnummer (valfritt)"
    ),
    format: str = Query(
        "PC8",
        description="Format: PC8 (Windows-1252) eller ASCII",
        regex="^(PC8|ASCII)$",
    ),
    download: bool = Query(
        True, description="True = returnera som filnedladdning, False = returnera som JSON"
    ),
    actor: str = Depends(get_current_actor),
):
    """
    Exportera bokföringsdata till SIE4-format.

    SIE (Standard Import/Export) version 4 är svensk standard för
    utbyte av bokföringsdata mellan bokföringsprogram.

    Exporten inkluderar:
    - Företagsinformation (#FNAMN, #FORGN, #ADRESS)
    - Kontoplan (#KONTO, #KPTYP, #SRU)
    - Ingående balanser (#IB)
    - Utgående balanser (#UB)
    - Resultat (#RES)
    - Periodsaldon (#PSALDO)
    - Alla bokförda verifikationer (#VER, #TRANS)

    Filen kodas i Windows-1252 med \\r\\n radbrytningar (SIE4-standard).
    """
    try:
        exporter = SIE4Exporter()
        content_bytes = exporter.export(
            fiscal_year_id=fiscal_year_id,
            company_name=company_name,
            org_number=org_number,
            format_type=format,
        )

        if exporter.errors:
            # Returnera varningar men fortsätt med exporten
            pass

        if download:
            # Generera filnamn
            from repositories.period_repo import PeriodRepository
            fy = PeriodRepository.get_fiscal_year(fiscal_year_id)
            if fy:
                filename = exporter.get_filename(
                    company_name or "Export", fy
                )
            else:
                filename = "export.si"

            return Response(
                content=content_bytes,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "application/x-sie",
                },
            )
        else:
            # Returnera som JSON med innehållet som textsträng
            text_content = exporter.export_text(
                fiscal_year_id=fiscal_year_id,
                company_name=company_name,
                org_number=org_number,
                format_type=format,
            )
            return {
                "content": text_content,
                "format": "SIE4",
                "encoding": "windows-1252" if format == "PC8" else "ascii",
                "warnings": exporter.errors,
            }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export misslyckades: {str(e)}",
        )


@router.post("/sie4", status_code=status.HTTP_200_OK)
async def export_sie4_post(
    fiscal_year_id: str = Query(
        ..., description="ID för räkenskapsåret att exportera"
    ),
    company_name: Optional[str] = Query(None),
    org_number: Optional[str] = Query(None),
    format: str = Query("PC8", regex="^(PC8|ASCII)$"),
    actor: str = Depends(get_current_actor),
):
    """
    Exportera bokföringsdata till SIE4-format (POST-variant).

    Samma funktionalitet som GET men via POST.
    Returnerar alltid filen som nedladdning.
    """
    try:
        exporter = SIE4Exporter()
        content_bytes = exporter.export(
            fiscal_year_id=fiscal_year_id,
            company_name=company_name,
            org_number=org_number,
            format_type=format,
        )

        from repositories.period_repo import PeriodRepository
        fy = PeriodRepository.get_fiscal_year(fiscal_year_id)
        filename = (
            exporter.get_filename(company_name or "Export", fy)
            if fy
            else "export.si"
        )

        return Response(
            content=content_bytes,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/x-sie",
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export misslyckades: {str(e)}",
        )
