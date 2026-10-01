"""API routes for agent-created invoice drafts."""

import logging
from datetime import date
from functools import partial
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_current_actor, get_human_actor
from domain.invoice_validation import ValidationError, quantity_from_centi
from services.invoice_draft import InvoiceDraftService

router = APIRouter(prefix="/api/v1/invoice-drafts", tags=["invoice-drafts"])


class InvoiceDraftAgentNotes(BaseModel):
    summary: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    warnings: List[str] = Field(default_factory=list)


class InvoiceDraftRowRequest(BaseModel):
    article_id: Optional[str] = None
    description: Optional[str] = None
    quantity: Union[int, float, str] = Field(
        ...,
        description="Positive, at most two decimals; 7.5 or '7,5'",
        examples=[7.5],
    )
    unit: Optional[str] = Field(
        None, description="Unit, e.g. 'h'. Default: the article's, else 'st'"
    )
    unit_price: Optional[int] = Field(None, ge=0)
    vat_code: Optional[str] = Field(None, pattern="^(MP1|MP2|MP3|MF)$")
    revenue_account: Optional[str] = None
    source_note: Optional[str] = None
    article_number: Optional[str] = Field(
        None, description="Taken from the article when article_id is given"
    )
    delivery_from: Optional[date] = None
    delivery_to: Optional[date] = None
    delivery_month: Optional[str] = Field(
        None, description="YYYY-MM, when the exact date is not known"
    )


class CreateInvoiceDraftRequest(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_org_number: Optional[str] = None
    customer_email: Optional[str] = None
    invoice_date: date
    due_date: Optional[date] = None
    reference: Optional[str] = Field(
        None, description="Er referens. Default: the customer's contact_person"
    )
    description: Optional[str] = None
    invoice_number: Optional[str] = Field(
        None,
        description=(
            "Proposed number, ^[A-Za-z0-9-]{1,32}$ and not a bare date. "
            "Unique only when issued."
        ),
    )
    customer_address: Optional[str] = Field(
        None, description="Default: the customer's address"
    )
    delivery_from: Optional[date] = Field(
        None, description="Delivery for rows without their own"
    )
    delivery_to: Optional[date] = None
    delivery_month: Optional[str] = Field(None, description="YYYY-MM")
    status: str = Field("needs_review", pattern="^(draft|needs_review)$")
    rows: List[InvoiceDraftRowRequest] = Field(..., min_length=1)
    agent_notes: InvoiceDraftAgentNotes = Field(default_factory=InvoiceDraftAgentNotes)


class UpdateInvoiceDraftRequest(CreateInvoiceDraftRequest):
    pass


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_invoice_draft(
    request: CreateInvoiceDraftRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        draft = InvoiceDraftService().create_draft(
            customer_id=request.customer_id,
            customer_name=request.customer_name,
            customer_org_number=request.customer_org_number,
            customer_email=request.customer_email,
            invoice_date=request.invoice_date,
            due_date=request.due_date,
            reference=request.reference,
            description=request.description,
            status=request.status,
            rows_data=[row.model_dump() for row in request.rows],
            agent_summary=request.agent_notes.summary,
            agent_confidence=request.agent_notes.confidence,
            agent_warnings=(
                "\n".join(request.agent_notes.warnings)
                if request.agent_notes.warnings
                else None
            ),
            created_by=actor,
            **_draft_fields(request),
        )
        return _draft_to_dict(draft)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "error": exc.message}
        )


@router.get("", response_model=dict)
async def list_invoice_drafts(
    status_filter: Optional[str] = Query(None),
):
    drafts = InvoiceDraftService().list_drafts(status=status_filter)
    return {"drafts": [_draft_to_list_item(draft) for draft in drafts]}


@router.get("/{draft_id}", response_model=dict)
async def get_invoice_draft(draft_id: str):
    try:
        return _draft_to_dict(InvoiceDraftService().get_draft(draft_id))
    except ValidationError as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "error": exc.message}
        )


