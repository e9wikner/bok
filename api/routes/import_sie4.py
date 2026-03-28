"""API routes for SIE4 import."""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import Optional

from api.deps import get_current_actor, verify_api_key
from services.sie4_import import SIE4Importer, create_sample_sie4

try:
    from db.tenant_context import get_current_tenant
except ImportError:
    get_current_tenant = None  # type: ignore[assignment]
from config import settings

router = APIRouter(prefix="/api/v1/import", tags=["import"])


@router.post("/sie4", status_code=status.HTTP_200_OK)
async def import_sie4(
    fiscal_year_id: Optional[str] = None,
    file: UploadFile = File(...),
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    Import accounting data from SIE4 format file.
    
    SIE (Standard Import/Export) is the Swedish standard for 
    exchanging accounting data between systems.
    
    - **file**: SIE4 file (.si, .sie, or .txt extension)
    - **fiscal_year_id**: Optional target fiscal year (auto-detected if not provided)
    
    Returns import statistics and any errors.
    """
    try:
        # Read file content
        content = await file.read()
        
        # Try different encodings
        encodings = ['windows-1252', 'iso-8859-1', 'utf-8']
        text_content = None
        
        for encoding in encodings:
            try:
                text_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if text_content is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not decode file - unsupported encoding"
            )
        
        # Determine tenant context for internal API calls
        tenant_id = None
        if settings.multi_tenant and get_current_tenant is not None:
            tenant_id = get_current_tenant()

        # Import — pass the caller's api_key and tenant so internal
        # sub-requests are authenticated for the correct tenant
        importer = SIE4Importer(
            api_url=settings.api_url,
            api_key=api_key,
            tenant_id=tenant_id,
        )
        
        # Run the synchronous importer in a thread pool to avoid blocking
        # the async event loop (importer makes blocking HTTP sub-requests)
        import asyncio
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, importer.import_content, text_content, fiscal_year_id
        )
        
        return {
            "success": success,
            "imported": importer.imported,
            "errors": importer.errors,
            "parser_errors": importer.parser.errors
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}"
        )


@router.get("/sie4/sample", status_code=status.HTTP_200_OK)
async def get_sie4_sample(
    actor: str = Depends(get_current_actor),
):
    """Get a sample SIE4 file for testing import functionality."""
    return {
        "content": create_sample_sie4(),
        "description": "Sample SIE4 file with 3 vouchers for testing",
        "format": "SIE4"
    }


@router.post("/sie4/validate", status_code=status.HTTP_200_OK)
async def validate_sie4(
    file: UploadFile = File(...),
    actor: str = Depends(get_current_actor),
):
    """
    Validate a SIE4 file without importing.
    
    Returns parsing results and any validation errors.
    """
    try:
        content = await file.read()
        
        encodings = ['windows-1252', 'iso-8859-1', 'utf-8']
        text_content = None
        
        for encoding in encodings:
            try:
                text_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if text_content is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not decode file"
            )
        
        from services.sie4_import import SIE4Parser
        parser = SIE4Parser()
        data = parser.parse_content(text_content)
        
        # Validate
        errors = parser.errors
        
        # Check for required fields
        if not data.vouchers:
            errors.append("No vouchers found in file")
        
        # Check voucher balance
        for voucher in data.vouchers:
            total = sum(row.amount for row in voucher.rows)
            if total != 0:
                errors.append(f"Voucher {voucher.series}{voucher.number} is unbalanced: {total}")
        
        return {
            "valid": len(errors) == 0,
            "company": {
                "name": data.company.name if data.company else None,
                "org_number": data.company.org_number if data.company else None,
            },
            "fiscal_year": {
                "start": data.fiscal_year_start.isoformat() if data.fiscal_year_start else None,
                "end": data.fiscal_year_end.isoformat() if data.fiscal_year_end else None,
            },
            "statistics": {
                "accounts": len(data.accounts),
                "vouchers": len(data.vouchers),
            },
            "errors": errors
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )
