"""Tests for intake source storage and processing APIs."""

import hashlib
from pathlib import Path

import pytest

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
