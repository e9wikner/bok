"""API routes for simple payroll."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from domain.payroll_models import Employee, EmployeeSalarySetting, PayrollRun, Payslip
from domain.validation import ValidationError
from services.payroll import PayrollService

router = APIRouter(prefix="/api/v1/payroll", tags=["payroll"])


class EmployeeRequest(BaseModel):
    name: str = Field(..., min_length=1)
    personal_number: Optional[str] = None
    email: Optional[str] = None
    bank_account: Optional[str] = None
    active: bool = True


class SalarySettingRequest(BaseModel):
    gross_monthly_salary: int = Field(..., ge=0)
    preliminary_tax: int = Field(..., ge=0)
    employer_fee_rate_bp: Optional[int] = Field(None, ge=0)
    employer_fee_amount: Optional[int] = Field(None, ge=0)
    payment_day: int = Field(25, ge=1, le=31)
    active: bool = True


class PayrollRunRequest(BaseModel):
    year: int
    month: int = Field(..., ge=1, le=12)
    payment_date: Optional[date] = None


class BookPayslipRequest(BaseModel):
    bank_transaction_id: str


@router.get("/employees", response_model=dict)
async def list_employees(
    active_only: bool = False,
    search: Optional[str] = Query(None),
):
    service = PayrollService()
    employees = service.employees.list_all(active_only=active_only, search=search)
    return {"employees": [_employee_to_dict(e, service.settings.get_for_employee(e.id)) for e in employees]}


@router.post("/employees", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_employee(
    request: EmployeeRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        service = PayrollService()
        employee = service.create_employee(
            request.name,
            personal_number=request.personal_number,
            email=request.email,
            bank_account=request.bank_account,
            actor=actor,
        )
        return _employee_to_dict(employee, None)
    except ValidationError as exc:
        raise _validation_http(exc)


@router.put("/employees/{employee_id}", response_model=dict)
async def update_employee(
    employee_id: str,
    request: EmployeeRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        service = PayrollService()
        employee = service.update_employee(
            employee_id,
            request.name,
            request.personal_number,
            request.email,
            request.bank_account,
            request.active,
            actor=actor,
        )
        return _employee_to_dict(employee, service.settings.get_for_employee(employee.id))
    except ValidationError as exc:
        raise _validation_http(exc)


@router.put("/employees/{employee_id}/salary", response_model=dict)
async def set_salary_setting(
    employee_id: str,
    request: SalarySettingRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        service = PayrollService()
        setting = service.set_salary_setting(
            employee_id,
            gross_monthly_salary=request.gross_monthly_salary,
            preliminary_tax=request.preliminary_tax,
            employer_fee_rate_bp=request.employer_fee_rate_bp,
            employer_fee_amount=request.employer_fee_amount,
            payment_day=request.payment_day,
            active=request.active,
            actor=actor,
        )
        employee = service.employees.get(employee_id)
        return _employee_to_dict(employee, setting)
    except ValidationError as exc:
        raise _validation_http(exc)


@router.get("/runs", response_model=dict)
async def list_payroll_runs():
    service = PayrollService()
    runs = service.runs.list_all()
    return {"payroll_runs": [_run_to_dict(run, service.payslips.list_for_run(run.id)) for run in runs]}


@router.post("/runs", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_payroll_run(
    request: PayrollRunRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        service = PayrollService()
        run = service.create_payroll_run(
            request.year,
            request.month,
            payment_date=request.payment_date,
            actor=actor,
        )
        return _run_to_dict(run, [])
    except ValidationError as exc:
        raise _validation_http(exc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/runs/{payroll_run_id}/generate", response_model=dict)
async def generate_payslips(
    payroll_run_id: str,
    actor: str = Depends(get_current_actor),
):
    try:
        service = PayrollService()
        payslips = service.generate_payslips(payroll_run_id, actor=actor)
        run = service.runs.get(payroll_run_id)
        return _run_to_dict(run, payslips)
    except ValidationError as exc:
        raise _validation_http(exc)


@router.get("/runs/{payroll_run_id}/payslips", response_model=dict)
async def list_payslips(payroll_run_id: str):
    service = PayrollService()
    return {"payslips": [_payslip_to_dict(p) for p in service.payslips.list_for_run(payroll_run_id)]}


@router.get("/payslips/{payslip_id}", response_model=dict)
async def get_payslip(payslip_id: str):
    service = PayrollService()
    payslip = service.payslips.get(payslip_id)
    if not payslip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
    return _payslip_to_dict(payslip)


@router.post("/payslips/{payslip_id}/mark-sent", response_model=dict)
async def mark_payslip_sent(
    payslip_id: str,
    actor: str = Depends(get_current_actor),
):
    try:
        service = PayrollService()
        return _payslip_to_dict(service.mark_payslip_sent(payslip_id, actor=actor))
    except ValidationError as exc:
        raise _validation_http(exc)


@router.post("/payslips/{payslip_id}/book", response_model=dict)
async def book_payslip(
    payslip_id: str,
    request: BookPayslipRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        service = PayrollService()
        payslip = service.match_bank_transaction_and_book(
            payslip_id,
            request.bank_transaction_id,
            actor=actor,
        )
        return _payslip_to_dict(payslip)
    except ValidationError as exc:
        raise _validation_http(exc)


def _employee_to_dict(employee: Employee, setting: Optional[EmployeeSalarySetting]) -> dict:
    payload = {
        "id": employee.id,
        "name": employee.name,
        "personal_number": employee.personal_number,
        "email": employee.email,
        "bank_account": employee.bank_account,
        "active": employee.active,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
    }
    payload["salary_setting"] = _setting_to_dict(setting) if setting else None
    return payload


def _setting_to_dict(setting: EmployeeSalarySetting) -> dict:
    return {
        "id": setting.id,
        "employee_id": setting.employee_id,
        "gross_monthly_salary": setting.gross_monthly_salary,
        "preliminary_tax": setting.preliminary_tax,
        "employer_fee_rate_bp": setting.employer_fee_rate_bp,
        "employer_fee_amount": setting.employer_fee_amount,
        "calculated_employer_fee": setting.calculate_employer_fee(),
        "payment_day": setting.payment_day,
        "active": setting.active,
    }


def _run_to_dict(run: PayrollRun, payslips: list[Payslip]) -> dict:
    return {
        "id": run.id,
        "year": run.year,
        "month": run.month,
        "payment_date": run.payment_date,
        "status": run.status,
        "created_at": run.created_at,
        "created_by": run.created_by,
        "generated_at": run.generated_at,
        "payslip_count": len(payslips),
        "total_gross_salary": sum(p.gross_salary for p in payslips),
        "total_preliminary_tax": sum(p.preliminary_tax for p in payslips),
        "total_employer_fee": sum(p.employer_fee for p in payslips),
        "total_net_salary": sum(p.net_salary for p in payslips),
        "total_employer_cost": sum(p.total_employer_cost for p in payslips),
        "payslips": [_payslip_to_dict(p) for p in payslips],
    }


def _payslip_to_dict(payslip: Payslip) -> dict:
    return {
        "id": payslip.id,
        "payroll_run_id": payslip.payroll_run_id,
        "employee_id": payslip.employee_id,
        "employee_name": payslip.employee.name if payslip.employee else None,
        "period_year": payslip.period_year,
        "period_month": payslip.period_month,
        "payment_date": payslip.payment_date,
        "gross_salary": payslip.gross_salary,
        "preliminary_tax": payslip.preliminary_tax,
        "employer_fee": payslip.employer_fee,
        "net_salary": payslip.net_salary,
        "total_employer_cost": payslip.total_employer_cost,
        "status": payslip.status,
        "pdf_sent_at": payslip.pdf_sent_at,
        "bank_transaction_id": payslip.bank_transaction_id,
        "voucher_id": payslip.voucher_id,
        "created_at": payslip.created_at,
    }


def _validation_http(exc: ValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": exc.message, "code": exc.code, "details": exc.details},
    )
