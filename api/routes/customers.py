"""API routes for customer register."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from domain.invoice_validation import ValidationError
from services.customer_article import CustomerService

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


class CreateCustomerRequest(BaseModel):
    name: str = Field(..., min_length=1)
    org_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms_days: int = Field(30, ge=0)


@router.get("", response_model=dict)
async def list_customers(
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
):
    service = CustomerService()
    customers = service.list_customers(active_only=active_only, search=search)
    return {"customers": [_customer_to_dict(customer) for customer in customers]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: CreateCustomerRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        customer = CustomerService().create_customer(**request.model_dump())
        return _customer_to_dict(customer)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "error": exc.message})


def _customer_to_dict(customer) -> dict:
    return {
        "id": customer.id,
        "name": customer.name,
        "org_number": customer.org_number,
        "email": customer.email,
        "address": customer.address,
        "payment_terms_days": customer.payment_terms_days,
        "active": customer.active,
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
    }
