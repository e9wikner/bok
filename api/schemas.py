"""Pydantic schemas for API requests/responses."""

from datetime import date as DateType
from datetime import datetime as DateTimeType
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Voucher Schemas


class VoucherRowRequest(BaseModel):
    """Request model for voucher row."""

    account: str = Field(..., description="Account code (e.g., '1510')")
    debit: int = Field(0, description="Debit amount in öre (1 kr = 100)")
    credit: int = Field(0, description="Credit amount in öre (1 kr = 100)")
    description: Optional[str] = None


class VoucherRowResponse(BaseModel):
    """Response model for voucher row."""

    id: str
    voucher_id: str
    account: str
    account_code: str
    account_name: Optional[str] = None
    debit: int
    credit: int
    description: Optional[str] = None


class CreateVoucherRequest(BaseModel):
    """Request to create new voucher."""

    series: str = Field("A", description="Voucher series (A=normal, B=correction)")
    number: Optional[int] = Field(
        None,
        description=(
            "Voucher number, set at posting (auto-assigned if omitted); "
            "requires auto_post"
        ),
    )
    date: DateType = Field(..., description="Voucher date")
    period_id: str = Field(..., description="Period ID")
    description: str = Field(..., description="Voucher description")
    rows: List[VoucherRowRequest] = Field(..., description="Accounting rows (min 2)")
    auto_post: bool = Field(False, description="Automatically post after creation")


class UpdateVoucherRequest(BaseModel):
    """Request to update voucher rows in-place."""

    description: Optional[str] = Field(None, description="Updated description")
    rows: List[VoucherRowRequest] = Field(..., description="Updated accounting rows")
    reason: Optional[str] = Field(None, description="Reason for the change")


class CorrectVoucherRequest(BaseModel):
    """Request to correct a posted voucher with a B-series correction."""

    corrected_rows: List[VoucherRowRequest] = Field(
        ..., description="Intended corrected accounting rows"
    )
    reason: Optional[str] = Field(None, description="Reason for the correction")


class CreateCorrectionNoteRequest(BaseModel):
    """Request to create a correction note for a posted voucher."""

    note_text: str = Field(
        ..., description="User explanation of what should be corrected"
    )


class CorrectionDraftRequest(BaseModel):
    """Request to create a draft B-series correction voucher."""

    correction_rows: List[VoucherRowRequest] = Field(
        ..., description="Draft correction rows"
    )


class SuggestCorrectionNoteRequest(BaseModel):
    """Request to link a correction note to a draft B-series suggestion."""

    correction_rows: List[VoucherRowRequest] = Field(
        ..., description="Suggested correction rows"
    )


class ApproveCorrectionNoteRequest(BaseModel):
    """Request to approve a suggested correction note."""

    rows: Optional[List[VoucherRowRequest]] = Field(
        None, description="Optional edited draft rows"
    )


class DismissCorrectionNoteRequest(BaseModel):
    """Request to dismiss a pending or suggested correction note."""

    reason: Optional[str] = Field(None, description="Reason for dismissing the note")


class RejectCorrectionNoteRequest(BaseModel):
    """Request for an agent to reject a correction note."""

    rejection_reason: str = Field(
        ..., description="Why no correction could be suggested"
    )


class CorrectionNoteResponse(BaseModel):
    """Response model for a correction note."""

    id: str
    voucher_id: str
    note_text: str
    status: str
    suggested_voucher_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: DateTimeType
    created_by: str
    updated_at: Optional[DateTimeType] = None
    resolved_at: Optional[DateTimeType] = None


class VoucherRefResponse(BaseModel):
    """Another voucher named in the list's meta, e.g. `B-7`."""

    id: str
    series: str
    number: Optional[int]


class UnderlagWaiverResponse(BaseModel):
    """A human's approval of a voucher without underlag (migration 051)."""

    id: str
    voucher_id: str
    reason: str = Field(
        ...,
        description=(
            "later: the underlag arrives after the posting and is still matched;"
            " none: the voucher is its own document (an accrual, a depreciation)"
        ),
    )
    note: Optional[str] = None
    waived_by: str
    created_at: DateTimeType
    revoked_at: Optional[DateTimeType] = None
    revoked_by: Optional[str] = None


class UnderlagWaiverRequest(BaseModel):
    """`POST /vouchers/{id}/underlag-waiver`."""

    model_config = ConfigDict(extra="forbid")

    reason: Literal["later", "none"]
    note: Optional[str] = Field(None, max_length=500)


