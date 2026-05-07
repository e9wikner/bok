"""Service for agent-created invoice drafts."""

from datetime import date, timedelta
from typing import Dict, List, Optional

from domain.invoice_validation import VATCalculator, ValidationError
from repositories.account_repo import AccountRepository
from repositories.customer_article_repo import ArticleRepository, CustomerRepository
from repositories.invoice_draft_repo import InvoiceDraftRepository
from repositories.period_repo import PeriodRepository
from repositories.audit_repo import AuditRepository
from services.invoice import InvoiceService
from domain.types import AuditAction


class InvoiceDraftService:
    def __init__(self):
        self.drafts = InvoiceDraftRepository()
        self.audit = AuditRepository()

    def create_draft(
        self,
        invoice_date: date,
        rows_data: List[Dict],
        due_date: Optional[date] = None,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_org_number: Optional[str] = None,
        customer_email: Optional[str] = None,
        reference: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "needs_review",
        agent_summary: Optional[str] = None,
        agent_confidence: Optional[float] = None,
        agent_warnings: Optional[str] = None,
        created_by: str = "system",
    ):
        customer = CustomerRepository.get(customer_id) if customer_id else None
        if customer_id and not customer:
            raise ValidationError("customer_not_found", "Customer not found")
        if customer:
            customer_name = customer_name or customer.name
            customer_org_number = customer_org_number or customer.org_number
            customer_email = customer_email or customer.email
            due_date = due_date or invoice_date + timedelta(days=customer.payment_terms_days)

        if not customer_name:
            raise ValidationError("missing_customer", "Customer name or customer_id is required")
        if not due_date:
            due_date = invoice_date + timedelta(days=30)
        if due_date < invoice_date:
            raise ValidationError("invalid_due_date", "Due date must be on or after invoice date")
        if not rows_data:
            raise ValidationError("missing_rows", "At least one invoice row is required")

        draft = self.drafts.create(
            customer_id=customer_id,
            customer_name=customer_name,
            customer_org_number=customer_org_number,
            customer_email=customer_email,
            invoice_date=invoice_date,
            due_date=due_date,
            reference=reference,
            description=description,
            status=status,
            agent_summary=agent_summary,
            agent_confidence=agent_confidence,
            agent_warnings=agent_warnings,
            created_by=created_by,
        )

        normalized_rows = [self._normalize_row(row) for row in rows_data]
        self.drafts.replace_rows(draft.id, normalized_rows)
        draft = self.drafts.get(draft.id)

        self.audit.log(
            entity_type="invoice_draft",
            entity_id=draft.id,
            action=AuditAction.CREATED.value,
            actor=created_by,
            payload={
                "customer": draft.customer_name,
                "amount_inc_vat": draft.amount_inc_vat,
                "rows_count": len(draft.rows),
                "agent_confidence": agent_confidence,
            },
        )
        return draft

    def list_drafts(self, status: Optional[str] = None):
        return self.drafts.list_all(status=status)

    def get_draft(self, draft_id: str):
        draft = self.drafts.get(draft_id)
        if not draft:
            raise ValidationError("draft_not_found", "Invoice draft not found")
        return draft

    def update_draft(
        self,
        draft_id: str,
        invoice_date: date,
        rows_data: List[Dict],
        due_date: Optional[date] = None,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_org_number: Optional[str] = None,
        customer_email: Optional[str] = None,
        reference: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "needs_review",
        agent_summary: Optional[str] = None,
        agent_confidence: Optional[float] = None,
        agent_warnings: Optional[str] = None,
        actor: str = "system",
    ):
        draft = self.get_draft(draft_id)
        if draft.status == "sent":
            raise ValidationError("draft_already_sent", "Sent invoice draft cannot be updated")
        if draft.status == "rejected":
            raise ValidationError("draft_rejected", "Rejected invoice draft cannot be updated")

        normalized = self._normalize_draft_input(
            invoice_date=invoice_date,
            rows_data=rows_data,
            due_date=due_date,
            customer_id=customer_id,
            customer_name=customer_name,
            customer_org_number=customer_org_number,
            customer_email=customer_email,
        )
        self.drafts.update(
            draft_id=draft_id,
            customer_id=normalized["customer_id"],
            customer_name=normalized["customer_name"],
            customer_org_number=normalized["customer_org_number"],
            customer_email=normalized["customer_email"],
            invoice_date=normalized["invoice_date"],
            due_date=normalized["due_date"],
            reference=reference,
            description=description,
            status=status,
            agent_summary=agent_summary,
            agent_confidence=agent_confidence,
            agent_warnings=agent_warnings,
        )
        self.drafts.replace_rows(draft_id, normalized["rows"])
        updated = self.drafts.get(draft_id)
        self.audit.log(
            entity_type="invoice_draft",
            entity_id=draft_id,
            action="updated",
            actor=actor,
            payload={
                "customer": updated.customer_name,
                "amount_inc_vat": updated.amount_inc_vat,
                "rows_count": len(updated.rows),
                "previous_status": draft.status,
                "status": updated.status,
            },
        )
        return updated

    def send(
        self,
        draft_id: str,
        period_id: Optional[str] = None,
        actor: str = "system",
    ):
        draft = self.get_draft(draft_id)
        if draft.status == "sent":
            raise ValidationError("draft_already_sent", "Invoice draft is already sent")
        if draft.status == "rejected":
            raise ValidationError("draft_rejected", "Rejected invoice draft cannot be sent")
        if not draft.rows:
            raise ValidationError("missing_rows", "Invoice draft has no rows")

        period_id = period_id or self._resolve_period_id(draft.invoice_date)
        invoice_service = InvoiceService()
        invoice = invoice_service.create_invoice(
            customer_name=draft.customer_name,
            invoice_date=draft.invoice_date,
            due_date=draft.due_date,
            rows_data=[
                {
                    "description": row.description,
                    "quantity": row.quantity,
                    "unit_price": row.unit_price,
                    "vat_code": row.vat_code,
                    "revenue_account": row.revenue_account,
                }
                for row in draft.rows
            ],
            customer_org_number=draft.customer_org_number,
            customer_email=draft.customer_email,
            description=draft.description or draft.reference,
            created_by=actor,
        )
        invoice_service.send_invoice(invoice.id, actor=actor)
        voucher_id = invoice_service.create_booking_for_invoice(invoice.id, period_id, actor=actor)
        self.drafts.mark_sent(draft.id, invoice.id, voucher_id)

        self.audit.log(
            entity_type="invoice_draft",
            entity_id=draft.id,
            action="sent",
            actor=actor,
            payload={"invoice_id": invoice.id, "voucher_id": voucher_id, "period_id": period_id},
        )
        return {
            "draft": self.drafts.get(draft.id),
            "invoice": invoice_service.invoices.get(invoice.id),
            "voucher_id": voucher_id,
            "pdf_url": f"/api/v1/export/pdf/invoice/{invoice.id}",
        }

    def reject(self, draft_id: str, actor: str = "system"):
        draft = self.get_draft(draft_id)
        if draft.status == "sent":
            raise ValidationError("draft_already_sent", "Sent invoice draft cannot be rejected")
        self.drafts.update_status(draft_id, "rejected")
        self.audit.log(
            entity_type="invoice_draft",
            entity_id=draft_id,
            action="rejected",
            actor=actor,
            payload={"previous_status": draft.status},
        )
        return self.drafts.get(draft_id)

    def _normalize_draft_input(
        self,
        invoice_date: date,
        rows_data: List[Dict],
        due_date: Optional[date] = None,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_org_number: Optional[str] = None,
        customer_email: Optional[str] = None,
    ) -> Dict:
        customer = CustomerRepository.get(customer_id) if customer_id else None
        if customer_id and not customer:
            raise ValidationError("customer_not_found", "Customer not found")
        if customer:
            customer_name = customer_name or customer.name
            customer_org_number = customer_org_number or customer.org_number
            customer_email = customer_email or customer.email
            due_date = due_date or invoice_date + timedelta(days=customer.payment_terms_days)

        if not customer_name:
            raise ValidationError("missing_customer", "Customer name or customer_id is required")
        if not due_date:
            due_date = invoice_date + timedelta(days=30)
        if due_date < invoice_date:
            raise ValidationError("invalid_due_date", "Due date must be on or after invoice date")
        if not rows_data:
            raise ValidationError("missing_rows", "At least one invoice row is required")

        return {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_org_number": customer_org_number,
            "customer_email": customer_email,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "rows": [self._normalize_row(row) for row in rows_data],
        }

    def _normalize_row(self, row: Dict) -> Dict:
        article = ArticleRepository.get(row["article_id"]) if row.get("article_id") else None
        description = row.get("description") or (article.description if article else None) or (article.name if article else None)
        quantity = int(row.get("quantity") or 0)
        unit_price = int(row.get("unit_price") if row.get("unit_price") is not None else (article.unit_price if article else 0))
        vat_code = row.get("vat_code") or (article.vat_code if article else "MP1")
        revenue_account = row.get("revenue_account") or (article.revenue_account if article else "3010")

        if not description:
            raise ValidationError("missing_description", "Invoice draft row description is required")
        if quantity <= 0:
            raise ValidationError("invalid_quantity", "Invoice draft row quantity must be greater than zero")
        if unit_price < 0:
            raise ValidationError("invalid_unit_price", "Invoice draft row unit price must be non-negative")
        if not VATCalculator.validate_vat_code(vat_code):
            raise ValidationError("invalid_vat_code", f"Invalid VAT code: {vat_code}")
        if not AccountRepository.get(revenue_account):
            raise ValidationError("invalid_revenue_account", f"Account {revenue_account} does not exist")

        amount_ex_vat = quantity * unit_price
        vat_amount = VATCalculator.calculate_vat(amount_ex_vat, vat_code)
        amount_inc_vat = amount_ex_vat + vat_amount
        return {
            "article_id": article.id if article else row.get("article_id"),
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
            "vat_code": vat_code,
            "revenue_account": revenue_account,
            "amount_ex_vat": amount_ex_vat,
            "vat_amount": vat_amount,
            "amount_inc_vat": amount_inc_vat,
            "source_note": row.get("source_note"),
        }

    def _resolve_period_id(self, invoice_date: date) -> str:
        for fiscal_year in PeriodRepository.list_fiscal_years():
            if fiscal_year.start_date <= invoice_date <= fiscal_year.end_date:
                period = PeriodRepository.get_period_by_date(fiscal_year.id, invoice_date)
                if period:
                    return period.id
        raise ValidationError("period_not_found", "No accounting period found for invoice date")
