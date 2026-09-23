"""Domain models for the accounting system."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from domain.types import (
    AccountType,
    AuditAction,
    BankInputStatus,
    IntakeSourceType,
    IntakeStatus,
    VoucherSeries,
    VoucherStatus,
)


@dataclass
class FiscalYear:
    """Räkenskapsår (accounting year)."""

    id: str
    start_date: date
    end_date: date
    locked: bool = False
    locked_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def is_open(self) -> bool:
        """Check if fiscal year is open for posting."""
        return not self.locked


@dataclass
class Period:
    """Redovisningsperiod (accounting period - typically monthly)."""

    id: str
    fiscal_year_id: str
    year: int
    month: int
    start_date: date
    end_date: date
    locked: bool = False
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def is_open(self) -> bool:
        """Check if period is open for posting (BFL varaktighet requirement)."""
        return not self.locked


@dataclass
class Account:
    """Konto (chart of accounts - BAS 2026)."""

    code: str  # e.g., "1510"
    name: str
    account_type: AccountType
    vat_code: Optional[str] = None  # e.g., "MP1" for 25% VAT
    sru_code: Optional[str] = None  # Skatteverkets rapporteringskoder
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def is_debit_account(self) -> bool:
        """Check if account normally has debit balance (assets, expenses)."""
        return self.account_type in [
            AccountType.ASSET,
            AccountType.EXPENSE,
            AccountType.VAT_IN,
        ]

    def is_credit_account(self) -> bool:
        """Check if account normally has credit balance (liabilities, equity, revenue)."""
        return self.account_type in [
            AccountType.LIABILITY,
            AccountType.EQUITY,
            AccountType.REVENUE,
            AccountType.VAT_OUT,
        ]


@dataclass
class VoucherRow:
    """Konteringsrad (accounting row in a voucher)."""

    id: str
    voucher_id: str
    account_code: str
    debit: int = 0  # In öre (1 kr = 100)
    credit: int = 0  # In öre
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def is_debit(self) -> bool:
        """Check if this row is a debit entry."""
        return self.debit > 0

    def is_credit(self) -> bool:
        """Check if this row is a credit entry."""
        return self.credit > 0

    def get_amount(self) -> int:
        """Get the amount (debit or credit) in öre."""
        return self.debit if self.is_debit() else self.credit


@dataclass
class Voucher:
    """Verifikation (accounting voucher - BFL §5 kap 6)."""

    id: str
    series: VoucherSeries  # A or B (B for corrections)
    number: Optional[int]  # None until posted (SPEC flode-verifikationer §4.3)
    date: date
    period_id: str
    description: str
    status: VoucherStatus = VoucherStatus.DRAFT
    fiscal_year_id: Optional[str] = None
    rows: List[VoucherRow] = field(default_factory=list)
    correction_of: Optional[str] = (
        None  # Reference to original voucher if this is a correction
    )
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    posted_at: Optional[datetime] = None
    # Derived by the repository, never stored (SPEC-oversikt.md §3). None on a
    # voucher that was built in memory rather than read back.
    missing_attachment: Optional[bool] = None
    age_days: Optional[int] = None

    def is_posted(self) -> bool:
        """Check if voucher is posted (varaktighet - immutable)."""
        return self.status == VoucherStatus.POSTED

    def is_draft(self) -> bool:
        """Check if voucher is still in draft status."""
        return self.status == VoucherStatus.DRAFT

    def is_balanced(self) -> bool:
        """Validate that debit = credit (BFL balansräkning requirement)."""
        total_debit = sum(row.debit for row in self.rows)
        total_credit = sum(row.credit for row in self.rows)
        return total_debit == total_credit

    def get_total_debit(self) -> int:
        """Get total debit amount in öre."""
        return sum(row.debit for row in self.rows)

    def get_total_credit(self) -> int:
        """Get total credit amount in öre."""
        return sum(row.credit for row in self.rows)

    def is_correction(self) -> bool:
        """Check if this is a correction voucher (B-series)."""
        return self.series == VoucherSeries.B or self.correction_of is not None


@dataclass
class AuditLogEntry:
    """Behandlingshistorik (audit log entry)."""

    id: str
    entity_type: str  # voucher, period, account, etc
    entity_id: str
    action: AuditAction
    actor: str  # User ID or "system"
    payload: Optional[dict] = None  # JSON with before/after values
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class VoucherAttachment:
    """Verifikationsbilag (voucher attachment)."""

    id: str
    voucher_id: str
    filename: str
    sha256: str
    mime_type: str
    stored_path: str
    size_bytes: int
    uploaded_at: datetime = field(default_factory=datetime.now)


@dataclass
class IntakeSource:
    """Uploaded voucher source material before a voucher exists."""

    id: str
    source_type: Optional[IntakeSourceType]
    status: IntakeStatus
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    stored_path: str
    explanation: Optional[str] = None
    agent_guidance: Optional[str] = None
    uploaded_by: str = "system"
    uploaded_at: datetime = field(default_factory=datetime.now)
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


@dataclass
class IntakeProcessingAttempt:
    """Agent processing attempt for an intake source."""

    id: str
    intake_source_id: str
    status: IntakeStatus
    summary: str
    warnings: Optional[List[str]] = None
    error_detail: Optional[str] = None
    voucher_id: Optional[str] = None
    actor: str = "system"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class VoucherIntakeSource:
    """Traceability link between a posted voucher and intake source material."""

    id: str
    voucher_id: str
    intake_source_id: str
    linked_by: str
    linked_at: datetime = field(default_factory=datetime.now)
    link_reason: Optional[str] = None


@dataclass
class BankInput:
    """Uploaded bank CSV source material before agent voucher posting."""

    id: str
    bank_connection_id: str
    status: BankInputStatus
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    stored_path: str
    uploaded_by: str
    uploaded_at: datetime = field(default_factory=datetime.now)
    detected_format: Optional[str] = None
    imported_count: int = 0
    skipped_count: int = 0
    parse_error: Optional[str] = None
    processed_at: Optional[datetime] = None


@dataclass
class BankInputTransactionLink:
    """Traceability link between a bank input and imported bank transaction."""

    id: str
    bank_input_id: str
    bank_transaction_id: str
    linked_at: datetime = field(default_factory=datetime.now)


@dataclass
class VoucherBankInput:
    """Traceability link between a posted voucher and uploaded bank input."""

    id: str
    voucher_id: str
    bank_input_id: str
    linked_by: str
    linked_at: datetime = field(default_factory=datetime.now)


@dataclass
class VoucherBankTransaction:
    """Traceability link between a posted voucher and used bank transaction."""

    id: str
    voucher_id: str
    bank_transaction_id: str
    linked_by: str
    linked_at: datetime = field(default_factory=datetime.now)


@dataclass
class CorrectionHistory:
    """Historik över bokföringskorrigeringar."""

    id: str
    original_voucher_id: str
    corrected_voucher_id: Optional[str] = None
    original_data: Optional[dict] = None
    corrected_data: Optional[dict] = None
    change_type: Optional[str] = (
        None  # 'account', 'amount', 'description', 'vat_code', 'multiple'
    )
    was_successful: Optional[bool] = None
    corrected_by: Optional[str] = None
    correction_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class CorrectionNote:
    """User correction note driving an agent-suggested B-series draft."""

    id: str
    voucher_id: str
    note_text: str
    status: str = "pending"  # pending, suggested, applied, dismissed, rejected
    suggested_voucher_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


@dataclass
class IdempotencyKey:
    """A client's claim on one irreversible write.

    Not accounting material: these rows protect vouchers, they are not vouchers.
    The audit trail is `audit_log`, never this table.
    """

    key: str
    endpoint: str
    request_fingerprint: str
    state: str  # in_flight, completed
    actor: str
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class AgentRun:
    """One pass of the agent runtime over the intake queue.

    Mirrors `agent_runs` (migration 024). `model` and `protocol` travel with
    the run rather than living in config, because model selection is per
    conversation (SPEC-agentruntime.md §2/§5).
    """

    id: str
    trigger: str  # 'schedule' | 'manual' | 'thread'
    status: str  # 'running' | 'completed' | 'failed' | 'abandoned'
    started_at: datetime
    model: str
    protocol: str  # 'messages' | 'chat'
    finished_at: Optional[datetime] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_ore: int = 0
    items_seen: int = 0
    items_posted: int = 0
    items_abstained: int = 0
    last_error: Optional[str] = None


@dataclass
class AgentRunEvent:
    """One row of `agent_run_events` — not the audit trail.

    `audit_log` is the accounting audit trail and never changes; these rows
    exist so `GET /agent/status` can show current activity and so `tradar`
    can later render the same events as thread posts.
    """

    id: str
    run_id: str
    seq: int
    kind: str  # 'item_started'|'tool_call'|'tool_result'|'posted'|'abstained'|'error'|'text'
    payload_json: str
    created_at: datetime
    source_id: Optional[str] = None
    voucher_id: Optional[str] = None


@dataclass
class Thread:
    """One conversation, bound to a view and a fiscal year (SPEC-tradar.md §4).

    `README.md`: "Chatten hör till vyn, inte till appen." `view_key` is the
    view and nothing else — no company prefix (decision §12.2, single-tenant).
    One thread per `(view_key, fiscal_year_id)` (decision §12.3), pinned by a
    unique constraint in migration 025 rather than by convention here.

    `model` is where the human's model choice is stored; a run takes it as an
    argument and `agent_runs.model`/`.protocol` per run is what makes a change
    mid-thread visible afterwards (§12.4).
    """

    id: str
    view_key: str
    fiscal_year_id: str
    model: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ThreadPost:
    """One post in a thread — what the human saw, in the order she saw it.

    Not the audit trail: `audit_log` is (SPEC-tradar.md antagande 5). Nothing
    here is ever modified or deleted; a correction is a new post. A streaming
    `agent_text` is written once, when the turn is done — the deltas along the
    way only travel over SSE and are never stored per character (§4).

    `body` carries the type's payload (the shape per type is §6.2), `traces`
    the `SparChip` row, and `run_id` binds an agent post to the run that
    produced it.
    """

    id: str
    thread_id: str
    seq: int
    type: str  # one of THREAD_POST_TYPES
    actor: str  # 'agent' or the user's name
    body: dict
    created_at: datetime = field(default_factory=datetime.now)
    traces: Optional[List[dict]] = None
    run_id: Optional[str] = None


@dataclass
class DecisionOption:
    """One row an agent laid out under a decision (SPEC-beslut.md §4).

    `decision_options` is its own table, not JSON packed onto `decisions`:
    the `option_id` an answer names must check against what was actually
    laid out, and `position` carries the order the options were shown in —
    part of the contract, since the last option is always a way out (§6.3).
    """

    id: str
    decision_id: str
    position: int
    title: str
    rationale: str
    account: Optional[str] = None
    amount_ore: Optional[int] = None
    recommended: bool = False
    is_exit: bool = False

    @property
    def changes_the_books(self) -> bool:
        """SPEC §6.3: whether choosing this option would write a ledger row.

        `account` set **and** `amount_ore` non-zero. This is derived from
        the option's own fields, not a second flag the agent has to
        remember to set — which is exactly what makes the escalation
        invariant testable in code instead of dependent on the prompt
        having been followed.
        """
        return (
            self.account is not None
            and self.amount_ore is not None
            and bool(self.amount_ore)
        )


@dataclass
class Decision:
    """A question the agent stopped to ask, tracked from open to closed
    (SPEC-beslut.md §4).

    `thread_posts` are never modified (SPEC-tradar.md §8.4), so "answered"
    cannot live as a column on the post that showed the question — that's
    the entire reason this table, and this class, exist. `options` is filled
    in by `DecisionRepository.get`/`.list_decisions`, sorted by `position`;
    nothing outside `repositories/decision_repo.py` writes SQL against
    `decision_options`.
    """

    id: str
    thread_id: str
    post_id: str
    view_key: str
    kind: str  # 'abstention' | 'approval'
    status: str  # 'open' | 'answered' | 'superseded'
    title: str
    reason: str
    consequence: str
    amount_ore: Optional[int] = None
    source_kind: Optional[str] = None
    source_id: Optional[str] = None
    source_date: Optional[date] = None
    created_at: datetime = field(default_factory=datetime.now)
    answered_at: Optional[datetime] = None
    answered_by: Optional[str] = None
    answer_option_id: Optional[str] = None
    answer_text: Optional[str] = None
    answer_post_id: Optional[str] = None
    reminded_at: Optional[datetime] = None
    options: list[DecisionOption] = field(default_factory=list)

    def age_days(self, today: Optional[date] = None) -> int:
        """Days since `created_at`, never negative.

        Counted in the domain, never in SQL — the same stance as
        `Invoice.counts_as_overdue` in `domain/invoice_models.py`, so the
        rule (and the reminder at seven days, §6.5) is testable without a
        database. `today` defaults to `date.today()`; a caller passes it
        explicitly to keep a test deterministic.
        """
        as_of = today if today is not None else date.today()
        return max((as_of - self.created_at.date()).days, 0)
