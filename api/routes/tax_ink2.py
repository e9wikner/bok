"""API routes for tax declaration presentation data."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_current_actor, verify_api_key
from services.ink2_declaration import build_ink2_declaration

router = APIRouter(prefix="/api/v1/tax", tags=["tax"])


@router.get("/ink2/{fiscal_year_id}")
async def get_ink2_declaration(
    fiscal_year_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """Return web-facing INK2/INK2R/INK2S declaration sections for a fiscal year."""
    try:
        return build_ink2_declaration(fiscal_year_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not build INK2 declaration: {str(exc)}",
        )
