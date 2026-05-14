"""Tests for intake source storage and processing APIs."""

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.deps import verify_api_key
from api.routes.agent import list_pending_intake_sources, record_intake_failed
from api.routes.intake import delete_intake_source, get_intake_source_file, upload_intake_source
from config import settings
from db.database import db
from domain.types import IntakeSourceType, IntakeStatus
from repositories.intake_repo import IntakeRepository
from services.intake import (
    DuplicateIntakeSourceError,
    IntakeFileAccessError,
    IntakeService,
)


@pytest.fixture
def intake_dir(tmp_path):
    """Use isolated intake storage for each test."""
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    yield Path(settings.intake_dir)
    settings.intake_dir = original


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


class _UploadFile:
    def __init__(self, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)


def test_intake_service_persists_pending_source_metadata(test_db, intake_dir):
    content = b"%PDF-1.4 test receipt"
    service = IntakeService()

    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=content,
        explanation="Lunch receipt",
        source_type="receipt",
        actor="api",
    )

    assert source.status == IntakeStatus.PENDING
    assert source.original_filename == "receipt.pdf"
    assert source.mime_type == "application/pdf"
    assert source.size_bytes == len(content)
    assert source.sha256 == hashlib.sha256(content).hexdigest()
    assert source.explanation == "Lunch receipt"
    assert source.source_type == IntakeSourceType.RECEIPT
    assert source.uploaded_by == "api"
    assert Path(source.stored_path).exists()

    stored = IntakeRepository.get_source(source.id)
    assert stored is not None
    assert stored.status == IntakeStatus.PENDING
    assert stored.sha256 == source.sha256


def test_intake_service_rejects_duplicate_upload_and_keeps_one_pending_source(
    test_db,
    intake_dir,
):
    content = b"%PDF-1.4 duplicate receipt"
    service = IntakeService()
    service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=content,
        explanation=None,
        source_type="receipt",
        actor="api",
    )

    with pytest.raises(DuplicateIntakeSourceError):
        service.create_source_from_upload_content(
            filename="same.pdf",
            content_type="application/pdf",
            content=content,
            explanation=None,
            source_type="receipt",
            actor="api",
        )

    assert IntakeRepository.count_pending() == 1


def test_intake_service_rejects_outside_root_stored_path(test_db, intake_dir, tmp_path):
    content = b"%PDF-1.4 path safety"
    service = IntakeService()
    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=content,
        explanation=None,
        source_type="receipt",
        actor="api",
    )
    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(content)
    db.execute(
        "UPDATE intake_sources SET stored_path = ? WHERE id = ?",
        (str(outside_file), source.id),
    )
    db.commit()

    tampered = IntakeRepository.get_source(source.id)
    with pytest.raises(IntakeFileAccessError):
        service.resolve_source_file(tampered)


@pytest.mark.asyncio
async def test_intake_upload_download_pending_and_soft_delete_api(
    test_db,
    intake_dir,
    auth_headers,
):
    content = b"%PDF-1.4 api receipt"
    source = await upload_intake_source(
        file=_UploadFile("receipt.pdf", "application/pdf", content),
        explanation="API receipt",
        source_type="receipt",
        actor="api",
    )
    assert source["id"]
    assert source["status"] == "pending"
    assert source["original_filename"] == "receipt.pdf"
    assert source["mime_type"] == "application/pdf"
    assert source["size_bytes"] == len(content)
    assert source["sha256"] == hashlib.sha256(content).hexdigest()
    assert source["source_type"] == "receipt"
    assert source["explanation"] == "API receipt"
    assert source["uploaded_by"] == "api"
    assert source["uploaded_at"]

    with pytest.raises(HTTPException) as exc_info:
        await upload_intake_source(
            file=_UploadFile("duplicate.pdf", "application/pdf", content),
            explanation=None,
            source_type="receipt",
            actor="api",
        )
    assert exc_info.value.status_code == 409

    pending = await list_pending_intake_sources(actor="api")
    pending_items = pending["items"]
    assert len(pending_items) == 1
    assert pending_items[0]["download_url"] == f"/api/v1/intake/{source['id']}/file"

    download = await get_intake_source_file(source["id"], actor="api")
    assert download.status_code == 200
    assert Path(download.path).read_bytes() == content

    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(None)
    assert exc_info.value.status_code == 401

    deleted = await delete_intake_source(source["id"], actor="api")
    assert deleted is None

    pending = await list_pending_intake_sources(actor="api")
    assert pending["items"] == []

    stored = IntakeRepository.get_source(source["id"])
    assert stored is not None
    assert stored.status == IntakeStatus.DELETED
    assert Path(stored.stored_path).exists()


@pytest.mark.asyncio
async def test_agent_failed_outcome_persists_attempt_and_hides_pending_source(
    test_db,
    intake_dir,
    auth_headers,
):
    service = IntakeService()
    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 failed",
        explanation=None,
        source_type="receipt",
        actor="api",
    )

    with pytest.raises(ValueError):
        from api.routes.agent import AgentFailedRequest

        AgentFailedRequest(summary="Could not process")

    from api.routes.agent import AgentFailedRequest

    attempt = await record_intake_failed(
        source.id,
        AgentFailedRequest(
            summary="Could not process",
            error_detail="Missing accounting period",
            warnings=["period lookup failed"],
        ),
        actor="api",
    )
    assert attempt["status"] == "failed"
    assert attempt["summary"] == "Could not process"
    assert attempt["error_detail"] == "Missing accounting period"
    assert attempt["actor"] == "api"
    assert attempt["created_at"]

    attempts = IntakeRepository.list_attempts_for_source(source.id)
    assert len(attempts) == 1
    assert attempts[0].summary == "Could not process"
    assert attempts[0].error_detail == "Missing accounting period"

    pending = await list_pending_intake_sources(actor="api")
    assert pending["items"] == []


@pytest.mark.asyncio
async def test_intake_file_api_rejects_outside_root_stored_path(
    test_db,
    intake_dir,
    tmp_path,
    auth_headers,
):
    service = IntakeService()
    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 outside",
        explanation=None,
        source_type="receipt",
        actor="api",
    )
    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"outside")
    db.execute(
        "UPDATE intake_sources SET stored_path = ? WHERE id = ?",
        (str(outside_file), source.id),
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_intake_source_file(source.id, actor="api")
    assert exc_info.value.status_code == 403
