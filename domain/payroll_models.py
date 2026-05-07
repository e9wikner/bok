"""Domain models for simple payroll."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


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
