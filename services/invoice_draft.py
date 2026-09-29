"""Service for agent-created invoice drafts."""

from datetime import date, timedelta
from typing import Dict, List, Optional

from domain.invoice_validation import (
    ValidationError,
    VATCalculator,
    amount_ex_vat_from_centi,
    legacy_quantity,
    normalize_delivery,
    normalize_invoice_number,
    parse_quantity_centi,
)
from domain.types import AuditAction
from repositories.account_repo import AccountRepository
from repositories.audit_repo import AuditRepository
from repositories.customer_article_repo import ArticleRepository, CustomerRepository
from repositories.invoice_draft_repo import InvoiceDraftRepository
from repositories.period_repo import PeriodRepository
from services.invoice import unit_of_work


def _refuse_issued(draft) -> None:
    """An issued draft is history: it has become an invoice
    (SPEC-fakturering.md §5) and changes no more."""
    if draft.status == "issued":
        raise ValidationError(
            "draft_already_issued",
            "Invoice draft is already issued",
            payload={"invoice_id": draft.approved_invoice_id},
        )


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
        invoice_number: Optional[str] = None,
        customer_address: Optional[str] = None,
        delivery_from: Optional[date] = None,
        delivery_to: Optional[date] = None,
        delivery_month: Optional[str] = None,
        _commit: bool = True,
    ):
        with unit_of_work(_commit):
            normalized = self._normalize_draft_input(
                invoice_date=invoice_date,
                rows_data=rows_data,
                due_date=due_date,
                customer_id=customer_id,
                customer_name=customer_name,
                customer_org_number=customer_org_number,
                customer_email=customer_email,
                reference=reference,
                invoice_number=invoice_number,
                customer_address=customer_address,
                delivery_from=delivery_from,
                delivery_to=delivery_to,
                delivery_month=delivery_month,
            )

            draft = self.drafts.create(
                description=description,
                status=status,
                agent_summary=agent_summary,
                agent_confidence=agent_confidence,
                agent_warnings=agent_warnings,
                created_by=created_by,
                **self._draft_columns(normalized),
            )
            self.drafts.replace_rows(draft.id, normalized["rows"])
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
                _commit=False,
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
        invoice_number: Optional[str] = None,
        customer_address: Optional[str] = None,
        delivery_from: Optional[date] = None,
        delivery_to: Optional[date] = None,
        delivery_month: Optional[str] = None,
        _commit: bool = True,
    ):
        with unit_of_work(_commit):
            draft = self.get_draft(draft_id)
            _refuse_issued(draft)
            if draft.status == "sent":
                raise ValidationError(
                    "draft_already_sent", "Sent invoice draft cannot be updated"
                )
            if draft.status == "rejected":
                raise ValidationError(
                    "draft_rejected", "Rejected invoice draft cannot be updated"
                )

            normalized = self._normalize_draft_input(
                invoice_date=invoice_date,
                rows_data=rows_data,
                due_date=due_date,
                customer_id=customer_id,
                customer_name=customer_name,
                customer_org_number=customer_org_number,
                customer_email=customer_email,
                reference=reference,
                invoice_number=invoice_number,
                customer_address=customer_address,
                delivery_from=delivery_from,
                delivery_to=delivery_to,
                delivery_month=delivery_month,
            )
            self.drafts.update(
                draft_id=draft_id,
                description=description,
                status=status,
                agent_summary=agent_summary,
                agent_confidence=agent_confidence,
                agent_warnings=agent_warnings,
                **self._draft_columns(normalized),
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
                _commit=False,
            )

        return updated

    def reject(self, draft_id: str, actor: str = "system", _commit: bool = True):
        with unit_of_work(_commit):
            draft = self.get_draft(draft_id)
            _refuse_issued(draft)
            if draft.status == "sent":
                raise ValidationError(
                    "draft_already_sent", "Sent invoice draft cannot be rejected"
                )
            self.drafts.update_status(draft_id, "rejected")
            self.audit.log(
                entity_type="invoice_draft",
                entity_id=draft_id,
                action="rejected",
                actor=actor,
                payload={"previous_status": draft.status},
                _commit=False,
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
        reference: Optional[str] = None,
        invoice_number: Optional[str] = None,
        customer_address: Optional[str] = None,
        delivery_from: Optional[date] = None,
        delivery_to: Optional[date] = None,
        delivery_month: Optional[str] = None,
    ) -> Dict:
        """The draft as it is stored. Fields not given are filled from the
        customer: address (§4.3), Er referens from `contact_person`, and the
        due date from the payment terms. The invoice number is checked here,
        when the draft is saved (§4.1 allows saving or issuing)."""
        customer = CustomerRepository.get(customer_id) if customer_id else None
        if customer_id and not customer:
            raise ValidationError("customer_not_found", "Customer not found")
        customer_address = (customer_address or "").strip() or None
        reference = (reference or "").strip() or None
        if customer:
            customer_name = customer_name or customer.name
            customer_org_number = customer_org_number or customer.org_number
            customer_email = customer_email or customer.email
            customer_address = customer_address or customer.address
            reference = reference or customer.contact_person
            due_date = due_date or invoice_date + timedelta(
                days=customer.payment_terms_days
            )

        if not customer_name:
            raise ValidationError(
                "missing_customer", "Customer name or customer_id is required"
            )
        if not due_date:
            due_date = invoice_date + timedelta(days=30)
        if due_date < invoice_date:
            raise ValidationError(
                "invalid_due_date", "Due date must be on or after invoice date"
            )
        if not rows_data:
            raise ValidationError(
                "missing_rows", "At least one invoice row is required"
            )

        delivery_from, delivery_to, delivery_month = normalize_delivery(
            delivery_from, delivery_to, delivery_month
        )
        return {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_org_number": customer_org_number,
            "customer_email": customer_email,
            "customer_address": customer_address,
            "reference": reference,
            "invoice_number": normalize_invoice_number(invoice_number),
            "invoice_date": invoice_date,
            "due_date": due_date,
            "delivery_from": delivery_from,
            "delivery_to": delivery_to,
            "delivery_month": delivery_month,
            "rows": [self._normalize_row(row) for row in rows_data],
        }

    @staticmethod
    def _draft_columns(normalized: Dict) -> Dict:
        """The draft-level columns of a normalized input (everything but
        the rows)."""
        return {key: value for key, value in normalized.items() if key != "rows"}

    def _normalize_row(self, row: Dict) -> Dict:
        article = (
            ArticleRepository.get(row["article_id"]) if row.get("article_id") else None
        )
        description = (
            row.get("description")
            or (article.description if article else None)
            or (article.name if article else None)
        )
        quantity_centi = parse_quantity_centi(row.get("quantity"))
        unit = (row.get("unit") or "").strip() or (article.unit if article else "st")
        article_number = (
            article.article_number
            if article
            else ((row.get("article_number") or "").strip() or None)
        )
        delivery_from, delivery_to, delivery_month = normalize_delivery(
            row.get("delivery_from"), row.get("delivery_to"), row.get("delivery_month")
        )
        unit_price = int(
            row.get("unit_price")
            if row.get("unit_price") is not None
            else (article.unit_price if article else 0)
        )
        vat_code = row.get("vat_code") or (article.vat_code if article else "MP1")
        revenue_account = row.get("revenue_account") or (
            article.revenue_account if article else "3010"
        )

        if not description:
            raise ValidationError(
                "missing_description", "Invoice draft row description is required"
            )
        if unit_price < 0:
            raise ValidationError(
                "invalid_unit_price",
                "Invoice draft row unit price must be non-negative",
            )
        if not VATCalculator.validate_vat_code(vat_code):
            raise ValidationError("invalid_vat_code", f"Invalid VAT code: {vat_code}")
        if not AccountRepository.get(revenue_account):
            raise ValidationError(
                "invalid_revenue_account", f"Account {revenue_account} does not exist"
            )

        amount_ex_vat = amount_ex_vat_from_centi(quantity_centi, unit_price)
        vat_amount = VATCalculator.calculate_vat(amount_ex_vat, vat_code)
        amount_inc_vat = amount_ex_vat + vat_amount
        return {
            "article_id": article.id if article else row.get("article_id"),
            "description": description,
            "quantity": legacy_quantity(quantity_centi),
            "quantity_centi": quantity_centi,
            "unit": unit,
            "unit_price": unit_price,
            "vat_code": vat_code,
            "revenue_account": revenue_account,
            "amount_ex_vat": amount_ex_vat,
            "vat_amount": vat_amount,
            "amount_inc_vat": amount_inc_vat,
            "source_note": row.get("source_note"),
            "delivery_from": delivery_from,
            "delivery_to": delivery_to,
            "delivery_month": delivery_month,
            "article_number": article_number,
        }

    def _resolve_period_id(self, invoice_date: date) -> str:
        for fiscal_year in PeriodRepository.list_fiscal_years():
            if fiscal_year.start_date <= invoice_date <= fiscal_year.end_date:
                period = PeriodRepository.get_period_by_date(
                    fiscal_year.id, invoice_date
                )
                if period:
                    return period.id
        raise ValidationError(
            "period_not_found", "No accounting period found for invoice date"
        )
