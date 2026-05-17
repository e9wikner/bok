"""Tests for bank input storage, upload APIs, and agent bank context."""

from datetime import date
from io import BytesIO
from pathlib import Path
import hashlib

import pytest
from fastapi import HTTPException
from pydantic import ValidationError as PydanticValidationError

from api.routes.agent import (
    AgentVoucherRequest,
    create_and_post_agent_voucher,
    list_pending_intake_sources,
)
from api.routes.bank_inputs import get_bank_input_file, list_bank_input_connections, upload_bank_input
from api.routes.intake import get_intake_workspace_detail, list_intake_workspace
from api.routes.vouchers import get_voucher_source_context
from api.schemas import VoucherRowRequest
from config import settings
from db.database import db
from domain.types import BankInputStatus
from repositories.intake_repo import IntakeRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.voucher_repo import VoucherRepository
from services.bank_inputs import (
    BankInputConflictError,
    BankInputFileAccessError,
    BankInputService,
    DuplicateBankInputError,
)
from services.bank_integration import BankIntegrationService
from services.intake import IntakeService
from services.ledger import LedgerService
from services.opening_balance import OpeningBalanceService


@pytest.fixture
def bank_input_dir(tmp_path):
    """Use isolated bank input storage for each test."""
    original = settings.bank_input_dir
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    yield Path(settings.bank_input_dir)
    settings.bank_input_dir = original


@pytest.fixture
def intake_dir(tmp_path):
    """Use isolated ordinary intake storage for mixed source tests."""
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    yield Path(settings.intake_dir)
    settings.intake_dir = original


class _UploadFile:
    def __init__(self, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)


def _active_connection():
    return BankIntegrationService().create_connection(
        provider="manual",
        bank_name="SEB",
        account_number="****1234",
        currency="SEK",
    )


def _processed_bank_input(content: bytes | None = None):
    conn = _active_connection()
    bank_input = BankInputService().create_from_upload_content(
        filename="transactions.csv",
        content_type="text/csv",
        content=content or b"Datum;Belopp;Text\n2026-03-01;100,00;Kundbetalning",
        bank_connection_id=conn.id,
        actor="api",
    )
    transaction_ids = BankInputRepository.list_transaction_ids_for_input(bank_input.id)
    return bank_input, transaction_ids


def _agent_sale_request(period_id: str, amount: int = 10000, **kwargs) -> AgentVoucherRequest:
    return AgentVoucherRequest(
        date=date(2026, 3, 1),
        period_id=period_id,
        description="Agent bank-driven sale",
        reasoning_summary="Bank transaction matched to sales voucher",
        rows=[
            VoucherRowRequest(account="1510", debit=amount, credit=0),
            VoucherRowRequest(account="3011", debit=0, credit=amount),
        ],
        **kwargs,
    )


def test_agent_voucher_request_rejects_invalid_series():
    with pytest.raises(PydanticValidationError):
        _agent_sale_request("period-id", series="X")


def test_bank_input_service_persists_processed_csv_metadata(test_db, bank_input_dir):
    conn = _active_connection()
    content = b"Datum;Belopp;Text\n2026-03-01;-100,00;Bankavgift"

    bank_input = BankInputService().create_from_upload_content(
        filename="transactions.csv",
        content_type="text/csv",
        content=content,
        bank_connection_id=conn.id,
        actor="api",
    )

    assert bank_input.status == BankInputStatus.PROCESSED
    assert bank_input.bank_connection_id == conn.id
    assert bank_input.original_filename == "transactions.csv"
    assert bank_input.mime_type == "text/csv"
    assert bank_input.size_bytes == len(content)
    assert bank_input.sha256 == hashlib.sha256(content).hexdigest()
    assert bank_input.uploaded_by == "api"
    assert bank_input.detected_format == "swedish_standard_semicolon"
    assert bank_input.imported_count == 1
    assert bank_input.skipped_count == 0
    assert Path(bank_input.stored_path).exists()

    stored = BankInputRepository.get_bank_input(bank_input.id)
    assert stored is not None
    assert stored.status == BankInputStatus.PROCESSED
    assert stored.sha256 == bank_input.sha256
    assert BankInputRepository.count_transactions_for_input(bank_input.id) == 1


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


