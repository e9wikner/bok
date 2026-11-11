"""Lönebeskedet som underlag (migration 050).

A salary voucher books gross salary, withheld tax and the net paid out. The
bank transaction supports only the net; the payslip is what supports the
gross and the tax (BFL 5 kap. 6-7 §§). So the payslip is underlag to the
voucher, beside the bank transaction, and it is räkenskapsinformation: kept
for seven years as it was drawn up (BFL 7 kap.), never re-rendered.

- `store(payslip_id)` renders the payslip once and keeps the bytes under
  `<intake_dir>/payslips/`. `PayrollService.generate_payslips` calls it, so
  the file is there before the bank statement is.
- `link(payslip, voucher_id)` makes the stored file an intake source linked
  to the voucher, as `services/invoice_issue.py` does with an issued
  invoice's PDF. Booking a payslip calls it.
- `attach(payslip_id, voucher_id)` links it afterwards: to the voucher the
  payslip already booked (booked before migration 050), or to a posted
  voucher that books the salary from the bank statement. Only a logged-in
  human calls it (the route answers the API key `403 human_only`). The
  voucher is never changed; the link is a row like any other underlag link.

The source is created only when it is linked, never before: an unlinked
source would be pending and land in the intake pass's queue.
"""

import hashlib
import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import List, Tuple

from config import settings
from db.database import db
from domain.payroll_models import Payslip
from domain.statement_coverage import is_bank_account
from domain.types import AuditAction, VoucherStatus
from domain.validation import ValidationError
from repositories.audit_repo import AuditRepository
from repositories.intake_repo import IntakeRepository
from repositories.payroll_repo import PayslipRepository
from repositories.voucher_repo import VoucherRepository

logger = logging.getLogger(__name__)

PDF_DIR = "payslips"


