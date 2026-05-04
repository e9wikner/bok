"""Invoice service - Fas 2 (Fakturering & Moms)."""

from datetime import date, datetime
from typing import List, Dict, Optional

from domain.invoice_models import Invoice, Payment, CreditNote
from domain.invoice_validation import (
    InvoiceValidator,
    VATCalculator,
    ValidationError
)
from repositories.invoice_repo import InvoiceRepository, PaymentRepository, CreditNoteRepository
from repositories.voucher_repo import VoucherRepository
from repositories.audit_repo import AuditRepository
from domain.types import AuditAction


class InvoiceService:
    """Manage invoices and payments."""
    
    def __init__(self):
        self.invoices = InvoiceRepository()
        self.payments = PaymentRepository()
        self.credits = CreditNoteRepository()
        self.vouchers = VoucherRepository()
        self.audit = AuditRepository()

    def preview_invoice(self, rows_data: List[Dict]) -> Dict:
        """Calculate invoice rows, VAT breakdown and totals without saving."""
        preview_rows = []
        total_ex_vat = 0
        total_vat = 0
        total_inc_vat = 0
        vat_breakdown: Dict[str, Dict] = {}

        for index, row_data in enumerate(rows_data):
            vat_code = row_data["vat_code"]
            if not VATCalculator.validate_vat_code(vat_code):
                raise ValidationError(
                    code="invalid_vat_code",
                    message=f"Invalid VAT code: {vat_code}",
                    details="valid codes: MP1, MP2, MP3, MF",
                )

            quantity = int(row_data["quantity"])
            unit_price = int(row_data["unit_price"])
            amount_ex_vat = quantity * unit_price
            vat_amount = VATCalculator.calculate_vat(amount_ex_vat, vat_code)
            amount_inc_vat = amount_ex_vat + vat_amount
            vat_rate = VATCalculator.get_vat_rate(vat_code)

            preview_rows.append(
                {
                    "index": index,
                    "description": row_data["description"],
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "vat_code": vat_code,
                    "vat_rate": vat_rate,
                    "amount_ex_vat": amount_ex_vat,
                    "vat_amount": vat_amount,
                    "amount_inc_vat": amount_inc_vat,
                }
            )

            total_ex_vat += amount_ex_vat
            total_vat += vat_amount
            total_inc_vat += amount_inc_vat

            if vat_code not in vat_breakdown:
                vat_breakdown[vat_code] = {
                    "vat_code": vat_code,
                    "vat_rate": vat_rate,
                    "amount_ex_vat": 0,
                    "vat_amount": 0,
                    "amount_inc_vat": 0,
                }
            vat_breakdown[vat_code]["amount_ex_vat"] += amount_ex_vat
            vat_breakdown[vat_code]["vat_amount"] += vat_amount
            vat_breakdown[vat_code]["amount_inc_vat"] += amount_inc_vat

        return {
            "rows": preview_rows,
            "vat_breakdown": [
                item for item in vat_breakdown.values() if item["vat_amount"] != 0
            ],
            "totals": {
                "amount_ex_vat": total_ex_vat,
                "vat_amount": total_vat,
                "amount_inc_vat": total_inc_vat,
            },
        }
    
    def create_invoice(
        self,
        customer_name: str,
        invoice_date: date,
        due_date: date,
        rows_data: List[Dict],
        customer_org_number: Optional[str] = None,
        customer_email: Optional[str] = None,
        description: Optional[str] = None,
        created_by: str = "system",
    ) -> Invoice:
        """Create new invoice."""
        # Create invoice
        invoice = self.invoices.create(
            customer_name=customer_name,
            invoice_date=invoice_date,
            due_date=due_date,
            customer_org_number=customer_org_number,
            customer_email=customer_email,
            description=description,
            created_by=created_by
        )
        
        # Add rows and calculate totals
        total_ex_vat = 0
        total_vat = 0
        total_inc_vat = 0
        
        for row_data in rows_data:
            # Validate VAT code
            if not VATCalculator.validate_vat_code(row_data["vat_code"]):
                raise ValidationError(
                    code="invalid_vat_code",
                    message=f"Invalid VAT code: {row_data['vat_code']}",
                    details="valid codes: MP1, MP2, MP3, MF"
                )
            
            row = self.invoices.add_row(
                invoice_id=invoice.id,
                description=row_data["description"],
                quantity=row_data["quantity"],
                unit_price=row_data["unit_price"],
                vat_code=row_data["vat_code"],
                revenue_account=row_data.get("revenue_account")
            )
            invoice.rows.append(row)
            
            total_ex_vat += row.amount_ex_vat
            total_vat += row.vat_amount
            total_inc_vat += row.amount_inc_vat
        
        # Update totals
        self.invoices.update_totals(invoice.id, total_ex_vat, total_vat, total_inc_vat)
        invoice.amount_ex_vat = total_ex_vat
        invoice.vat_amount = total_vat
        invoice.amount_inc_vat = total_inc_vat
        
        # Validate
        InvoiceValidator.validate_new_invoice(invoice)
        
        # Log
        self.audit.log(
            entity_type="invoice",
            entity_id=invoice.id,
            action=AuditAction.CREATED.value,
            actor=created_by,
            payload={
                "invoice_number": invoice.invoice_number,
                "customer": customer_name,
                "amount_inc_vat": total_inc_vat,
                "rows_count": len(invoice.rows)
            }
        )
        
        return invoice
    
    def send_invoice(self, invoice_id: str, actor: str = "system") -> Invoice:
        """Send invoice to customer."""
        invoice = self.invoices.get(invoice_id)
        if not invoice:
            raise ValidationError("invoice_not_found", "Invoice not found")
        
        InvoiceValidator.validate_can_send(invoice)
        
        # Update status
        self.invoices.update_sent(invoice_id)
        
        # Log
        self.audit.log(
            entity_type="invoice",
            entity_id=invoice_id,
            action=AuditAction.SENT.value,
            actor=actor,
            payload={
                "customer_email": invoice.customer_email,
                "sent_at": datetime.now().isoformat()
            }
        )
        
        return self.invoices.get(invoice_id)
    
    def create_booking_for_invoice(
        self,
        invoice_id: str,
        period_id: str,
        actor: str = "system"
    ) -> str:
        """Auto-book invoice to accounting system (creates voucher)."""
        invoice = self.invoices.get(invoice_id)
        if not invoice:
            raise ValidationError("invoice_not_found", "Invoice not found")
        
        # Create voucher with invoice rows
        voucher_rows = []
        
        # Debit: Customer receivables
        voucher_rows.append({
            "account": "1510",  # Kundfordringar
            "debit": invoice.amount_inc_vat,
            "credit": 0,
            "description": f"Invoice {invoice.invoice_number}"
        })
        
        # Group revenue by VAT code and revenue account. Article-based invoice
        # drafts can set revenue_account per row; legacy invoices fall back to
        # the original VAT-code mapping.
        vat_groups = {}
        for row in invoice.rows:
            revenue_account = row.revenue_account or self._default_revenue_account(row.vat_code)
            key = (row.vat_code, revenue_account)
            if key not in vat_groups:
                vat_groups[key] = {
                    "vat_code": row.vat_code,
                    "revenue_account": revenue_account,
                    "amount_ex_vat": 0,
                    "vat_amount": 0
                }
            vat_groups[key]["amount_ex_vat"] += row.amount_ex_vat
            vat_groups[key]["vat_amount"] += row.vat_amount
        
        # Credit: Revenue and VAT
        vat_account_map = {
            "MP1": ("3011", "2610"),  # Revenue 25%, VAT 25%
            "MP2": ("3020", "2620"),  # Revenue 12%, VAT 12%
            "MP3": ("3030", "2630"),  # Revenue 6%, VAT 6%
            "MF": ("3010", None),     # Revenue 0%, No VAT
        }
        
        for amounts in vat_groups.values():
            vat_code = amounts["vat_code"]
            revenue_acct = amounts["revenue_account"]
            _, vat_acct = vat_account_map.get(vat_code, ("3010", None))
            
            # Revenue
            voucher_rows.append({
                "account": revenue_acct,
                "debit": 0,
                "credit": amounts["amount_ex_vat"],
                "description": f"Revenue - {vat_code}"
            })
            
            # VAT (if applicable)
            if vat_acct and amounts["vat_amount"] > 0:
                voucher_rows.append({
                    "account": vat_acct,
                    "debit": 0,
                    "credit": amounts["vat_amount"],
                    "description": f"VAT {vat_code}"
                })
        
        # Create and post voucher
        from services.ledger import LedgerService
        ledger = LedgerService()
        
        voucher = ledger.create_voucher(
            series="A",
            date=invoice.invoice_date,
            period_id=period_id,
            description=f"Invoice {invoice.invoice_number} - {invoice.customer_name}",
            rows_data=voucher_rows,
            created_by=actor
        )
        
        ledger.post_voucher(voucher.id, actor=actor)
        
        # Link invoice to voucher
        self.invoices.link_voucher(invoice_id, voucher.id)
        
        # Log
        self.audit.log(
            entity_type="invoice",
            entity_id=invoice_id,
            action="booked",
            actor=actor,
            payload={
                "voucher_id": voucher.id,
                "period_id": period_id
            }
        )
        
        return voucher.id

    def _default_revenue_account(self, vat_code: str) -> str:
        return {
            "MP1": "3011",
            "MP2": "3020",
            "MP3": "3030",
            "MF": "3010",
        }.get(vat_code, "3010")
    
    def register_payment(
        self,
        invoice_id: str,
        amount: int,
        payment_date: date,
        payment_method: str,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        period_id: Optional[str] = None,
        actor: str = "system"
    ) -> Payment:
        """Register payment for invoice."""
        invoice = self.invoices.get(invoice_id)
        if not invoice:
            raise ValidationError("invoice_not_found", "Invoice not found")
        
        InvoiceValidator.validate_can_pay(invoice, amount)
        
        # Create payment record
        payment = self.payments.create(
            invoice_id=invoice_id,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            reference=reference,
            notes=notes,
            created_by=actor
        )
        
        # Update invoice paid amount and status
        self.invoices.update_paid_amount(invoice_id, amount)
        
        # Auto-book payment if period provided
        if period_id:
            self._create_payment_voucher(invoice, payment, period_id, actor)
        
        # Log
        self.audit.log(
            entity_type="payment",
            entity_id=payment.id,
            action="registered",
            actor=actor,
            payload={
                "invoice_number": invoice.invoice_number,
                "amount": amount,
                "method": payment_method
            }
        )
        
        return payment
    
    def _create_payment_voucher(
        self,
        invoice: Invoice,
        payment: Payment,
        period_id: str,
        actor: str
    ) -> None:
        """Create accounting voucher for payment."""
        from services.ledger import LedgerService
        ledger = LedgerService()
        
        # Create voucher: Bank debit, Customer receivables credit
        voucher = ledger.create_voucher(
            series="A",
            date=payment.payment_date,
            period_id=period_id,
            description=f"Payment - Invoice {invoice.invoice_number}",
            rows_data=[
                {
                    "account": "1010",  # PlusGiro/Bank
                    "debit": payment.amount,
                    "credit": 0,
                    "description": "Payment received"
                },
                {
                    "account": "1510",  # Kundfordringar
                    "debit": 0,
                    "credit": payment.amount,
                    "description": f"Invoice {invoice.invoice_number}"
                }
            ],
            created_by=actor
        )
        
        ledger.post_voucher(voucher.id, actor=actor)
        self.payments.link_voucher(payment.id, voucher.id)
    
    def create_credit_note(
        self,
        invoice_id: str,
        amount_ex_vat: int,
        reason: str,
        credit_date: date,
        period_id: Optional[str] = None,
        actor: str = "system"
    ) -> CreditNote:
        """Create credit note for invoice."""
        invoice = self.invoices.get(invoice_id)
        if not invoice:
            raise ValidationError("invoice_not_found", "Invoice not found")
        
        InvoiceValidator.validate_can_create_credit_note(invoice, amount_ex_vat)
        
        # Calculate VAT (use average rate from original invoice)
        original_rate = invoice.vat_amount / invoice.amount_ex_vat if invoice.amount_ex_vat > 0 else 0
        vat_amount = int(amount_ex_vat * original_rate)
        
        # Create credit note
        credit = self.credits.create(
            invoice_id=invoice_id,
            reason=reason,
            amount_ex_vat=amount_ex_vat,
            vat_amount=vat_amount,
            credit_date=credit_date,
            created_by=actor
        )
        
        # Auto-book if period provided
        if period_id:
            self._create_credit_voucher(invoice, credit, period_id, actor)
        
        # Log
        self.audit.log(
            entity_type="credit_note",
            entity_id=credit.id,
            action="created",
            actor=actor,
            payload={
                "invoice_number": invoice.invoice_number,
                "amount_inc_vat": credit.amount_inc_vat,
                "reason": reason
            }
        )
        
        return credit
    
    def _create_credit_voucher(
        self,
        invoice: Invoice,
        credit: CreditNote,
        period_id: str,
        actor: str
    ) -> None:
        """Create accounting voucher for credit note."""
        from services.ledger import LedgerService
        ledger = LedgerService()
        
        # Reverse original booking (credit note reduces receivables and revenue)
        voucher = ledger.create_voucher(
            series="B",
            date=credit.credit_date,
            period_id=period_id,
            description=f"Credit note {credit.credit_note_number} - {credit.reason}",
            rows_data=[
                {
                    "account": "3011",  # Revenue reversal (debit reduces revenue)
                    "debit": credit.amount_ex_vat,
                    "credit": 0,
                    "description": "Revenue reversal"
                },
                {
                    "account": "2610",  # VAT reversal (debit reduces VAT liability)
                    "debit": credit.vat_amount,
                    "credit": 0,
                    "description": "VAT reversal"
                },
                {
                    "account": "1510",  # Reduce receivables (credit)
                    "debit": 0,
                    "credit": credit.amount_inc_vat,
                    "description": f"Credit - Invoice {invoice.invoice_number}"
                },
            ],
            created_by=actor
        )
        
        ledger.post_voucher(voucher.id, actor=actor)
        self.credits.link_voucher(credit.id, voucher.id)
    
    def get_vat_summary_for_period(self, period_id: str) -> Dict:
        """Get VAT summary for period (for momsrapport)."""
        # Get all invoices and payments in period
        # This would sum up VAT by code for momsrapporting
        # For now, skeleton
        return {
            "period_id": period_id,
            "total_sales_25": 0,
            "total_sales_12": 0,
            "total_sales_6": 0,
            "total_sales_0": 0,
            "total_vat_25": 0,
            "total_vat_12": 0,
            "total_vat_6": 0,
            "total_input_vat": 0,
            "net_vat_due": 0
        }
