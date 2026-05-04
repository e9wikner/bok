"""API routes for accounting pattern analysis and backtesting."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from services.accounting_patterns import AccountingPatternAnalysisService

router = APIRouter(prefix="/api/v1/accounting-patterns", tags=["accounting-patterns"])


class AnalyzePatternsRequest(BaseModel):
    fiscal_year_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_examples: int = Field(2, ge=1, le=20)


class EvaluatePatternsRequest(BaseModel):
    name: str = "Backtest aktiva och föreslagna regler"
    fiscal_year_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    candidate_rule_ids: Optional[List[str]] = None
    include_all_suggested: bool = True


class UpdatePatternRequest(BaseModel):
    name: Optional[str] = None
    match_config: Optional[dict] = None
    voucher_template: Optional[dict] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)


@router.post("/analyze", response_model=dict, status_code=status.HTTP_201_CREATED)
async def analyze_patterns(
    request: AnalyzePatternsRequest,
    actor: str = Depends(get_current_actor),
):
    service = AccountingPatternAnalysisService()
    return service.analyze(
        fiscal_year_id=request.fiscal_year_id,
        date_from=request.date_from,
        date_to=request.date_to,
        min_examples=request.min_examples,
        created_by=actor,
    )


@router.get("", response_model=dict)
async def list_patterns(
    status_filter: Optional[str] = Query(None, alias="status"),
    include_examples: bool = Query(False),
):
    service = AccountingPatternAnalysisService()
    patterns = service.list_patterns(status=status_filter, include_examples=include_examples)
    return {"total": len(patterns), "patterns": patterns}


@router.get("/{pattern_id}", response_model=dict)
async def get_pattern(pattern_id: str):
    pattern = AccountingPatternAnalysisService().get_pattern(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern


@router.patch("/{pattern_id}", response_model=dict)
async def update_pattern(
    pattern_id: str,
    request: UpdatePatternRequest,
):
    from repositories.accounting_pattern_repo import AccountingPatternRepository

    pattern = AccountingPatternRepository.update(
        pattern_id=pattern_id,
        name=request.name,
        match_config=request.match_config,
        voucher_template=request.voucher_template,
        confidence=request.confidence,
    )
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return AccountingPatternAnalysisService().pattern_to_dict(pattern, include_examples=True)


@router.post("/{pattern_id}/approve", response_model=dict)
async def approve_pattern(
    pattern_id: str,
    actor: str = Depends(get_current_actor),
):
    pattern = AccountingPatternAnalysisService().approve(pattern_id, actor)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern


@router.post("/{pattern_id}/reject", response_model=dict)
async def reject_pattern(pattern_id: str):
    pattern = AccountingPatternAnalysisService().reject(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern


@router.post("/evaluations", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    request: EvaluatePatternsRequest,
    actor: str = Depends(get_current_actor),
):
    return AccountingPatternAnalysisService().evaluate(
        name=request.name,
        fiscal_year_id=request.fiscal_year_id,
        date_from=request.date_from,
        date_to=request.date_to,
        candidate_rule_ids=request.candidate_rule_ids,
        include_all_suggested=request.include_all_suggested,
        created_by=actor,
    )


@router.get("/evaluations/list", response_model=dict)
async def list_evaluations():
    evaluations = AccountingPatternAnalysisService().list_evaluations()
    return {"total": len(evaluations), "evaluations": evaluations}


@router.get("/evaluations/{evaluation_id}", response_model=dict)
async def get_evaluation(evaluation_id: str):
    evaluation = AccountingPatternAnalysisService().get_evaluation(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation


@router.get("/evaluations/{evaluation_id}/cases", response_model=dict)
async def list_evaluation_cases(
    evaluation_id: str,
    winner: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    cases = AccountingPatternAnalysisService().list_evaluation_cases(
        evaluation_id=evaluation_id,
        winner=winner,
        limit=limit,
    )
    return {"total": len(cases), "cases": cases}
