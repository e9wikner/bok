"""The agent's tool surface (docs/redesign/SPEC-agentruntime.md §6.4).

Nine tools, each a specific, typed action -- never a generic bash, SQL,
filesystem, or HTTP tool (SPEC §10's "Aldrig" list). Every allowed action a
model can take is its own function with its own Pydantic argument schema, so
each one can be validated, logged, and rendered independently, and so that
the append-only guarantee (CLAUDE.md) can be checked *structurally*: test
case 17 asserts directly against ``AGENT_TOOL_DEFINITIONS`` that no tool
name or description implies the ability to edit or delete a posted voucher.

``posta_verifikation`` is the only tool that writes to the general ledger,
and it goes through the exact same code as ``POST /api/v1/agent/vouchers``
(``services/voucher_posting.post_agent_voucher``, A1) -- same
``VoucherValidator``, same transaction, same idempotency key.

Layering (CLAUDE.md): this module is pure ``services/`` -- no SQL of its own
(everything here calls a repository or another service), no HTTP concepts
(no ``fastapi``, no ``HTTPException``), and no ``anthropic``/``openai``
import (SPEC §4, §10 -- that boundary is ``services/llm/`` alone).

What this module deliberately does *not* do (SPEC §6.3, §6.7 -- A8's job):
gate a tool call before it runs, write an ``agent_run_events`` row, or wrap a
raised exception into an Anthropic ``tool_result`` with ``is_error: true``.
``execute_tool`` either returns a JSON-serializable result or raises -- the
session decides what a raise means.
"""

import uuid
from datetime import date as DateType
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from domain.models import (
    Account,
    BankInput,
    CorrectionHistory,
    IntakeProcessingAttempt,
    IntakeSource,
    Period,
    Voucher,
    VoucherRow,
)
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.agent_documents import ContentBlock, select_content_for_source
from services.bank_inputs import BankInputService
from services.idempotency import IdempotencyOutcome, IdempotencyService
from services.intake import IntakeService
from services.llm import LLMCapabilities
from services.voucher_posting import VoucherPostingRequest, post_agent_voucher

# ---------------------------------------------------------------------------
# Idempotency key derivation (SPEC §6.4)
# ---------------------------------------------------------------------------
#
# A fixed, hardcoded namespace UUID -- generated once (uuid4), never
# regenerated at runtime. The entire point of uuid5-deriving the posting key
# from the intake source id is that a worker crashing after posting but
# before advancing the queue replays the *same* key on its next attempt
# instead of minting a new one; a namespace that changed across process
# restarts would silently defeat that.
BOK_NAMESPACE = uuid.UUID("8f2b6e6c-8a2b-4a9a-9f7c-3a0b6f7f0b1a")

#: Idempotency-key endpoint scope for tool-driven postings. Deliberately
#: distinct from ``AGENT_VOUCHER_ENDPOINT`` in ``api/routes/agent.py`` --
#: the two entry points reserve keys in independent namespaces, and a
#: worker's uuid5-derived key must never collide with an unrelated
#: HTTP-supplied ``Idempotency-Key`` header value that happens to match.
_POSTA_VERIFIKATION_ENDPOINT = "TOOL posta_verifikation"


def derive_posting_idempotency_key(source_id: str) -> str:
    """``uuid5(BOK_NAMESPACE, f"intake:{source_id}")`` -- SPEC §6.4.

    "Ett underlag, en avsikt, en nyckel": deterministic per intake source id,
    so re-processing the same source after a crash produces the *same* key
    and replays instead of posting a second voucher.
    """
    return str(uuid.uuid5(BOK_NAMESPACE, f"intake:{source_id}"))


