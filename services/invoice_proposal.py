"""Invoice drafts proposed in a thread (docs/redesign/SPEC-fakturering-f1.md).

`foresla_faktura` and `andra_fakturautkast` land here, as do the issue's
thread hooks and the agent's two read tools. A proposal is three writes that
only make sense together -- the invoice draft, the `draft` card
(`kind: "invoice"`) and the `thread_invoice_drafts` row -- so they are made
in one transaction, the pattern `DraftService.propose` uses for vouchers.

What this module deliberately does not do:

- Issue. The human's press on `Utfärda` is the approval (F0 beslut 3); a
  proposal only prepares the draft that press issues.
- Change a draft in place. A change is a new draft that replaces the old one,
  which is rejected (beslut 1), so the draft behind a card is always exactly
  what the card shows.
- Compute a number. The agent proposes it (F0 beslut 4); the server checks
  only that it is unique -- here, and again when issued.

Layering (AGENTS.md): no SQL here, and no HTTP. Errors are `ValidationError`s
with the `{code, message, details}` shape the session renders for the model.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from db.database import db
from domain.models import InvoiceProposal, Thread, ThreadPost
from domain.types import ThreadViewKey
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.audit_repo import AuditRepository
from repositories.customer_article_repo import ArticleRepository, CustomerRepository
from repositories.invoice_draft_repo import InvoiceDraftRepository
from repositories.invoice_proposal_repo import InvoiceProposalRepository
from repositories.invoice_repo import InvoiceRepository, PaymentRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_draft_repo import ThreadDraftTransitionError
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.idempotency import IdempotencyOutcome, IdempotencyService

logger = logging.getLogger(__name__)

#: Idempotency-key scopes (§5.3, §5.4): their own namespaces, so a proposal,
#: a change and a posting from the same user post never collide.
FORESLA_FAKTURA_ENDPOINT = "TOOL foresla_faktura"
ANDRA_FAKTURAUTKAST_ENDPOINT = "TOOL andra_fakturautkast"

#: The one view whose thread the writing tools belong to (beslut 3).
INVOICING_VIEW = ThreadViewKey.BETALA_FAKTURERING.value

_HTTP_201_CREATED = 201

#: Statuses `GET /drafts` accepts for invoice rows.
PROPOSAL_STATUSES = ("pending", "issued", "superseded", "rejected")

_VAT_TOTAL_LABELS = {"MP1": "Moms 25 %", "MP2": "Moms 12 %", "MP3": "Moms 6 %"}

#: Trace chips on the receipt (§8.1).
RECEIPT_INVOICE_TOOL = "utfarda_faktura"
RECEIPT_POSTED_TOOL = "posta_utkast"
RECEIPT_PDF_TOOL = "pdf"
RECEIPT_DUE_TOOL = "forfallodag"
RECEIPT_WAITING_TOOL = "vantar"

_NOTHING_CHANGED = "Ingenting har bokförts och ingen faktura är utfärdad."

#: Failures that are not failures for the thread (§9): the card's own state
#: says what happened.
_NOT_A_FAILURE = frozenset(
    {"draft_already_issued", "draft_rejected", "draft_not_found", "draft_in_thread"}
)

#: Swedish names of `company_info_incomplete.missing` (§9).
_COMPANY_FIELDS = {
    "name": "företagsnamn",
    "address": "adress",
    "org_number": "organisationsnummer",
    "seat": "säte",
    "vat_number": "momsregistreringsnummer",
    "bankgiro_or_plusgiro": "bankgiro eller plusgiro",
}

#: Draft fields a change may clear with an empty string (§5.4).
_CLEARABLE = (
    "reference",
    "customer_email",
    "customer_org_number",
    "delivery_from",
    "delivery_to",
    "delivery_month",
)


# --- the card (§6.1) --------------------------------------------------------


def _row_delivery(row, draft) -> Tuple[Any, Any, Any]:
    own = (row.delivery_from, row.delivery_to, row.delivery_month)
    if any(own):
        return own
    return (draft.delivery_from, draft.delivery_to, draft.delivery_month)


def _accounts_phrase(codes: Sequence[str]) -> str:
    """`1510 mot 3011 och 2610`: the receivable against the rest."""
    first, rest = codes[0], list(codes[1:])
    if not rest:
        return first
    tail = rest[0] if len(rest) == 1 else ", ".join(rest[:-1]) + " och " + rest[-1]
    return f"{first} mot {tail}"


def invoice_draft_body(
    draft,
    *,
    footnote: Optional[str],
    decision_id: Optional[str],
    replaces: bool = False,
) -> dict:
    """The `draft` card's body for an invoice (§6.1). Everything but
    `footnote` is the server's, built from the draft as stored."""
    from services.draft_service import period_name
    from services.invoice import invoice_booking_rows
    from services.invoice_issue import InvoiceIssueService
    from services.pdf_export import delivery_text

    rows = []
    net = 0
    vat_by_code: Dict[str, int] = {}
    vat_free = 0
    for row in draft.rows:
        quantity_centi = row.quantity_centi or row.quantity * 100
        rows.append(
            {
                "text": row.description,
                "article_number": row.article_number,
                "delivery": delivery_text(*_row_delivery(row, draft)) or None,
                "quantity_centi": quantity_centi,
                "unit": row.unit or "st",
                "unit_price_ore": row.unit_price,
                "amount_ore": row.amount_ex_vat,
            }
        )
        net += row.amount_ex_vat
        if row.vat_code == "MF":
            vat_free += row.amount_ex_vat
        else:
            vat_by_code[row.vat_code] = (
                vat_by_code.get(row.vat_code, 0) + row.vat_amount
            )

    totals = [{"key": "net", "text": "Netto", "amount_ore": net}]
    for code in ("MP1", "MP2", "MP3"):
        if code in vat_by_code:
            totals.append(
                {
                    "key": "vat",
                    "text": _VAT_TOTAL_LABELS[code],
                    "amount_ore": vat_by_code[code],
                }
            )
    if vat_free:
        totals.append({"key": "vat_free", "text": "Momsfritt", "amount_ore": vat_free})
    total = net + sum(vat_by_code.values())
    totals.append(
        {
            "key": "total",
            "text": f"Att betala senast {draft.due_date.isoformat()}",
            "amount_ore": total,
        }
    )

    codes = list(
        dict.fromkeys(
            r["account"]
            for r in invoice_booking_rows(draft.invoice_number, total, draft.rows)
        )
    )
    period = InvoiceIssueService._open_period(draft.invoice_date)
    consequence = (
        f"Utfärdas och bokförs i ett steg · {_accounts_phrase(codes)} · "
        f"period {period_name(period)} öppen\n"
        "PDF:en laddar du ner och skickar själv"
    )

    return {
        "draft_id": draft.id,
        "kind": "invoice",
        "title": f"Faktura {draft.invoice_number} · {draft.customer_name}",
        "meta": (
            f"{'nytt förslag' if replaces else 'förslag'} · "
            f"fakturadatum {draft.invoice_date.isoformat()}"
        ),
        "recipient": {
            "name": draft.customer_name,
            "address": (draft.customer_address or "").strip(),
            "reference": draft.reference,
        },
        "rows": rows,
        "totals": totals,
        "terms": f"{(draft.due_date - draft.invoice_date).days} dagar",
        "footnote": footnote,
        "consequence": consequence,
        "decision_id": decision_id,
    }


