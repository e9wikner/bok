"""API routes exposing accounting corrections to agents."""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_actor
from repositories.learning_repo import LearningRepository
from repositories.voucher_repo import VoucherRepository

router = APIRouter(prefix="/api/v1/accounting-corrections", tags=["accounting-corrections"])


@router.get("", response_model=dict)
async def list_accounting_corrections(
    limit: int = Query(100, ge=1, le=500),
    actor: str = Depends(get_current_actor),
):
    """List correction history for agent learning."""
    try:
        histories = LearningRepository.get_correction_history()[:limit]
        from api.routes.vouchers import _voucher_to_response

        corrections = []
        for history in histories:
            original = VoucherRepository.get(history.original_voucher_id)
            corrected = (
                VoucherRepository.get(history.corrected_voucher_id)
                if history.corrected_voucher_id
                else None
            )
            corrections.append(
                {
                    "id": history.id,
                    "original_voucher_id": history.original_voucher_id,
                    "corrected_voucher_id": history.corrected_voucher_id,
                    "change_type": history.change_type,
                    "correction_reason": history.correction_reason,
                    "corrected_by": history.corrected_by,
                    "created_at": history.created_at,
                    "original_data": history.original_data,
                    "corrected_data": history.corrected_data,
                    "original_voucher": _voucher_to_response(original).model_dump()
                    if original
                    else None,
                    "correction_voucher": _voucher_to_response(corrected).model_dump()
                    if corrected
                    else None,
                }
            )
        return {"total": len(corrections), "corrections": corrections}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