class PostingConflictError(Exception):
    """Raised when ``posta_verifikation``'s idempotency key is already
    claimed (SPEC §6.7).

    Two cases: ``request_in_flight`` (another worker/request holds the same
    key right now -- SPEC's answer is "leave the source, move on", which is
    a session-level (A8) decision this module only makes possible by raising
    a typed, inspectable error), and ``idempotency_key_reuse`` (the stored
    fingerprint doesn't match -- for a key derived purely from a source id
    this should only happen if the same source was posted with genuinely
    different arguments between attempts, which is worth surfacing loudly
    rather than silently replaying the old response).

    Same ``{code, message, details}`` shape as ``IntakeError``/
    ``BankInputError`` so a caller already branching on ``.code`` doesn't
    need a different pattern for this module.
    """

    def __init__(self, code: str, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


# ---------------------------------------------------------------------------
# Tool argument schemas
# ---------------------------------------------------------------------------


class LasKontoplanArgs(BaseModel):
    """Läs kontoplanen. No filters beyond active/inactive."""

    active_only: bool = True


class LasPerioderArgs(BaseModel):
    """Läs perioder -- öppna och/eller låsta, med `locked_by`/`locked_at`."""

    fiscal_year_id: Optional[str] = None
    include_locked: bool = True


class LasVerifikationerArgs(BaseModel):
    """Läs verifikationer, filtrerbart på period och status."""

    period_id: Optional[str] = None
    status: Optional[Literal["draft", "posted"]] = None
    limit: int = Field(50, ge=1, le=200)


class LasKorrigeringarArgs(BaseModel):
    """Läs rättelsehistorik, valfritt avgränsad till en verifikation."""

    voucher_id: Optional[str] = None
    limit: int = Field(20, ge=1, le=200)


class LasUnderlagArgs(BaseModel):
    """Läs intagskön, eller en enskild posts metadata om `source_id` ges."""

    source_id: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class HamtaUnderlagsfilArgs(BaseModel):
    """Hämta och tolka innehållet i ett underlags fil (SPEC §6.3)."""

    source_id: str


class LasBankhandelserArgs(BaseModel):
    """Läs bankhändelser -- kön, eller ett enskilt bankunderlags metadata."""

    bank_input_id: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class PostaVerifikationRow(BaseModel):
    """One accounting row -- the same shape ``ledger.create_voucher`` expects."""

    account: str
    debit: int = 0
    credit: int = 0
    description: Optional[str] = None


class PostaVerifikationArgs(BaseModel):
    """Skapa och posta en ny verifikation i ett steg.

    Går genom ``services/voucher_posting.post_agent_voucher`` -- samma
    validering, transaktion och idempotensnyckel som
    ``POST /api/v1/agent/vouchers``. Kan aldrig ändra eller radera en redan
    postad verifikation: en felaktig postning rättas med en ny B-serie-
    verifikation, inte genom detta verktyg.
    """

    date: DateType
    period_id: str
    description: str
    rows: list[PostaVerifikationRow] = Field(..., min_length=2)
    series: Literal["A", "B"] = "A"
    reasoning_summary: Optional[str] = None
    intake_source_ids: list[str] = Field(default_factory=list)
    bank_input_ids: list[str] = Field(default_factory=list)
    bank_transaction_ids: list[str] = Field(default_factory=list)


class RegistreraAvstaendeArgs(BaseModel):
    """Registrera ett dokumenterat avstående för ett underlag i intagskön.

    Skapar aldrig en verifikation -- motsatsen till ``posta_verifikation``.
    """

    source_id: str
    summary: str
    error_detail: str
    warnings: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# JSON-serializable result shapes
# ---------------------------------------------------------------------------


def _account_dict(account: Account) -> dict:
    return {
        "code": account.code,
        "name": account.name,
        "account_type": account.account_type.value,
        "vat_code": account.vat_code,
        "sru_code": account.sru_code,
        "active": account.active,
    }


def _period_dict(period: Period) -> dict:
    return {
        "id": period.id,
        "fiscal_year_id": period.fiscal_year_id,
        "year": period.year,
        "month": period.month,
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "locked": period.locked,
        "locked_at": period.locked_at.isoformat() if period.locked_at else None,
        "locked_by": period.locked_by,
    }


def _voucher_row_dict(row: VoucherRow) -> dict:
    return {
        "account_code": row.account_code,
        "debit": row.debit,
        "credit": row.credit,
        "description": row.description,
    }


def _voucher_dict(voucher: Voucher) -> dict:
    return {
        "id": voucher.id,
        "series": voucher.series.value,
        "number": voucher.number,
        "date": voucher.date.isoformat(),
        "period_id": voucher.period_id,
        "description": voucher.description,
        "status": voucher.status.value,
        "fiscal_year_id": voucher.fiscal_year_id,
        "rows": [_voucher_row_dict(row) for row in voucher.rows],
        "correction_of": voucher.correction_of,
        "created_by": voucher.created_by,
        "created_at": voucher.created_at.isoformat(),
        "posted_at": voucher.posted_at.isoformat() if voucher.posted_at else None,
    }


def _correction_dict(entry: CorrectionHistory) -> dict:
    return {
        "id": entry.id,
        "original_voucher_id": entry.original_voucher_id,
        "corrected_voucher_id": entry.corrected_voucher_id,
        "original_data": entry.original_data,
        "corrected_data": entry.corrected_data,
        "change_type": entry.change_type,
        "was_successful": entry.was_successful,
        "corrected_by": entry.corrected_by,
        "correction_reason": entry.correction_reason,
        "created_at": entry.created_at.isoformat(),
    }


def _intake_source_dict(source: IntakeSource) -> dict:
    return {
        "id": source.id,
        "source_type": source.source_type.value if source.source_type else None,
        "status": source.status.value,
        "original_filename": source.original_filename,
        "mime_type": source.mime_type,
        "size_bytes": source.size_bytes,
        "sha256": source.sha256,
        "explanation": source.explanation,
        "agent_guidance": source.agent_guidance,
        "uploaded_by": source.uploaded_by,
        "uploaded_at": source.uploaded_at.isoformat(),
    }


def _intake_attempt_dict(attempt: IntakeProcessingAttempt) -> dict:
    return {
        "id": attempt.id,
        "intake_source_id": attempt.intake_source_id,
        "status": attempt.status.value,
        "summary": attempt.summary,
        "warnings": attempt.warnings,
        "error_detail": attempt.error_detail,
        "voucher_id": attempt.voucher_id,
        "actor": attempt.actor,
        "created_at": attempt.created_at.isoformat(),
    }


def _bank_input_dict(bank_input: BankInput) -> dict:
    return {
        "id": bank_input.id,
        "bank_connection_id": bank_input.bank_connection_id,
        "status": bank_input.status.value,
        "original_filename": bank_input.original_filename,
        "mime_type": bank_input.mime_type,
        "size_bytes": bank_input.size_bytes,
        "sha256": bank_input.sha256,
        "uploaded_by": bank_input.uploaded_by,
        "uploaded_at": bank_input.uploaded_at.isoformat(),
        "detected_format": bank_input.detected_format,
        "imported_count": bank_input.imported_count,
        "skipped_count": bank_input.skipped_count,
        "parse_error": bank_input.parse_error,
        "processed_at": (
            bank_input.processed_at.isoformat() if bank_input.processed_at else None
        ),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _run_las_kontoplan(
    args: LasKontoplanArgs, *, actor: str, capabilities: LLMCapabilities
) -> list[dict]:
    accounts = AccountRepository.list_all(active_only=args.active_only)
    return [_account_dict(account) for account in accounts]


def _run_las_perioder(
    args: LasPerioderArgs, *, actor: str, capabilities: LLMCapabilities
) -> list[dict]:
    if args.fiscal_year_id:
        periods = PeriodRepository.list_periods(args.fiscal_year_id)
    else:
        periods = PeriodRepository.list_all_periods()
    if not args.include_locked:
        periods = [period for period in periods if not period.locked]
    return [_period_dict(period) for period in periods]


def _run_las_verifikationer(
    args: LasVerifikationerArgs, *, actor: str, capabilities: LLMCapabilities
) -> dict:
    if args.period_id:
        all_vouchers = VoucherRepository.list_for_period(
            args.period_id, status=args.status
        )
        total = len(all_vouchers)
        vouchers = all_vouchers[: args.limit]
    else:
        vouchers, total = VoucherRepository.list_all(
            status=args.status, limit=args.limit
        )
    return {"total": total, "items": [_voucher_dict(v) for v in vouchers]}


def _run_las_korrigeringar(
    args: LasKorrigeringarArgs, *, actor: str, capabilities: LLMCapabilities
) -> list[dict]:
    entries = AccountingCorrectionRepository.list(
        limit=args.limit, voucher_id=args.voucher_id
    )
    return [_correction_dict(entry) for entry in entries]


def _run_las_underlag(
    args: LasUnderlagArgs, *, actor: str, capabilities: LLMCapabilities
) -> dict:
    intake = IntakeService()
    if args.source_id:
        return _intake_source_dict(intake.get_source(args.source_id))
    queue = intake.get_pending_queue(limit=args.limit, offset=args.offset)
    return {
        "total": queue["total"],
        "limit": queue["limit"],
        "offset": queue["offset"],
        "items": [_intake_source_dict(s) for s in queue["items"]],
    }


def _run_hamta_underlagsfil(
    args: HamtaUnderlagsfilArgs, *, actor: str, capabilities: LLMCapabilities
) -> ContentBlock:
    intake = IntakeService()
    source = intake.get_source(args.source_id)
    file_path = intake.resolve_source_file(source)
    file_bytes = file_path.read_bytes()
    # DocumentUnreadableError propagates uncaught -- SPEC §6.3 step 3 is an
    # abstention, and this module's contract is "raise the specific domain
    # exception", not swallow it into a generic result (A8 decides what an
    # unreadable source means for the pass).
    return select_content_for_source(source, file_bytes, capabilities)


def _run_las_bankhandelser(
    args: LasBankhandelserArgs, *, actor: str, capabilities: LLMCapabilities
) -> dict:
    bank_inputs = BankInputService()
    if args.bank_input_id:
        return _bank_input_dict(bank_inputs.get_bank_input(args.bank_input_id))
    return bank_inputs.agent_queue_items(limit=args.limit, offset=args.offset)


def _post_voucher(args: PostaVerifikationArgs, *, actor: str) -> dict:
    request = VoucherPostingRequest(
        date=args.date,
        period_id=args.period_id,
        description=args.description,
        rows=[row.model_dump() for row in args.rows],
        series=args.series,
        reasoning_summary=args.reasoning_summary,
        intake_source_ids=args.intake_source_ids,
        bank_input_ids=args.bank_input_ids,
        bank_transaction_ids=args.bank_transaction_ids,
    )

    idempotency_key: Optional[str] = None
    if args.intake_source_ids:
        # SPEC §6.4's uuid5 formula assumes exactly one primary intake
        # source per posting ("En post i taget", §6.2): the first id drives
        # the key even when more are listed for traceability (e.g. a
        # multi-source posting). Each intake source can only ever be linked
        # to one voucher (IntakeService._ensure_can_record_outcome), so a
        # second, third, ... id here does not get its own key -- there is
        # exactly one posting intent per tool call, and the first source is
        # its anchor.
        idempotency_key = derive_posting_idempotency_key(args.intake_source_ids[0])

    idempotency = IdempotencyService()
    reserved = False
    if idempotency_key:
        outcome = idempotency.begin(
            key=idempotency_key,
            endpoint=_POSTA_VERIFIKATION_ENDPOINT,
            body=args.model_dump(mode="json"),
            actor=actor,
        )
        if outcome.kind == IdempotencyOutcome.REPLAY:
            payload = dict(outcome.response_payload or {})
            payload["idempotent_replay"] = True
            return payload
        if outcome.kind == IdempotencyOutcome.MISMATCH:
            raise PostingConflictError(
                code="idempotency_key_reuse",
                message="Idempotency key already used for a different request",
                details=outcome.original_fingerprint,
            )
        if outcome.kind == IdempotencyOutcome.IN_FLIGHT:
            raise PostingConflictError(
                code="request_in_flight",
                message="Another attempt is already posting this intake source",
            )
        reserved = True

    try:
        return post_agent_voucher(
            request=request,
            actor=actor,
            idempotency=idempotency,
            idempotency_key=idempotency_key,
            endpoint=_POSTA_VERIFIKATION_ENDPOINT,
        )
    except Exception:
        if reserved and idempotency_key:
            idempotency.release(idempotency_key, _POSTA_VERIFIKATION_ENDPOINT)
        raise


def _run_posta_verifikation(
    args: PostaVerifikationArgs, *, actor: str, capabilities: LLMCapabilities
) -> dict:
    return _post_voucher(args, actor=actor)


def _run_registrera_avstaende(
    args: RegistreraAvstaendeArgs, *, actor: str, capabilities: LLMCapabilities
) -> dict:
    attempt = IntakeService().record_failed(
        source_id=args.source_id,
        summary=args.summary,
        error_detail=args.error_detail,
        actor=actor,
        warnings=args.warnings,
    )
    return _intake_attempt_dict(attempt)


# ---------------------------------------------------------------------------
# Tool definitions and dispatcher (SPEC §6.4, §6.6)
# ---------------------------------------------------------------------------
#
# A literal, ordered tuple -- never a dict iterated for its values, never
# built from a set -- so AGENT_TOOL_DEFINITIONS' order is the same in every
# process run. SPEC §6.6: the tool list is part of the cached system prompt
# prefix, and an accidental reorder is a silent cache-buster.

_ToolHandler = Callable[..., Any]

_TOOL_SPECS: tuple[tuple[str, str, type[BaseModel], _ToolHandler], ...] = (
    (
        "las_kontoplan",
        "Läs kontoplanen (BAS). Skrivskyddat -- returnerar kontokoder, namn, "
        "typ, momskod och SRU-kod.",
        LasKontoplanArgs,
        _run_las_kontoplan,
    ),
    (
        "las_perioder",
        "Läs bokföringsperioder, med låsstatus (`locked_by`/`locked_at`). "
        "Skrivskyddat -- perioder låses via ett separat, mänskligt flöde, "
        "aldrig av agenten.",
        LasPerioderArgs,
        _run_las_perioder,
    ),
    (
        "las_verifikationer",
        "Läs postade och ej postade verifikationer, filtrerbart på period "
        "och status. Skrivskyddat -- returnerar verifikationer som de redan "
        "är, ändrar ingenting.",
        LasVerifikationerArgs,
        _run_las_verifikationer,
    ),
    (
        "las_korrigeringar",
        "Läs rättelsehistorik (B-serie-korrigeringar) -- vad en människa "
        "senast rättade är den starkaste signalen som finns. Skrivskyddat.",
        LasKorrigeringarArgs,
        _run_las_korrigeringar,
    ),
    (
        "las_underlag",
        "Läs intagskön för underlag, eller en enskild posts metadata. "
        "Skrivskyddat -- ändrar inte kön.",
        LasUnderlagArgs,
        _run_las_underlag,
    ),
    (
        "hamta_underlagsfil",
        "Hämta innehållet i ett underlags fil, tolkat enligt textlager- och "
        "avstämningsreglerna (textlager först, sedan dokumentblock om "
        "modellen stödjer det, annars avstående). Skrivskyddat.",
        HamtaUnderlagsfilArgs,
        _run_hamta_underlagsfil,
    ),
    (
        "las_bankhandelser",
        "Läs bankhändelser relevanta för intaget, eller ett enskilt "
        "bankunderlags metadata och transaktioner. Skrivskyddat.",
        LasBankhandelserArgs,
        _run_las_bankhandelser,
    ),
    (
        "posta_verifikation",
        "Skapa och posta en ny verifikation till huvudboken i ett steg. "
        "Enda vägen att skriva till huvudboken. Kan aldrig ändra eller "
        "radera en redan postad verifikation -- felaktiga postningar rättas "
        "genom en ny B-serieverifikation, inte genom detta verktyg.",
        PostaVerifikationArgs,
        _run_posta_verifikation,
    ),
    (
        "registrera_avstaende",
        "Registrera ett dokumenterat avstående för ett underlag, med en "
        "motivering till varför det inte gick att bokföra. Skapar aldrig "
        "någon verifikation.",
        RegistreraAvstaendeArgs,
        _run_registrera_avstaende,
    ),
)

#: Anthropic tool-definition shape: {"name", "description", "input_schema"}.
#: Built once, in the fixed order of ``_TOOL_SPECS`` above.
AGENT_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": name,
        "description": description,
        "input_schema": args_model.model_json_schema(),
    }
    for name, description, args_model, _handler in _TOOL_SPECS
]

