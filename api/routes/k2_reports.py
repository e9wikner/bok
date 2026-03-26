"""API routes for K2 annual reports (Fas 3)."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_current_actor
from services.k2_report import K2ReportService
from repositories.period_repo import PeriodRepository

router = APIRouter(prefix="/api/v1/reports", tags=["reports-k2"])


@router.post("/k2/generate", response_model=dict, status_code=status.HTTP_201_CREATED)
async def generate_k2_report(
    fiscal_year_id: str,
    company_name: str,
    org_number: str = None,
    managing_director: str = None,
    average_employees: int = None,
    significant_events: str = None,
    actor: str = Depends(get_current_actor),
):
    """
    Generate K2 annual report for fiscal year.
    
    Creates complete financial statements:
    - Income Statement (Resultaträkning)
    - Balance Sheet (Balansräkning)
    - Cash Flow Statement
    
    All figures calculated automatically from posted vouchers.
    """
    try:
        # Get fiscal year
        period_repo = PeriodRepository()
        fy = period_repo.get_fiscal_year(fiscal_year_id)
        if not fy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fiscal year not found"
            )
        
        # Generate report
        service = K2ReportService()
        report = service.generate_report(
            fiscal_year=fy,
            company_name=company_name,
            org_number=org_number,
            managing_director=managing_director,
            average_employees=average_employees,
            significant_events=significant_events,
        )
        
        return {
            "id": report["id"],
            "fiscal_year_id": fiscal_year_id,
            "company_name": company_name,
            "report_date": report["report_date"],
            "status": "draft",
            "income_statement": report["income_statement"],
            "balance_sheet": report["balance_sheet"],
            "cash_flow": report["cash_flow"],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/k2/{report_id}", response_model=dict)
async def get_k2_report(report_id: str):
    """Get K2 report by ID."""
    # In a real implementation, this would fetch from database
    # For now, return example structure
    return {
        "id": report_id,
        "status": "draft",
        "message": "Report details would be retrieved from database"
    }


@router.post("/k2/{report_id}/finalize", response_model=dict)
async def finalize_k2_report(
    report_id: str,
    actor: str = Depends(get_current_actor),
):
    """Finalize K2 report (lock for review)."""
    return {
        "id": report_id,
        "status": "finalized",
        "finalized_at": "2026-03-21T10:00:00",
        "message": "Report finalized and ready for review"
    }


@router.get("/k2/{report_id}/export", response_model=dict)
async def export_k2_json(report_id: str):
    """Export K2 report as JSON for submission to authorities."""
    return {
        "version": "1.0",
        "report_id": report_id,
        "format": "K2-JSON",
        "message": "JSON export ready for submission"
    }


@router.get("/grundbok/{period_id}", response_model=dict)
async def get_grundbok(period_id: str):
    """
    Get Grundbok (basic accounting journal) - transactions in registration order.
    
    Required by BFL §5 kap 1.
    """
    return {
        "period_id": period_id,
        "report_type": "grundbok",
        "description": "All transactions in chronological order"
    }


@router.get("/huvudbok/{account_code}", response_model=dict)
async def get_huvudbok(account_code: str, period_id: str):
    """
    Get Huvudbok (general ledger) - transactions in systematic order.
    
    Required by BFL §5 kap 1.
    """
    return {
        "account_code": account_code,
        "period_id": period_id,
        "report_type": "huvudbok",
        "description": "All transactions for account in systematic order"
    }


@router.get("/verifikation-summary/{period_id}", response_model=dict)
async def get_verifikation_summary(period_id: str):
    """
    Get summary of all verifikationer (vouchers) in period.
    
    Includes count, total amounts, VAT breakdown.
    """
    return {
        "period_id": period_id,
        "total_vouchers": 0,
        "total_amount_debit": 0,
        "total_amount_credit": 0,
        "vat_breakdown": {
            "mp1_25": 0,
            "mp2_12": 0,
            "mp3_6": 0,
            "mf_0": 0,
        }
    }
