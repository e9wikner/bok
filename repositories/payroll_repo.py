"""Payroll repositories."""

from datetime import date, datetime
from typing import List, Optional
import uuid

from db.database import db
from domain.payroll_models import Employee, EmployeeSalarySetting, PayrollRun, Payslip


def _dt(value) -> datetime:
    return datetime.fromisoformat(value) if value else datetime.now()


def _date(value) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


class EmployeeRepository:
    @staticmethod
    def create(
        name: str,
        personal_number: Optional[str] = None,
        email: Optional[str] = None,
        bank_account: Optional[str] = None,
    ) -> Employee:
        employee_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """INSERT INTO employees
               (id, name, personal_number, email, bank_account, active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (employee_id, name, personal_number, email, bank_account, now, now),
        )
        db.commit()
        return Employee(employee_id, name, personal_number, email, bank_account, True, now, now)

    @staticmethod
    def get(employee_id: str) -> Optional[Employee]:
        row = db.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        return EmployeeRepository._row_to_employee(row) if row else None

    @staticmethod
    def list_all(active_only: bool = False, search: Optional[str] = None) -> List[Employee]:
        sql = "SELECT * FROM employees WHERE 1=1"
        params = []
        if active_only:
            sql += " AND active = 1"
        if search:
            sql += " AND (LOWER(name) LIKE ? OR personal_number LIKE ? OR LOWER(email) LIKE ?)"
            needle = f"%{search.lower()}%"
            params.extend([needle, f"%{search}%", needle])
        sql += " ORDER BY active DESC, name"
        return [
            EmployeeRepository._row_to_employee(row)
            for row in db.execute(sql, tuple(params)).fetchall()
        ]

    @staticmethod
    def update(
        employee_id: str,
        name: str,
        personal_number: Optional[str],
        email: Optional[str],
        bank_account: Optional[str],
        active: bool,
    ) -> Optional[Employee]:
        db.execute(
            """UPDATE employees
               SET name = ?, personal_number = ?, email = ?, bank_account = ?, active = ?, updated_at = ?
               WHERE id = ?""",
            (name, personal_number, email, bank_account, int(active), datetime.now(), employee_id),
        )
        db.commit()
        return EmployeeRepository.get(employee_id)

    @staticmethod
    def _row_to_employee(row) -> Employee:
        return Employee(
            id=row["id"],
            name=row["name"],
            personal_number=row["personal_number"],
            email=row["email"],
            bank_account=row["bank_account"],
            active=bool(row["active"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )


class SalarySettingRepository:
    @staticmethod
    def upsert(
        employee_id: str,
        gross_monthly_salary: int,
        preliminary_tax: int,
        employer_fee_rate_bp: Optional[int],
        employer_fee_amount: Optional[int],
        payment_day: int,
        active: bool = True,
    ) -> EmployeeSalarySetting:
        existing = SalarySettingRepository.get_for_employee(employee_id)
        now = datetime.now()
        if existing:
            db.execute(
                """UPDATE employee_salary_settings
                   SET gross_monthly_salary = ?, preliminary_tax = ?, employer_fee_rate_bp = ?,
                       employer_fee_amount = ?, payment_day = ?, active = ?, updated_at = ?
                   WHERE employee_id = ?""",
                (
                    gross_monthly_salary,
                    preliminary_tax,
                    employer_fee_rate_bp,
                    employer_fee_amount,
                    payment_day,
                    int(active),
                    now,
                    employee_id,
                ),
            )
        else:
            db.execute(
                """INSERT INTO employee_salary_settings
                   (id, employee_id, gross_monthly_salary, preliminary_tax, employer_fee_rate_bp,
                    employer_fee_amount, payment_day, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    employee_id,
                    gross_monthly_salary,
                    preliminary_tax,
                    employer_fee_rate_bp,
                    employer_fee_amount,
                    payment_day,
                    int(active),
                    now,
                    now,
                ),
            )
        db.commit()
        return SalarySettingRepository.get_for_employee(employee_id)

    @staticmethod
    def get_for_employee(employee_id: str) -> Optional[EmployeeSalarySetting]:
        row = db.execute(
            "SELECT * FROM employee_salary_settings WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
        return SalarySettingRepository._row_to_setting(row) if row else None

    @staticmethod
    def list_active() -> List[EmployeeSalarySetting]:
        rows = db.execute(
            """SELECT s.* FROM employee_salary_settings s
               JOIN employees e ON e.id = s.employee_id
               WHERE s.active = 1 AND e.active = 1
               ORDER BY e.name"""
        ).fetchall()
        return [SalarySettingRepository._row_to_setting(row) for row in rows]

    @staticmethod
    def _row_to_setting(row) -> EmployeeSalarySetting:
        return EmployeeSalarySetting(
            id=row["id"],
            employee_id=row["employee_id"],
            gross_monthly_salary=row["gross_monthly_salary"],
            preliminary_tax=row["preliminary_tax"],
            employer_fee_rate_bp=row["employer_fee_rate_bp"],
            employer_fee_amount=row["employer_fee_amount"],
            payment_day=row["payment_day"],
            active=bool(row["active"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )


class PayrollRunRepository:
    @staticmethod
    def create(year: int, month: int, payment_date: date, created_by: str = "system") -> PayrollRun:
        run_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """INSERT INTO payroll_runs (id, year, month, payment_date, status, created_at, created_by)
               VALUES (?, ?, ?, ?, 'draft', ?, ?)""",
            (run_id, year, month, payment_date.isoformat(), now, created_by),
        )
        db.commit()
        return PayrollRun(run_id, year, month, payment_date, "draft", now, created_by)

    @staticmethod
    def get(run_id: str) -> Optional[PayrollRun]:
        row = db.execute("SELECT * FROM payroll_runs WHERE id = ?", (run_id,)).fetchone()
        return PayrollRunRepository._row_to_run(row) if row else None

    @staticmethod
    def list_all() -> List[PayrollRun]:
        return [
            PayrollRunRepository._row_to_run(row)
            for row in db.execute(
                "SELECT * FROM payroll_runs ORDER BY year DESC, month DESC, payment_date DESC"
            ).fetchall()
        ]

    @staticmethod
    def set_status(run_id: str, status: str) -> None:
        generated_at = datetime.now() if status == "generated" else None
        if generated_at:
            db.execute(
                "UPDATE payroll_runs SET status = ?, generated_at = ? WHERE id = ?",
                (status, generated_at, run_id),
            )
        else:
            db.execute("UPDATE payroll_runs SET status = ? WHERE id = ?", (status, run_id))
        db.commit()

    @staticmethod
    def _row_to_run(row) -> PayrollRun:
        return PayrollRun(
            id=row["id"],
            year=row["year"],
            month=row["month"],
            payment_date=_date(row["payment_date"]),
            status=row["status"],
            created_at=_dt(row["created_at"]),
            created_by=row["created_by"],
            generated_at=datetime.fromisoformat(row["generated_at"]) if row["generated_at"] else None,
        )


class PayslipRepository:
    @staticmethod
    def create(
        payroll_run_id: str,
        employee_id: str,
        period_year: int,
        period_month: int,
        payment_date: date,
        gross_salary: int,
        preliminary_tax: int,
        employer_fee: int,
    ) -> Payslip:
        net_salary = gross_salary - preliminary_tax
        total_employer_cost = gross_salary + employer_fee
        payslip_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """INSERT INTO payslips
               (id, payroll_run_id, employee_id, period_year, period_month, payment_date,
                gross_salary, preliminary_tax, employer_fee, net_salary, total_employer_cost,
                status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated', ?)""",
            (
                payslip_id,
                payroll_run_id,
                employee_id,
                period_year,
                period_month,
                payment_date.isoformat(),
                gross_salary,
                preliminary_tax,
                employer_fee,
                net_salary,
                total_employer_cost,
                now,
            ),
        )
        db.commit()
        return PayslipRepository.get(payslip_id)

    @staticmethod
    def get(payslip_id: str) -> Optional[Payslip]:
        row = db.execute("SELECT * FROM payslips WHERE id = ?", (payslip_id,)).fetchone()
        return PayslipRepository._row_to_payslip(row) if row else None

    @staticmethod
    def list_for_run(payroll_run_id: str) -> List[Payslip]:
        rows = db.execute(
            "SELECT * FROM payslips WHERE payroll_run_id = ? ORDER BY created_at",
            (payroll_run_id,),
        ).fetchall()
        return [PayslipRepository._row_to_payslip(row) for row in rows]

    @staticmethod
    def list_unbooked() -> List[Payslip]:
        rows = db.execute(
            "SELECT * FROM payslips WHERE voucher_id IS NULL ORDER BY payment_date, created_at"
        ).fetchall()
        return [PayslipRepository._row_to_payslip(row) for row in rows]

    @staticmethod
    def mark_sent(payslip_id: str) -> Optional[Payslip]:
        db.execute(
            "UPDATE payslips SET status = CASE WHEN status = 'generated' THEN 'sent' ELSE status END, pdf_sent_at = ? WHERE id = ?",
            (datetime.now(), payslip_id),
        )
        db.commit()
        return PayslipRepository.get(payslip_id)

    @staticmethod
    def link_booking(payslip_id: str, bank_transaction_id: str, voucher_id: str) -> Optional[Payslip]:
        db.execute(
            "UPDATE payslips SET status = 'booked', bank_transaction_id = ?, voucher_id = ? WHERE id = ?",
            (bank_transaction_id, voucher_id, payslip_id),
        )
        db.commit()
        return PayslipRepository.get(payslip_id)

    @staticmethod
    def _row_to_payslip(row) -> Payslip:
        employee = EmployeeRepository.get(row["employee_id"])
        return Payslip(
            id=row["id"],
            payroll_run_id=row["payroll_run_id"],
            employee_id=row["employee_id"],
            period_year=row["period_year"],
            period_month=row["period_month"],
            payment_date=_date(row["payment_date"]),
            gross_salary=row["gross_salary"],
            preliminary_tax=row["preliminary_tax"],
            employer_fee=row["employer_fee"],
            net_salary=row["net_salary"],
            total_employer_cost=row["total_employer_cost"],
            status=row["status"],
            pdf_sent_at=datetime.fromisoformat(row["pdf_sent_at"]) if row["pdf_sent_at"] else None,
            bank_transaction_id=row["bank_transaction_id"],
            voucher_id=row["voucher_id"],
            created_at=_dt(row["created_at"]),
            employee=employee,
        )