@router.put("/{draft_id}", response_model=dict)
async def update_invoice_draft(
    draft_id: str,
    request: UpdateInvoiceDraftRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        draft = InvoiceDraftService().update_draft(
            draft_id=draft_id,
            customer_id=request.customer_id,
            customer_name=request.customer_name,
            customer_org_number=request.customer_org_number,
            customer_email=request.customer_email,
            invoice_date=request.invoice_date,
            due_date=request.due_date,
            reference=request.reference,
            description=request.description,
            status=request.status,
            rows_data=[row.model_dump() for row in request.rows],
            agent_summary=request.agent_notes.summary,
            agent_confidence=request.agent_notes.confidence,
            agent_warnings=(
                "\n".join(request.agent_notes.warnings)
                if request.agent_notes.warnings
                else None
            ),
            actor=actor,
            **_draft_fields(request),
        )
        return _draft_to_dict(draft)
    except ValidationError as exc:
        raise _change_error(exc)


_ISSUE_CONFLICTS = ("draft_already_issued", "number_taken", "period_locked")


@router.post(
    "/{draft_id}/issue",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def issue_invoice_draft(
    draft_id: str,
    actor: str = Depends(get_human_actor),
):
    """
    Issue the draft (utfärda, SPEC-fakturering.md §5): the invoice with the
    draft's number, a posted A-series voucher (1510 / 30xx / 26xx), the PDF
    stored and linked as underlag, and the draft marked `issued`, in one
    transaction -- all of it or none of it.

    Logged-in users only (JWT): the agent's API key gets `403 human_only`.
    The agent proposes the draft; a human issues it.

    - `201 {invoice_id, invoice_number, voucher_id, pdf_url}`
    - `404 draft_not_found`
    - `409 draft_already_issued {invoice_id}`,
      `409 number_taken {invoice_number, invoice_id}`,
      `409 period_locked {locked_by, locked_at}`
    - `422 invoice_number_missing | number_is_date | invalid_invoice_number
      | missing_rows | draft_rejected | customer_address_missing
      | delivery_date_missing | company_info_incomplete {missing}
      | period_not_found`
    """
    from services.invoice_issue import InvoiceIssueService
    from services.invoice_proposal import InvoiceProposalService

    proposals = InvoiceProposalService()
    try:
        result = InvoiceIssueService().issue(draft_id, actor=actor)
    except ValidationError as exc:
        # SPEC-fakturering-f1.md §7.4, §9: the thread hears of it after the
        # rollback. A repeated press resumes a receipt that is missing.
        if exc.code == "draft_already_issued":
            _thread_hook(proposals.on_issued, draft_id, actor)
        else:
            _thread_hook(partial(proposals.on_issue_failed, error=exc), draft_id, actor)
        if exc.code == "draft_not_found":
            code = status.HTTP_404_NOT_FOUND
        elif exc.code in _ISSUE_CONFLICTS:
            code = status.HTTP_409_CONFLICT
        else:
            code = 422  # HTTP_422_UNPROCESSABLE_{ENTITY,CONTENT} varies by Starlette
        raise HTTPException(
            status_code=code,
            detail={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
                **exc.payload,
            },
        )
    _thread_hook(proposals.on_issued, draft_id, actor)
    return result


def _thread_hook(hook, draft_id: str, actor: str) -> None:
    """A thread hook after the issue: its failure is logged and never changes
    the answer -- the invoice is already committed, or already refused."""
    try:
        hook(draft_id, actor=actor)
    except Exception:
        logging.getLogger(__name__).exception(
            "Thread hook after issuing invoice draft %s failed", draft_id
        )


@router.post("/{draft_id}/reject", response_model=dict)
async def reject_invoice_draft(
    draft_id: str,
    actor: str = Depends(get_current_actor),
):
    try:
        return _draft_to_dict(InvoiceDraftService().reject(draft_id, actor=actor))
    except ValidationError as exc:
        raise _change_error(exc)


def _change_error(exc: ValidationError) -> HTTPException:
    """A refused PUT or reject. `draft_in_thread` is a conflict with the
    pending card in the thread (SPEC-fakturering-f1.md §4.3) and carries
    where it is; everything else is the old `400`."""
    if exc.code == "draft_in_thread":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "error": exc.message,
                "details": exc.details,
                **exc.payload,
            },
        )
    return HTTPException(
        status_code=400, detail={"code": exc.code, "error": exc.message}
    )


