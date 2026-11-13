"""What a voucher rests on, for review: `GET /vouchers/{id}/source-context`.

The underlag linked to it now (and through another voucher's link, a
`voucher_source_references` row), the statement files and transactions
behind it, the underlag once linked and since unlinked (underlag-ersatt),
what the intake pass noted while processing each, and the correction chain
it belongs to. Read only.
"""

from typing import Any, Optional

from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.intake_link_repo import VoucherSourceReferenceRepository
from repositories.intake_repo import IntakeRepository
from repositories.voucher_repo import VoucherRepository


def voucher_source_context(voucher_id: str) -> Optional[dict]:
    """The context of *voucher_id*, or `None` if there is no such voucher."""
    vouchers = VoucherRepository()
    voucher = vouchers.get(voucher_id)
    if voucher is None:
        return None

    intake_repo = IntakeRepository()
    bank_repo = BankInputRepository()
    source_material: list[dict[str, Any]] = []
    processing_notes: list[dict[str, Any]] = []

    for link in intake_repo.list_links_for_voucher(voucher_id):
        source = intake_repo.get_source(link.intake_source_id)
        if not source:
            continue
        source_material.append(_voucher_source_material(source, link))
        processing_notes.extend(
            _source_processing_note(attempt)
            for attempt in intake_repo.list_attempts_for_source(source.id)
            if attempt.voucher_id == voucher_id
        )

    # A voucher that refers to a receipt
    # through another voucher's link (A-121 via A-118) lists that receipt,
    # named with the voucher it is linked to, so the receipt can be opened
    # from it too.
    reference = VoucherSourceReferenceRepository.get_for_voucher(voucher_id)
    if reference is not None:
        # The link the reference went through, current or since undone:
        # the reference stands either way (underlag-ersatt).
        via_link = intake_repo.latest_link(
            reference.intake_source_id, reference.via_voucher_id
        )
        source = intake_repo.get_source(reference.intake_source_id)
        via = vouchers.get(reference.via_voucher_id)
        if source is not None and via_link is not None:
            source_material.append(
                {
                    **_voucher_source_material(source, via_link),
                    "via_voucher_id": reference.via_voucher_id,
                    "via_voucher_number": (
                        f"{via.series.value}-{via.number}"
                        if via is not None and via.number is not None
                        else None
                    ),
                }
            )

    voucher_transaction_links = bank_repo.list_transactions_for_voucher(voucher_id)
    for input_link in bank_repo.list_inputs_for_voucher(voucher_id):
        bank_input = bank_repo.get_bank_input(input_link.bank_input_id)
        if not bank_input:
            continue
        transaction_ids_for_input = set(
            bank_repo.list_transaction_ids_for_input(bank_input.id)
        )
        transaction_ids = [
            tx_link.bank_transaction_id
            for tx_link in voucher_transaction_links
            if tx_link.bank_transaction_id in transaction_ids_for_input
        ]
        source_material.append(
            {
                "kind": "bank_input",
                "id": bank_input.id,
                "bank_connection_id": bank_input.bank_connection_id,
                "status": bank_input.status.value,
                "original_filename": bank_input.original_filename,
                "mime_type": bank_input.mime_type,
                "size_bytes": bank_input.size_bytes,
                "sha256": bank_input.sha256,
                "uploaded_by": bank_input.uploaded_by,
                "uploaded_at": bank_input.uploaded_at.isoformat(),
                "download_url": f"/api/v1/bank-inputs/{bank_input.id}/file",
                "linked_at": input_link.linked_at.isoformat(),
                "linked_by": input_link.linked_by,
                "link_reason": None,
                "imported_count": bank_input.imported_count,
                "skipped_count": bank_input.skipped_count,
                "detected_format": bank_input.detected_format,
                "parse_error": bank_input.parse_error,
                "transaction_ids": transaction_ids,
                "transaction_count": len(transaction_ids),
            }
        )
        processing_notes.append(
            {
                "kind": "bank_input",
                "id": bank_input.id,
                "status": bank_input.status.value,
                "summary": _bank_input_processing_summary(bank_input),
                "warnings": [],
                "error_detail": bank_input.parse_error,
                "voucher_id": voucher_id,
                "actor": bank_input.uploaded_by,
                "created_at": (
                    bank_input.processed_at or bank_input.uploaded_at
                ).isoformat(),
                "imported_count": bank_input.imported_count,
                "skipped_count": bank_input.skipped_count,
                "detected_format": bank_input.detected_format,
                "transaction_ids": transaction_ids,
            }
        )

    # underlag-ersatt: underlag once linked here and since unlinked. Not
    # `source_material` -- the voucher does not have it -- but the trace
    # the replacement leaves, with who undid it and why.
    unlinked_source_material = []
    for link in intake_repo.list_unlinked_for_voucher(voucher_id):
        source = intake_repo.get_source(link.intake_source_id)
        if source is None:
            continue
        unlinked_source_material.append(
            {
                **_voucher_source_material(source, link),
                "unlinked_at": (
                    link.unlinked_at.isoformat() if link.unlinked_at else None
                ),
                "unlinked_by": link.unlinked_by,
                "unlink_reason": link.unlink_reason,
            }
        )

    return {
        "voucher_id": voucher_id,
        "source_material": source_material,
        "unlinked_source_material": unlinked_source_material,
        "processing_notes": sorted(
            processing_notes,
            key=lambda note: note["created_at"],
        ),
        "correction_chain": _correction_chain_for_voucher(voucher),
        # The statement transactions that are the voucher's underlag
        # (services/statement_match.py), each with the file it came from.
        "statement_links": [
            {
                "bank_transaction_id": link["bank_transaction_id"],
                "account_code": link["account_code"],
                "date": str(link["transaction_date"])[:10],
                "amount_ore": link["amount"],
                "description": link["description"],
                "bank_input_id": link["bank_input_id"],
                "original_filename": link["original_filename"],
                "download_url": (
                    f"/api/v1/bank-inputs/{link['bank_input_id']}/file"
                    if link["bank_input_id"]
                    else None
                ),
                "linked_by": link["linked_by"],
            }
            for link in bank_repo.list_statement_links_for_voucher(voucher_id)
        ],
    }


