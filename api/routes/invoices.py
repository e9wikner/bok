"""API routes for invoices (Fas 2)."""

from datetime import date
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from domain.invoice_validation import ValidationError as InvoiceValidationError
from domain.invoice_validation import quantity_from_centi
from domain.validation import ValidationError
from services.invoice import InvoiceService

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


class PreviewInvoiceRowRequest(BaseModel):
    """A preview row, computed like a draft row (SPEC-fakturering.md §4.2)."""

    description: str
    quantity: Union[int, float, str] = Field(
        ...,
        description="Positive, at most two decimals; 7.5 or '7,5'",
        examples=[7.5],
    )
    unit: Optional[str] = Field(None, description="Unit, e.g. 'h' (default 'st')")
    unit_price: int = Field(..., ge=0, description="Unit price in öre")
    vat_code: str = Field(..., pattern="^(MP1|MP2|MP3|MF)$")
    revenue_account: Optional[str] = None
    article_number: Optional[str] = None
    delivery_from: Optional[date] = None
    delivery_to: Optional[date] = None
    delivery_month: Optional[str] = Field(None, description="YYYY-MM")


class PreviewInvoiceRequest(BaseModel):
    """Request model for previewing invoice totals without saving."""

    rows: List[PreviewInvoiceRowRequest] = Field(..., min_length=1)


@router.post("/preview", response_model=dict)
async def preview_invoice(
    request: PreviewInvoiceRequest,
    actor: str = Depends(get_current_actor),
):
    """Calculate invoice rows, VAT summary and totals without creating an invoice."""
    try:
        service = InvoiceService()
        return service.preview_invoice([r.model_dump() for r in request.rows])
    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": str(e),
                "code": getattr(e, "code", "validation_error"),
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("", response_model=dict)
async def list_invoices(
    status_filter: str = None,
    search: str = Query(None, description="Search customer name or invoice number"),
    limit: int = Query(None, description="Max invoices to return"),
    offset: int = Query(0, description="Number of invoices to skip"),
):
    """List invoices with server-side filtering, pagination and summary."""
    try:
        service = InvoiceService()
        invoices = service.invoices.list_all(status=status_filter)
        if search:
            search_lower = search.lower()
            invoices = [
                inv
                for inv in invoices
                if search_lower in (inv.customer_name or "").lower()
                or search_lower in str(inv.invoice_number or "").lower()
            ]

        total = len(invoices)
        summary = _invoice_summary(invoices)
        page_invoices = (
            invoices[offset : offset + limit] if limit is not None else invoices
        )
        page_total = sum(inv.amount_inc_vat for inv in page_invoices)

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "summary": summary,
            "page_total": page_total,
            "invoices": [_invoice_to_list_item(inv) for inv in page_invoices],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


def _invoice_summary(invoices) -> dict:
    total_amount = sum(inv.amount_inc_vat for inv in invoices)
    paid_amount = sum(inv.paid_amount for inv in invoices)
    return {
        "total_amount": total_amount,
        "total_paid": paid_amount,
        "total_remaining": total_amount - paid_amount,
        "invoice_count": len(invoices),
        "paid_count": sum(1 for inv in invoices if inv.status == "paid"),
        "overdue_count": sum(1 for inv in invoices if inv.counts_as_overdue()),
    }


def _invoice_to_list_item(inv) -> dict:
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "customer_name": inv.customer_name,
        "customer_email": inv.customer_email,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "amount_ex_vat": inv.amount_ex_vat,
        "vat_amount": inv.vat_amount,
        "amount_inc_vat": inv.amount_inc_vat,
        "paid_amount": inv.paid_amount,
        "remaining_amount": inv.remaining_amount(),
        "status": inv.status,
        "is_overdue": inv.is_overdue(),
        "row_count": len(inv.rows),
        "created_at": inv.created_at,
        # SPEC-fakturering.md §4.3–4.4. Empty on invoices from before F0.
        "issued_at": inv.issued_at,
        "pdf_url": _pdf_url(inv),
        "customer_address": inv.customer_address,
        "customer_reference": inv.customer_reference,
        "payment_terms_days": inv.payment_terms_days,
        "source_draft_id": inv.source_draft_id,
    }


def _pdf_url(inv) -> Optional[str]:
    """The stored PDF's URL; None for an invoice with none stored, whose
    PDF only the rendering export (`/export/pdf/invoice/{id}`) gives."""
    return f"/api/v1/invoices/{inv.id}/pdf" if inv.pdf_path else None


def _invoice_row_to_dict(r) -> dict:
    quantity_centi = r.quantity_centi or r.quantity * 100
    return {
        "description": r.description,
        "quantity": quantity_from_centi(quantity_centi),
        "quantity_centi": quantity_centi,
        "unit": r.unit,
        "unit_price": r.unit_price,
        "vat_code": r.vat_code,
        "revenue_account": r.revenue_account,
        "article_number": r.article_number,
        "delivery_from": r.delivery_from,
        "delivery_to": r.delivery_to,
        "delivery_month": r.delivery_month,
        "amount_ex_vat": r.amount_ex_vat,
        "vat_amount": r.vat_amount,
        "amount_inc_vat": r.amount_inc_vat,
    }