@pytest.mark.asyncio
async def test_bank_input_connections_selector_returns_active_display_fields(test_db):
    active = _active_connection()
    inactive = BankIntegrationService().create_connection(
        provider="manual",
        bank_name="Nordea",
        account_number="****9999",
        iban="SE999",
        currency="SEK",
    )
    db.execute("UPDATE bank_connections SET status = 'expired' WHERE id = ?", (inactive.id,))
    db.commit()

    response = await list_bank_input_connections(actor="api")
    items = response["items"]
    assert [item["id"] for item in items] == [active.id]
    assert items[0]["bank_name"] == active.bank_name
    assert items[0]["account_number"] == active.account_number
    assert items[0]["currency"] == "SEK"
    assert items[0]["status"] == "active"

    route_paths = [route.path for route in list_bank_input_connections.__globals__["router"].routes]
    assert route_paths.index("/api/v1/bank-inputs/connections") < route_paths.index(
        "/api/v1/bank-inputs/{bank_input_id}"
    )


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


def test_bank_input_upload_marks_unsupported_csv_failed(test_db, bank_input_dir):
    conn = _active_connection()

    bank_input = BankInputService().create_from_upload_content(
        filename="transactions.csv",
        content_type="text/csv",
        content=b"When;Value;Memo\n2026-03-01;-100,00;Bankavgift",
        bank_connection_id=conn.id,
        actor="api",
    )

    assert bank_input.status == BankInputStatus.FAILED
    assert bank_input.imported_count == 0
    assert bank_input.skipped_count == 0
    assert bank_input.parse_error is not None
    assert "unsupported_bank_csv_format" in bank_input.parse_error
    assert Path(bank_input.stored_path).exists()


def test_bank_input_upload_records_duplicate_transaction_skip_count(test_db, bank_input_dir):
    conn = _active_connection()

    bank_input = BankInputService().create_from_upload_content(
        filename="transactions.csv",
        content_type="text/csv",
        content="\n".join(
            [
                "Datum;Belopp;Text",
                "2026-03-01;-100,00;Bankavgift",
                "2026-03-01;-100,00;Bankavgift",
            ]
        ).encode(),
        bank_connection_id=conn.id,
        actor="api",
    )

    assert bank_input.status == BankInputStatus.PROCESSED
    assert bank_input.imported_count == 1
    assert bank_input.skipped_count == 1
    assert BankInputRepository.count_transactions_for_input(bank_input.id) == 1


def test_bank_csv_import_detects_supported_format_and_reports_details(test_db):
    conn = _active_connection()
    result = BankIntegrationService().import_csv(
        conn.id,
        "Datum;Belopp;Text\n2026-03-01;-100,00;Bankavgift\n",
    )

    assert result.detected_format == "swedish_standard_semicolon"
    assert result.imported_count == 1
    assert result.skipped_count == 0
    assert len(result.imported_transaction_ids) == 1


def test_bank_csv_import_rejects_unsupported_format(test_db):
    conn = _active_connection()

    with pytest.raises(Exception) as exc_info:
        BankIntegrationService().import_csv(
            conn.id,
            "When;Value;Memo\n2026-03-01;-100,00;Bankavgift\n",
        )

    assert getattr(exc_info.value, "code") == "unsupported_bank_csv_format"


