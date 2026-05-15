"""Tests for intake source storage and processing APIs."""

from datetime import date
import hashlib
import inspect
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.deps import get_current_actor, verify_api_key
from api.routes.agent import (
    AgentVoucherRequest,
    create_and_post_agent_voucher,
    list_pending_intake_sources,
    record_intake_failed,
)
from api.routes.intake import delete_intake_source, get_intake_source_file, upload_intake_source
from api.routes.intake import get_intake_workspace_detail, list_intake_workspace
from api.routes.vouchers import get_voucher_source_context
from api.schemas import VoucherRowRequest
from config import settings
from db.database import db
from domain.types import IntakeSourceType, IntakeStatus
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.intake_repo import IntakeRepository
from services.ledger import LedgerService
from services.intake import (
    DuplicateIntakeSourceError,
    IntakeConflictError,
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

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)


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

    with pytest.raises(HTTPException) as exc_info:
        await upload_intake_source(
            file=_UploadFile("huge.pdf", "application/pdf", b"x" * (10 * 1024 * 1024 + 1)),
            explanation=None,
            source_type="receipt",
            actor="api",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "file_too_large"

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
async def test_intake_workspace_failed_source_detail_includes_full_error_without_storage_path(
    test_db,
    intake_dir,
):
    service = IntakeService()
    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 failed workspace",
        explanation="Needs review",
        source_type="receipt",
        actor="api",
    )
    service.record_failed(
        source.id,
        summary="Could not process",
        error_detail="Missing supplier name and accounting period",
        warnings=["supplier lookup failed"],
        actor="api",
    )

    workspace = await list_intake_workspace(status="failed", actor="api")
    assert workspace["total"] == 1
    assert workspace["status_counts"]["failed"] == 1
    item = workspace["items"][0]
    assert item["kind"] == "voucher_source"
    assert item["download_url"] == f"/api/v1/intake/{source.id}/file"
    assert item["latest_error_detail"] == "Missing supplier name and accounting period"
    assert "stored_path" not in repr(item)

    detail = await get_intake_workspace_detail("voucher_source", source.id, actor="api")
    assert detail["kind"] == "voucher_source"
    assert detail["processing_attempts"][0]["error_detail"] == (
        "Missing supplier name and accounting period"
    )
    assert "stored_path" not in repr(detail)


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


@pytest.mark.asyncio
async def test_agent_voucher_posts_and_links_single_intake_source(
    test_period,
    intake_dir,
):
    service = IntakeService()
    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 agent posted",
        explanation="Customer payment receipt",
        source_type="receipt",
        actor="api",
    )

    response = await create_and_post_agent_voucher(
        AgentVoucherRequest(
            date=date(2026, 3, 15),
            period_id=test_period.id,
            description="Agent booked receipt",
            reasoning_summary="Receipt matched to sale and VAT",
            intake_source_ids=[source.id],
            rows=[
                VoucherRowRequest(account="1510", debit=12500, credit=0),
                VoucherRowRequest(account="3011", debit=0, credit=10000),
                VoucherRowRequest(account="2610", debit=0, credit=2500),
            ],
        ),
        actor="api",
    )

    assert response["status"] == "posted"
    assert response["created_by"] == "agent"
    assert response["agent"]["posted_directly"] is True
    assert response["agent"]["intake_source_ids"] == [source.id]
    assert response["agent"]["processing_attempt_id"]

    stored_source = IntakeRepository.get_source(source.id)
    assert stored_source is not None
    assert stored_source.status == IntakeStatus.PROCESSED

    links = IntakeRepository.list_links_for_voucher(response["id"])
    assert len(links) == 1
    assert links[0].intake_source_id == source.id
    assert links[0].linked_by == "api"
    assert links[0].link_reason == "agent_posted_voucher"

    attempts = IntakeRepository.list_attempts_for_source(source.id)
    assert len(attempts) == 1
    assert attempts[0].id == response["agent"]["processing_attempt_id"]
    assert attempts[0].status == IntakeStatus.PROCESSED
    assert attempts[0].summary == "Receipt matched to sale and VAT"
    assert attempts[0].voucher_id == response["id"]

    source_context = await get_voucher_source_context(
        response["id"],
        ledger=LedgerService(),
        actor="api",
    )
    assert source_context["source_material"][0]["kind"] == "voucher_source"
    assert source_context["source_material"][0]["download_url"] == (
        f"/api/v1/intake/{source.id}/file"
    )
    assert source_context["processing_notes"][0]["summary"] == (
        "Receipt matched to sale and VAT"
    )
    assert "stored_path" not in repr(source_context)