# --- possible duplicates (§5.3) ---------------------------------------------


def _interval(
    delivery_from, delivery_to, delivery_month
) -> Optional[Tuple[date, date]]:
    if delivery_from or delivery_to:
        start = delivery_from or delivery_to
        end = delivery_to or delivery_from
        return (start, end) if start <= end else (end, start)
    if delivery_month:
        try:
            year, month = (int(p) for p in delivery_month.split("-"))
            first = date(year, month, 1)
        except (ValueError, TypeError):
            return None
        following = date(year + (month == 12), month % 12 + 1, 1)
        return first, following - timedelta(days=1)
    return None


def possible_duplicates(draft) -> List[dict]:
    """Invoices to the same customer (by name) with a row of the same
    article number or description whose delivery overlaps a row of the
    draft. Stops nothing: the agent asks, the human decides."""
    found: List[dict] = []
    seen = set()
    for invoice in InvoiceRepository.list_for_customer(draft.customer_name):
        for draft_row in draft.rows:
            mine = _interval(*_row_delivery(draft_row, draft))
            if mine is None:
                continue
            for row in invoice.rows:
                same = (
                    draft_row.article_number
                    and row.article_number == draft_row.article_number
                ) or (
                    row.description.strip().lower()
                    == draft_row.description.strip().lower()
                )
                theirs = _interval(
                    row.delivery_from, row.delivery_to, row.delivery_month
                )
                if not same or theirs is None:
                    continue
                if theirs[0] <= mine[1] and mine[0] <= theirs[1]:
                    key = (invoice.id, row.id)
                    if key in seen:
                        continue
                    seen.add(key)
                    from services.pdf_export import delivery_text

                    found.append(
                        {
                            "invoice_id": invoice.id,
                            "invoice_number": invoice.invoice_number,
                            "invoice_date": invoice.invoice_date.isoformat(),
                            "row": row.description,
                            "delivery": delivery_text(
                                row.delivery_from, row.delivery_to, row.delivery_month
                            ),
                        }
                    )
    return found


