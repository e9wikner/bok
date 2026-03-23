"""API routes for AI learning and corrections."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from typing import List, Optional

from api.schemas import (
    CorrectionRequest,
    LearningRuleResponse,
    LearningStatsResponse,
    AccountSuggestionResponse,
    ErrorResponse,
)
from api.deps import get_current_actor
from services.learning import LearningService
from services.ledger import LedgerService
from repositories.learning_repo import LearningRepository

router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


def get_learning_service() -> LearningService:
    """Dependency to get learning service."""
    return LearningService()


def get_ledger_service() -> LedgerService:
    """Dependency to get ledger service."""
    return LedgerService()


@router.post("/corrections", response_model=LearningRuleResponse, status_code=http_status.HTTP_201_CREATED)
async def record_correction(
    request: CorrectionRequest,
    learning: LearningService = Depends(get_learning_service),
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """Record a correction and learn from it.
    
    When a user corrects a voucher, this endpoint:
    1. Analyzes what changed between original and corrected
    2. Creates or updates a learning rule
    3. Records the correction in history
    
    Example:
    ```json
    {
      "original_voucher_id": "voucher-uuid",
      "reason": "Wrong account - should be travel expenses",
      "teach_ai": true,
      "corrected_rows": [
        {"account": "5610", "debit": 50000, "credit": 0},
        {"account": "1930", "debit": 0, "credit": 50000}
      ]
    }
    ```
    """
    try:
        # Get original voucher
        original = learning.vouchers.get(request.original_voucher_id)
        if not original:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Original voucher {request.original_voucher_id} not found"
            )
        
        # Create corrected voucher if needed
        if request.corrected_voucher_id:
            corrected = learning.vouchers.get(request.corrected_voucher_id)
            if not corrected:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Corrected voucher {request.corrected_voucher_id} not found"
                )
        else:
            # Create a correction voucher (B-series)
            corrected = ledger.create_correction(
                original_voucher_id=original.id,
                created_by=actor
            )
            
            # Add the corrected rows
            rows_data = [r.dict() for r in request.corrected_rows]
            for row_data in rows_data:
                learning.vouchers.add_row(
                    voucher_id=corrected.id,
                    account_code=row_data['account'],
                    debit=row_data.get('debit', 0),
                    credit=row_data.get('credit', 0),
                    description=row_data.get('description'),
                )
        
        if request.teach_ai:
            # Learn from the correction
            rule = learning.learn_from_correction(
                original_voucher=original,
                corrected_voucher=corrected,
                correction_reason=request.reason,
                corrected_by=actor,
            )
            return _rule_to_response(rule)
        else:
            # Just record history without learning
            history = learning.rules.create_correction_history(
                original_voucher_id=original.id,
                corrected_voucher_id=corrected.id,
                corrected_by=actor,
                correction_reason=request.reason,
            )
            # Return a dummy rule (no learning occurred)
            return LearningRuleResponse(
                id="none",
                pattern_type="none",
                pattern_value="none",
                corrected_account="",
                confidence=0.0,
                usage_count=0,
                success_count=0,
                is_golden=False,
                is_active=False,
                created_at=history.created_at,
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/rules")
async def list_rules(
    active_only: bool = Query(True, description="Only show active rules"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    pattern_type: Optional[str] = Query(None, description="Filter by pattern type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
):
    """List all learned rules with optional filters."""
    try:
        repo = LearningRepository()
        rules = repo.list_rules(
            active_only=active_only,
            min_confidence=min_confidence,
            pattern_type=pattern_type,
            limit=limit,
        )
        rule_responses = [_rule_to_response(r) for r in rules]
        return {
            "total": len(rule_responses),
            "rules": rule_responses,
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/rules/{rule_id}", response_model=LearningRuleResponse)
async def get_rule(rule_id: str):
    """Get a specific learning rule with its history."""
    try:
        repo = LearningRepository()
        rule = repo.get_rule(rule_id)
        
        if not rule:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Rule {rule_id} not found"
            )
        
        return _rule_to_response(rule)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/rules/{rule_id}/confirm", response_model=LearningRuleResponse)
async def confirm_rule(
    rule_id: str,
    actor: str = Depends(get_current_actor),
):
    """Confirm a rule as correct (sets is_golden flag).
    
    Only accountants should confirm rules. Once confirmed, the rule
    has maximum confidence and won't be auto-deactivated.
    """
    try:
        learning = LearningService()
        
        rule = learning.rules.get_rule(rule_id)
        if not rule:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Rule {rule_id} not found"
            )
        
        learning.confirm_rule(rule_id, actor)
        
        # Refresh rule data
        rule = learning.rules.get_rule(rule_id)
        return _rule_to_response(rule)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/rules/{rule_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def deactivate_rule(
    rule_id: str,
    actor: str = Depends(get_current_actor),
):
    """Deactivate a rule that has proven to be incorrect."""
    try:
        learning = LearningService()
        
        rule = learning.rules.get_rule(rule_id)
        if not rule:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Rule {rule_id} not found"
            )
        
        learning.deactivate_rule(rule_id)
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/stats", response_model=LearningStatsResponse)
async def get_stats():
    """Get statistics about AI learning.
    
    Returns:
    - Total number of rules
    - Active rules count
    - Average confidence
    - Golden (confirmed) rules
    - Recent corrections
    - Top rules by confidence
    """
    try:
        learning = LearningService()
        stats = learning.get_learning_stats()
        
        return LearningStatsResponse(
            total_rules=stats['total_rules'],
            active_rules=stats['active_rules'],
            golden_rules=stats['golden_rules'],
            avg_confidence=stats['avg_confidence'],
            recent_corrections=stats['recent_corrections'],
            top_rules=[_rule_to_response(r) for r in stats['top_rules']],
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/suggest", response_model=AccountSuggestionResponse)
async def suggest_account(
    description: str = Query(..., description="Transaction description"),
    counterparty: Optional[str] = Query(None, description="Counterparty name"),
    amount: Optional[int] = Query(None, description="Amount in öre"),
    suggested_account: Optional[str] = Query(None, description="Currently suggested account (if any)"),
):
    """Suggest account code based on learned rules.
    
    Returns a suggestion only if there's a high-confidence rule (>0.8).
    Otherwise returns empty suggestion.
    """
    try:
        learning = LearningService()
        result = learning.apply_learning(
            transaction_description=description,
            suggested_account=suggested_account,
            counterparty=counterparty,
            amount=amount,
        )
        
        if result:
            account, confidence, rule_id = result
            rule = learning.rules.get_rule(rule_id)
            return AccountSuggestionResponse(
                suggested_account=account,
                confidence=confidence,
                rule_id=rule_id,
                description=rule.description if rule else None,
            )
        
        return AccountSuggestionResponse()
    
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _rule_to_response(rule) -> LearningRuleResponse:
    """Convert LearningRule to response model."""
    return LearningRuleResponse(
        id=rule.id,
        pattern_type=rule.pattern_type,
        pattern_value=rule.pattern_value,
        original_account=rule.original_account,
        corrected_account=rule.corrected_account,
        description=rule.description,
        confidence=rule.confidence,
        usage_count=rule.usage_count,
        success_count=rule.success_count,
        is_golden=rule.is_golden,
        is_active=rule.is_active,
        source_voucher_id=rule.source_voucher_id,
        created_by=rule.created_by,
        created_at=rule.created_at,
        last_used=rule.last_used,
        last_confirmed=rule.last_confirmed,
    )
# Force container restart on next deploy