@pytest.mark.asyncio
async def test_voucher_source_context_correction_chain_includes_reason(
    test_period,
    intake_dir,
):
    response = await create_and_post_agent_voucher(
        AgentVoucherRequest(
            date=date(2026, 3, 20),
            period_id=test_period.id,
            description="Voucher to correct",
            reasoning_summary="Initial agent posting",
            rows=[
                VoucherRowRequest(account="1510", debit=12500, credit=0),
                VoucherRowRequest(account="3011", debit=0, credit=10000),
                VoucherRowRequest(account="2610", debit=0, credit=2500),
            ],
        ),
        actor="api",
    )
    correction = AccountingCorrectionRepository.create(
        original_voucher_id=response["id"],
        corrected_voucher_id="correction-voucher-id",
        correction_reason="Wrong source interpretation",
        corrected_by="api",
    )

    source_context = await get_voucher_source_context(
        response["id"],
        ledger=LedgerService(),
        actor="api",
    )
    assert source_context["correction_chain"][0]["original_voucher_id"] == response["id"]
    assert source_context["correction_chain"][0]["correction_voucher_id"] == (
        correction.corrected_voucher_id
    )
    assert source_context["correction_chain"][0]["correction_reason"] == (
        "Wrong source interpretation"
    )


def test_voucher_source_context_route_requires_current_actor_dependency():
    actor_param = inspect.signature(get_voucher_source_context).parameters["actor"]
    assert actor_param.default.dependency is get_current_actor


@pytest.mark.asyncio
async def test_agent_voucher_without_intake_sources_still_posts_directly(
    test_period,
):
    response = await create_and_post_agent_voucher(
        AgentVoucherRequest(
            date=date(2026, 3, 16),
            period_id=test_period.id,
            description="Agent booked sale without source",
            rows=[
                VoucherRowRequest(account="1510", debit=12500, credit=0),
                VoucherRowRequest(account="3011", debit=0, credit=10000),
                VoucherRowRequest(account="2610", debit=0, credit=2500),
            ],
        ),
        actor="api",
    )

    assert response["status"] == "posted"
    assert response["agent"]["posted_directly"] is True
    assert response["agent"]["intake_source_ids"] == []
    assert response["agent"]["processing_attempt_id"] is None


@pytest.mark.asyncio
async def test_agent_voucher_rejects_duplicate_intake_link(
    test_period,
    intake_dir,
):
    service = IntakeService()
    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 duplicate link",
        explanation=None,
        source_type="receipt",
        actor="api",
    )

    request = AgentVoucherRequest(
        date=date(2026, 3, 17),
        period_id=test_period.id,
        description="Agent booked receipt",
        reasoning_summary="Booked once",
        intake_source_ids=[source.id],
        rows=[
            VoucherRowRequest(account="1510", debit=12500, credit=0),
            VoucherRowRequest(account="3011", debit=0, credit=10000),
            VoucherRowRequest(account="2610", debit=0, credit=2500),
        ],
    )
    first = await create_and_post_agent_voucher(request, actor="api")

    with pytest.raises(HTTPException) as exc_info:
        await create_and_post_agent_voucher(
            request.model_copy(update={"description": "Duplicate booking attempt"}),
            actor="api",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "intake_not_processable"
    assert len(IntakeRepository.list_links_for_voucher(first["id"])) == 1
    assert len(IntakeRepository.list_attempts_for_source(source.id)) == 1


@pytest.mark.asyncio
async def test_agent_voucher_can_link_multiple_intake_sources(
    test_period,
    intake_dir,
):
    service = IntakeService()
    first = service.create_source_from_upload_content(
        filename="receipt-1.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 receipt one",
        explanation=None,
        source_type="receipt",
        actor="api",
    )
    second = service.create_source_from_upload_content(
        filename="receipt-2.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 receipt two",
        explanation=None,
        source_type="receipt",
        actor="api",
    )

    response = await create_and_post_agent_voucher(
        AgentVoucherRequest(
            date=date(2026, 3, 18),
            period_id=test_period.id,
            description="Multiple sources",
            reasoning_summary="Both receipts support this voucher",
            intake_source_ids=[first.id, second.id],
            rows=[
                VoucherRowRequest(account="1510", debit=12500, credit=0),
                VoucherRowRequest(account="3011", debit=0, credit=10000),
                VoucherRowRequest(account="2610", debit=0, credit=2500),
            ],
        ),
        actor="api",
    )

    assert response["status"] == "posted"
    assert response["agent"]["intake_source_ids"] == [first.id, second.id]
    assert len(response["agent"]["processing_attempt_ids"]) == 2
    links = IntakeRepository.list_links_for_voucher(response["id"])
    assert {link.intake_source_id for link in links} == {first.id, second.id}


def test_intake_service_rejects_linking_draft_voucher(
    test_period,
    intake_dir,
):
    service = IntakeService()
    source = service.create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 draft link",
        explanation=None,
        source_type="receipt",
        actor="api",
    )
    voucher = LedgerService().create_voucher(
        series="A",
        date=date(2026, 3, 19),
        period_id=test_period.id,
        description="Draft voucher",
        rows_data=[
            {"account": "1510", "debit": 12500, "credit": 0},
            {"account": "3011", "debit": 0, "credit": 10000},
            {"account": "2610", "debit": 0, "credit": 2500},
        ],
        created_by="agent",
    )

    with pytest.raises(IntakeConflictError) as exc_info:
        service.link_existing_voucher(
            source_id=source.id,
            voucher_id=voucher.id,
            actor="api",
            summary="Attempted draft link",
        )

    assert exc_info.value.code == "voucher_not_posted"
    stored_source = IntakeRepository.get_source(source.id)
    assert stored_source is not None
    assert stored_source.status == IntakeStatus.PENDING
    assert IntakeRepository.list_links_for_voucher(voucher.id) == []