class CorrectionAccountResponse(BaseModel):
    """One account's net (debit minus credit, öre) before and after."""

    account_code: str
    account_name: Optional[str] = None
    before: int
    after: int


class VoucherCorrectionResponse(BaseModel):
    """What a correction did, derived on
    read: on a corrected voucher the effect of all its posted corrections,
    on a correction the effect of that one."""

    kind: str = Field(
        ...,
        description=(
            "makulering when the voucher nets to zero on every account "
            "afterwards, otherwise andring"
        ),
    )
    title: str = Field(..., description="Display title: `Makulering av A-53: …`")
    original: VoucherRefResponse
    original_description: str
    correction: VoucherRefResponse
    correction_date: DateType
    correction_status: str
    posted_at: Optional[DateTimeType] = None
    actor: Optional[str] = Field(None, description="Who posted the correction")
    reason: Optional[str] = None
    before_total: int
    after_total: int
    accounts: List[CorrectionAccountResponse]


class VoucherOriginResponse(BaseModel):
    """What a voucher is a booking of, when a flow posted it
    (`services/voucher_origin.py`)."""

    kind: str = Field(..., description="payslip, agi, invoice or invoice_payment")
    title: str
    view_key: str = Field(..., description="The /v4 view the thing lives in")


class VoucherResponse(BaseModel):
    """Response model for voucher."""

    id: str
    series: str
    number: Optional[int]  # None for a draft
    date: DateType
    period_id: str
    description: str
    comment: Optional[str] = Field(
        None,
        description=(
            "Free text beside the description, written when the voucher was "
            "created -- e.g. the exchange rate a foreign amount was converted "
            "at, its date and source. Never changes once posted"
        ),
    )
    status: str  # draft, posted
    rows: List[VoucherRowResponse]
    total_debit: int = 0
    total_credit: int = 0
    balanced: bool = True
    row_count: int = 0
    correction_of: Optional[str] = None
    created_at: DateTimeType
    created_by: str
    posted_at: Optional[DateTimeType] = None
    missing_attachment: bool = Field(
        False, description="True when no attachment is linked to the voucher"
    )
    age_days: int = Field(
        0,
        description="Whole days since the voucher date; negative for a date ahead",
    )
    missing_statement_accounts: List[str] = Field(
        default_factory=list,
        description=(
            "While the voucher lacks underlag: the statement accounts (1630, "
            "1900-1989) whose rows have no linked bank transaction yet"
        ),
    )
    corrected_by: Optional[VoucherRefResponse] = Field(
        None, description="The posted voucher that corrects this one"
    )
    corrects: Optional[VoucherRefResponse] = Field(
        None, description="The voucher this one corrects (correction_of)"
    )
    referenced_by: Optional[VoucherRefResponse] = Field(
        None,
        description=(
            "The posted voucher whose underlag is this one's linked receipt "
            "(voucher_source_references), e.g. a difference booked on its own"
        ),
    )
    underlag_waiver: Optional[UnderlagWaiverResponse] = Field(
        None,
        description=(
            "A logged-in human's current approval to stand without underlag;"
            " takes the voucher out of missing_attachment"
        ),
    )
    correction: Optional[VoucherCorrectionResponse] = Field(
        None,
        description=(
            "On a corrected voucher and on a correction: kind, net per account "
            "before and after, who and when"
        ),
    )
    origin: Optional[VoucherOriginResponse] = Field(
        None,
        description=(
            "What the voucher books, when an invoice, a payment, a payslip or "
            "an AGI posted it. Only on GET /vouchers/{id}"
        ),
    )


# Overview Schemas


class OverviewFiscalYear(BaseModel):
    """The fiscal year the header shows."""

    id: str
    label: str
    start: str
    end: str


class OverviewPeriodState(BaseModel):
    """The current period, shown once in the header and not per page."""

    current_period_id: str
    label: str
    locked: bool


class OverviewCounters(BaseModel):
    """The same counters on every page."""

    open_decisions: int = 0
    overdue_invoices: int = 0
    payroll_waiting: int = 0
    missing_attachments: int = 0
    closing_checks: int = 0


class OverviewPageResponse(BaseModel):
    """One page tab: a dot when something waits, and a meta line saying what."""

    key: str
    title: str
    waiting: bool
    meta: str
    counters: OverviewCounters


class OverviewViewWaiting(BaseModel):
    """What waits on the human in one view (tab), in the counted year."""

    key: str
    waiting: int


