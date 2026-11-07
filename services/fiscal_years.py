"""Fiscal years: creating one, and where a date lands in the books.

`create` is the one way a fiscal year comes into being outside an SIE4 import:
`POST /api/v1/fiscal-years` and a press on a `foresla_rakenskapsar` card
(`services/fiscal_year_proposal.py`) both call it. The year and its monthly
periods are written in one transaction, so a failure never leaves a year
without periods.

The rules (BFL 3 kap.): a fiscal year is at most eighteen months, and years
follow one another without gap or overlap -- the opening balance of a year is
derived from the year before it (`services/opening_balance.py`), which only
works when "the year before" is the one that ends the day before.

`placement` answers where an underlag's date lands: an open period, a locked
period or year, or no fiscal year at all. `tolka_underlag` returns it to the
agent, and `check_underlag_dates` holds the posting tools to it.

Layering (AGENTS.md): no SQL here, no HTTP.
"""

from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from domain.models import FiscalYear, Period
from domain.types import AuditAction
from domain.validation import ValidationError
from repositories.audit_repo import AuditRepository
from repositories.period_repo import PeriodRepository

#: BFL 3 kap. 1 §: a changed or first fiscal year may be at most 18 months.
MAX_FISCAL_YEAR_MONTHS = 18

#: Statuses of `placement` that say the date cannot be booked as it stands.
LOCKED_PLACEMENTS = ("period_locked", "fiscal_year_locked")