def test_bank_csv_import_reports_duplicate_rows(test_db):
    conn = _active_connection()
    result = BankIntegrationService().import_csv(
        conn.id,
        "\n".join(
            [
                "Datum;Belopp;Text",
                "2026-03-01;-100,00;Bankavgift",
                "2026-03-01;-100,00;Bankavgift",
            ]
        ),
    )

    assert result.detected_format == "swedish_standard_semicolon"
    assert result.imported_count == 1
    assert result.skipped_count == 1
    assert len(result.imported_transaction_ids) == 1
    assert result.skipped_external_ids == ["csv-2026-03-01--100.00-Bankavgift"]


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
    assert response["status"] == "processed"
    assert response["original_filename"] == "transactions.csv"
    assert response["mime_type"] == "text/csv"
    assert response["size_bytes"] == len(content)
    assert response["sha256"] == hashlib.sha256(content).hexdigest()
    assert response["uploaded_by"] == "api"
    assert response["detected_format"] == "swedish_standard_semicolon"
    assert response["imported_count"] == 1

    with pytest.raises(HTTPException) as exc_info:
        await upload_bank_input(
            file=_UploadFile("duplicate.csv", "text/csv", content),
            bank_connection_id=conn.id,
            actor="api",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "duplicate_bank_input"

    with pytest.raises(HTTPException) as exc_info:
        await upload_bank_input(
            file=_UploadFile(
                "huge.csv",
                "text/csv",
                b"x" * (10 * 1024 * 1024 + 1),
            ),
            bank_connection_id=conn.id,
            actor="api",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "file_too_large"

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


@pytest.mark.asyncio
async def test_agent_pending_queue_returns_voucher_sources_and_bank_inputs(
    test_db,
    bank_input_dir,
    intake_dir,
):
    source = IntakeService().create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 receipt",
        explanation="Receipt",
        source_type="receipt",
        actor="api",
    )
    bank_input, transaction_ids = _processed_bank_input()

    queue = await list_pending_intake_sources(actor="api")

    assert queue["correction_history_url"] == "/api/v1/accounting-corrections"
    voucher_item = next(item for item in queue["items"] if item["id"] == source.id)
    bank_item = next(item for item in queue["items"] if item["id"] == bank_input.id)
    assert voucher_item["kind"] == "voucher_source"
    assert bank_item["kind"] == "bank_input"
    assert bank_item["transaction_ids"] == transaction_ids
    assert bank_item["transaction_count"] == 1
    assert isinstance(bank_item["match_signals"], list)
    assert "description" not in bank_item["match_signals"][0]


@pytest.mark.asyncio
async def test_agent_pending_queue_applies_combined_limit(
    test_db,
    bank_input_dir,
    intake_dir,
):
    IntakeService().create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 receipt",
        explanation="Receipt",
        source_type="receipt",
        actor="api",
    )
    _processed_bank_input()

    queue = await list_pending_intake_sources(limit=1, offset=0, actor="api")

    assert queue["limit"] == 1
    assert len(queue["items"]) == 1
    assert queue["total"] == 2


@pytest.mark.asyncio
async def test_intake_workspace_returns_voucher_sources_and_bank_inputs_with_filters(
    test_db,
    bank_input_dir,
    intake_dir,
):
    source = IntakeService().create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 workspace receipt",
        explanation="Receipt",
        source_type="receipt",
        actor="api",
    )
    failed_source = IntakeService().create_source_from_upload_content(
        filename="failed.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 failed workspace receipt",
        explanation=None,
        source_type="receipt",
        actor="api",
    )
    IntakeService().record_failed(
        failed_source.id,
        summary="Could not process",
        error_detail="Missing amount",
        actor="api",
    )
    bank_input, transaction_ids = _processed_bank_input()
    failed_bank = BankInputService().create_from_upload_content(
        filename="bad.csv",
        content_type="text/csv",
        content=b"When;Value;Memo\n2026-03-01;-100,00;Bankavgift",
        bank_connection_id=bank_input.bank_connection_id,
        actor="api",
    )

    workspace = await list_intake_workspace(actor="api")
    item_kinds = {item["id"]: item["kind"] for item in workspace["items"]}
    assert item_kinds[source.id] == "voucher_source"
    assert item_kinds[bank_input.id] == "bank_input"
    assert "stored_path" not in repr(workspace)

    failed = await list_intake_workspace(status="failed", actor="api")
    assert {item["id"] for item in failed["items"]} == {failed_source.id, failed_bank.id}
    assert {item["status"] for item in failed["items"]} == {"failed"}

    only_sources = await list_intake_workspace(kind="voucher_source", actor="api")
    assert all(item["kind"] == "voucher_source" for item in only_sources["items"])

    detail = await get_intake_workspace_detail("bank_input", bank_input.id, actor="api")
    assert detail["kind"] == "bank_input"
    assert detail["transaction_ids"] == transaction_ids
    assert detail["transaction_count"] == 1
    assert detail["download_url"] == f"/api/v1/bank-inputs/{bank_input.id}/file"
    assert "stored_path" not in repr(detail)