class OverviewClosingView(BaseModel):
    """The year-end checks left to do in one Bokslut view, shown under it."""

    key: str
    waiting: int
    meta: str


class OverviewOtherYear(BaseModel):
    """Another fiscal year where something waits on the human."""

    id: str
    label: str
    waiting: int
    meta: str


class OverviewResponse(BaseModel):
    """Everything the header needs, in one call."""

    fiscal_year: Optional[OverviewFiscalYear] = None
    period_state: Optional[OverviewPeriodState] = None
    pages: List[OverviewPageResponse]
    counted_fiscal_year_id: Optional[str] = None
    views: List[OverviewViewWaiting] = []
    other_years: List[OverviewOtherYear] = []
    closing_views: List[OverviewClosingView] = []


# Account Schemas


class CreateAccountRequest(BaseModel):
    """Request to create a new account."""

    code: str = Field(..., description="Account code (e.g., '1930')")
    name: str = Field(..., description="Account name")
    account_type: str = Field(
        ..., description="Account type (asset, liability, equity, revenue, expense)"
    )
    vat_code: Optional[str] = Field(None, description="VAT code if applicable")
    sru_code: Optional[str] = Field(None, description="SRU code for tax reporting")
    active: bool = Field(True, description="Whether account is active")


class AccountResponse(BaseModel):
    """Response model for account."""

    code: str
    name: str
    account_type: str
    vat_code: Optional[str] = None
    sru_code: Optional[str] = None
    active: bool


class AccountListResponse(BaseModel):
    """Response with list of accounts."""

    accounts: List[AccountResponse]
    total: int


# Period Schemas


class PeriodResponse(BaseModel):
    """Response model for period."""

    id: str
    fiscal_year_id: str
    year: int
    month: int
    start_date: DateType
    end_date: DateType
    locked: bool
    locked_at: Optional[DateTimeType] = None
    locked_by: Optional[str] = None
    created_at: DateTimeType


class FiscalYearCreateRequest(BaseModel):
    """A new fiscal year. Periods are created per calendar month, clipped to
    the year's own dates."""

    start_date: DateType
    end_date: DateType


class FiscalYearResponse(BaseModel):
    """Response model for fiscal year."""

    id: str
    start_date: DateType
    end_date: DateType
    locked: bool
    locked_at: Optional[DateTimeType] = None
    created_at: DateTimeType


class OpeningBalanceRow(BaseModel):
    """One account's opening balance."""

    account: str = Field(..., description="Account code, class 1-2")
    amount: int = Field(..., description="Öre, debit positive, credit negative")


class OpeningBalanceDifference(BaseModel):
    """An account where the stated IB and the derived one disagree."""

    account: str
    stated: int
    derived: int


class OpeningBalanceResponse(BaseModel):
    """A fiscal year's opening balance (ingående balans).

    `source`: `derived` -- from the previous fiscal year, follows it until
    that year is locked; `stated` -- the first year's, entered or imported;
    `none` -- a first year without one.
    """

    fiscal_year_id: str
    source: str
    previous_fiscal_year_id: Optional[str] = None
    balanced: bool
    balances: List[OpeningBalanceRow]
    stated_differences: List[OpeningBalanceDifference] = []


class OpeningBalanceRequest(BaseModel):
    """Replaces the first fiscal year's stated opening balance."""

    balances: List[OpeningBalanceRow]


# Report Schemas


class TrialBalanceRow(BaseModel):
    """Row in trial balance."""

    account_code: str
    debit: int
    credit: int
    balance: int


class TrialBalanceResponse(BaseModel):
    """Trial balance report."""

    period_id: str
    period: str
    as_of: DateType
    rows: List[TrialBalanceRow]
    total_debit: int
    total_credit: int


class AccountLedgerRow(BaseModel):
    """Row in account ledger."""

    date: DateType
    voucher_series: str
    voucher_number: str
    description: str
    debit: int
    credit: int
    balance: int


class AccountLedgerResponse(BaseModel):
    """Account ledger report."""

    account_code: str
    account_name: str
    period_id: str
    rows: List[AccountLedgerRow]
    ending_balance: int


# Audit Schemas


class AuditLogEntryResponse(BaseModel):
    """Audit log entry."""

    id: str
    entity_type: str
    entity_id: str
    action: str
    actor: str
    payload: Optional[dict] = None
    timestamp: DateTimeType


class AuditHistoryResponse(BaseModel):
    """Audit history."""

    entity_type: str
    entity_id: str
    entries: List[AuditLogEntryResponse]