@router.get("/{invoice_id}", response_model=dict)
async def get_invoice(invoice_id: str):
    """Get invoice by ID."""
    try:
        service = InvoiceService()
        invoice = service.invoices.get(invoice_id)

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
            )

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "customer_org_number": invoice.customer_org_number,
            "customer_email": invoice.customer_email,
            "invoice_date": invoice.invoice_date,
            "due_date": invoice.due_date,
            "description": invoice.description,
            "amount_ex_vat": invoice.amount_ex_vat,
            "vat_amount": invoice.vat_amount,
            "amount_inc_vat": invoice.amount_inc_vat,
            "paid_amount": invoice.paid_amount,
            "remaining_amount": invoice.remaining_amount(),
            "status": invoice.status,
            "is_overdue": invoice.is_overdue(),
            "rows": [_invoice_row_to_dict(r) for r in invoice.rows],
            "created_at": invoice.created_at,
            "sent_at": invoice.sent_at,
            "voucher_id": invoice.voucher_id,
            "issued_at": invoice.issued_at,
            "issued_by": invoice.issued_by,
            "pdf_url": _pdf_url(invoice),
            "customer_address": invoice.customer_address,
            "customer_reference": invoice.customer_reference,
            "payment_terms_days": invoice.payment_terms_days,
            "source_draft_id": invoice.source_draft_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str):
    """
    The PDF stored when the invoice was issued, byte for byte
    (SPEC-fakturering.md §3.6). It is never rendered again.

    - `404 invoice_not_found`
    - `404 pdf_not_stored`: an invoice from before F0, not issued in Bok.
      `export_url` renders one from the current data; it is not the stored
      original.
    - `500 pdf_file_missing`: the row names a file that is not on disk.
    """
    from services.invoice_issue import InvoiceIssueService

    try:
        filename, pdf_bytes = InvoiceIssueService().stored_pdf(invoice_id)
    except ValidationError as e:
        code = (
            status.HTTP_500_INTERNAL_SERVER_ERROR
            if e.code == "pdf_file_missing"
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(
            status_code=code,
            detail={
                "error": e.message,
                "code": e.code,
                "details": e.details,
                **e.payload,
            },
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class RegisterPaymentRequest(BaseModel):
    """Request model for registering a payment."""

    amount: int = Field(..., gt=0, description="Payment amount in öre")
    payment_date: date
    payment_method: str
    reference: Optional[str] = None
    notes: Optional[str] = None
    period_id: Optional[str] = None


@router.post("/{invoice_id}/payment", response_model=dict)
async def register_payment(
    invoice_id: str,
    request: RegisterPaymentRequest,
    actor: str = Depends(get_current_actor),
):
    """
    Register payment for invoice.

    If period_id provided, auto-creates payment voucher.
    """
    try:
        service = InvoiceService()
        payment = service.register_payment(
            invoice_id=invoice_id,
            amount=request.amount,
            payment_date=request.payment_date,
            payment_method=request.payment_method,
            reference=request.reference,
            notes=request.notes,
            period_id=request.period_id,
            actor=actor,
        )

        invoice = service.invoices.get(invoice_id)

        return {
            "payment_id": payment.id,
            "invoice_id": invoice_id,
            "amount": request.amount,
            "payment_date": request.payment_date,
            "method": request.payment_method,
            "invoice_status": invoice.status,
            "remaining_amount": invoice.remaining_amount(),
            "voucher_id": payment.voucher_id,
        }

    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "code": getattr(e, "code", "validation_error")},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


class CreateCreditNoteRequest(BaseModel):
    """Request model for creating a credit note."""

    amount_ex_vat: int = Field(..., gt=0, description="Credit amount ex VAT in öre")
    reason: str = Field(..., min_length=1)
    credit_date: date
    period_id: Optional[str] = None


@router.post("/{invoice_id}/credit-note", response_model=dict)
async def create_credit_note(
    invoice_id: str,
    request: CreateCreditNoteRequest,
    actor: str = Depends(get_current_actor),
):
    """
    Create credit note (Kreditfaktura).

    If period_id provided, auto-creates credit voucher.
    """
    try:
        service = InvoiceService()
        credit = service.create_credit_note(
            invoice_id=invoice_id,
            amount_ex_vat=request.amount_ex_vat,
            reason=request.reason,
            credit_date=request.credit_date,
            period_id=request.period_id,
            actor=actor,
        )

        return {
            "credit_note_id": credit.id,
            "credit_note_number": credit.credit_note_number,
            "invoice_id": invoice_id,
            "reason": request.reason,
            "amount_ex_vat": request.amount_ex_vat,
            "vat_amount": credit.vat_amount,
            "amount_inc_vat": credit.amount_inc_vat,
            "credit_date": request.credit_date,
            "voucher_id": credit.voucher_id,
        }

    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "code": getattr(e, "code", "validation_error")},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
