"""API routes for voucher attachments."""

import os
import uuid
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi import status as http_status
from fastapi.responses import FileResponse

from api.deps import get_current_actor
from db.database import db

router = APIRouter(prefix="/api/v1/vouchers", tags=["attachments"])

_DEFAULT_ATTACHMENTS_DIR = Path(os.environ.get("ATTACHMENTS_DIR", "/app/data/attachments"))
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _get_attachments_dir() -> Path:
    """Get the attachments directory."""
    return _DEFAULT_ATTACHMENTS_DIR


@router.post("/{voucher_id}/attachments", response_model=dict, status_code=http_status.HTTP_201_CREATED)
async def upload_attachment(
    voucher_id: str,
    file: UploadFile = File(...),
    actor: str = Depends(get_current_actor),
):
    """Upload a file attachment to a voucher (image or PDF)."""
    # Verify voucher exists
    row = db.execute("SELECT id FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Voucher not found")

    # Validate mime type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{content_type}' not allowed. Allowed: JPEG, PNG, GIF, WebP, PDF"
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    # Compute hash
    sha256 = hashlib.sha256(content).hexdigest()

    # Check for duplicate
    existing = db.execute(
        "SELECT id FROM attachments WHERE voucher_id = ? AND sha256 = ?",
        (voucher_id, sha256)
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="This file is already attached to this voucher")

    # Store file
    attachment_id = str(uuid.uuid4())
    ext = Path(file.filename or "file").suffix or _ext_from_mime(content_type)
    stored_filename = f"{attachment_id}{ext}"
    voucher_dir = _get_attachments_dir() / voucher_id
    voucher_dir.mkdir(parents=True, exist_ok=True)
    stored_path = voucher_dir / stored_filename

    with open(stored_path, "wb") as f:
        f.write(content)

    # Insert DB record
    db.execute(
        """INSERT INTO attachments (id, voucher_id, filename, sha256, mime_type, stored_path, size_bytes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (attachment_id, voucher_id, file.filename, sha256, content_type, str(stored_path), len(content))
    )
    db.commit()

    return {
        "id": attachment_id,
        "voucher_id": voucher_id,
        "filename": file.filename,
        "mime_type": content_type,
        "size_bytes": len(content),
    }


@router.get("/{voucher_id}/attachments", response_model=dict)
async def list_attachments(voucher_id: str):
    """List all attachments for a voucher."""
    rows = db.execute(
        "SELECT id, filename, mime_type, size_bytes, uploaded_at FROM attachments WHERE voucher_id = ? ORDER BY uploaded_at",
        (voucher_id,)
    ).fetchall()

    return {
        "voucher_id": voucher_id,
        "total": len(rows),
        "attachments": [
            {
                "id": r["id"],
                "filename": r["filename"],
                "mime_type": r["mime_type"],
                "size_bytes": r["size_bytes"],
                "uploaded_at": r["uploaded_at"],
            }
            for r in rows
        ]
    }


@router.get("/{voucher_id}/attachments/{attachment_id}")
async def get_attachment(voucher_id: str, attachment_id: str):
    """Download/view an attachment file."""
    row = db.execute(
        "SELECT filename, mime_type, stored_path FROM attachments WHERE id = ? AND voucher_id = ?",
        (attachment_id, voucher_id)
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")

    stored_path = Path(row["stored_path"])
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing from storage")

    return FileResponse(
        path=str(stored_path),
        media_type=row["mime_type"],
        filename=row["filename"],
    )


@router.delete("/{voucher_id}/attachments/{attachment_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    voucher_id: str,
    attachment_id: str,
    actor: str = Depends(get_current_actor),
):
    """Delete an attachment. Only allowed on draft vouchers."""
    # Check voucher status
    voucher = db.execute("SELECT status FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")
    if voucher["status"] == "posted":
        raise HTTPException(status_code=400, detail="Cannot delete attachments from posted vouchers")

    row = db.execute(
        "SELECT stored_path FROM attachments WHERE id = ? AND voucher_id = ?",
        (attachment_id, voucher_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Delete file
    stored_path = Path(row["stored_path"])
    if stored_path.exists():
        stored_path.unlink()

    # Delete DB record
    db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    db.commit()


def _ext_from_mime(mime_type: str) -> str:
    """Get file extension from mime type."""
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }.get(mime_type, ".bin")