_TOOL_HANDLERS: dict[str, tuple[type[BaseModel], _ToolHandler]] = {
    name: (args_model, handler)
    for name, _description, args_model, handler in _TOOL_SPECS
}


def execute_tool(
    name: str,
    arguments: dict,
    *,
    actor: str,
    capabilities: LLMCapabilities,
) -> Any:
    """Validate and run one model-requested tool call.

    Returns a JSON-serializable result on success. Raises on failure --
    either ``domain.validation.ValidationError`` (unknown tool name, or
    arguments that fail the tool's own Pydantic schema) or whatever domain
    exception the backing repository/service call itself raises
    (``IntakeError``, ``BankInputError``, ``DocumentUnreadableError``,
    ``PostingConflictError``, ...). None of these are caught and converted
    here -- wrapping a raised exception into a ``tool_result`` with
    ``is_error: true`` is the session's (A8) job, since only the session
    holds the ``ToolCall.id`` needed to build that content block.
    """
    entry = _TOOL_HANDLERS.get(name)
    if entry is None:
        raise ValidationError(
            code="unknown_tool",
            message=f"No such tool: {name!r}",
            details=f"known tools: {sorted(_TOOL_HANDLERS)}",
        )
    args_model, handler = entry
    try:
        parsed_args = args_model.model_validate(arguments or {})
    except PydanticValidationError as exc:
        raise ValidationError(
            code="invalid_tool_arguments",
            message=f"Invalid arguments for tool {name!r}",
            details=str(exc),
        ) from exc
    return handler(parsed_args, actor=actor, capabilities=capabilities)