# --- the service ------------------------------------------------------------


class InvoiceProposalService:
    """`propose` (§5.3), `change` (§5.4), the issue's hooks (§7.3, §7.4,
    §9), the list the card reads its state from (§10.1), and the two read
    tools (§5.1, §5.2)."""

    def __init__(self):
        self.audit = AuditRepository()

    # -- foresla_faktura --------------------------------------------------

    def propose(
        self,
        thread: Thread,
        *,
        fields: Dict[str, Any],
        footnote: Optional[str] = None,
        decision_id: Optional[str] = None,
        actor: str = "agent",
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Check, then write draft, card and row in one transaction.
        `fields` are `InvoiceDraftService.create_draft`'s keyword arguments.
        """
        request = {
            "fields": _jsonable(fields),
            "footnote": footnote,
            "decision_id": decision_id,
        }
        return self._with_key(
            idempotency_key,
            FORESLA_FAKTURA_ENDPOINT,
            thread,
            request,
            actor,
            lambda idem: self._propose(
                thread,
                fields=fields,
                footnote=footnote,
                decision_id=decision_id,
                replaces=None,
                actor=actor,
                idempotency=idem,
                idempotency_key=idempotency_key,
                endpoint=FORESLA_FAKTURA_ENDPOINT,
            ),
        )

    # -- andra_fakturautkast ----------------------------------------------

    def change(
        self,
        thread: Thread,
        *,
        draft_id: str,
        changes: Dict[str, Any],
        rows: Optional[List[Dict[str, Any]]] = None,
        footnote: Optional[str] = None,
        decision_id: Optional[str] = None,
        reject_reason: Optional[str] = None,
        actor: str = "agent",
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """A new draft with the change that replaces `draft_id`, or --
        with `reject_reason` -- `draft_id` rejected (§5.4)."""
        request = {
            "draft_id": draft_id,
            "changes": _jsonable(changes),
            "rows": _jsonable(rows),
            "footnote": footnote,
            "decision_id": decision_id,
            "reject_reason": reject_reason,
        }
        return self._with_key(
            idempotency_key,
            ANDRA_FAKTURAUTKAST_ENDPOINT,
            thread,
            request,
            actor,
            lambda idem: self._change(
                thread,
                draft_id=draft_id,
                changes=changes,
                rows=rows,
                footnote=footnote,
                decision_id=decision_id,
                reject_reason=reject_reason,
                actor=actor,
                idempotency=idem,
                idempotency_key=idempotency_key,
            ),
        )

    # -- the issue's hooks ------------------------------------------------

    @staticmethod
    def on_issuing(draft_id: str, invoice_id: str, issued_at: datetime) -> None:
        """§7.3, inside the issue's transaction: a pending card is issued
        with its draft. A draft with no pending card is left alone."""
        proposal = InvoiceProposalRepository.get(draft_id)
        if proposal is None or proposal.status != "pending":
            return
        InvoiceProposalRepository.mark_issued(
            draft_id, invoice_id, issued_at, _commit=False
        )

    def on_issued(self, draft_id: str, *, actor: str) -> Optional[ThreadPost]:
        """§7.4, after the issue has committed: the receipt, then
        `message.completed` and `view.changed`. Idempotent and resumable --
        nothing unless the row is issued and has no receipt yet. The caller
        must not let an exception from here change the issue's answer."""
        proposal = InvoiceProposalRepository.get(draft_id)
        if (
            proposal is None
            or proposal.status != "issued"
            or proposal.receipt_post_id is not None
            or proposal.invoice_id is None
        ):
            return None
        invoice = InvoiceRepository.get(proposal.invoice_id)
        if invoice is None or invoice.voucher_id is None:
            return None
        voucher = VoucherRepository.get(invoice.voucher_id)
        if voucher is None:
            return None

        from services.decision_service import DecisionService
        from services.draft_service import voucher_label

        accounts = AccountRepository.get_all_as_dict()
        label = voucher_label(voucher)
        body = {
            "title": f"Faktura {invoice.invoice_number} utfärdad · {label}",
            "labels": ["var", "blir"],
            "rows": [
                {
                    "key": code,
                    "text": accounts[code].name if code in accounts else code,
                    "left_ore": before,
                    "right_ore": after,
                }
                for code, before, after in VoucherRepository.account_balances_around(
                    voucher.id
                )
            ],
            "voucher_id": voucher.id,
            "invoice_id": invoice.id,
            "pdf_url": f"/api/v1/invoices/{invoice.id}/pdf",
        }
        traces = [
            {
                "tool": RECEIPT_INVOICE_TOOL,
                "label": "faktura utfärdad",
                "detail": invoice.invoice_number,
                "invoice_id": invoice.id,
            },
            {
                "tool": RECEIPT_POSTED_TOOL,
                "label": "verifikation postad",
                "detail": label,
                "voucher_id": voucher.id,
            },
            {"tool": RECEIPT_PDF_TOOL, "label": "pdf sparad"},
            {
                "tool": RECEIPT_DUE_TOOL,
                "label": f"förfaller {invoice.due_date.isoformat()}",
            },
            {
                "tool": RECEIPT_WAITING_TOOL,
                "label": f"{DecisionService().count_waiting(proposal.view_key)} kvar",
            },
        ]
        try:
            with db.transaction():
                post = ThreadRepository.add_post(
                    thread_id=proposal.thread_id,
                    post_type="receipt",
                    actor=actor,
                    body=body,
                    traces=traces,
                    _commit=False,
                )
                InvoiceProposalRepository.set_receipt(draft_id, post.id, _commit=False)
        except ThreadDraftTransitionError:
            logger.info("Receipt for invoice draft %s already written", draft_id)
            return None

        from services.thread_stream import (
            EVENT_MESSAGE_COMPLETED,
            EVENT_VIEW_CHANGED,
            get_broker,
            post_event_payload,
        )

        broker = get_broker()
        broker.publish(
            proposal.thread_id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
        )
        broker.publish(
            proposal.thread_id,
            EVENT_VIEW_CHANGED,
            {
                "view_key": proposal.view_key,
                "changed": {
                    "invoice_id": invoice.id,
                    "draft_id": draft_id,
                    "voucher_id": voucher.id,
                    "kind": "invoice_issued",
                },
            },
        )
        return post

    def on_issue_failed(
        self, draft_id: str, error: ValidationError, *, actor: str
    ) -> Optional[ThreadPost]:
        """§9: a refused issue of a pending card, after the rollback. One
        `error` post per card and code, with `last_error_code`, in a
        transaction of their own. The caller must not let an exception from
        here change the issue's answer."""
        if error.code in _NOT_A_FAILURE:
            return None
        proposal = InvoiceProposalRepository.get(draft_id)
        if proposal is None or not _needs_error_post(proposal, error.code):
            return None
        body = issue_error_body(error, draft_id)
        try:
            with db.transaction():
                current = InvoiceProposalRepository.get(draft_id)
                if current is None or not _needs_error_post(current, error.code):
                    return None
                post = ThreadRepository.add_post(
                    thread_id=proposal.thread_id,
                    post_type="error",
                    actor=actor,
                    body=body,
                    _commit=False,
                )
                InvoiceProposalRepository.set_error(
                    draft_id, error.code, post.id, _commit=False
                )
        except ThreadDraftTransitionError:
            return None

        from services.thread_stream import (
            EVENT_MESSAGE_COMPLETED,
            get_broker,
            post_event_payload,
        )

        get_broker().publish(
            proposal.thread_id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
        )
        return post

    # -- GET /drafts (§10.1) ----------------------------------------------

    @staticmethod
    def list_proposals(
        *, view_key: str, status: str = "all", limit: Optional[int] = None
    ) -> Tuple[List[Tuple[InvoiceProposal, Optional[dict]]], int]:
        """One view's invoice proposals, oldest first, each with its
        `invoice` block when issued (one query per table for the page)."""
        proposals, total = InvoiceProposalRepository.list(
            view_key=view_key, status=status, limit=limit
        )
        invoices = {
            p.invoice_id: InvoiceRepository.get(p.invoice_id)
            for p in proposals
            if p.status == "issued" and p.invoice_id
        }
        numbers = VoucherRepository.numbers_for(
            [i.voucher_id for i in invoices.values() if i and i.voucher_id]
        )
        items = []
        for proposal in proposals:
            block = None
            invoice = invoices.get(proposal.invoice_id) if proposal.invoice_id else None
            if proposal.status == "issued" and invoice is not None:
                series_number = numbers.get(invoice.voucher_id or "")
                block = {
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "voucher_id": invoice.voucher_id,
                    "voucher": (
                        f"{series_number[0]}-{series_number[1]}"
                        if series_number
                        else None
                    ),
                    "pdf_url": (
                        f"/api/v1/invoices/{invoice.id}/pdf"
                        if invoice.pdf_path
                        else None
                    ),
                }
            items.append((proposal, block))
        return items, total

    # -- las_kunder, las_fakturor (§5.1, §5.2) ----------------------------

    @staticmethod
    def read_customers(
        *,
        query: Optional[str] = None,
        customer_id: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 50,
    ) -> dict:
        if customer_id:
            one = CustomerRepository.get(customer_id)
            customers = [one] if one else []
        else:
            customers = CustomerRepository.list_all(
                active_only=not include_inactive, search=query
            )
        truncated = len(customers) > limit
        customers = customers[:limit]
        last = InvoiceRepository.last_by_customer_names([c.name for c in customers])
        result = {
            "customers": [
                {
                    "id": c.id,
                    "name": c.name,
                    "org_number": c.org_number,
                    "email": c.email,
                    "address": c.address,
                    "payment_terms_days": c.payment_terms_days,
                    "contact_person": c.contact_person,
                    "active": c.active,
                    "last_invoice": (
                        {
                            "invoice_number": last[c.name][0],
                            "invoice_date": (
                                last[c.name][1].isoformat() if last[c.name][1] else None
                            ),
                        }
                        if c.name in last
                        else None
                    ),
                }
                for c in customers
            ],
            "articles": [
                {
                    "id": a.id,
                    "article_number": a.article_number,
                    "name": a.name,
                    "description": a.description,
                    "unit": a.unit,
                    "unit_price": a.unit_price,
                    "vat_code": a.vat_code,
                    "revenue_account": a.revenue_account,
                }
                for a in ArticleRepository.list_all(active_only=True)
            ],
        }
        if truncated:
            result["truncated"] = True
        return result

    @staticmethod
    def read_invoices(
        *,
        invoice_id: Optional[str] = None,
        customer: Optional[str] = None,
        status: str = "all",
        drafts: bool = False,
        limit: int = 20,
    ) -> dict:
        from services.pdf_export import delivery_text

        if invoice_id:
            invoice = InvoiceRepository.get(invoice_id)
            if invoice is None:
                raise ValidationError(
                    "invoice_not_found", "Invoice not found", f"invoice_id={invoice_id}"
                )
            return {
                "invoice": {
                    **_invoice_summary(invoice),
                    "customer_address": invoice.customer_address,
                    "customer_reference": invoice.customer_reference,
                    "rows": [
                        {
                            "description": r.description,
                            "article_number": r.article_number,
                            "quantity": str(
                                Decimal(r.quantity_centi or r.quantity * 100) / 100
                            ),
                            "unit": r.unit,
                            "unit_price": r.unit_price,
                            "vat_code": r.vat_code,
                            "amount_ex_vat": r.amount_ex_vat,
                            "delivery": delivery_text(
                                r.delivery_from, r.delivery_to, r.delivery_month
                            )
                            or None,
                        }
                        for r in invoice.rows
                    ],
                    "payments": [
                        {
                            "amount": p.amount,
                            "payment_date": p.payment_date.isoformat(),
                            "reference": p.reference,
                        }
                        for p in PaymentRepository.list_for_invoice(invoice.id)
                    ],
                }
            }

        needle = (customer or "").strip().lower()
        if drafts:
            items = [
                d
                for d in InvoiceDraftRepository.list_all()
                if d.status in ("draft", "needs_review")
                and (not needle or needle in d.customer_name.lower())
            ]
            pending = InvoiceProposalRepository.pending_post_ids([d.id for d in items])
            return {
                "drafts": [
                    {
                        "id": d.id,
                        "invoice_number": d.invoice_number,
                        "customer_name": d.customer_name,
                        "invoice_date": d.invoice_date.isoformat(),
                        "amount_inc_vat": d.amount_inc_vat,
                        "status": d.status,
                        "pending_post_id": pending.get(d.id),
                    }
                    for d in items[:limit]
                ],
                "total": len(items),
            }

        today = date.today()
        invoices = [
            i
            for i in InvoiceRepository.list_all()
            if (not needle or needle in i.customer_name.lower())
            and _status_matches(i, status, today)
        ]
        page = invoices[:limit]
        numbers = VoucherRepository.numbers_for(
            [i.voucher_id for i in page if i.voucher_id]
        )
        return {
            "invoices": [
                {
                    **_invoice_summary(i, today),
                    "voucher": (
                        f"{numbers[i.voucher_id][0]}-{numbers[i.voucher_id][1]}"
                        if i.voucher_id in numbers
                        else None
                    ),
                }
                for i in page
            ],
            "latest_numbers": InvoiceRepository.latest_numbers(5),
            "total": len(invoices),
        }

    # -- internals --------------------------------------------------------

    def _with_key(self, key, endpoint, thread, request, actor, run) -> dict:
        idempotency = IdempotencyService()
        if key:
            outcome = idempotency.begin(
                key=key,
                endpoint=endpoint,
                body={"thread_id": thread.id, **request},
                actor=actor,
            )
            if outcome.kind == IdempotencyOutcome.REPLAY:
                payload = dict(outcome.response_payload or {})
                payload["idempotent_replay"] = True
                return payload
            if outcome.kind == IdempotencyOutcome.MISMATCH:
                raise ValidationError(
                    "idempotency_key_reuse",
                    "This proposal slot in the turn was already used for "
                    "different arguments",
                    details=outcome.original_fingerprint,
                )
            if outcome.kind == IdempotencyOutcome.IN_FLIGHT:
                raise ValidationError(
                    "request_in_flight",
                    "Another attempt is already writing this proposal",
                )
        try:
            return run(idempotency)
        except Exception:
            if key:
                idempotency.release(key, endpoint)
            raise

    @staticmethod
    def _check_thread(thread: Thread) -> None:
        if thread.view_key != INVOICING_VIEW:
            raise ValidationError(
                "wrong_view",
                "Invoice proposals belong to Fakturering's thread",
                f"view_key={thread.view_key}; expected {INVOICING_VIEW}",
            )

    def _propose(
        self,
        thread: Thread,
        *,
        fields: Dict[str, Any],
        footnote: Optional[str],
        decision_id: Optional[str],
        replaces: Optional[Tuple[Any, Optional[InvoiceProposal]]],
        actor: str,
        idempotency: IdempotencyService,
        idempotency_key: Optional[str],
        endpoint: str,
    ) -> dict:
        from services.draft_service import DraftService
        from services.invoice_draft import InvoiceDraftService
        from services.invoice_issue import InvoiceIssueService

        self._check_thread(thread)
        DraftService._check_decision(thread, decision_id)

        with db.transaction():
            draft = InvoiceDraftService().create_draft(
                **fields, status="needs_review", created_by="agent", _commit=False
            )
            # §5.3 (beslut 6): what the issue will check, now -- a card with
            # `Utfärda` can be issued when it is shown.
            InvoiceIssueService().check(draft)
            body = invoice_draft_body(
                draft,
                footnote=footnote,
                decision_id=decision_id,
                replaces=replaces is not None,
            )
            post = ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="draft",
                actor=actor,
                body=body,
                _commit=False,
            )
            InvoiceProposalRepository.create(
                draft_id=draft.id,
                thread_id=thread.id,
                post_id=post.id,
                view_key=thread.view_key,
                decision_id=decision_id,
                _commit=False,
            )
            replaced_draft_id = None
            if replaces is not None:
                old, old_proposal = replaces
                replaced_draft_id = old.id
                # §4.2: the row first (it guards `pending` itself), then the
                # old draft rejected -- never deleted, it is the trace.
                if old_proposal is not None and old_proposal.status == "pending":
                    InvoiceProposalRepository.mark_superseded(
                        old.id, draft.id, _commit=False
                    )
                self._reject_draft(old, actor, f"ersatt av {draft.id}")

            result = {
                "draft_id": draft.id,
                "post_id": post.id,
                "status": "pending",
                "invoice_number": draft.invoice_number,
                "invoice_date": draft.invoice_date.isoformat(),
                "due_date": draft.due_date.isoformat(),
                "amount_ex_vat": draft.amount_ex_vat,
                "vat_amount": draft.vat_amount,
                "amount_inc_vat": draft.amount_inc_vat,
                "meta": body["meta"],
                "consequence": body["consequence"],
                "decision_id": decision_id,
                "possible_duplicates": possible_duplicates(draft),
            }
            if replaces is not None:
                result["replaced_draft_id"] = replaced_draft_id
            if idempotency_key:
                idempotency.complete(
                    key=idempotency_key,
                    endpoint=endpoint,
                    response_status=_HTTP_201_CREATED,
                    response_payload=result,
                    entity_type="invoice_draft",
                    entity_id=draft.id,
                    _commit=False,
                )
        return result

    def _change(
        self,
        thread: Thread,
        *,
        draft_id: str,
        changes: Dict[str, Any],
        rows: Optional[List[Dict[str, Any]]],
        footnote: Optional[str],
        decision_id: Optional[str],
        reject_reason: Optional[str],
        actor: str,
        idempotency: IdempotencyService,
        idempotency_key: Optional[str],
    ) -> dict:
        self._check_thread(thread)
        old = InvoiceDraftRepository.get(draft_id)
        if old is None:
            raise ValidationError(
                "draft_not_found", "Invoice draft not found", f"draft_id={draft_id}"
            )
        proposal = InvoiceProposalRepository.get(draft_id)
        if proposal is not None and proposal.status == "superseded":
            raise ValidationError(
                "draft_superseded",
                "This proposal has been replaced: change the newer one",
                f"replaced_by={proposal.replaced_by}",
                payload={"replaced_by": proposal.replaced_by},
            )
        if old.status in ("issued", "sent"):
            invoice_id = (
                old.approved_invoice_id
                or InvoiceRepository.find_id_by_source_draft(old.id)
            )
            raise ValidationError(
                "draft_already_issued",
                "The draft is issued; an issued invoice is corrected with a "
                "credit note",
                f"invoice_id={invoice_id}",
                payload={"invoice_id": invoice_id},
            )
        if old.status == "rejected":
            raise ValidationError(
                "draft_rejected", "The draft is rejected", f"draft_id={draft_id}"
            )

        if reject_reason is not None:
            if changes or rows is not None or footnote is not None:
                raise ValidationError(
                    "reject_is_exclusive",
                    "reject_reason rejects the draft: give no other change with it",
                )
            with db.transaction():
                if proposal is not None and proposal.status == "pending":
                    InvoiceProposalRepository.mark_rejected(draft_id, _commit=False)
                self._reject_draft(old, actor, reject_reason)
                result = {"draft_id": draft_id, "status": "rejected"}
                if idempotency_key:
                    idempotency.complete(
                        key=idempotency_key,
                        endpoint=ANDRA_FAKTURAUTKAST_ENDPOINT,
                        response_status=200,
                        response_payload=result,
                        entity_type="invoice_draft",
                        entity_id=draft_id,
                        _commit=False,
                    )
            if proposal is not None:
                self._publish_view_changed(proposal, draft_id, "invoice_rejected")
            return result

        original = _fields_from_draft(old)
        merged = _merge(original, changes, rows)
        if merged == original:
            raise ValidationError(
                "nothing_changed",
                "The change gives the same invoice as the draft already is",
            )
        return self._propose(
            thread,
            fields=merged,
            footnote=footnote,
            decision_id=decision_id,
            replaces=(old, proposal),
            actor=actor,
            idempotency=idempotency,
            idempotency_key=idempotency_key,
            endpoint=ANDRA_FAKTURAUTKAST_ENDPOINT,
        )

    def _reject_draft(self, draft, actor: str, reason: str) -> None:
        """The old draft `rejected`, inside the caller's transaction. Through
        the repository, not `InvoiceDraftService.reject`: that refuses a
        draft with a pending card, which this is until the row moved."""
        InvoiceDraftRepository.update_status(draft.id, "rejected")
        self.audit.log(
            entity_type="invoice_draft",
            entity_id=draft.id,
            action="rejected",
            actor=actor,
            payload={"previous_status": draft.status, "reason": reason},
            _commit=False,
        )

    @staticmethod
    def _publish_view_changed(proposal: InvoiceProposal, draft_id: str, kind: str):
        try:
            from services.thread_stream import EVENT_VIEW_CHANGED, get_broker

            get_broker().publish(
                proposal.thread_id,
                EVENT_VIEW_CHANGED,
                {
                    "view_key": proposal.view_key,
                    "changed": {"draft_id": draft_id, "kind": kind},
                },
            )
        except Exception:
            logger.exception("view.changed for invoice draft %s failed", draft_id)


