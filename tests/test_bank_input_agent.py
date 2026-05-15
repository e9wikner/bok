"""Tests for bank input storage, upload APIs, and agent bank context."""

from io import BytesIO
from pathlib import Path
import hashlib

import pytest
from fastapi import HTTPException

from api.routes.bank_inputs import get_bank_input_file, upload_bank_input
from config import settings
from db.database import db
from domain.types import BankInputStatus
from repositories.bank_input_repo import BankInputRepository
from services.bank_inputs import (
    BankInputFileAccessError,
    BankInputService,
    DuplicateBankInputError,
)
from services.bank_integration import BankIntegrationService


@pytest.fixture
def bank_input_dir(tmp_path):
    """Use isolated bank input storage for each test."""
    original = settings.bank_input_dir
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    yield Path(settings.bank_input_dir)
    settings.bank_input_dir = original


class _UploadFile:
    def __init__(self, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)


def _active_connection():
    return BankIntegrationService().create_connection(
        provider="manual",
        bank_name="SEB",
        account_number="****1234",
        currency="SEK",
    )


def test_bank_input_service_persists_pending_csv_metadata(test_db, bank_input_dir):
    conn = _active_connection()
    content = b"Datum;Belopp;Text\n2026-03-01;-100,00;Bankavgift"

    bank_input = BankInputService().create_from_upload_content(
        filename="transactions.csv",
        content_type="text/csv",
        content=content,
        bank_connection_id=conn.id,
        actor="api",
    )

    assert bank_input.status == BankInputStatus.PENDING
    assert bank_input.bank_connection_id == conn.id
    assert bank_input.original_filename == "transactions.csv"
    assert bank_input.mime_type == "text/csv"
    assert bank_input.size_bytes == len(content)
    assert bank_input.sha256 == hashlib.sha256(content).hexdigest()
    assert bank_input.uploaded_by == "api"
    assert bank_input.imported_count == 0
    assert bank_input.skipped_count == 0
    assert Path(bank_input.stored_path).exists()

    stored = BankInputRepository.get_bank_input(bank_input.id)
    assert stored is not None
    assert stored.status == BankInputStatus.PENDING
    assert stored.sha256 == bank_input.sha256


def test_bank_input_service_rejects_duplicate_upload(test_db, bank_input_dir):
    conn = _active_connection()
    content = b"Datum;Belopp;Text\n2026-03-01;-100,00;Bankavgift"
    service = BankInputService()
    service.create_from_upload_content(
        filename="transactions.csv",
        content_type="text/csv",
        content=content,
        bank_connection_id=conn.id,
        actor="api",
    )

    with pytest.raises(DuplicateBankInputError) as exc_info:
        service.create_from_upload_content(
            filename="copy.csv",
            content_type="text/csv",
            content=content,
            bank_connection_id=conn.id,
            actor="api",
        )

    assert exc_info.value.code == "duplicate_bank_input"


def test_bank_input_upload_requires_active_connection(test_db, bank_input_dir):
    with pytest.raises(Exception) as exc_info:
        BankInputService().create_from_upload_content(
            filename="transactions.csv",
            content_type="text/csv",
            content=b"Datum;Belopp;Text\n",
            bank_connection_id="missing-connection",
            actor="api",
        )

    assert getattr(exc_info.value, "code") == "bank_connection_not_found"

    conn = _active_connection()
    db.execute("UPDATE bank_connections SET status = 'expired' WHERE id = ?", (conn.id,))
    db.commit()

    with pytest.raises(Exception) as exc_info:
        BankInputService().create_from_upload_content(
            filename="transactions.csv",
            content_type="text/csv",
            content=b"Datum;Belopp;Text\n",
            bank_connection_id=conn.id,
            actor="api",
        )

    assert getattr(exc_info.value, "code") == "inactive_bank_connection"


def test_bank_input_service_rejects_non_csv(test_db, bank_input_dir):
    conn = _active_connection()

    with pytest.raises(Exception) as exc_info:
        BankInputService().create_from_upload_content(
            filename="statement.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4",
            bank_connection_id=conn.id,
            actor="api",
        )

    assert getattr(exc_info.value, "code") == "unsupported_bank_input_file"


def test_bank_input_service_rejects_outside_root_stored_path(test_db, bank_input_dir, tmp_path):
    conn = _active_connection()
    content = b"Datum;Belopp;Text\n2026-03-01;-100,00;Bankavgift"
    service = BankInputService()
    bank_input = service.create_from_upload_content(
        filename="transactions.csv",
        content_type="text/csv",
        content=content,
        bank_connection_id=conn.id,
        actor="api",
    )
    outside_file = tmp_path / "outside.csv"
    outside_file.write_bytes(content)
    db.execute(
        "UPDATE bank_inputs SET stored_path = ? WHERE id = ?",
        (str(outside_file), bank_input.id),
    )
    db.commit()

    tampered = BankInputRepository.get_bank_input(bank_input.id)
    with pytest.raises(BankInputFileAccessError):
        service.resolve_input_file(tampered)


@pytest.mark.asyncio
async def test_bank_input_upload_download_and_error_mapping_api(
    test_db,
    bank_input_dir,
):
    conn = _active_connection()
    content = b"Datum;Belopp;Text\n2026-03-01;-100,00;Bankavgift"

    response = await upload_bank_input(
        file=_UploadFile("transactions.csv", "text/csv", content),
        bank_connection_id=conn.id,
        actor="api",
    )

    assert response["id"]
    assert response["bank_connection_id"] == conn.id
    assert response["status"] == "pending"
    assert response["original_filename"] == "transactions.csv"
    assert response["mime_type"] == "text/csv"
    assert response["size_bytes"] == len(content)
    assert response["sha256"] == hashlib.sha256(content).hexdigest()
    assert response["uploaded_by"] == "api"

    with pytest.raises(HTTPException) as exc_info:
        await upload_bank_input(
            file=_UploadFile("duplicate.csv", "text/csv", content),
            bank_connection_id=conn.id,
            actor="api",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "duplicate_bank_input"

    download = await get_bank_input_file(response["id"], actor="api")
    assert download.status_code == 200
    assert Path(download.path).read_bytes() == content

    outside_file = bank_input_dir.parent / "outside.csv"
    outside_file.write_bytes(content)
    db.execute(
        "UPDATE bank_inputs SET stored_path = ? WHERE id = ?",
        (str(outside_file), response["id"]),
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_bank_input_file(response["id"], actor="api")
    assert exc_info.value.status_code == 403