def _source_processing_note(attempt) -> dict:
    return {
        "kind": "voucher_source",
        "id": attempt.id,
        "intake_source_id": attempt.intake_source_id,
        "status": attempt.status.value,
        "summary": attempt.summary,
        "warnings": attempt.warnings or [],
        "error_detail": attempt.error_detail,
        "voucher_id": attempt.voucher_id,
        "actor": attempt.actor,
        "created_at": attempt.created_at.isoformat(),
    }


def _bank_input_processing_summary(bank_input) -> str:
    if bank_input.parse_error:
        return "Bank input parsing failed"
    return (
        f"Bank input processed: {bank_input.imported_count} imported, "
        f"{bank_input.skipped_count} skipped"
    )


def _correction_chain_for_voucher(voucher) -> list[dict]:
    voucher_ids = {voucher.id}
    if voucher.correction_of:
        voucher_ids.add(voucher.correction_of)

    chain = []
    seen = set()
    for voucher_id in voucher_ids:
        for history in AccountingCorrectionRepository.list(voucher_id=voucher_id):
            if history.id in seen:
                continue
            seen.add(history.id)
            chain.append(
                {
                    "id": history.id,
                    "original_voucher_id": history.original_voucher_id,
                    "correction_voucher_id": history.corrected_voucher_id,
                    "correction_reason": history.correction_reason,
                    "actor": history.corrected_by,
                    "timestamp": history.created_at.isoformat(),
                    "change_type": history.change_type,
                    "original_data": history.original_data,
                    "corrected_data": history.corrected_data,
                }
            )
    return sorted(chain, key=lambda item: item["timestamp"])


def _voucher_source_material(source, link) -> dict:
    """One `voucher_source` entry of `source-context`: the intake source and
    the `voucher_intake_sources` row that links it."""
    return {
        "kind": "voucher_source",
        "id": source.id,
        "source_type": source.source_type.value if source.source_type else None,
        "status": source.status.value,
        "original_filename": source.original_filename,
        "mime_type": source.mime_type,
        "size_bytes": source.size_bytes,
        "sha256": source.sha256,
        "explanation": source.explanation,
        "uploaded_by": source.uploaded_by,
        "uploaded_at": source.uploaded_at.isoformat(),
        "download_url": f"/api/v1/intake/{source.id}/file",
        "linked_at": link.linked_at.isoformat(),
        "linked_by": link.linked_by,
        "link_reason": link.link_reason,
    }