# --- the error post (§9) ----------------------------------------------------


def issue_error_body(error: ValidationError, draft_id: str) -> dict:
    """Cause and consequence in bookkeeping terms, never a status code.
    `retry_draft_id` is always `None`: whether `Utfärda` stays is the card's
    state (beslut 8), not the error card's."""
    from services.draft_service import period_name

    code = error.code
    payload = getattr(error, "payload", {}) or {}
    if code == "number_taken":
        number = payload.get("invoice_number", "")
        cause = f"Nummer {number} användes av en annan faktura medan förslaget låg."
        tail = "Be agenten föreslå nästa nummer."
    elif code == "period_locked":
        period = None
        if payload.get("period_id"):
            period = PeriodRepository.get_period(payload["period_id"])
        name = period_name(period) if period else "perioden"
        when = (payload.get("locked_at") or "")[:16].replace("T", " ")
        who = payload.get("locked_by")
        cause = (
            f"Perioden {name} låstes"
            + (f" {when}" if when else "")
            + (f" av {who}" if who else "")
            + " medan förslaget låg."
        )
        tail = "Lås upp perioden och tryck igen, eller be agenten ändra fakturadatumet."
    elif code == "company_info_incomplete":
        missing = [_COMPANY_FIELDS.get(m, m) for m in payload.get("missing", [])]
        cause = f"Företagsuppgifter saknas: {', '.join(missing)}."
        tail = "Fyll i dem under Inställningar och tryck igen."
    else:
        cause = (
            "Fakturan klarade inte kontrollerna vid utfärdandet " f"({error.message})."
        )
        tail = "Förslaget ligger kvar men kan inte utfärdas som det står."
    return {
        "cause": cause,
        "consequence": f"{_NOTHING_CHANGED} {tail}",
        "retry_draft_id": None,
    }


