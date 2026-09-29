"""Domain models for simple payroll."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class Employee:
    id: str
    name: str
    personal_number: Optional[str] = None
    email: Optional[str] = None
    bank_account: Optional[str] = None
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class EmployeeSalarySetting:
    id: str
    employee_id: str
    gross_monthly_salary: int
    preliminary_tax: int
    employer_fee_rate_bp: Optional[int] = None
    employer_fee_amount: Optional[int] = None
    payment_day: int = 25
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def calculate_employer_fee(self) -> int:
        if self.employer_fee_amount is not None:
            return self.employer_fee_amount
        if self.employer_fee_rate_bp is not None:
            return round(self.gross_monthly_salary * self.employer_fee_rate_bp / 10000)
        return 0


@dataclass
class PayrollRun:
    id: str
    year: int
    month: int
    payment_date: date
    status: str = "draft"
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    generated_at: Optional[datetime] = None


@dataclass
class Payslip:
    id: str
    payroll_run_id: str
    employee_id: str
    period_year: int
    period_month: int
    payment_date: date
    gross_salary: int
    preliminary_tax: int
    employer_fee: int
    net_salary: int
    total_employer_cost: int
    status: str = "generated"
    pdf_sent_at: Optional[datetime] = None
    bank_transaction_id: Optional[str] = None
    voucher_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    employee: Optional[Employee] = None

    @property
    def tax_rate_percent(self) -> float:
        """Skatteavdraget i procent av bruttolönen, som lönebeskedet ska visa."""
        if self.gross_salary <= 0:
            return 0.0
        return round(self.preliminary_tax * 100 / self.gross_salary, 1)


def agi_due_date(year: int, month: int) -> date:
    """Last day to file and pay the AGI for *year*-*month* (the month the
    salary was paid): the 12th of the next month, the 17th in January and
    August, moved past a weekend. Public holidays are not moved past; the
    12th rarely lands on one, but check Skatteverket's calendar when it does.
    Applies to employers with a turnover up to 40 MSEK."""
    due_year, due_month = (year + 1, 1) if month == 12 else (year, month + 1)
    due = date(due_year, due_month, 17 if due_month in (1, 8) else 12)
    while due.weekday() >= 5:
        due += timedelta(days=1)
    return due


@dataclass
class AgiIndividual:
    """One employee's individuppgift: cash salary (ruta 011) and withheld
    preliminary tax (ruta 001), plus the employer fee it gives rise to."""

    employee_id: str
    name: str
    personal_number: Optional[str]
    gross_salary: int
    preliminary_tax: int
    employer_fee: int


#: The two parts of an AGI that the tax account debits separately, each
#: booked as its own voucher: kind -> (liability account, description).
AGI_PARTS = {
    "tax": ("2710", "avdragen skatt"),
    "employer_fee": ("2730", "arbetsgivaravgifter"),
}


@dataclass
class AgiDeclaration:
    """The underlag for a month's arbetsgivardeklaration, summed from the
    payslips paid that month. `voucher_ids` holds the current booking of
    each part (`AGI_PARTS`) that has one."""

    year: int
    month: int
    due_date: date
    individuals: List[AgiIndividual]
    unbooked_payslips: int = 0
    voucher_ids: Dict[str, str] = field(default_factory=dict)

    def amount(self, kind: str) -> int:
        return {
            "tax": self.total_preliminary_tax,
            "employer_fee": self.total_employer_fee,
        }[kind]

    @property
    def unbooked_parts(self) -> List[str]:
        """The parts with an amount and no current voucher."""
        return [
            kind
            for kind in AGI_PARTS
            if self.amount(kind) > 0 and kind not in self.voucher_ids
        ]

    @property
    def booked(self) -> bool:
        return bool(self.individuals) and not self.unbooked_parts

    @property
    def total_gross_salary(self) -> int:
        return sum(i.gross_salary for i in self.individuals)

    @property
    def total_preliminary_tax(self) -> int:
        """Huvuduppgift ruta 497, summa skatteavdrag."""
        return sum(i.preliminary_tax for i in self.individuals)

    @property
    def total_employer_fee(self) -> int:
        """Huvuduppgift ruta 487, summa arbetsgivaravgifter."""
        return sum(i.employer_fee for i in self.individuals)

    @property
    def total_to_pay(self) -> int:
        return self.total_preliminary_tax + self.total_employer_fee