@pytest.mark.asyncio
async def test_mixed_intake_workspace_paginates_without_skipping_bank_inputs(
    test_db,
    bank_input_dir,
    intake_dir,
):
    source_ids = []
    for index in range(3):
        source = IntakeService().create_source_from_upload_content(
            filename=f"receipt-{index}.pdf",
            content_type="application/pdf",
            content=f"%PDF-1.4 workspace receipt {index}".encode(),
            explanation="Receipt",
            source_type="receipt",
            actor="api",
        )
        source_ids.append(source.id)

    bank_ids = []
    for index in range(3):
        bank_input, _ = _processed_bank_input(
            content=f"Datum;Belopp;Text\n2026-03-0{index + 1};-{index + 1}00,00;Avgift {index}".encode()
        )
        bank_ids.append(bank_input.id)

    seen_ids = []
    for offset in range(0, 6, 2):
        page = await list_intake_workspace(limit=2, offset=offset, actor="api")
        seen_ids.extend(item["id"] for item in page["items"])

    assert set(seen_ids) == set(source_ids + bank_ids)
    assert len(seen_ids) == 6


@pytest.mark.asyncio
async def test_agent_bank_driven_posting_links_input_and_transaction(
    test_period,
    bank_input_dir,
):
    bank_input, transaction_ids = _processed_bank_input()

    response = await create_and_post_agent_voucher(
        _agent_sale_request(
            test_period.id,
            bank_input_ids=[bank_input.id],
            bank_transaction_ids=transaction_ids,
        ),
        actor="api",
    )

    assert response["status"] == "posted"
    assert response["agent"]["bank_input_ids"] == [bank_input.id]
    assert response["agent"]["bank_transaction_ids"] == transaction_ids
    assert response["agent"]["traceability"]["bank_input_link_count"] == 1
    assert response["agent"]["traceability"]["bank_transaction_link_count"] == 1

    input_links = BankInputRepository.list_inputs_for_voucher(response["id"])
    transaction_links = BankInputRepository.list_transactions_for_voucher(response["id"])
    assert [link.bank_input_id for link in input_links] == [bank_input.id]
    assert [link.bank_transaction_id for link in transaction_links] == transaction_ids

    tx = BankIntegrationService().get_transaction(transaction_ids[0])
    assert tx.status == "booked"
    assert tx.matched_voucher_id == response["id"]

    source_context = await get_voucher_source_context(
        response["id"],
        ledger=LedgerService(),
        actor="api",
    )
    bank_source = source_context["source_material"][0]
    assert bank_source["kind"] == "bank_input"
    assert bank_source["download_url"] == f"/api/v1/bank-inputs/{bank_input.id}/file"
    assert bank_source["transaction_ids"] == transaction_ids
    assert source_context["processing_notes"][0]["kind"] == "bank_input"
    assert "stored_path" not in repr(source_context)