def _needs_error_post(proposal: InvoiceProposal, code: str) -> bool:
    if proposal.status != "pending":
        return False
    return not (proposal.last_error_code == code and proposal.last_error_post_id)


# --- helpers ----------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _fields_from_draft(draft) -> Dict[str, Any]:
    """The draft as `create_draft` input, so a change can be merged into it
    and compared with it (§5.4)."""
    return {
        "invoice_number": draft.invoice_number,
        "invoice_date": draft.invoice_date,
        "due_date": draft.due_date,
        "customer_id": draft.customer_id,
        "customer_name": draft.customer_name,
        "customer_org_number": draft.customer_org_number,
        "customer_email": draft.customer_email,
        "customer_address": draft.customer_address,
        "reference": draft.reference,
        "delivery_from": draft.delivery_from,
        "delivery_to": draft.delivery_to,
        "delivery_month": draft.delivery_month,
        "rows_data": [
            {
                "article_id": r.article_id,
                "description": r.description,
                "quantity": str(Decimal(r.quantity_centi or r.quantity * 100) / 100),
                "unit": r.unit,
                "unit_price": r.unit_price,
                "vat_code": r.vat_code,
                "revenue_account": r.revenue_account,
                "article_number": r.article_number,
                "delivery_from": r.delivery_from,
                "delivery_to": r.delivery_to,
                "delivery_month": r.delivery_month,
            }
            for r in draft.rows
        ],
    }


