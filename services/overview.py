"""Översikt — the counters behind the three page tabs.

One read, all three pages. The server decides what is waiting and writes the
meta line; the client formats and counts nothing (datakontraktet regel 1 och 2).

Read-only by construction: nothing here writes, locks or persists, unlike
POST /compliance/check which saves the issues it finds.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from repositories.invoice_repo import InvoiceRepository
from repositories.payroll_repo import PayrollRunRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository

# The three pages of the information architecture, in the order the design
# draws them. A list, not a mapping: the order is the design's to decide.
PAGE_TITLES = [
    ("bocker", "Böcker"),
    ("betala", "Fakturering och löner"),
    ("bokslut", "Bokslut"),
]

# Payroll runs that have not been booked yet.
_PAYROLL_UNBOOKED = ("draft", "generated")

# The intake statuses that used to be summed here live on as
# `_INTAKE_OPEN_STATUSES` in `services/decision_service.py`, which owns the
# union `open_decisions` is counted from now (SPEC-beslut.md §5).


@dataclass
class PageCounters:
    """The same four counters on every page, so a counter can move home."""

    open_decisions: int = 0
    overdue_invoices: int = 0
    payroll_waiting: int = 0
    missing_attachments: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "open_decisions": self.open_decisions,
            "overdue_invoices": self.overdue_invoices,
            "payroll_waiting": self.payroll_waiting,
            "missing_attachments": self.missing_attachments,
        }

    def any_waiting(self) -> bool:
        return any(value != 0 for value in self.as_dict().values())


@dataclass
class OverviewPage:
    key: str
    title: str
    waiting: bool
    meta: str
    counters: Dict[str, int] = field(default_factory=dict)


@dataclass
class FiscalYearSummary:
    id: str
    label: str
    start: str
    end: str


@dataclass
class PeriodStateSummary:
    current_period_id: str
    label: str
    locked: bool


@dataclass
class Overview:
    fiscal_year: Optional[FiscalYearSummary]
    period_state: Optional[PeriodStateSummary]
    pages: List[OverviewPage]


class OverviewService:
    """Aggregates the page counters. Reads only."""

    def get_overview(self, today: Optional[date] = None) -> Overview:
        today = today or date.today()

        counters = {
            "bocker": PageCounters(
                open_decisions=self._count_open_decisions(),
                missing_attachments=VoucherRepository.count_missing_attachments(),
            ),
            "betala": PageCounters(
                overdue_invoices=self._count_overdue_invoices(today),
                payroll_waiting=self._count_payroll_waiting(),
            ),
            # Nothing is counted for Bokslut yet. The period-level checks that
            # belong here arrive with flode-verifikationer; until then a quiet
            # page is an honest one.
            "bokslut": PageCounters(),
        }

        fiscal_year = self._current_fiscal_year(today)
        period = self._current_period(fiscal_year, today) if fiscal_year else None

        return Overview(
            fiscal_year=self._fiscal_year_payload(fiscal_year),
            period_state=self._period_payload(period),
            pages=[self._page(key, title, counters[key]) for key, title in PAGE_TITLES],
        )

    # -- counters ---------------------------------------------------------

    def _count_open_decisions(self) -> int:
        """The `beslut` module owns this now (SPEC-beslut.md §6.6).

        The field did not change — only the arithmetic behind it, which is
        what SPEC-oversikt.md said would happen: "När `beslut` kommer byter
        den ut uträkningen bakom fältet — inte fältet." The approximation
        that stood here summed the two synthetic sources DecisionService
        still unions, so the number is unchanged on the day of the switch
        and only grows as real decisions are written (testfall 33).

        Deferred import, per AGENTS.md's service-to-service rule.
        """
        from services.decision_service import DecisionService

        return DecisionService().count_open()

    def _count_overdue_invoices(self, today: date) -> int:
        """Same predicate as the invoice list summary — see Invoice.counts_as_overdue."""
        return sum(
            1
            for invoice in InvoiceRepository.list_all()
            if invoice.counts_as_overdue(today)
        )

    def _count_payroll_waiting(self) -> int:
        """Approximation until lönens fyra spår exist (out of scope, ANALYS §2).

        "Not booked yet" is true but coarser than the four tracks the design
        asks for (payment file, AGI, payslips, booking).
        """
        return sum(
            1
            for run in PayrollRunRepository.list_all()
            if run.status in _PAYROLL_UNBOOKED
        )

    # -- period ------------------------------------------------------------

    def _current_fiscal_year(self, today: date):
        fiscal_years = PeriodRepository.list_fiscal_years()
        for fiscal_year in fiscal_years:
            if fiscal_year.start_date <= today <= fiscal_year.end_date:
                return fiscal_year
        # list_fiscal_years is newest first; fall back to the latest one.
        return fiscal_years[0] if fiscal_years else None

    def _current_period(self, fiscal_year, today: date):
        period = PeriodRepository.get_period_by_date(fiscal_year.id, today)
        if period:
            return period
        periods = PeriodRepository.list_periods(fiscal_year.id)
        return periods[-1] if periods else None

    def _fiscal_year_payload(self, fiscal_year) -> Optional[FiscalYearSummary]:
        if not fiscal_year:
            return None
        start, end = fiscal_year.start_date, fiscal_year.end_date
        label = (
            str(start.year) if start.year == end.year else f"{start.year}/{end.year}"
        )
        return FiscalYearSummary(
            id=fiscal_year.id,
            label=label,
            start=start.isoformat(),
            end=end.isoformat(),
        )

    def _period_payload(self, period) -> Optional[PeriodStateSummary]:
        if not period:
            return None
        return PeriodStateSummary(
            current_period_id=period.id,
            label=f"{period.year}-{period.month:02d}",
            locked=period.locked,
        )

    # -- presentation ------------------------------------------------------

    def _page(self, key: str, title: str, counters: PageCounters) -> OverviewPage:
        return OverviewPage(
            key=key,
            title=title,
            waiting=counters.any_waiting(),
            meta=self._meta(counters),
            counters=counters.as_dict(),
        )

    def _meta(self, counters: PageCounters) -> str:
        """The server's wording, in Swedish. The client only renders it."""
        parts = []
        if counters.open_decisions:
            parts.append(f"{counters.open_decisions} väntar på dig")
        if counters.overdue_invoices:
            parts.append(
                f"{counters.overdue_invoices} förfallen faktura"
                if counters.overdue_invoices == 1
                else f"{counters.overdue_invoices} förfallna fakturor"
            )
        if counters.payroll_waiting:
            parts.append(
                f"{counters.payroll_waiting} lönekörning väntar"
                if counters.payroll_waiting == 1
                else f"{counters.payroll_waiting} lönekörningar väntar"
            )
        if counters.missing_attachments:
            parts.append(f"{counters.missing_attachments} saknar underlag")

        return " · ".join(parts) if parts else "Inget väntar"