# Agent Runtime Schemas (GET /api/v1/agent/status)


class AgentCurrentRunResponse(BaseModel):
    """The in-progress `agent_runs` row, if any (`current_run`).

    `current_source_id`/`current_activity` come from the process-wide
    `AgentWorker`, not from the `agent_runs` row itself -- see
    `api/routes/agent.py`'s `GET /agent/status` for how coarse-grained
    `current_activity` is (task A11).
    """

    id: str
    started_at: str
    trigger: str
    model: str
    protocol: str
    items_seen: int
    items_posted: int
    items_abstained: int
    current_source_id: Optional[str] = None
    current_activity: Optional[str] = None


class AgentLastRunResponse(BaseModel):
    """The most recently finished `agent_runs` row (`last_run`).

    `last_error` here is this specific run's own `agent_runs.last_error`
    column (e.g. why it failed) -- distinct from the response's top-level
    `last_error`, which is the runner's own last in-thread failure and may
    describe something that never got as far as an `agent_runs` row at all
    (see `api/routes/agent.py`'s `GET /agent/status`).
    """

    id: str
    started_at: str
    finished_at: Optional[str] = None
    trigger: str
    model: str
    protocol: str
    items_seen: int
    items_posted: int
    items_abstained: int
    status: str
    cost_ore: int
    last_error: Optional[str] = None


class AgentStatusResponse(BaseModel):
    """`GET /api/v1/agent/status`.

    Never carries the LLM gateway's API key setting -- see the route's docstring for the guarantee and the test that
    pins it.

    The four fields `datakontrakt.md` §7 asks for -- `state`, `since`,
    `current_task`, `paused_reason` -- were added with the threads.
    The pre-existing fields were **not** removed alongside them: this
    endpoint already has a consumer, and `enabled`/`running` answer a
    different question than `state` does (is the machinery on, versus what
    is it doing).

    The mode is **global, not per view**: one worker,
    one flock, one budget.
    """

    #: One of `arbetar` / `postar` / `pausad` / `vilande`
    #: (`services.agent_runtime.agent_state`). `komponenter.md`'s
    #: `AgentStatus` names the first three; the fourth is the ordinary case
    #: of nothing happening, which the design draws as no indicator at all.
    state: str
    #: When the current state began: the running pass's `started_at`, or
    #: `None` when nothing is running. What `AgentStatus` renders as "sedan".
    since: Optional[DateTimeType] = None
    #: The live tool name, e.g. `posta_verifikation` -- what
    #: `SkriverIndikator` says instead of being "en anonym spinner". `None`
    #: between items. Possible only since T5's streaming hook.
    current_task: Optional[str] = None
    #: Why the agent is paused, for as long as it is paused -- "inte bara i
    #: felinlägget" (`komponenter.md`). `None` when it is not.
    paused_reason: Optional[str] = None
    enabled: bool
    running: bool
    current_run: Optional[AgentCurrentRunResponse] = None
    last_run: Optional[AgentLastRunResponse] = None
    queue_depth: int
    cost_today_ore: int
    # `None` when no daily budget is configured.
    budget_today_ore: Optional[int] = None
    last_error: Optional[str] = None


# Thread Schemas (§6.2 — `datakontrakt.md` §1)


class ThreadPostResponse(BaseModel):
    """One post in a thread, in the shape `datakontrakt.md` §1 asks for:
    "Varje inlägg bär `id`, `created_at`, `actor` (`agent` eller användarens
    namn) och valfria `traces[]` (spårchipsen)."

    `seq` is the cursor a client passes back as `?since=` — dense and
    ascending per thread, so "what I missed" is a comparison, not a guess.
    `body` is the type's own payload; the eight shapes are deliberately not eight Pydantic models here, since
    the client renders one component per `type` and the server would gain
    nothing but a second place to keep them in step.
    """

    id: str
    seq: int
    type: str
    actor: str
    created_at: DateTimeType
    body: dict
    traces: Optional[List[dict]] = None
    run_id: Optional[str] = None


