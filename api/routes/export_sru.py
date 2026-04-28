"""API routes for SRU export (INK2 tax declaration)."""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from typing import Optional

from api.deps import get_current_actor, verify_api_key
from services.sru_export import export_sru_for_fiscal_year

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/sru/{fiscal_year_id}")
async def export_sru(
    fiscal_year_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    Export INK2 tax declaration in SRU format.
    
    Generates INFO.SRU and BLANKETTER.SRU files for Swedish tax filing.
    Returns a ZIP file containing both files.
    
    The SRU format is used for electronic submission to Skatteverket.
    """
    try:
        zip_bytes, filename, errors, warnings = export_sru_for_fiscal_year(fiscal_year_id)
        
        if not zip_bytes:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Export failed: {'; '.join(errors)}"
            )
        
        # Return ZIP file
        # Sanitize warnings for HTTP headers (latin-1 encoding only)
        safe_warnings = "; ".join(warnings).replace('≠', '!=') if warnings else "none"
        safe_filename = filename.encode('ascii', 'ignore').decode('ascii')
        
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "X-Export-Warnings": safe_warnings,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.get("/sru/{fiscal_year_id}/preview")
async def preview_sru(
    fiscal_year_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    Preview INK2 tax declaration data without generating files.
    
    Returns all SRU field values and validation results.
    Useful for reviewing data before actual export.
    """
    from services.sru_export import SRUExportService
    
    try:
        service = SRUExportService()
        declaration = service.calculate_sru_fields(fiscal_year_id)
        
        # Convert to serializable format
        fields_data = []
        for field_number in sorted(declaration.fields.keys()):
            field = declaration.fields[field_number]
            fields_data.append({
                "field_number": field.field_number,
                "description": field.description,
                "value": field.value,
                "source_accounts": field.source_accounts,
                "source_account_values": field.source_account_values or [],
            })
        
        return {
            "fiscal_year_id": declaration.fiscal_year_id,
            "company": {
                "org_number": declaration.company_org_number,
                "name": declaration.company_name,
            },
            "fiscal_year": {
                "start": declaration.fiscal_year_start,
                "end": declaration.fiscal_year_end,
            },
            "fields": fields_data,
            "validation": {
                "errors": service.errors,
                "warnings": service.warnings,
                "is_valid": len(service.errors) == 0,
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preview failed: {str(e)}"
        )
