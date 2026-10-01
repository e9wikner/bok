"""Domain models for simple payroll."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from domain.validation import ValidationError


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


def normalize_personal_number(value: str) -> str:
    """*value* as ÅÅÅÅMMDD-NNNN, or ValidationError. Twelve digits, because
    the AGI reports the personnummer with the century; a hyphen or plus
    before the last four is allowed. The date must exist (a samordnings-
    nummer adds 60 to the day) and the last digit is the Luhn check digit
    over the ten digits after the century."""
    digits = value.strip().replace("-", "").replace("+", "").replace(" ", "")
    if len(digits) != 12 or not digits.isdigit():
        raise ValidationError(
            "invalid_personal_number",
            "Personnumret ska ha tolv siffror, ÅÅÅÅMMDD-NNNN",
            value,
        )
    day = int(digits[6:8])
    try:
        date(int(digits[:4]), int(digits[4:6]), day - 60 if day > 60 else day)
    except ValueError:
        raise ValidationError(
            "invalid_personal_number", "Personnumrets datum finns inte", value
        )
    total = 0
    for i, digit in enumerate(digits[2:]):
        product = int(digit) * (2 if i % 2 == 0 else 1)
        total += product - 9 if product > 9 else product
    if total % 10 != 0:
        raise ValidationError(
            "invalid_personal_number",
            "Personnumrets kontrollsiffra stämmer inte",
            value,
        )
    return f"{digits[:8]}-{digits[8:]}"


def mask_trailing(value: Optional[str], keep: int = 4) -> Optional[str]:
    """*value* with all but its last *keep* characters hidden, for what the
    agent reads back: it needs to recognise a personnummer or bank account,
    not repeat it."""
    if not value:
        return value
    return "*" * max(len(value) - keep, 0) + value[-keep:]


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


def whole_kronor(ore: int) -> int:
    """*ore* with the öre dropped, not rounded: the AGI reports whole kronor,
    and the employer fee is computed "genom att ta bort ören" (Skatteverket,
    SKV 401, Avrundning)."""
    if ore < 0:
        return -whole_kronor(-ore)
    return ore - ore % 100


def employer_fee_rate_bp(gross_salary: int, employer_fee: int) -> Optional[int]:
    """The rate, in basis points, that gives *employer_fee* on
    *gross_salary* the way `calculate_employer_fee` computes it, or None for
    a fee that is no such rate (set as an amount). A payslip does not store
    its rate; above a few hundred kronor the rate is unique."""
    if gross_salary <= 0 or employer_fee <= 0:
        return None
    rate_bp = round(employer_fee * 10000 / gross_salary)
    if round(gross_salary * rate_bp / 10000) != employer_fee:
        return None
    return rate_bp


def declared_employer_fee(payslips: List["Payslip"]) -> int:
    """Huvuduppgift ruta 487: for each rate, the rate on the cash salary
    reported for its individuals (ruta 011, whole kronor), öre dropped, and
    the results summed (SKV 401, Avrundning). A fee set as an amount has no
    rate and counts as its own amount, öre dropped, per individual."""
    by_rate: Dict[Optional[int], Dict[str, List[int]]] = {}
    for payslip in payslips:
        rate_bp = employer_fee_rate_bp(payslip.gross_salary, payslip.employer_fee)
        sums = by_rate.setdefault(rate_bp, {}).setdefault(payslip.employee_id, [0, 0])
        sums[0] += payslip.gross_salary
        sums[1] += payslip.employer_fee
    total = 0
    for rate_bp, employees in by_rate.items():
        if rate_bp is None:
            total += sum(whole_kronor(fee) for _, fee in employees.values())
        else:
            reported = sum(whole_kronor(gross) for gross, _ in employees.values())
            total += whole_kronor(reported * rate_bp // 10000)
    return total


@dataclass
class AgiIndividual:
    """One employee's individuppgift: cash salary (ruta 011) and withheld
    preliminary tax (ruta 001) in whole kronor, as they are reported, and
    the employer fee on the payslips (in öre; ruta 487 is computed per rate,
    see `declared_employer_fee`)."""

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
    """The underlag for a month's arbetsgivardeklaration, from the payslips
    paid that month. The declared amounts are whole kronor; `liabilities`
    holds what the payslips booked on 2710 and 2730, in öre, which the
    booking clears (the difference is öresutjämning). `voucher_ids` holds
    the current booking of each part (`AGI_PARTS`) that has one."""

    year: int
    month: int
    due_date: date
    individuals: List[AgiIndividual]
    employer_fee: int = 0
    liabilities: Dict[str, int] = field(default_factory=dict)
    unbooked_payslips: int = 0
    voucher_ids: Dict[str, str] = field(default_factory=dict)

    def amount(self, kind: str) -> int:
        """The part as declared and drawn from the tax account."""
        return {
            "tax": self.total_preliminary_tax,
            "employer_fee": self.total_employer_fee,
        }[kind]

    def liability(self, kind: str) -> int:
        """The part as the payslips booked it on its liability account."""
        return self.liabilities.get(kind, 0)

    @property
    def unbooked_parts(self) -> List[str]:
        """The parts with an amount and no current voucher."""
        return [
            kind
            for kind in AGI_PARTS
            if (self.amount(kind) > 0 or self.liability(kind) > 0)
            and kind not in self.voucher_ids
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
        return self.employer_fee

    @property
    def total_to_pay(self) -> int:
        return self.total_preliminary_tax + self.total_employer_fee