@pytest.mark.asyncio
async def test_agent_bank_driven_posting_can_use_multiple_transactions(
    test_period,
    bank_input_dir,
):
    bank_input, transaction_ids = _processed_bank_input(
        b"Datum;Belopp;Text\n2026-03-01;100,00;Kundbetalning\n2026-03-02;100,00;Kundbetalning 2"
    )

    response = await create_and_post_agent_voucher(
        _agent_sale_request(
            test_period.id,
            amount=20000,
            bank_input_ids=[bank_input.id],
            bank_transaction_ids=transaction_ids,
        ),
        actor="api",
    )

    assert response["status"] == "posted"
    assert response["agent"]["traceability"]["bank_transaction_link_count"] == 2
    assert len(BankInputRepository.list_transactions_for_voucher(response["id"])) == 2


@pytest.mark.asyncio
async def test_source_context_only_lists_transactions_linked_to_voucher(
    test_period,
    bank_input_dir,
):
    bank_input, transaction_ids = _processed_bank_input(
        b"Datum;Belopp;Text\n2026-03-01;100,00;Kundbetalning\n2026-03-02;100,00;Kundbetalning 2"
    )

    response = await create_and_post_agent_voucher(
        _agent_sale_request(
            test_period.id,
            amount=10000,
            bank_input_ids=[bank_input.id],
            bank_transaction_ids=[transaction_ids[0]],
        ),
        actor="api",
    )

    source_context = await get_voucher_source_context(
        response["id"],
        ledger=LedgerService(),
        actor="api",
    )
    bank_source = source_context["source_material"][0]
    assert bank_source["transaction_ids"] == [transaction_ids[0]]
    assert bank_source["transaction_count"] == 1
    assert source_context["processing_notes"][0]["transaction_ids"] == [transaction_ids[0]]


@pytest.mark.asyncio
async def test_agent_bank_driven_posting_deduplicates_transaction_ids(
    test_period,
    bank_input_dir,
):
    bank_input, transaction_ids = _processed_bank_input()
    duplicated_ids = [transaction_ids[0], transaction_ids[0]]

    response = await create_and_post_agent_voucher(
        _agent_sale_request(
            test_period.id,
            bank_input_ids=[bank_input.id],
            bank_transaction_ids=duplicated_ids,
        ),
        actor="api",
    )

    assert response["status"] == "posted"
    assert response["agent"]["bank_transaction_ids"] == [transaction_ids[0]]
    assert response["agent"]["traceability"]["bank_transaction_link_count"] == 1
    assert response["agent"]["traceability"]["booked_transaction_count"] == 1
    transaction_links = BankInputRepository.list_transactions_for_voucher(response["id"])
    assert [link.bank_transaction_id for link in transaction_links] == [transaction_ids[0]]


@pytest.mark.asyncio
async def test_agent_posting_rolls_back_voucher_when_traceability_link_fails(
    test_period,
    monkeypatch,
):
    def fail_link_posted_voucher(*args, **kwargs):
        raise BankInputConflictError(
            "forced_traceability_failure",
            "Forced traceability failure",
        )

    monkeypatch.setattr(
        BankInputService,
        "link_posted_voucher",
        fail_link_posted_voucher,
    )
    _, before_count = VoucherRepository.list_all()

    with pytest.raises(HTTPException) as exc_info:
        await create_and_post_agent_voucher(
            _agent_sale_request(test_period.id),
            actor="api",
        )

    assert exc_info.value.detail["code"] == "forced_traceability_failure"
    _, after_count = VoucherRepository.list_all()
    assert after_count == before_count


@pytest.mark.asyncio
async def test_agent_posting_updates_next_year_opening_balances_after_commit(
    test_period,
    monkeypatch,
):
    calls = []
    original_update = OpeningBalanceService.update_opening_balances_for_next_year

    def spy_update(self, fiscal_year_id: str, actor: str = "system"):
        _, voucher_count = VoucherRepository.list_all()
        calls.append((fiscal_year_id, actor, voucher_count))
        return original_update(self, fiscal_year_id, actor)

    monkeypatch.setattr(
        OpeningBalanceService,
        "update_opening_balances_for_next_year",
        spy_update,
    )

    response = await create_and_post_agent_voucher(
        _agent_sale_request(test_period.id),
        actor="api",
    )

    assert response["status"] == "posted"
    assert calls == [(test_period.fiscal_year_id, "api", 1)]


