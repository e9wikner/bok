"""API routes for invoices (Fas 2)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import date
from typing import List, Optional

from api.deps import get_current_actor
from domain.validation import ValidationError
from domain.invoice_validation import ValidationError as InvoiceValidationError
from services.invoice import InvoiceService

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


class InvoiceRowRequest(BaseModel):
    """Request model for invoice row."""
    description: str
    quantity: int = Field(..., gt=0)
    unit_price: int = Field(..., ge=0, description="Unit price in öre")
    vat_code: str = Field(..., pattern="^(MP1|MP2|MP3|MF)$")


class CreateInvoiceRequest(BaseModel):
    """Request model for creating an invoice."""
    customer_name: str = Field(..., min_length=1)
    invoice_date: date
    due_date: date
    description: Optional[str] = None
    customer_org_number: Optional[str] = None
    customer_email: Optional[str] = None
    rows: List[InvoiceRowRequest] = Field(..., min_length=1)


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    request: CreateInvoiceRequest,
    actor: str = Depends(get_current_actor),
):
    """
    Create new invoice (Faktura).
    
    Request body should include invoice rows:
    ```json
    {
      "rows": [
        {
          "description": "Consulting services",
          "quantity": 10,
          "unit_price": 100000,  # 1,000 kr in öre
          "vat_code": "MP1"  # 25% VAT
        }
      ]
    }
    ```
    """
    try:
        service = InvoiceService()
        
        rows_data = [r.model_dump() for r in request.rows]
        
        invoice = service.create_invoice(
            customer_name=request.customer_name,
            invoice_date=request.invoice_date,
            due_date=request.due_date,
            rows_data=rows_data,
            customer_org_number=request.customer_org_number,
            customer_email=request.customer_email,
            description=request.description,
            created_by=actor
        )
        
        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "invoice_date": invoice.invoice_date,
            "due_date": invoice.due_date,
            "amount_ex_vat": invoice.amount_ex_vat,
            "vat_amount": invoice.vat_amount,
            "amount_inc_vat": invoice.amount_inc_vat,
            "status": invoice.status,
            "rows_count": len(invoice.rows),
            "created_at": invoice.created_at
        }
    
    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": str(e),
                "code": getattr(e, "code", "validation_error")
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=dict)
async def list_invoices(
    status_filter: str = None,
):
    """List all invoices, optionally filtered by status."""
    try:
        service = InvoiceService()
        invoices = service.invoices.list_all(status=status_filter)
        
        return {
            "total": len(invoices),
            "invoices": [
                {
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
                    "rows": [
                        {
                            "description": r.description,
                            "quantity": r.quantity,
                            "unit_price": r.unit_price,
                            "vat_code": r.vat_code,
                            "amount_ex_vat": r.amount_ex_vat,
                            "vat_amount": r.vat_amount,
                            "amount_inc_vat": r.amount_inc_vat
                        }
                        for r in inv.rows
                    ],
                    "created_at": inv.created_at
                }
                for inv in invoices
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{invoice_id}", response_model=dict)
async def get_invoice(invoice_id: str):
    """Get invoice by ID."""
    try:
        service = InvoiceService()
        invoice = service.invoices.get(invoice_id)
        
        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found"
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
            "rows": [
                {
                    "description": r.description,
                    "quantity": r.quantity,
                    "unit_price": r.unit_price,
                    "vat_code": r.vat_code,
                    "amount_ex_vat": r.amount_ex_vat,
                    "vat_amount": r.vat_amount,
                    "amount_inc_vat": r.amount_inc_vat
                }
                for r in invoice.rows
            ],
            "created_at": invoice.created_at,
            "sent_at": invoice.sent_at,
            "voucher_id": invoice.voucher_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{invoice_id}/send", response_model=dict)
async def send_invoice(
    invoice_id: str,
    actor: str = Depends(get_current_actor),
):
    """Send invoice to customer."""
    try:
        service = InvoiceService()
        invoice = service.send_invoice(invoice_id, actor=actor)
        
        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "sent_at": invoice.sent_at
        }
    
    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "code": getattr(e, "code", "validation_error")}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


class BookInvoiceRequest(BaseModel):
    """Request model for booking an invoice."""
    period_id: str


@router.post("/{invoice_id}/book", response_model=dict)
async def book_invoice(
    invoice_id: str,
    request: BookInvoiceRequest,
    actor: str = Depends(get_current_actor),
):
    """
    Auto-book invoice to accounting system.
    
    Creates a double-entry voucher:
    - Debit: Customer receivables (1510)
    - Credit: Revenue + VAT
    """
    try:
        service = InvoiceService()
        voucher_id = service.create_booking_for_invoice(invoice_id, request.period_id, actor=actor)
        
        return {
            "invoice_id": invoice_id,
            "voucher_id": voucher_id,
            "status": "booked"
        }
    
    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "code": getattr(e, "code", "validation_error")}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
            actor=actor
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
            "voucher_id": payment.voucher_id
        }
    
    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "code": getattr(e, "code", "validation_error")}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
            actor=actor
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
            "voucher_id": credit.voucher_id
        }
    
    except (ValidationError, InvoiceValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "code": getattr(e, "code", "validation_error")}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