def _draft_fields(request: CreateInvoiceDraftRequest) -> dict:
    return {
        "invoice_number": request.invoice_number,
        "customer_address": request.customer_address,
        "delivery_from": request.delivery_from,
        "delivery_to": request.delivery_to,
        "delivery_month": request.delivery_month,
    }


def _draft_to_list_item(draft) -> dict:
    return {
        "id": draft.id,
        "invoice_number": draft.invoice_number,
        "customer_name": draft.customer_name,
        "invoice_date": draft.invoice_date,
        "due_date": draft.due_date,
        "reference": draft.reference,
        "status": draft.status,
        "amount_ex_vat": draft.amount_ex_vat,
        "vat_amount": draft.vat_amount,
        "amount_inc_vat": draft.amount_inc_vat,
        "agent_confidence": draft.agent_confidence,
        "approved_invoice_id": draft.approved_invoice_id,
        "approved_voucher_id": draft.approved_voucher_id,
        "pdf_url": _pdf_url(draft),
        "created_at": draft.created_at,
        "row_count": len(draft.rows),
    }


def _pdf_url(draft) -> Optional[str]:
    """An issued draft's invoice has a stored PDF; one sent the old way
    only has the rendering export."""
    if not draft.approved_invoice_id:
        return None
    if draft.status == "issued":
        return f"/api/v1/invoices/{draft.approved_invoice_id}/pdf"
    return f"/api/v1/export/pdf/invoice/{draft.approved_invoice_id}"


def _draft_to_dict(draft) -> dict:
    data = _draft_to_list_item(draft)
    data.update(
        {
            "customer_id": draft.customer_id,
            "customer_org_number": draft.customer_org_number,
            "customer_email": draft.customer_email,
            "customer_address": draft.customer_address,
            "delivery_from": draft.delivery_from,
            "delivery_to": draft.delivery_to,
            "delivery_month": draft.delivery_month,
            "description": draft.description,
            "agent_notes": {
                "summary": draft.agent_summary,
                "confidence": draft.agent_confidence,
                "warnings": (
                    draft.agent_warnings.splitlines() if draft.agent_warnings else []
                ),
            },
            "rows": [_draft_row_to_dict(row) for row in draft.rows],
        }
    )
    return data


def _draft_row_to_dict(row) -> dict:
    article_number = row.article_number
    article_name = None
    if row.article_id:
        from repositories.customer_article_repo import ArticleRepository

        article = ArticleRepository.get(row.article_id)
        if article:
            article_number = article_number or article.article_number
            article_name = article.name
    quantity_centi = row.quantity_centi or row.quantity * 100
    return {
        "id": row.id,
        "article_id": row.article_id,
        "article_number": article_number,
        "article_name": article_name,
        "description": row.description,
        "quantity": quantity_from_centi(quantity_centi),
        "quantity_centi": quantity_centi,
        "unit": row.unit,
        "delivery_from": row.delivery_from,
        "delivery_to": row.delivery_to,
        "delivery_month": row.delivery_month,
        "unit_price": row.unit_price,
        "vat_code": row.vat_code,
        "revenue_account": row.revenue_account,
        "amount_ex_vat": row.amount_ex_vat,
        "vat_amount": row.vat_amount,
        "amount_inc_vat": row.amount_inc_vat,
        "source_note": row.source_note,
    }
