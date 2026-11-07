"""Invoices and salaries booked outside BokAI, as Fakturering and Löner show them.

An invoice issued in another system is in BokAI only as its voucher (debit
kundfordringar, credit revenue and output VAT), and so is a salary booked
from a payslip made elsewhere. Neither has an invoice or a payslip here, and
none is created: the views read them off the ledger, next to BokAI's own.

Whether such an invoice is paid is read off the ledger too: a later voucher
that lowers kundfordringar by exactly the invoice's amount settles it, each
payment settling at most one invoice, oldest invoice first. A payment that
settles several invoices at once matches none of them, and the invoice reads
as without a matched payment -- never as paid on a guess.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from repositories.ledger_bookings_repo import LedgerBookingRepository, LedgerVoucher


def _voucher_fields(v: LedgerVoucher) -> Dict[str, Any]:
    return {
        "voucher_id": v.id,
        "voucher_number": f"{v.series}{v.number}" if v.number is not None else None,
        "date": v.date.isoformat(),
        "description": v.description,
    }


class LedgerBookingService:
    def invoices(
        self, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """The outgoing invoices booked outside BokAI dated in the range,
        newest first, each with the payment that settled it, if one did."""
        # Matched over every year: last year's invoice may be paid this year,
        # and this year's payment may belong to last year's invoice.
        invoices = LedgerBookingRepository.invoices_outside_bokai()
        credits = LedgerBookingRepository.receivable_credits()
        used: set = set()
        payment: Dict[str, Any] = {}
        for inv in invoices:
            for c in credits:
                if c.id in used or c.id == inv.id:
                    continue
                if c.date >= inv.date and c.amount == inv.amount_inc_vat:
                    used.add(c.id)
                    payment[inv.id] = c
                    break

        result = []
        for inv in reversed(invoices):
            if date_from is not None and inv.date < date_from:
                continue
            if date_to is not None and inv.date > date_to:
                continue
            paid = payment.get(inv.id)
            result.append(
                {
                    **_voucher_fields(inv),
                    "amount_inc_vat": inv.amount_inc_vat,
                    "vat_amount": inv.vat_amount,
                    "paid": paid is not None,
                    "payment_voucher_id": paid.id if paid else None,
                    "payment_date": paid.date.isoformat() if paid else None,
                }
            )
        return result

    def salaries(
        self, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """The salary payouts booked outside BokAI dated in the range,
        newest first."""
        return [
            {
                **_voucher_fields(s),
                "gross_salary": s.gross,
                "preliminary_tax": s.tax,
                "net_salary": s.net,
            }
            for s in reversed(
                LedgerBookingRepository.salaries_outside_bokai(date_from, date_to)
            )
        ]
