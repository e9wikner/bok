"""Simple payroll service with payslip-backed voucher booking."""

from calendar import monthrange
from datetime import date
from typing import Dict, List, Optional

from domain.payroll_models import Employee, EmployeeSalarySetting, PayrollRun, Payslip
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.audit_repo import AuditRepository
from repositories.payroll_repo import (
    EmployeeRepository,
    PayrollRunRepository,
    PayslipRepository,
    SalarySettingRepository,
)
from repositories.period_repo import PeriodRepository
from services.bank_integration import BankIntegrationService
from services.ledger import LedgerService
from domain.types import AuditAction


PAYROLL_ACCOUNTS = {
    "1930": ("Företagskonto", "asset"),
    "2710": ("Personalskatt", "liability"),
    "2730": ("Avräkning arbetsgivaravgifter", "liability"),
    "7010": ("Löner", "expense"),
    "7510": ("Arbetsgivaravgifter", "expense"),
}


class PayrollService:
    """Manage employees, payslips and payroll voucher booking."""

    def __init__(self):
        self.employees = EmployeeRepository()
        self.settings = SalarySettingRepository()
        self.runs = PayrollRunRepository()
        self.payslips = PayslipRepository()
        self.audit = AuditRepository()
        self.bank = BankIntegrationService()
        self.periods = PeriodRepository()

    def create_employee(
        self,
        name: str,
        personal_number: Optional[str] = None,
        email: Optional[str] = None,
        bank_account: Optional[str] = None,
        actor: str = "system",
    ) -> Employee:
        if not name.strip():
            raise ValidationError("invalid_employee", "Employee name is required")
        employee = self.employees.create(name.strip(), personal_number, email, bank_account)
        self.audit.log(
            "employee",
            employee.id,
            AuditAction.CREATED.value,
            actor,
            {"name": employee.name},
        )
        return employee

    def update_employee(
        self,
        employee_id: str,
        name: str,
        personal_number: Optional[str],
        email: Optional[str],
        bank_account: Optional[str],
        active: bool,
        actor: str = "system",
    ) -> Employee:
        if not self.employees.get(employee_id):
            raise ValidationError("employee_not_found", "Employee not found")
        employee = self.employees.update(
            employee_id, name.strip(), personal_number, email, bank_account, active
        )
        self.audit.log(
            "employee",
            employee_id,
            AuditAction.UPDATED.value,
            actor,
            {"active": active},
        )
        return employee

    def set_salary_setting(
        self,
        employee_id: str,
        gross_monthly_salary: int,
        preliminary_tax: int,
        payment_day: int,
        employer_fee_rate_bp: Optional[int] = None,
        employer_fee_amount: Optional[int] = None,
        active: bool = True,
        actor: str = "system",
    ) -> EmployeeSalarySetting:
        employee = self.employees.get(employee_id)
        if not employee:
            raise ValidationError("employee_not_found", "Employee not found")
        if gross_monthly_salary < 0 or preliminary_tax < 0:
            raise ValidationError("invalid_salary", "Salary and tax must be non-negative")
        if preliminary_tax > gross_monthly_salary:
            raise ValidationError("invalid_salary", "Preliminary tax cannot exceed gross salary")
        if payment_day < 1 or payment_day > 31:
            raise ValidationError("invalid_payment_day", "Payment day must be 1-31")
        if employer_fee_rate_bp is None and employer_fee_amount is None:
            employer_fee_amount = 0
        if employer_fee_rate_bp is not None and employer_fee_rate_bp < 0:
            raise ValidationError("invalid_employer_fee", "Employer fee rate must be non-negative")
        if employer_fee_amount is not None and employer_fee_amount < 0:
            raise ValidationError("invalid_employer_fee", "Employer fee amount must be non-negative")

        setting = self.settings.upsert(
            employee_id,
            gross_monthly_salary,
            preliminary_tax,
            employer_fee_rate_bp,
            employer_fee_amount,
            min(payment_day, 31),
            active,
        )
        self.audit.log(
            "employee_salary_setting",
            setting.id,
            AuditAction.UPDATED.value,
            actor,
            {
                "employee_id": employee_id,
                "gross_monthly_salary": gross_monthly_salary,
                "preliminary_tax": preliminary_tax,
            },
        )
        return setting

    def create_payroll_run(
        self,
        year: int,
        month: int,
        payment_date: Optional[date] = None,
        actor: str = "system",
    ) -> PayrollRun:
        if month < 1 or month > 12:
            raise ValidationError("invalid_period", "Month must be 1-12")
        if payment_date is None:
            payment_date = self._default_payment_date(year, month)
        if payment_date.year != year or payment_date.month != month:
            raise ValidationError(
                "invalid_payment_date",
                "Payment date must be within the payroll month",
                f"period={year}-{month:02d} payment_date={payment_date.isoformat()}",
            )
        existing_runs = self.runs.list_for_period(year, month)
        if existing_runs:
            raise ValidationError(
                "payroll_run_already_exists",
                "Det finns redan en lönekörning för den här månaden",
                f"existing_run_id={existing_runs[0].id}",
            )
        validation = self._validate_run(
            PayrollRun(
                id="preview",
                year=year,
                month=month,
                payment_date=payment_date,
                created_by=actor,
            ),
            include_existing_payslips=False,
        )
        if not validation["valid"]:
            first_error = validation["errors"][0]
            raise ValidationError(first_error["code"], first_error["message"])
        run = self.runs.create(year, month, payment_date, actor)
        self.audit.log(
            "payroll_run",
            run.id,
            AuditAction.CREATED.value,
            actor,
            {"year": year, "month": month, "payment_date": payment_date.isoformat()},
        )
        return run

    def validate_payroll_run(self, payroll_run_id: str) -> Dict:
        run = self.runs.get(payroll_run_id)
        if not run:
            raise ValidationError("payroll_run_not_found", "Payroll run not found")
        return self._validate_run(run, include_existing_payslips=True)

    def generate_payslips(self, payroll_run_id: str, actor: str = "system") -> List[Payslip]:
        run = self.runs.get(payroll_run_id)
        if not run:
            raise ValidationError("payroll_run_not_found", "Payroll run not found")
        existing = self.payslips.list_for_run(payroll_run_id)
        if existing:
            raise ValidationError("payslips_already_generated", "Payslips already generated")

        validation = self._validate_run(run, include_existing_payslips=False)
        if not validation["valid"]:
            first_error = validation["errors"][0]
            raise ValidationError(first_error["code"], first_error["message"])

        created: List[Payslip] = []
        for item in validation["settings"]:
            setting = item["setting"]
            created.append(
                self.payslips.create(
                    payroll_run_id=run.id,
                    employee_id=setting.employee_id,
                    period_year=run.year,
                    period_month=run.month,
                    payment_date=run.payment_date,
                    gross_salary=setting.gross_monthly_salary,
                    preliminary_tax=setting.preliminary_tax,
                    employer_fee=item["employer_fee"],
                )
            )
        self.runs.set_status(run.id, "generated")
        self.audit.log(
            "payroll_run",
            run.id,
            AuditAction.UPDATED.value,
            actor,
            {"generated_payslips": len(created)},
        )
        return self.payslips.list_for_run(run.id)

    def delete_payroll_run(self, payroll_run_id: str, actor: str = "system") -> None:
        run = self.runs.get(payroll_run_id)
        if not run:
            raise ValidationError("payroll_run_not_found", "Payroll run not found")
        payslips = self.payslips.list_for_run(payroll_run_id)
        if any(p.voucher_id for p in payslips):
            raise ValidationError(
                "payroll_run_has_booked_payslips",
                "Cannot delete a payroll run with booked payslips",
            )
        self.runs.delete(payroll_run_id)
        self.audit.log(
            "payroll_run",
            payroll_run_id,
            AuditAction.DELETED.value,
            actor,
            {"year": run.year, "month": run.month, "deleted_payslips": len(payslips)},
        )

    def mark_payslip_sent(self, payslip_id: str, actor: str = "system") -> Payslip:
        payslip = self.payslips.get(payslip_id)
        if not payslip:
            raise ValidationError("payslip_not_found", "Payslip not found")
        updated = self.payslips.mark_sent(payslip_id)
        self.audit.log(
            "payslip",
            payslip_id,
            AuditAction.UPDATED.value,
            actor,
            {"pdf_sent": True},
        )
        return updated

    def match_bank_transaction_and_book(
        self,
        payslip_id: str,
        bank_transaction_id: str,
        actor: str = "system",
    ) -> Payslip:
        self._ensure_payroll_accounts()

        payslip = self.payslips.get(payslip_id)
        if not payslip:
            raise ValidationError("payslip_not_found", "Payslip not found")
        if payslip.voucher_id:
            raise ValidationError("payslip_already_booked", "Payslip is already booked")

        tx = self.bank.get_transaction(bank_transaction_id)
        if not tx:
            raise ValidationError("bank_transaction_not_found", "Bank transaction not found")
        if tx.status == "booked" or tx.matched_voucher_id:
            raise ValidationError("bank_transaction_already_booked", "Bank transaction is already booked")
        if tx.amount >= 0:
            raise ValidationError("invalid_bank_transaction", "Payroll payment must be a negative bank transaction")
        if abs(tx.amount) != payslip.net_salary:
            raise ValidationError(
                "payroll_amount_mismatch",
                "Bank transaction amount must match payslip net salary",
                f"transaction={abs(tx.amount)} net_salary={payslip.net_salary}",
            )

        period = self._find_period_for_date(tx.transaction_date)
        if not period:
            raise ValidationError(
                "period_not_found",
                "No accounting period found for payroll payment date",
                tx.transaction_date.isoformat(),
            )

        ledger = LedgerService()
        rows = self._voucher_rows_for_payslip(payslip)
        description = self._voucher_description(payslip)
        voucher = ledger.create_voucher(
            series="A",
            date=tx.transaction_date,
            period_id=period.id,
            description=description,
            rows_data=rows,
            created_by=actor,
        )
        voucher = ledger.post_voucher(voucher.id, actor=actor)

        self.bank.update_transaction_status(
            tx.id,
            status="booked",
            voucher_id=voucher.id,
            account_code="7010",
            confidence=1.0,
        )
        updated = self.payslips.link_booking(payslip.id, tx.id, voucher.id)
        self._update_run_status_if_complete(payslip.payroll_run_id)
        self.audit.log(
            "payslip",
            payslip.id,
            AuditAction.POSTED.value,
            actor,
            {"voucher_id": voucher.id, "bank_transaction_id": tx.id},
        )
        return updated

    def get_payslip_context(self, payslip_id: str) -> Dict:
        payslip = self.payslips.get(payslip_id)
        if not payslip:
            raise ValidationError("payslip_not_found", "Payslip not found")
        run = self.runs.get(payslip.payroll_run_id)
        return {"payslip": payslip, "employee": payslip.employee, "payroll_run": run}

    def _voucher_rows_for_payslip(self, payslip: Payslip) -> List[Dict]:
        return [
            {
                "account": "7010",
                "debit": payslip.gross_salary,
                "credit": 0,
                "description": "Bruttolön",
            },
            {
                "account": "7510",
                "debit": payslip.employer_fee,
                "credit": 0,
                "description": "Arbetsgivaravgifter",
            },
            {
                "account": "2710",
                "debit": 0,
                "credit": payslip.preliminary_tax,
                "description": "Preliminärskatt",
            },
            {
                "account": "2730",
                "debit": 0,
                "credit": payslip.employer_fee,
                "description": "Skuld arbetsgivaravgifter",
            },
            {
                "account": "1930",
                "debit": 0,
                "credit": payslip.net_salary,
                "description": "Nettolön",
            },
        ]

    def _voucher_description(self, payslip: Payslip) -> str:
        employee_name = payslip.employee.name if payslip.employee else payslip.employee_id
        return f"Lön {employee_name} {payslip.period_year}-{payslip.period_month:02d}"

    def _find_period_for_date(self, target_date: date):
        for fiscal_year in self.periods.list_fiscal_years():
            if fiscal_year.start_date <= target_date <= fiscal_year.end_date:
                period = self.periods.get_period_by_date(fiscal_year.id, target_date)
                if period:
                    return period
        return None

    def _default_payment_date(self, year: int, month: int) -> date:
        settings = self.settings.list_active()
        payment_day = settings[0].payment_day if settings else 25
        last_day = monthrange(year, month)[1]
        return date(year, month, min(payment_day, last_day))

    def _validate_run(self, run: PayrollRun, include_existing_payslips: bool) -> Dict:
        errors = []
        warnings = []
        prepared = []

        if run.payment_date.year != run.year or run.payment_date.month != run.month:
            errors.append(
                {
                    "code": "invalid_payment_date",
                    "message": "Utbetalningsdatum måste ligga i lönekörningens månad.",
                }
            )

        if include_existing_payslips and self.payslips.list_for_run(run.id):
            errors.append(
                {
                    "code": "payslips_already_generated",
                    "message": "Lönespecifikationer är redan skapade för körningen.",
                }
            )

        active_settings = self.settings.list_active()
        if not active_settings:
            errors.append(
                {
                    "code": "no_active_salary_settings",
                    "message": "Det finns inga aktiva anställda med löneinställning.",
                }
            )

        for setting in active_settings:
            employee = self.employees.get(setting.employee_id)
            employee_name = employee.name if employee else setting.employee_id
            if setting.gross_monthly_salary <= 0:
                errors.append(
                    {
                        "code": "invalid_gross_salary",
                        "message": f"{employee_name} saknar bruttolön över 0 kr.",
                    }
                )
            if setting.preliminary_tax > setting.gross_monthly_salary:
                errors.append(
                    {
                        "code": "invalid_preliminary_tax",
                        "message": f"{employee_name} har preliminärskatt som överstiger bruttolönen.",
                    }
                )
            employer_fee = setting.calculate_employer_fee()
            if employer_fee == 0:
                warnings.append(
                    {
                        "code": "missing_employer_fee",
                        "message": f"{employee_name} har 0 kr i arbetsgivaravgift.",
                    }
                )
            prepared.append({"setting": setting, "employee": employee, "employer_fee": employer_fee})

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "employee_count": len(active_settings),
            "settings": prepared,
        }

    def _ensure_payroll_accounts(self) -> None:
        for code, (name, account_type) in PAYROLL_ACCOUNTS.items():
            if not AccountRepository.exists(code):
                AccountRepository.create(code, name, account_type)

    def _update_run_status_if_complete(self, payroll_run_id: str) -> None:
        payslips = self.payslips.list_for_run(payroll_run_id)
        if payslips and all(p.voucher_id for p in payslips):
            self.runs.set_status(payroll_run_id, "booked")
