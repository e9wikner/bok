"""Where a voucher came from, when something other than the ledger made it.

An issued invoice, its payment, a payslip and an AGI part are each booked
by their own flow, and each records the voucher it posted. Read from the
voucher's side, that link says what the voucher is a booking *of*: the
detail layer shows it, and leads back to the view the thing lives in
(`/v4`: Fakturering or Löner). A voucher posted from an underlag or by hand
has no origin here.

Layering (AGENTS.md): no SQL here, no HTTP.
"""

from typing import Dict, Optional

from domain.payroll_models import AGI_PARTS
from repositories.invoice_repo import InvoiceRepository, PaymentRepository
from repositories.payroll_repo import AgiBookingRepository, PayslipRepository

_MANAD = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]  # fmt: skip

LONER = "betala.loner"
FAKTURERING = "betala.fakturering"


def voucher_origin(voucher_id: str) -> Optional[Dict[str, str]]:
    """`{kind, title, view_key}` for the thing *voucher_id* booked, or
    `None`. `kind` is `payslip`, `agi`, `invoice` or `invoice_payment`."""
    payslip = PayslipRepository.get_by_voucher(voucher_id)
    if payslip is not None:
        name = payslip.employee.name if payslip.employee else "lönebesked"
        month = _MANAD[payslip.period_month - 1]
        return {
            "kind": "payslip",
            "title": f"Lön {name} · {month} {payslip.period_year}",
            "view_key": LONER,
        }

    agi = AgiBookingRepository.get_by_voucher(voucher_id)
    if agi is not None:
        _account, label = AGI_PARTS[agi["kind"]]
        month = _MANAD[agi["month"] - 1]
        return {
            "kind": "agi",
            "title": f"Arbetsgivardeklaration {month} {agi['year']} · {label}",
            "view_key": LONER,
        }

    invoice_id = InvoiceRepository.find_id_by_voucher(voucher_id)
    if invoice_id is not None:
        return {
            "kind": "invoice",
            "title": _invoice_title("Faktura", invoice_id),
            "view_key": FAKTURERING,
        }

    payment = PaymentRepository.find_by_voucher(voucher_id)
    if payment is not None:
        return {
            "kind": "invoice_payment",
            "title": _invoice_title("Betalning av faktura", payment.invoice_id),
            "view_key": FAKTURERING,
        }
    return None


def _invoice_title(what: str, invoice_id: str) -> str:
    invoice = InvoiceRepository.get(invoice_id)
    if invoice is None:
        return what
    parts = [f"{what} {invoice.invoice_number or ''}".strip()]
    if invoice.customer_name:
        parts.append(invoice.customer_name)
    return " · ".join(parts)