def _merge(
    original: Dict[str, Any],
    changes: Mapping[str, Any],
    rows: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """`original` with `changes` on top: `None` keeps, `""` clears a
    clearable field. A new customer brings its own name and address unless
    they are given. A new invoice date without a due date keeps the terms."""
    merged = dict(original)
    new_customer = (
        changes.get("customer_id") is not None
        and changes["customer_id"] != original["customer_id"]
    )
    if new_customer:
        for key in (
            "customer_name",
            "customer_org_number",
            "customer_email",
            "customer_address",
            "reference",
            "due_date",
        ):
            merged[key] = None
    for key, value in changes.items():
        if value is None:
            continue
        if value == "" and key in _CLEARABLE:
            merged[key] = None
        else:
            merged[key] = value
    if (
        changes.get("invoice_date") is not None
        and changes.get("due_date") is None
        and not new_customer
    ):
        terms = original["due_date"] - original["invoice_date"]
        merged["due_date"] = changes["invoice_date"] + terms
    if rows is not None:
        merged["rows_data"] = [_row_input(r) for r in rows]
    if _canonical(merged) == _canonical(original):
        return original
    return merged


def _row_input(row: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    if isinstance(out.get("quantity"), Decimal):
        out["quantity"] = str(out["quantity"])
    return out


def _canonical(fields: Mapping[str, Any]) -> Any:
    """For the `nothing_changed` comparison: quantities as numbers and
    empty values as None, so `"28"` and `"28.00"` are the same."""

    def norm(value):
        if value == "":
            return None
        return value

    out = {k: norm(v) for k, v in fields.items() if k != "rows_data"}
    out["rows_data"] = [
        {
            **{k: norm(v) for k, v in row.items() if k != "quantity"},
            "quantity": Decimal(str(row.get("quantity")).replace(",", ".")),
        }
        for row in fields.get("rows_data", [])
    ]
    return _jsonable(out)


def _status_matches(invoice, status: str, today: date) -> bool:
    if status == "all":
        return True
    if status == "paid":
        return invoice.status == "paid"
    unpaid = invoice.status in ("sent", "partially_paid", "overdue")
    if status == "unpaid":
        return unpaid
    if status == "overdue":
        return invoice.counts_as_overdue(today)
    return True


def _invoice_summary(invoice, today: Optional[date] = None) -> dict:
    today = today or date.today()
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer_name": invoice.customer_name,
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "amount_inc_vat": invoice.amount_inc_vat,
        "remaining_amount": invoice.remaining_amount(),
        "status": invoice.status,
        "is_overdue": invoice.counts_as_overdue(today),
        "issued_in_bok": invoice.issued_at is not None,
        "pdf_url": (f"/api/v1/invoices/{invoice.id}/pdf" if invoice.pdf_path else None),
    }


__all__ = [
    "ANDRA_FAKTURAUTKAST_ENDPOINT",
    "FORESLA_FAKTURA_ENDPOINT",
    "INVOICING_VIEW",
    "InvoiceProposalService",
    "invoice_draft_body",
    "issue_error_body",
    "possible_duplicates",
]