class ThreadResponse(BaseModel):
    """`GET /api/v1/threads/{view_key}` — posts in order, oldest first.

    `fiscal_year_id` says which year's thread this is: one thread per view
    and fiscal year (decision §12.3), so a client that wants an older one
    asks for it by id. `archive_fiscal_year_ids` is what it may ask for,
    newest first — the thread resets at the turn of the year, and older ones
    are reachable rather than gone.

    `thread_id` is `None` when nothing has been said in this view this year
    yet. That is an empty thread, not an error: a thread is created by the
    first message, and a `GET` is a pure read that creates nothing.

    `context_from_seq` is the conversation's reset boundary (migration 034):
    posts with a `seq` at or below it are still returned, but no longer go
    into the agent's context. 0 = never reset.
    """

    view_key: str
    thread_id: Optional[str] = None
    fiscal_year_id: Optional[str] = None
    model: Optional[str] = None
    posts: List[ThreadPostResponse] = Field(default_factory=list)
    cursor: int = 0
    archive_fiscal_year_ids: List[str] = Field(default_factory=list)
    context_from_seq: int = 0
    context_reset_at: Optional[DateTimeType] = None


class ThreadResetResponse(BaseModel):
    """`POST /api/v1/threads/{view_key}/reset` — the new context boundary.

    Every post at or below `context_from_seq` stays in the thread; none of
    them goes into the next turn's context.
    """

    thread_id: str
    view_key: str
    context_from_seq: int
    context_reset_at: DateTimeType


class ThreadModelRequest(BaseModel):
    """`PUT /api/v1/threads/{view_key}/model` — the human's model choice.

    Decision §12.4: `threads.model` is where the choice is stored, and
    `agent_runs.model`/`.protocol` per run is what makes a switch mid-thread
    visible afterwards, without a new table.
    """

    model: str = Field(..., min_length=1)


class ThreadModelResponse(BaseModel):
    """What a thread's model can and cannot do (§12.4).

    The protocol differences travel up and are **shown**: a thread on a Chat
    Completions model cannot read a PDF underlag directly and has no cache
    economy. "Det är en produktsanning, inte en detalj att dölja."
    """

    thread_id: str
    view_key: str
    model: str
    protocol: str
    reads_pdf_documents: bool
    has_cache_economy: bool
    streams: bool
    limitations: List[str] = Field(default_factory=list)


class ThreadMessageRequest(BaseModel):
    """`POST /api/v1/threads/{view_key}/messages` — `{ text, attachments[] }`.

    `attachments` are ids of intake sources already uploaded through
    `POST /api/v1/intake`, never the bytes themselves: the file already has a
    path, a hash and an audit trail there, and a second copy inside a thread
    post would have none of those ("Base64 kommer
    aldrig in i ett inlägg").

    This is also the **decision channel**. `README.md`: "Beslutskortets
    primärknapp är aldrig den enda vägen: samma beslut ska gå att uttrycka i
    text i chattfältet."

    `text` may be empty -- or only whitespace, which is the same -- when
    `attachments` is not: dropping a receipt
    without writing anything is the common case on a phone, and the client
    must not put words in the human's mouth. Without either it is a `422`,
    as before.
    """

    text: str = ""
    attachments: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _text_or_attachments(self) -> "ThreadMessageRequest":
        if not self.text.strip() and not self.attachments:
            raise ValueError("A message needs text or at least one attachment")
        return self

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


class ThreadMessageResponse(BaseModel):
    """What `POST .../messages` answers with, **before** the agent has said
    anything.

    The human's own reply must stand in the thread before the agent has
    begun; the answer arrives over the stream. `cursor` is where a client
    should subscribe from to see exactly what follows and nothing it already
    has.
    """

    thread_id: str
    view_key: str
    fiscal_year_id: str
    posts: List[ThreadPostResponse]
    cursor: int


# Decision Schemas (§6.1 -- the three-source union, B7)


class DecisionOptionResponse(BaseModel):
    """One row of `DecisionResponse.options` -- `decision_options`, in the
    order they were laid out (`position`). Always `[]` for the two
    synthetic sources (`kind` `intake` / `correction`): neither
    has an alternatives list of its own.
    """

    id: str
    position: int
    title: str
    rationale: str
    account: Optional[str] = None
    amount_ore: Optional[int] = None
    recommended: bool = False
    is_exit: bool = False


class DecisionSourceResponse(BaseModel):
    """`DecisionResponse.source` -- what grounds the decision, when there
    is one. `None` for an abstention raised mid-conversation."""

    kind: str
    id: str
    date: Optional[DateType] = None


