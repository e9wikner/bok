"""Utfärda en faktura från ett utkast (SPEC-fakturering.md §5).

One step that is either wholly done or not at all: the invoice and its rows,
a posted A-series voucher, the rendered PDF stored and linked as underlag to
the voucher, and the draft marked `issued`. Everything is written in one
`with db.transaction():`; the checks that need no write come first, so a
refused issue writes nothing.

The PDF file is written before the commit. If the transaction then fails the
file is removed again (best effort); a file left behind anyway is an orphan
with no meaning, as §5 allows.

Where the PDF lives: `<intake_dir>/invoices/<invoice_number>_<invoice_id>.pdf`.
Under the intake directory because it is underlag like any uploaded receipt
(`IntakeService.resolve_source_file` only serves files inside it), in its own
`invoices/` folder so it never mixes with the per-source upload folders, and
named by number *and* id: the number makes the file recognisable, the id makes
a retry after a failed attempt a new file instead of overwriting one. The
invoice stores the path relative to the intake directory, so an immutable row
does not pin the container's mount point.
"""

import hashlib
import os
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional

from config import settings
from db.database import db
from domain.invoice_validation import (
    VATCalculator,
    amount_ex_vat_from_centi,
    legacy_quantity,
    normalize_invoice_number,
)
from domain.types import AuditAction
from domain.validation import ValidationError, period_lock_payload
from repositories.audit_repo import AuditRepository
from repositories.intake_repo import IntakeRepository
from repositories.invoice_draft_repo import InvoiceDraftRepository
from repositories.invoice_repo import InvoiceRepository
from repositories.period_repo import PeriodRepository

PDF_DIR = "invoices"


