"""API routes for agent-created invoice drafts."""

from datetime import date
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_current_actor
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


class SendInvoiceDraftRequest(BaseModel):
    period_id: Optional[str] = None


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
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "error": exc.message}
        )


@router.post("/{draft_id}/send", response_model=dict)
async def send_invoice_draft(
    draft_id: str,
    request: SendInvoiceDraftRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        result = InvoiceDraftService().send(
            draft_id=draft_id,
            period_id=request.period_id,
            actor=actor,
        )
        draft = result["draft"]
        invoice = result["invoice"]
        return {
            "draft": _draft_to_dict(draft),
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "voucher_id": result["voucher_id"],
            "pdf_url": result["pdf_url"],
        }
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "error": exc.message}
        )


@router.post("/{draft_id}/reject", response_model=dict)
async def reject_invoice_draft(
    draft_id: str,
    actor: str = Depends(get_current_actor),
):
    try:
        return _draft_to_dict(InvoiceDraftService().reject(draft_id, actor=actor))
    except ValidationError as exc:
        raise HTTPException(
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
        "pdf_url": (
            f"/api/v1/export/pdf/invoice/{draft.approved_invoice_id}"
            if draft.approved_invoice_id
            else None
        ),
        "created_at": draft.created_at,
        "row_count": len(draft.rows),
    }


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
