"""The month's salaries created and booked without a card.

Two ways in, both resting on a human's press:

- **Automatically on the payment day**, when a logged-in human has turned
  the choice on (`PUT /payroll/auto-booking`, migration 054). A background
  thread (`start_payroll_scheduler`, started from `lifespan`) checks every
  `CHECK_INTERVAL_SECONDS`. On or after the month's payment day it creates
  the payroll run, its payslips and one posted voucher per payslip. It does
  so once: a month that already has a payroll run is left alone, whoever
  made it and whatever became of it. Only months whose payment day is on or
  after the day the choice was turned on are booked, so a month that passed
  before is never booked behind the user's back.
- **Afterwards, with a button** (`POST /payroll/runs/book`): the same thing
  for a month the human chooses, past or present.

The agent never reaches either: the choice and the button are `human_only`,
and `skapa_lonekorning` still only creates payslips, booked by a card.

A payslip that cannot be booked (a locked period, no fiscal year) stays
generated and unbooked; the card (`foresla_lonebokforing`) books it later.
The button refuses up front instead, so the human can fix it first.
"""

import logging
import threading
from datetime import date
from typing import Dict, List, Optional

from domain.types import AuditAction
from domain.validation import ValidationError
from repositories.audit_repo import AuditRepository
from repositories.payroll_repo import PayrollAutoBookingRepository

logger = logging.getLogger(__name__)

#: `created_by` and audit actor of what the payment-day booking does.
AUTO_ACTOR = "payroll_auto"

#: How often the thread looks at the date. The booking runs once a month;
#: this only bounds how long after midnight (or a restart) it happens.
CHECK_INTERVAL_SECONDS = 15 * 60


def _today() -> date:
    """The server's date. A function so tests can fix it."""
    return date.today()


class PayrollAutoService:
    def __init__(self) -> None:
        from services.payroll import PayrollService

        self.payroll = PayrollService()
        self.settings = PayrollAutoBookingRepository()
        self.audit = AuditRepository()

    # -- the choice ---------------------------------------------------------

    def status(self, today: Optional[date] = None) -> Dict:
        """The current choice and the next payment day it books."""
        current = self.settings.current()
        enabled = bool(current and current["enabled"])
        return {
            "enabled": enabled,
            "set_by": current["set_by"] if current else None,
            "set_at": current["created_at"].isoformat() if current else None,
            "next_payment_date": (
                self._next_payment_date(today or _today()).isoformat()
                if enabled
                else None
            ),
        }

    def set_enabled(self, enabled: bool, actor: str) -> Dict:
        """Record a human's choice. A choice equal to the current one is
        not written again."""
        current = self.settings.current()
        if not current or current["enabled"] != enabled:
            setting_id = self.settings.record(enabled, actor)
            self.audit.log(
                "payroll_auto_booking",
                setting_id,
                AuditAction.UPDATED.value,
                actor,
                {"enabled": enabled},
            )
        return self.status()

    # -- booking ------------------------------------------------------------

    def run_due(self, today: Optional[date] = None) -> Optional[Dict]:
        """Create and book this month's salaries if the choice is on and
        the payment day has come. Returns what `create_and_book` did, or
        None when nothing was due."""
        today = today or _today()
        current = self.settings.current()
        if not current or not current["enabled"]:
            return None
        payment_date = self._payment_date(today.year, today.month)
        if today < payment_date or payment_date < current["created_at"].date():
            return None
        if self.payroll.runs.list_for_period(today.year, today.month):
            return None
        if not self.payroll.settings.list_active():
            return None
        return self.create_and_book(
            today.year, today.month, payment_date, actor=AUTO_ACTOR
        )

    def check_bookable(self, year: int, month: int, payment_date: date) -> None:
        """What the button checks before it writes anything: a run can be
        created for the month and the payment day's period is open."""
        if self.payroll.runs.list_for_period(year, month):
            raise ValidationError(
                "payroll_run_already_exists",
                "Det finns redan en lönekörning för den här månaden",
            )
        self.payroll.check_payment_date_booking(payment_date)

    def create_and_book(
        self,
        year: int,
        month: int,
        payment_date: Optional[date],
        actor: str,
    ) -> Dict:
        """Create the month's payroll run and payslips, then book each
        payslip (`PayrollService.book_payslip`). A payslip that cannot be
        booked is reported under `errors` and stays unbooked."""
        run = self.payroll.create_payroll_run(year, month, payment_date, actor=actor)
        try:
            payslips = self.payroll.generate_payslips(run.id, actor=actor)
        except Exception:
            self.payroll.delete_payroll_run(run.id, actor=actor)
            raise
        errors: List[Dict] = []
        for payslip in payslips:
            try:
                self.payroll.book_payslip(payslip.id, actor=actor)
            except ValidationError as exc:
                errors.append(
                    {"payslip_id": payslip.id, "code": exc.code, "message": exc.message}
                )
                logger.warning(
                    "Payslip %s created but not booked: %s", payslip.id, exc.message
                )
        self.audit.log(
            "payroll_run",
            run.id,
            AuditAction.POSTED.value,
            actor,
            {
                "booked": len(payslips) - len(errors),
                "not_booked": [e["code"] for e in errors],
            },
        )
        return {
            "run": self.payroll.runs.get(run.id),
            "payslips": self.payroll.payslips.list_for_run(run.id),
            "errors": errors,
        }

    # -- dates --------------------------------------------------------------

    def _payment_date(self, year: int, month: int) -> date:
        return self.payroll._default_payment_date(year, month)

    def _next_payment_date(self, today: date) -> date:
        """The next payment day the choice books: this month's, unless it
        passed or this month already has a run."""
        this_month = self._payment_date(today.year, today.month)
        if today <= this_month and not self.payroll.runs.list_for_period(
            today.year, today.month
        ):
            return this_month
        year, month = (
            (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        )
        return self._payment_date(year, month)


# ---------------------------------------------------------------------------
# The background thread
# ---------------------------------------------------------------------------


class PayrollScheduler:
    """Calls `PayrollAutoService.run_due` on an interval. One process runs
    the API (uvicorn without workers); two would still not book a month
    twice, since `payroll_runs` is unique per month and payment date."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="payroll-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = PayrollAutoService().run_due()
                if result:
                    logger.info(
                        "Payroll %s booked automatically: %d payslips, %d not booked",
                        result["run"].id,
                        len(result["payslips"]),
                        len(result["errors"]),
                    )
            except Exception:
                logger.exception("Automatic payroll booking failed")
            self._stop.wait(CHECK_INTERVAL_SECONDS)


_scheduler = PayrollScheduler()


def start_payroll_scheduler() -> None:
    _scheduler.start()


def stop_payroll_scheduler() -> None:
    _scheduler.stop()
