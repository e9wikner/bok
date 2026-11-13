"""API routes for SIE4 import."""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from api.deps import get_current_actor, verify_api_key
from config import settings
from domain.validation import ValidationError
from services.sie4_import import SIE4Importer, SIE4Parser

router = APIRouter(prefix="/api/v1/import", tags=["import"])


async def _read_sie4_content(
    request: Request, file: Optional[UploadFile]
) -> tuple[str, Optional[str]]:
    if file:
        return SIE4Parser.decode_bytes(await file.read()), None

    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        content = payload.get("content")
        if content:
            return content, payload.get("fiscal_year_id")

    raise HTTPException(
        status_code=422,
        detail="Provide either a SIE4 file upload or JSON content",
    )


@router.post("/sie4", status_code=status.HTTP_200_OK)
async def import_sie4(
    request: Request,
    fiscal_year_id: Optional[str] = None,
    file: Optional[UploadFile] = File(None),
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
        text_content, body_fiscal_year_id = await _read_sie4_content(request, file)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode file - unsupported encoding",
        )
    target_fiscal_year_id = fiscal_year_id or body_fiscal_year_id

    # Validate the target fiscal year before any import writes occur.
    importer = SIE4Importer(
        api_url=settings.api_url,
        api_key=api_key,
    )
    preview_data = importer.parser.parse_content(text_content)
    encoding_issues = SIE4Parser.find_encoding_issues(preview_data)
    if encoding_issues:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "SIE4 file contains suspicious text encoding artifacts",
                "encoding_issues": encoding_issues,
                "hint": "Check the file encoding. SIE #FORMAT PC8 should be decoded as CP437.",
            },
        )
    try:
        resolved_fiscal_year_id = importer.resolve_fiscal_year(
            preview_data, target_fiscal_year_id
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
                "fiscal_year": {
                    "start": (
                        preview_data.fiscal_year_start.isoformat()
                        if preview_data.fiscal_year_start
                        else None
                    ),
                    "end": (
                        preview_data.fiscal_year_end.isoformat()
                        if preview_data.fiscal_year_end
                        else None
                    ),
                },
            },
        )

    # Run the synchronous importer in a thread pool to avoid blocking
    # the async event loop during database-heavy imports.
    import asyncio

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(
        None,
        importer.import_content,
        text_content,
        resolved_fiscal_year_id,
    )

    return {
        "success": success,
        "imported": importer.imported,
        "errors": importer.errors,
        "warnings": importer.warnings,
        "parser_errors": importer.parser.errors,
        "fiscal_year": importer.fiscal_year_resolution,
    }


@router.post("/sie4/validate", status_code=status.HTTP_200_OK)
async def validate_sie4(
    request: Request,
    file: Optional[UploadFile] = File(None),
    actor: str = Depends(get_current_actor),
):
    """
    Validate a SIE4 file without importing.

    Returns parsing results and any validation errors.
    """
    try:
        text_content, _ = await _read_sie4_content(request, file)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode file",
        )

    parser = SIE4Parser()
    data = parser.parse_content(text_content)

    # Validate
    errors = parser.errors
    encoding_issues = SIE4Parser.find_encoding_issues(data)
    errors.extend(encoding_issues)

    # Check for required fields
    if not data.fiscal_year_start or not data.fiscal_year_end:
        errors.append("Missing valid #RAR 0 fiscal year interval")

    if not data.vouchers:
        errors.append("No vouchers found in file")

    # Check voucher balance
    for voucher in data.vouchers:
        total = sum(row.amount for row in voucher.rows)
        if total != 0:
            errors.append(
                f"Voucher {voucher.series}{voucher.number} is unbalanced: {total}"
            )

    return {
        "valid": len(errors) == 0,
        "company": {
            "name": data.company.name if data.company else None,
            "org_number": data.company.org_number if data.company else None,
        },
        "fiscal_year": {
            "start": (
                data.fiscal_year_start.isoformat() if data.fiscal_year_start else None
            ),
            "end": (data.fiscal_year_end.isoformat() if data.fiscal_year_end else None),
        },
        "statistics": {
            "accounts": len(data.accounts),
            "vouchers": len(data.vouchers),
        },
        "errors": errors,
        "encoding_issues": encoding_issues,
    }