def add_months(day: date, months: int) -> date:
    """`day` moved `months` calendar months, clipped to the month's length."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def fiscal_year_dict(fiscal_year: FiscalYear) -> Dict[str, Any]:
    return {
        "id": fiscal_year.id,
        "start_date": fiscal_year.start_date.isoformat(),
        "end_date": fiscal_year.end_date.isoformat(),
        "locked": fiscal_year.locked,
    }


def _period_dict(period: Period) -> Dict[str, Any]:
    return {
        "id": period.id,
        "name": f"{period.year}-{period.month:02d}",
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
    }


class FiscalYearService:
    """Create fiscal years and place dates in them."""

    # -- reading -----------------------------------------------------------

    @staticmethod
    def list_ascending() -> List[FiscalYear]:
        return sorted(PeriodRepository.list_fiscal_years(), key=lambda y: y.start_date)

    @staticmethod
    def containing(day: date) -> Optional[FiscalYear]:
        for fiscal_year in PeriodRepository.list_fiscal_years():
            if fiscal_year.start_date <= day <= fiscal_year.end_date:
                return fiscal_year
        return None

    @staticmethod
    def current(today: Optional[date] = None) -> Optional[FiscalYear]:
        """The year a thread belongs to: the one containing today, else the
        most recent (`api/routes/threads.py::_current_fiscal_year_id`)."""
        today = today or date.today()
        fiscal_years = PeriodRepository.list_fiscal_years()  # newest first
        for fiscal_year in fiscal_years:
            if fiscal_year.start_date <= today <= fiscal_year.end_date:
                return fiscal_year
        return fiscal_years[0] if fiscal_years else None

    # -- creating ----------------------------------------------------------

    def validate_new(self, start_date: date, end_date: date) -> None:
        """Every rule `create` holds a new year to, without writing.

        `invalid_dates` and `fiscal_year_too_long` are the dates themselves;
        `fiscal_year_overlap` names the year in the way (payload
        `fiscal_year`); `fiscal_year_not_adjacent` is a gap to the years in
        the books (payload `adjacent`: the dates that would have fit).
        """
        if start_date >= end_date:
            raise ValidationError(
                "invalid_dates",
                "start_date must be before end_date",
                f"start_date={start_date}, end_date={end_date}",
            )
        if end_date >= add_months(start_date, MAX_FISCAL_YEAR_MONTHS):
            raise ValidationError(
                "fiscal_year_too_long",
                f"A fiscal year is at most {MAX_FISCAL_YEAR_MONTHS} months "
                "(BFL 3 kap. 1 §)",
                f"start_date={start_date}, end_date={end_date}",
            )
        years = self.list_ascending()
        for existing in years:
            if start_date <= existing.end_date and existing.start_date <= end_date:
                raise ValidationError(
                    "fiscal_year_overlap",
                    f"Overlaps fiscal year {existing.start_date} - "
                    f"{existing.end_date}",
                    f"fiscal_year_id={existing.id}",
                    payload={"fiscal_year": fiscal_year_dict(existing)},
                )
        if not years:
            return
        first, last = years[0], years[-1]
        if start_date == last.end_date + timedelta(days=1):
            return
        if end_date == first.start_date - timedelta(days=1):
            return
        raise ValidationError(
            "fiscal_year_not_adjacent",
            "A new fiscal year must start the day after the last one ends, "
            "or end the day before the first one starts",
            f"last_end={last.end_date}, first_start={first.start_date}",
            payload={
                "adjacent": {
                    "after_start_date": (last.end_date + timedelta(days=1)).isoformat(),
                    "before_end_date": (
                        first.start_date - timedelta(days=1)
                    ).isoformat(),
                }
            },
        )

    def create(
        self, start_date: date, end_date: date, *, actor: str, _commit: bool = True
    ) -> FiscalYear:
        """Create the year and one period per calendar month, clipped to the
        year's own dates (a shortened or extended year may start or end
        mid-month). One transaction; audit-logged. `_commit=False` lets a
        caller put it in its own transaction."""
        self.validate_new(start_date, end_date)
        from db.database import db

        if not _commit:
            return self._create(start_date, end_date, actor)
        with db.transaction():
            return self._create(start_date, end_date, actor)

    @staticmethod
    def _create(start_date: date, end_date: date, actor: str) -> FiscalYear:
        fiscal_year = PeriodRepository.create_fiscal_year(
            start_date, end_date, _commit=False
        )
        period_ids = []
        current_start = start_date
        while current_start <= end_date:
            last_day = monthrange(current_start.year, current_start.month)[1]
            period_end = min(
                date(current_start.year, current_start.month, last_day), end_date
            )
            period = PeriodRepository.create_period(
                fiscal_year_id=fiscal_year.id,
                year=current_start.year,
                month=current_start.month,
                start_date=current_start,
                end_date=period_end,
                _commit=False,
            )
            period_ids.append(period.id)
            current_start = period_end + timedelta(days=1)
        AuditRepository.log(
            entity_type="fiscal_year",
            entity_id=fiscal_year.id,
            action=AuditAction.CREATED.value,
            actor=actor,
            payload={
                "fiscal_year": f"{start_date} - {end_date}",
                "periods": len(period_ids),
            },
            _commit=False,
        )
        return fiscal_year

    # -- suggesting --------------------------------------------------------

    def suggest(self, day: date) -> tuple:
        """The fiscal year that should hold `day`: twelve months, directly
        after the last year in the books or directly before the first.

        Raises `fiscal_year_exists` (a year already holds the date),
        `no_fiscal_year` (the books have none to follow -- the first year is
        set up by a human), `document_date_too_far` (the date is more than one
        year away: more likely a misread date than a year to skip ahead to)
        and `fiscal_year_gap` (the date falls between two years)."""
        existing = self.containing(day)
        if existing is not None:
            raise ValidationError(
                "fiscal_year_exists",
                f"{day} is already in fiscal year {existing.start_date} - "
                f"{existing.end_date}",
                f"fiscal_year_id={existing.id}",
                payload={"fiscal_year": fiscal_year_dict(existing)},
            )
        years = self.list_ascending()
        if not years:
            raise ValidationError(
                "no_fiscal_year",
                "The books have no fiscal year to follow; the first one is "
                "created in settings",
            )
        first, last = years[0], years[-1]
        if day > last.end_date:
            start = last.end_date + timedelta(days=1)
            end = add_months(start, 12) - timedelta(days=1)
        elif day < first.start_date:
            end = first.start_date - timedelta(days=1)
            start = add_months(end + timedelta(days=1), -12)
        else:
            raise ValidationError(
                "fiscal_year_gap",
                f"{day} falls between two fiscal years in the books",
                f"document_date={day}",
            )
        if not start <= day <= end:
            raise ValidationError(
                "document_date_too_far",
                f"{day} is more than one fiscal year from the years in the "
                "books -- check the date on the underlag",
                f"document_date={day}, next_year={start} - {end}",
            )
        return start, end

    # -- placing a date ----------------------------------------------------

    def placement(self, day: Optional[date], today: Optional[date] = None) -> dict:
        """Where `day` lands in the books, for `tolka_underlag`'s answer.

        `status`: `open` (an open period holds it), `no_fiscal_year` (no
        year does -- with `suggested_fiscal_year`, or `suggestion_error`
        when there is none to suggest), `period_locked` /
        `fiscal_year_locked` (with `first_open_period` and `suggested_date`:
        the earliest open period after the date, where a late underlag can be
        booked once the user agrees), `no_period` (the year has no period for
        it), or `no_date`."""
        if day is None:
            return {"status": "no_date"}
        result: Dict[str, Any] = {"document_date": day.isoformat()}
        fiscal_year = self.containing(day)
        if fiscal_year is None:
            result["status"] = "no_fiscal_year"
            try:
                start, end = self.suggest(day)
                result["suggested_fiscal_year"] = {
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                }
            except ValidationError as exc:
                result["suggestion_error"] = {"code": exc.code, "message": exc.message}
            return result
        result["fiscal_year"] = fiscal_year_dict(fiscal_year)
        period = PeriodRepository.get_period_by_date(fiscal_year.id, day)
        if period is None:
            result["status"] = "no_period"
            return result
        result["period"] = _period_dict(period)
        if not (fiscal_year.locked or period.locked):
            result["status"] = "open"
            return result
        result["status"] = (
            "fiscal_year_locked" if fiscal_year.locked else "period_locked"
        )
        result["locked_by"] = period.locked_by
        result["locked_at"] = period.locked_at.isoformat() if period.locked_at else None
        target = self.first_open_period_after(day)
        result["first_open_period"] = _period_dict(target) if target else None
        if target is not None:
            today = today or date.today()
            suggested = (
                today
                if target.start_date <= today <= target.end_date
                else (target.start_date)
            )
            result["suggested_date"] = suggested.isoformat()
        return result

    @staticmethod
    def first_open_period_after(day: date) -> Optional[Period]:
        """The earliest open period, in an open year, that starts after
        `day`."""
        open_years = {
            fiscal_year.id
            for fiscal_year in PeriodRepository.list_fiscal_years()
            if not fiscal_year.locked
        }
        candidates = [
            period
            for period in PeriodRepository.list_all_periods()
            if period.fiscal_year_id in open_years
            and not period.locked
            and period.start_date > day
        ]
        return min(candidates, key=lambda p: p.start_date) if candidates else None

    # -- holding the posting tools to it -----------------------------------

    def check_underlag_dates(
        self,
        source_ids: Sequence[str],
        voucher_date: Optional[date],
        *,
        decision_id: Optional[str],
        in_thread: bool,
    ) -> None:
        """Refuse a voucher that moves an underlag out of a locked period, or
        out of a missing fiscal year, without the user having decided it.

        The date read from each underlag is its latest interpretation's
        (`tolka_underlag`). When it is in a locked period or year, a voucher
        on another date is a late booking: in a thread it needs `decision_id`
        (the user agreed to the date), and the intake pass, which has no one
        to ask, may not make one -- it abstains. When it is outside every
        fiscal year, the voucher may not be dated into another year to make
        it fit: the year is proposed with `foresla_rakenskapsar`. An underlag
        never interpreted, or a voucher on the underlag's own date, passes --
        the ledger's own checks (`period_locked`) apply as always.
        """
        if voucher_date is None:
            return
        from repositories.interpretation_repo import InterpretationRepository

        for source_id in source_ids:
            interpretation = InterpretationRepository.latest_for_source(source_id)
            if interpretation is None or interpretation.document_date is None:
                continue
            document_date = interpretation.document_date
            if document_date == voucher_date:
                continue
            placement = self.placement(document_date)
            status = placement["status"]
            if status == "no_fiscal_year":
                raise ValidationError(
                    "underlag_outside_fiscal_years",
                    f"The underlag is dated {document_date}, outside every "
                    "fiscal year. Do not date the voucher into another year: "
                    "propose the year with foresla_rakenskapsar.",
                    f"source_id={source_id}, document_date={document_date}",
                    payload={"placement": placement},
                )
            if status in LOCKED_PLACEMENTS and (not in_thread or decision_id is None):
                where = "year" if status == "fiscal_year_locked" else "period"
                hint = (
                    "Ask the user with be_om_beslut first and pass its " "decision_id."
                    if in_thread
                    else "Abstain with registrera_avstaende: the user decides "
                    "a late booking."
                )
                raise ValidationError(
                    "underlag_in_locked_period",
                    f"The underlag is dated {document_date}, in a locked "
                    f"{where}. Booking it on {voucher_date} is a late booking "
                    f"the user has to agree to. {hint}",
                    f"source_id={source_id}, document_date={document_date}",
                    payload={"placement": placement},
                )
