"""Voucher posting orchestration — the single path into the general ledger.

Extracted from ``api/routes/agent.py::_create_and_post_voucher`` (see
``docs/redesign/SPEC-agentruntime.md`` §7) so that the HTTP route and the
future agent-runtime tool (A7) share exactly the same posting code. This is
pure orchestration: it raises domain exceptions (``ValidationError``,
``IntakeError``, ``BankInputError``) on failure and returns the response
dict on success, leaving HTTP-status mapping to the caller.
"""

from typing import TYPE_CHECKING, Optional

from fastapi.encoders import jsonable_encoder

from db.database import db
from domain.validation import ValidationError
from services.bank_inputs import BankInputService
from services.idempotency import IdempotencyService
from services.intake import IntakeService
from services.ledger import LedgerService

if TYPE_CHECKING:
    from api.routes.agent import AgentVoucherRequest

# Mirrors fastapi.status.HTTP_201_CREATED. Kept as a literal because
# services/ must not import fastapi.status (no HTTP concepts down here).
_HTTP_201_CREATED = 201


def post_agent_voucher(
    request: "AgentVoucherRequest",
    actor: str,
    idempotency: IdempotencyService,
    idempotency_key: Optional[str],
    endpoint: str,
) -> dict:
    """Post the voucher, and the key that protects it, in one transaction."""
    intake = IntakeService()
    bank_inputs = BankInputService()
    intake_source_ids = _unique_preserve_order(request.intake_source_ids)
    bank_input_ids = _unique_preserve_order(request.bank_input_ids)
    bank_transaction_ids = _unique_preserve_order(request.bank_transaction_ids)

    for source_id in intake_source_ids:
        intake.ensure_source_ready_for_voucher_link(source_id)
    _ensure_agent_voucher_has_traceability(intake_source_ids, bank_input_ids)
    bank_inputs.ensure_transactions_available(
        bank_input_ids,
        bank_transaction_ids,
    )

    fiscal_year_id = None
    voucher_series = None
    with db.transaction():
        ledger = LedgerService()
        voucher = ledger.create_voucher(
            series=request.series,
            date=request.date,
            period_id=request.period_id,
            description=request.description,
            rows_data=[row.model_dump() for row in request.rows],
            created_by="agent",
            _commit=False,
        )
        voucher = ledger.post_voucher(
            voucher.id,
            actor=actor,
            _commit=False,
            update_opening_balance=False,
        )
        processing_attempt_ids = []
        summary = request.reasoning_summary or request.description
        for source_id in intake_source_ids:
            attempt, _link = intake.link_existing_voucher(
                source_id=source_id,
                voucher_id=voucher.id,
                actor=actor,
                summary=summary,
                link_reason="agent_posted_voucher",
                _commit=False,
            )
            processing_attempt_ids.append(attempt.id)
        traceability = bank_inputs.link_posted_voucher(
            voucher_id=voucher.id,
            bank_input_ids=bank_input_ids,
            bank_transaction_ids=bank_transaction_ids,
            actor=actor,
            _commit=False,
        )
        fiscal_year_id = voucher.fiscal_year_id
        voucher_series = voucher.series.value

        from api.routes.vouchers import _voucher_to_response

        response = _voucher_to_response(voucher).model_dump()
        response["agent"] = {
            "posted_directly": True,
            "reasoning_summary": request.reasoning_summary,
            "intake_source_ids": intake_source_ids,
            "processing_attempt_id": (
                processing_attempt_ids[0] if len(processing_attempt_ids) == 1 else None
            ),
            "processing_attempt_ids": processing_attempt_ids,
            "bank_input_ids": bank_input_ids,
            "bank_transaction_ids": bank_transaction_ids,
            "traceability": traceability,
        }

        # The key row must commit with the voucher. Written in its own
        # transaction it leaves a window where the voucher is posted but
        # the key is gone — exactly the hole this module closes.
        if idempotency_key:
            idempotency.complete(
                key=idempotency_key,
                endpoint=endpoint,
                response_status=_HTTP_201_CREATED,
                response_payload=jsonable_encoder(response),
                entity_type="voucher",
                entity_id=voucher.id,
                _commit=False,
            )
    if fiscal_year_id and voucher_series != "IB":
        try:
            from services.opening_balance import OpeningBalanceService

            OpeningBalanceService().update_opening_balances_for_next_year(
                fiscal_year_id,
                actor,
            )
        except Exception:
            pass
    return response


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _ensure_agent_voucher_has_traceability(
    intake_source_ids: list[str],
    bank_input_ids: list[str],
) -> None:
    if intake_source_ids or bank_input_ids:
        return
    raise ValidationError(
        code="missing_source_traceability",
        message="Agent vouchers must reference intake source material",
        details=(
            "Provide intake_source_ids for voucher sources or bank_input_ids "
            "for bank inputs"
        ),
    )