class DecisionResponse(BaseModel):
    """One row of `GET /decisions`'s union, exactly this JSON shape
    -- `services/decision_service.py::DecisionView` with `created_at` (the
    union's own sort key) left off, since a client never needs it.

    `id` is raw `decisions.id` for `kind="abstention"`, and prefixed
    (`intake:{id}` / `correction:{id}`) for the two synthetic sources
    -- the three id spaces don't collide, so a client and
    `GET /decisions/{id}` can tell them apart from the id alone.

    `reason` is the agent's own words for `abstention` and `intake`, but
    **not** for `correction`: there `note_text` is the human's text, and
    `kind="correction"` is the tell a reader has to use instead of a
    different field name (`services/decision_service.py`'s
    `_correction_to_view` docstring -- "hela priset").
    """

    id: str
    view_key: str
    kind: str
    status: str
    title: str
    amount_ore: Optional[int] = None
    reason: str
    consequence: str
    source: Optional[DecisionSourceResponse] = None
    age_days: int
    thread_id: Optional[str] = None
    post_id: Optional[str] = None
    options: List[DecisionOptionResponse] = Field(default_factory=list)
    # How it was answered -- so a reloaded card can say when and mark the
    # chosen option, not just `Besvarat` (question 3).
    # `answer_text` is the human's words verbatim; `None` throughout for an
    # unanswered row and for the two synthetic sources.
    answered_at: Optional[DateTimeType] = None
    answered_by: Optional[str] = None
    answer_option_id: Optional[str] = None
    answer_text: Optional[str] = None


class DraftVoucherNumber(BaseModel):
    """The number a posted thread draft got."""

    series: str
    number: int


class DraftInvoice(BaseModel):
    """What an issued invoice proposal became."""

    invoice_id: str
    invoice_number: str
    voucher_id: Optional[str] = None
    voucher: Optional[str] = None
    pdf_url: Optional[str] = None


class ThreadDraftResponse(BaseModel):
    """One row of `GET /drafts`. `voucher`
    is set only when `status='posted'` -- the one place the client gets a
    number from."""

    # "voucher" or "invoice".
    kind: str = "voucher"
    draft_id: str
    post_id: str
    decision_id: Optional[str] = None
    correction_of: Optional[str] = None
    # The note a correction answers; the view folds the pending draft into the
    # synthetic `correction:{note}` decision it answers (§11.1, F14).
    correction_note_id: Optional[str] = None
    status: str
    replaced_by: Optional[str] = None
    posted_at: Optional[DateTimeType] = None
    voucher: Optional[DraftVoucherNumber] = None
    last_error_code: Optional[str] = None
    created_at: DateTimeType
    # An invoice proposal that is issued: the invoice, its voucher and PDF.
    invoice: Optional[DraftInvoice] = None


class ThreadDraftListResponse(BaseModel):
    """`GET /drafts` -- oldest first; `total` is the count before `limit`."""

    drafts: List[ThreadDraftResponse]
    total: int


class DecisionListResponse(BaseModel):
    """`GET /decisions` -- oldest first **over the whole union**, not per
    source. `total` is the union's count before
    `limit`/`offset` slice it, so a client can page correctly even though
    `len(decisions)` on any one page may be smaller than `limit`.
    """

    decisions: List[DecisionResponse]
    total: int


# Decision answer schemas


class DecisionAnswerRequest(BaseModel):
    """`POST /decisions/{id}/answer` -- `{ option_id }` **or**
    `{ free_text }`, exactly one. Both fields stay optional here: which
    one (or whether both, or neither) is a body-shape error is a rule on
    the answer itself, not on the request's shape, so it is
    `DecisionService.answer()` that raises `400`
    (`ValidationError(code="invalid_answer")`), not a Pydantic validator
    here -- the same "no business rule in the route" split this router
    keeps everywhere else.

    Fritextvägen is not a courtesy: `README.md`'s accessibility
    requirement is that every decision a `BeslutKort`'s primary button can
    express is equally expressible as plain text (testfall 12).
    """

    option_id: Optional[str] = None
    free_text: Optional[str] = None


class DecisionAnswerResponse(BaseModel):
    """What `POST /decisions/{id}/answer` answers `202` with: the decision
    in its new (`answered`) state, plus the id and `seq` of the
    `user_text` reply post that was written for it -- the same pairing
    `ThreadMessageResponse` gives a client for the human's own post, so it
    can find the reply in the thread (or as the SSE cursor to subscribe
    from) without a second request.
    """

    decision: DecisionResponse
    answer_post_id: str
    answer_post_seq: int


# Error Schemas


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    code: str
    details: Optional[str] = None
    timestamp: DateTimeType = Field(default_factory=DateTimeType.now)