class InvoiceIssueService:
    """`issue(draft_id, actor)`: from draft to invoice, voucher and PDF."""

    def __init__(self):
        self.drafts = InvoiceDraftRepository()
        self.invoices = InvoiceRepository()
        self.audit = AuditRepository()

    def issue(self, draft_id: str, actor: str) -> Dict[str, str]:
        """Issue *draft_id*. Returns `invoice_id`, `invoice_number`,
        `voucher_id` and `pdf_url`; raises `ValidationError` with the codes
        of §5, and with `payload` for the 409 cases and
        `company_info_incomplete`."""
        draft = self._draft(draft_id)
        self._refuse_already_issued(draft)
        number = self._check_draft(draft)
        company = self._company()
        period = self._open_period(draft.invoice_date)

        pdf_file: Optional[Path] = None
        try:
            with db.transaction():
                # §5 steps 1–2 again, inside the transaction, on the draft
                # that is written from. A concurrent issue of the same draft
                # is also caught by the unique index on source_draft_id.
                draft = self._draft(draft_id)
                self._refuse_already_issued(draft)
                number = self._check_draft(draft)
                self._refuse_taken_number(number)

                invoice_id = self._create_invoice(draft, number, actor)
                voucher_id = self._book(invoice_id, number, draft, period.id, actor)
                pdf_bytes = self._render(invoice_id, company)
                pdf_file = self._write_pdf(number, invoice_id, pdf_bytes)
                sha256 = hashlib.sha256(pdf_bytes).hexdigest()
                self._link_underlag(
                    voucher_id, number, invoice_id, pdf_file, pdf_bytes, sha256, actor
                )
                issued_at = datetime.now()
                self.invoices.mark_issued(
                    invoice_id,
                    pdf_sha256=sha256,
                    pdf_path=str(pdf_file.relative_to(Path(settings.intake_dir))),
                    issued_at=issued_at,
                    issued_by=actor,
                )
                self.drafts.mark_issued(draft_id, invoice_id, voucher_id)
                self._log(draft_id, invoice_id, number, voucher_id, sha256, actor)
        except Exception as exc:
            self._remove(pdf_file)
            if isinstance(exc, sqlite3.IntegrityError):
                self._raise_conflict(exc, draft_id, number)
            raise

        # After the commit, as every posting does (services/voucher_posting.py).
        from services.ledger import run_statement_match_after_posting

        run_statement_match_after_posting()

        return {
            "invoice_id": invoice_id,
            "invoice_number": number,
            "voucher_id": voucher_id,
            "pdf_url": f"/api/v1/invoices/{invoice_id}/pdf",
        }

    # --- checks (§5 step 2: each has its code, and nothing is written) ------

    def _draft(self, draft_id: str):
        draft = self.drafts.get(draft_id)
        if not draft:
            raise ValidationError("draft_not_found", "Invoice draft not found")
        return draft

    def _refuse_already_issued(self, draft) -> None:
        # `sent` is the old send path's issued: it too already made an
        # invoice, and a second one from the same draft is what §3.3 forbids.
        if draft.status in ("issued", "sent"):
            invoice_id = draft.approved_invoice_id or (
                self.invoices.find_id_by_source_draft(draft.id)
            )
            raise ValidationError(
                "draft_already_issued",
                "Invoice draft is already issued",
                payload={"invoice_id": invoice_id},
            )

    def _check_draft(self, draft) -> str:
        """The draft's own checks (§4). Returns the invoice number."""
        if draft.status == "rejected":
            raise ValidationError(
                "draft_rejected", "Rejected invoice draft cannot be issued"
            )
        number = normalize_invoice_number(draft.invoice_number)
        if number is None:
            raise ValidationError(
                "invoice_number_missing",
                "The draft has no invoice number",
                "propose the next number in the series of the latest issued "
                "invoices",
            )
        if not draft.rows:
            raise ValidationError("missing_rows", "Invoice draft has no rows")
        if not (draft.customer_address or "").strip():
            raise ValidationError(
                "customer_address_missing",
                "The invoice needs the customer's full address",
            )
        if not _delivery(draft) and any(not _delivery(row) for row in draft.rows):
            raise ValidationError(
                "delivery_date_missing",
                "Every row needs a delivery date, period or month, on the row "
                "or on the draft",
            )
        for row in draft.rows:
            if not VATCalculator.validate_vat_code(row.vat_code):
                raise ValidationError(
                    "invalid_vat_code", f"Invalid VAT code: {row.vat_code}"
                )
        return number

    @staticmethod
    def _company():
        # Deferred import (AGENTS.md: service-to-service imports wait until
        # the method runs).
        from services.pdf_export import CompanyInfo

        company = CompanyInfo.load()
        company.check_complete_for_invoice()
        return company

    @staticmethod
    def _open_period(invoice_date: date):
        from services.invoice_draft import InvoiceDraftService

        period_id = InvoiceDraftService()._resolve_period_id(invoice_date)
        period = PeriodRepository.get_period(period_id)
        if period is None:
            raise ValidationError(
                "period_not_found", "No accounting period found for invoice date"
            )
        if period.locked:
            raise ValidationError(
                "period_locked",
                "The period of the invoice date is locked",
                f"period={period.year}-{period.month:02d}",
                payload=period_lock_payload(period),
            )
        return period

    def _refuse_taken_number(self, number: str) -> None:
        existing = self.invoices.find_id_by_number(number)
        if existing:
            raise _number_taken(number, existing)

    def _raise_conflict(
        self, exc: sqlite3.IntegrityError, draft_id: str, number: str
    ) -> None:
        """A UNIQUE the SELECTs did not see coming: a concurrent issue."""
        message = str(exc)
        if "invoices.source_draft_id" in message:
            raise ValidationError(
                "draft_already_issued",
                "Invoice draft is already issued",
                payload={"invoice_id": self.invoices.find_id_by_source_draft(draft_id)},
            ) from exc
        if "invoices.invoice_number" in message:
            raise _number_taken(
                number, self.invoices.find_id_by_number(number)
            ) from exc

    # --- writes (§5 steps 3–6, inside the transaction) ----------------------

    def _create_invoice(self, draft, number: str, actor: str) -> str:
        """The invoice and its rows, standing on their own: a row without
        its own delivery gets the draft's written onto it."""
        default = (draft.delivery_from, draft.delivery_to, draft.delivery_month)
        rows = []
        for row in draft.rows:
            quantity_centi = row.quantity_centi or row.quantity * 100
            amount_ex_vat = amount_ex_vat_from_centi(quantity_centi, row.unit_price)
            vat_amount = VATCalculator.calculate_vat(amount_ex_vat, row.vat_code)
            own = (row.delivery_from, row.delivery_to, row.delivery_month)
            delivery_from, delivery_to, delivery_month = own if any(own) else default
            rows.append(
                {
                    "description": row.description,
                    "quantity": legacy_quantity(quantity_centi),
                    "quantity_centi": quantity_centi,
                    "unit": row.unit or "st",
                    "unit_price": row.unit_price,
                    "vat_code": row.vat_code,
                    "revenue_account": row.revenue_account,
                    "amount_ex_vat": amount_ex_vat,
                    "vat_amount": vat_amount,
                    "amount_inc_vat": amount_ex_vat + vat_amount,
                    "delivery_from": delivery_from,
                    "delivery_to": delivery_to,
                    "delivery_month": delivery_month,
                    "article_number": row.article_number,
                }
            )

        amount_ex_vat = sum(r["amount_ex_vat"] for r in rows)
        vat_amount = sum(r["vat_amount"] for r in rows)
        invoice_id = self.invoices.create_for_issue(
            invoice_number=number,
            source_draft_id=draft.id,
            customer_name=draft.customer_name,
            invoice_date=draft.invoice_date,
            due_date=draft.due_date,
            customer_org_number=draft.customer_org_number,
            customer_email=draft.customer_email,
            customer_address=draft.customer_address.strip(),
            customer_reference=draft.reference,
            # The terms shown next to the due date are the ones that give
            # it; for a draft built from a customer they are its terms.
            payment_terms_days=(draft.due_date - draft.invoice_date).days,
            description=draft.description,
            amount_ex_vat=amount_ex_vat,
            vat_amount=vat_amount,
            amount_inc_vat=amount_ex_vat + vat_amount,
            created_by=actor,
        )
        for row in rows:
            self.invoices.insert_issue_row(invoice_id=invoice_id, **row)
        return invoice_id

    @staticmethod
    def _book(invoice_id: str, number: str, draft, period_id: str, actor: str) -> str:
        """§5 step 4: the posting of `create_booking_for_invoice`, A series,
        on the invoice date. It also links the voucher to the invoice, while
        the invoice is not yet issued."""
        from services.invoice import InvoiceService

        return InvoiceService().create_booking_for_invoice(
            invoice_id,
            period_id,
            actor=actor,
            _commit=False,
            description=f"Faktura {number} {draft.customer_name}",
        )

    @staticmethod
    def _render(invoice_id: str, company) -> bytes:
        # Same thread, same connection: the renderer reads the invoice that
        # is written but not yet committed.
        from services.pdf_export import PDFExportService

        return PDFExportService(company=company).export_invoice(invoice_id)

    @staticmethod
    def _write_pdf(number: str, invoice_id: str, pdf_bytes: bytes) -> Path:
        directory = Path(settings.intake_dir) / PDF_DIR
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{number}_{invoice_id}.pdf"
        partial = target.with_suffix(".pdf.part")
        partial.write_bytes(pdf_bytes)
        os.replace(partial, target)
        return target

    @staticmethod
    def _link_underlag(
        voucher_id: str,
        number: str,
        invoice_id: str,
        pdf_file: Path,
        pdf_bytes: bytes,
        sha256: str,
        actor: str,
    ) -> None:
        """The PDF as an intake source, linked to the voucher when it is
        posted, as a posting with underlag links it
        (`services/voucher_posting.py`): the link row, a `processed` attempt
        and the source's status. A link made at posting has no row in
        `intake_link_basis`; that table records links made after the fact."""
        from services.intake import IntakeService

        source_id = str(uuid.uuid4())
        IntakeRepository.create_source(
            source_id=source_id,
            source_type="customer_invoice",
            original_filename=pdf_file.name,
            mime_type="application/pdf",
            size_bytes=len(pdf_bytes),
            sha256=sha256,
            stored_path=str(pdf_file),
            uploaded_by=actor,
            explanation=f"Faktura {number}, skapad vid utfärdandet",
            _commit=False,
        )
        IntakeService().link_existing_voucher(
            source_id=source_id,
            voucher_id=voucher_id,
            actor=actor,
            summary=f"Faktura {number} utfärdad",
            link_reason=f"invoice_issued invoice={invoice_id}",
            _commit=False,
        )

    def _log(
        self,
        draft_id: str,
        invoice_id: str,
        number: str,
        voucher_id: str,
        sha256: str,
        actor: str,
    ) -> None:
        payload = {
            "draft_id": draft_id,
            "invoice_id": invoice_id,
            "invoice_number": number,
            "voucher_id": voucher_id,
            "pdf_sha256": sha256,
        }
        for entity_type, entity_id in (
            ("invoice_draft", draft_id),
            ("invoice", invoice_id),
        ):
            self.audit.log(
                entity_type=entity_type,
                entity_id=entity_id,
                action=AuditAction.ISSUED.value,
                actor=actor,
                payload=payload,
                _commit=False,
            )

    @staticmethod
    def _remove(pdf_file: Optional[Path]) -> None:
        if pdf_file is None:
            return
        try:
            pdf_file.unlink(missing_ok=True)
        except OSError:
            pass


def _delivery(item) -> bool:
    return bool(item.delivery_from or item.delivery_to or item.delivery_month)


def _number_taken(number: str, invoice_id: Optional[str]) -> ValidationError:
    return ValidationError(
        "number_taken",
        f"Invoice number {number} is already used",
        "propose a new number instead of trying again",
        payload={"invoice_number": number, "invoice_id": invoice_id},
    )
