"""API routes for BFL compliance checking."""

from typing import Optional
from fastapi import APIRouter, Query

from services.compliance import ComplianceService

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])

compliance_service = ComplianceService()


@router.post("/check")
async def run_compliance_check():
    """Run all BFL compliance checks.
    
    Checks for:
    - Booking timeliness (BFL 5 kap 2§)
    - Period closing (best practice)
    - Voucher sequence gaps (BFL 5 kap 6§)
    - Trial balance accuracy
    - VAT declaration deadlines
    - Unbooked bank transaction backlogs
    - Missing voucher attachments
    - Unusually large transactions
    
    Returns summary with all open issues sorted by severity.
    """
    results = compliance_service.run_all_checks()
    return results


@router.get("/issues")
async def list_issues(
    severity: Optional[str] = Query(None, description="Filter by severity: critical, error, warning, info"),
):
    """List all open compliance issues."""
    issues = compliance_service.get_open_issues(severity=severity)
    return {
        "count": len(issues),
        "issues": [
            {
                "id": i.id,
                "check_type": i.check_type,
                "severity": i.severity,
                "status": i.status,
                "title": i.title,
                "description": i.description,
                "recommendation": i.recommendation,
                "deadline": i.deadline.isoformat() if i.deadline else None,
                "entity_type": i.entity_type,
                "entity_id": i.entity_id,
            }
            for i in issues
        ],
    }


@router.post("/issues/{issue_id}/acknowledge")
async def acknowledge_issue(issue_id: str):
    """Acknowledge a compliance issue (stops it from re-appearing in checks)."""
    compliance_service.acknowledge_issue(issue_id)
    return {"message": "Issue acknowledged", "id": issue_id}


@router.post("/issues/{issue_id}/resolve")
async def resolve_issue(issue_id: str, resolved_by: str = "user"):
    """Mark a compliance issue as resolved."""
    compliance_service.resolve_issue(issue_id, resolved_by=resolved_by)
    return {"message": "Issue resolved", "id": issue_id}


@router.post("/issues/{issue_id}/false-positive")
async def mark_false_positive(issue_id: str):
    """Mark a compliance issue as false positive."""
    compliance_service.mark_false_positive(issue_id)
    return {"message": "Issue marked as false positive", "id": issue_id}