class PayslipUnderlagService:
    """Store a payslip's PDF and link it as underlag to its voucher."""

    def __init__(self):
        self.payslips = PayslipRepository()
        self.audit = AuditRepository()

    # -- the stored file -------------------------------------------------------

    def store(self, payslip_id: str, actor: str = "system") -> Payslip:
        """Render *payslip_id* and keep the bytes, once. A payslip whose PDF
        is stored is returned as it is."""
        payslip = self._payslip(payslip_id)
        if payslip.pdf_sha256:
            return payslip
        try:
            pdf_bytes = self._render(payslip_id)
            target = self._write(payslip, pdf_bytes)
        except Exception as exc:
            raise ValidationError(
                "payslip_pdf_failed",
                "Lönebeskedet kunde inte skapas som PDF",
                str(exc),
            ) from exc
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        relative = str(target.relative_to(Path(settings.intake_dir)))
        self.payslips.store_pdf(payslip_id, relative, sha256)
        self.audit.log(
            "payslip",
            payslip_id,
            AuditAction.CREATED.value,
            actor,
            {"pdf_path": relative, "pdf_sha256": sha256},
        )
        return self._payslip(payslip_id)

    def try_store(self, payslip_id: str, actor: str = "system") -> None:
        """`store`, for generation: a payslip whose PDF cannot be made now
        is still generated. Its PDF is stored when it is booked or attached,
        which refuse to go on without it."""
        try:
            self.store(payslip_id, actor=actor)
        except ValidationError as exc:
            logger.warning(
                "Payslip %s generated without a stored PDF: %s",
                payslip_id,
                exc.details or exc.message,
            )

    def stored_pdf(self, payslip_id: str) -> Tuple[str, bytes]:
        """The stored PDF, byte for byte, and its download name. Never
        renders. `pdf_not_stored` with `export_url` when there is none yet;
        `pdf_file_missing` when the row names a file that is not on disk."""
        payslip = self._payslip(payslip_id)
        if not payslip.pdf_path:
            raise ValidationError(
                "pdf_not_stored",
                "Lönebeskedet har ingen lagrad PDF",
                payload={"export_url": f"/api/v1/export/pdf/payslip/{payslip_id}"},
            )
        path = self._absolute(payslip.pdf_path)
        if not path.is_file():
            raise ValidationError(
                "pdf_file_missing",
                "Lönebeskedets lagrade PDF finns inte på disk",
                f"pdf_path={payslip.pdf_path}",
            )
        return self._download_name(payslip), path.read_bytes()

    # -- the link --------------------------------------------------------------

    def link(
        self,
        payslip: Payslip,
        voucher_id: str,
        actor: str,
        *,
        book: bool = False,
    ) -> str:
        """Link *payslip*'s stored PDF to the posted *voucher_id* as
        underlag and return the intake source's id. The PDF must be stored.
        With *book*, the payslip is also marked booked by *voucher_id*, in
        the same transaction.

        The first link creates the source; a later one (the earlier link
        undone) links the same source again."""
        from services.intake import IntakeService

        if not payslip.pdf_path or not payslip.pdf_sha256:
            raise ValidationError("pdf_not_stored", "Lönebeskedet har ingen lagrad PDF")
        if (
            not book
            and payslip.intake_source_id
            and IntakeRepository.current_link(payslip.intake_source_id, voucher_id)
        ):
            return payslip.intake_source_id

        path = self._absolute(payslip.pdf_path)
        label = self._label(payslip)
        number = self._voucher_number(voucher_id)
        with db.transaction():
            if book:
                self.payslips.link_booking(payslip.id, None, voucher_id, _commit=False)
                self.audit.log(
                    "payslip",
                    payslip.id,
                    AuditAction.BOOKED.value,
                    actor,
                    {"voucher_id": voucher_id, "attached_afterwards": True},
                    _commit=False,
                )
            source_id = payslip.intake_source_id
            if source_id is None:
                existing = IntakeRepository.get_by_sha256(payslip.pdf_sha256)
                if existing is not None:
                    raise ValidationError(
                        "payslip_pdf_already_underlag",
                        "Lönebeskedets PDF finns redan som underlag",
                        f"intake_source_id={existing.id}",
                    )
                source_id = str(uuid.uuid4())
                IntakeRepository.create_source(
                    source_id=source_id,
                    source_type="other",
                    original_filename=self._download_name(payslip),
                    mime_type="application/pdf",
                    size_bytes=path.stat().st_size,
                    sha256=payslip.pdf_sha256,
                    stored_path=str(path),
                    uploaded_by=actor,
                    explanation=label,
                    _commit=False,
                )
                self.payslips.set_intake_source(payslip.id, source_id)
                IntakeService().link_existing_voucher(
                    source_id=source_id,
                    voucher_id=voucher_id,
                    actor=actor,
                    summary=f"{label} kopplat till {number}",
                    link_reason=f"payslip payslip={payslip.id}",
                    _commit=False,
                )
            else:
                IntakeService().persist_voucher_link(
                    source_id,
                    voucher_id,
                    actor=actor,
                    summary=f"{label} kopplat till {number}",
                    link_reason=f"payslip payslip={payslip.id}",
                )
            self.audit.log(
                "payslip",
                payslip.id,
                AuditAction.UPDATED.value,
                actor,
                {"underlag_voucher_id": voucher_id, "intake_source_id": source_id},
                _commit=False,
            )
        return source_id

    def attach(self, payslip_id: str, voucher_id: str, actor: str) -> Payslip:
        """Link *payslip_id*'s PDF to the posted *voucher_id* afterwards.

        A booked payslip attaches only to the voucher it booked. An
        unbooked one attaches to a posted voucher that books it -- gross on
        the salary account, tax on 2710, the net out of a bank account --
        and is then booked by that voucher, so it is not offered for a
        second booking. Writes nothing to the voucher."""
        from services.payroll import PayrollService

        payslip = self._payslip(payslip_id)
        voucher = VoucherRepository.get(voucher_id)
        if voucher is None:
            raise ValidationError("voucher_not_found", "Verifikationen finns inte")
        if voucher.status != VoucherStatus.POSTED:
            raise ValidationError(
                "voucher_not_posted", "Verifikationen är inte bokförd"
            )
        if payslip.voucher_id and payslip.voucher_id != voucher_id:
            raise ValidationError(
                "payslip_already_booked",
                "Lönebeskedet är bokfört på en annan verifikation",
                f"voucher_id={payslip.voucher_id}",
            )
        if not payslip.voucher_id:
            other = self.payslips.get_by_voucher(voucher_id)
            if other is not None:
                raise ValidationError(
                    "voucher_books_another_payslip",
                    "Verifikationen bokför ett annat lönebesked",
                    f"payslip_id={other.id}",
                )
            if not self.matches(voucher, payslip):
                raise ValidationError(
                    "payroll_amount_mismatch",
                    "Verifikationens belopp stämmer inte med lönebeskedet",
                    f"gross={payslip.gross_salary} tax={payslip.preliminary_tax} "
                    f"net={payslip.net_salary}",
                )

        payslip = self.store(payslip_id, actor=actor)
        booking = not payslip.voucher_id
        self.link(payslip, voucher_id, actor, book=booking)
        if booking:
            PayrollService()._update_run_status_if_complete(payslip.payroll_run_id)
        return self._payslip(payslip_id)

    def voucher_candidates(self, payslip_id: str) -> List:
        """Posted vouchers *payslip_id* can be attached to: for a booked
        payslip the voucher it booked; for an unbooked one the vouchers
        within `PAYMENT_WINDOW_DAYS` of its payment date that book it and
        book no other payslip. Closest date first."""
        from services.payroll import PAYMENT_WINDOW_DAYS, PayrollService

        payslip = self._payslip(payslip_id)
        if payslip.voucher_id:
            voucher = VoucherRepository.get(payslip.voucher_id)
            return [voucher] if voucher else []

        window = timedelta(days=PAYMENT_WINDOW_DAYS)
        payroll = PayrollService()
        period_ids = []
        for day in range(-PAYMENT_WINDOW_DAYS, PAYMENT_WINDOW_DAYS + 1):
            period = payroll._find_period_for_date(
                payslip.payment_date + timedelta(days=day)
            )
            if period and period.id not in period_ids:
                period_ids.append(period.id)

        found = []
        for period_id in period_ids:
            for voucher in VoucherRepository.list_for_period(
                period_id, status=VoucherStatus.POSTED.value
            ):
                if abs(voucher.date - payslip.payment_date) > window:
                    continue
                if not self.matches(voucher, payslip):
                    continue
                if self.payslips.get_by_voucher(voucher.id) is not None:
                    continue
                found.append(voucher)
        return sorted(found, key=lambda v: abs((v.date - payslip.payment_date).days))

    @staticmethod
    def is_linked(payslip: Payslip) -> bool:
        """Whether the payslip's PDF is a current underlag of its voucher."""
        if not payslip.intake_source_id or not payslip.voucher_id:
            return False
        return (
            IntakeRepository.current_link(payslip.intake_source_id, payslip.voucher_id)
            is not None
        )

    @staticmethod
    def matches(voucher, payslip: Payslip) -> bool:
        """Whether *voucher* books *payslip*: the gross debited to the salary
        account, the tax credited to 2710 and the net credited to a bank
        account."""
        from services.payroll import SALARY_ACCOUNT

        def has(account_test, debit: int, credit: int) -> bool:
            return any(
                account_test(row.account_code)
                and row.debit == debit
                and row.credit == credit
                for row in voucher.rows
            )

        return (
            has(lambda a: a == SALARY_ACCOUNT, payslip.gross_salary, 0)
            and (
                payslip.preliminary_tax == 0
                or has(lambda a: a == "2710", 0, payslip.preliminary_tax)
            )
            and has(is_bank_account, 0, payslip.net_salary)
        )

    # -- helpers ---------------------------------------------------------------

    def _payslip(self, payslip_id: str) -> Payslip:
        payslip = self.payslips.get(payslip_id)
        if not payslip:
            raise ValidationError("payslip_not_found", "Payslip not found")
        return payslip

    @staticmethod
    def _render(payslip_id: str) -> bytes:
        from services.pdf_export import CompanyInfo, PDFExportService

        company = CompanyInfo.load()
        if not company.name:
            company.name = CompanyInfo.name
        return PDFExportService(company=company).export_payslip(payslip_id)

    @staticmethod
    def _write(payslip: Payslip, pdf_bytes: bytes) -> Path:
        directory = Path(settings.intake_dir) / PDF_DIR
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (
            f"{payslip.period_year}-{payslip.period_month:02d}_{payslip.id}.pdf"
        )
        partial = target.with_suffix(".pdf.part")
        partial.write_bytes(pdf_bytes)
        os.replace(partial, target)
        return target

    @staticmethod
    def _absolute(relative: str) -> Path:
        return Path(settings.intake_dir) / relative

    @staticmethod
    def _label(payslip: Payslip) -> str:
        name = payslip.employee.name if payslip.employee else payslip.employee_id
        return f"Lönebesked {name} {payslip.period_year}-{payslip.period_month:02d}"

    @staticmethod
    def _download_name(payslip: Payslip) -> str:
        return (
            f"lonebesked_{payslip.period_year}-{payslip.period_month:02d}"
            f"_{payslip.id[:8]}.pdf"
        )

    @staticmethod
    def _voucher_number(voucher_id: str) -> str:
        voucher = VoucherRepository.get(voucher_id)
        if voucher is None or voucher.number is None:
            return voucher_id
        return f"{voucher.series.value}-{voucher.number}"