@pytest.mark.asyncio
async def test_agent_bank_driven_posting_can_link_ordinary_intake_source(
    test_period,
    bank_input_dir,
    intake_dir,
):
    bank_input, transaction_ids = _processed_bank_input()
    source = IntakeService().create_source_from_upload_content(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 receipt for bank tx",
        explanation="Receipt",
        source_type="receipt",
        actor="api",
    )

    response = await create_and_post_agent_voucher(
        _agent_sale_request(
            test_period.id,
            bank_input_ids=[bank_input.id],
            bank_transaction_ids=transaction_ids,
            intake_source_ids=[source.id],
        ),
        actor="api",
    )

    assert response["status"] == "posted"
    assert response["agent"]["intake_source_ids"] == [source.id]
    assert response["agent"]["processing_attempt_ids"]
    assert IntakeRepository.list_links_for_voucher(response["id"])[0].intake_source_id == source.id
    assert BankInputRepository.list_inputs_for_voucher(response["id"])[0].bank_input_id == bank_input.id


@pytest.mark.asyncio
async def test_agent_rejects_booked_bank_transaction_without_creating_voucher(
    test_period,
    bank_input_dir,
):
    bank_input, transaction_ids = _processed_bank_input()
    first = await create_and_post_agent_voucher(
        _agent_sale_request(
            test_period.id,
            bank_input_ids=[bank_input.id],
            bank_transaction_ids=transaction_ids,
        ),
        actor="api",
    )
    _, before_count = VoucherRepository.list_all()

    with pytest.raises(HTTPException) as exc_info:
        await create_and_post_agent_voucher(
            _agent_sale_request(
                test_period.id,
                bank_input_ids=[bank_input.id],
                bank_transaction_ids=transaction_ids,
            ),
            actor="api",
        )

    assert first["status"] == "posted"
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "bank_transaction_already_booked"
    _, after_count = VoucherRepository.list_all()
    assert after_count == before_count


@pytest.mark.asyncio
async def test_agent_rejects_matched_bank_transaction_without_creating_voucher(
    test_period,
    bank_input_dir,
):
    bank_input, transaction_ids = _processed_bank_input()
    voucher = await create_and_post_agent_voucher(
        _agent_sale_request(
            test_period.id,
            bank_input_ids=[bank_input.id],
            bank_transaction_ids=transaction_ids,
        ),
        actor="api",
    )
    db.execute(
        "UPDATE bank_transactions SET status = 'pending', matched_voucher_id = ? WHERE id = ?",
        (voucher["id"], transaction_ids[0]),
    )
    db.commit()
    _, before_count = VoucherRepository.list_all()

    with pytest.raises(HTTPException) as exc_info:
        await create_and_post_agent_voucher(
            _agent_sale_request(
                test_period.id,
                bank_input_ids=[bank_input.id],
                bank_transaction_ids=transaction_ids,
            ),
            actor="api",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "bank_transaction_already_matched"
    _, after_count = VoucherRepository.list_all()
    assert after_count == before_count


@pytest.mark.asyncio
async def test_agent_rejects_unlinked_bank_transaction_before_voucher_creation(
    test_period,
    bank_input_dir,
):
    bank_input, _transaction_ids = _processed_bank_input()
    other_input, other_transaction_ids = _processed_bank_input(
        b"Datum;Belopp;Text\n2026-03-09;100,00;Other payment"
    )
    _, before_count = VoucherRepository.list_all()

    with pytest.raises(HTTPException) as exc_info:
        await create_and_post_agent_voucher(
            _agent_sale_request(
                test_period.id,
                bank_input_ids=[bank_input.id],
                bank_transaction_ids=other_transaction_ids,
            ),
            actor="api",
        )

    assert other_input.id != bank_input.id
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "bank_transaction_not_linked"
    _, after_count = VoucherRepository.list_all()
    assert after_count == before_count
