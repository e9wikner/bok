"""API routes for company metadata."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_actor, verify_api_key
from db.database import get_db
from repositories.company_info_repo import CompanyInfoRepository

router = APIRouter(prefix="/api/v1/company-info", tags=["company-info"])


class CompanyInfoResponse(BaseModel):
    name: str = ""
    org_number: str = ""
    contact_name: Optional[str] = None
    address: Optional[str] = None
    postnr: Optional[str] = None
    postort: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    seat: Optional[str] = None
    vat_number: Optional[str] = None
    bankgiro: Optional[str] = None
    plusgiro: Optional[str] = None
    f_skatt: bool = False


class CompanyInfoUpdate(BaseModel):
    """Only the fields sent are written; `null` or `""` removes a field.

    A client that does not know a field (e.g. an older settings page without
    `seat`) therefore leaves it as it is.
    """

    name: str
    org_number: str
    contact_name: Optional[str] = None
    address: Optional[str] = None
    postnr: Optional[str] = None
    postort: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    seat: Optional[str] = None
    vat_number: Optional[str] = None
    bankgiro: Optional[str] = None
    plusgiro: Optional[str] = None
    f_skatt: Optional[bool] = None


COMPANY_INFO_KEYS = [
    "name",
    "org_number",
    "contact_name",
    "address",
    "postnr",
    "postort",
    "email",
    "phone",
    "website",
    "seat",
    "vat_number",
    "bankgiro",
    "plusgiro",
]


@router.get("", response_model=CompanyInfoResponse)
async def get_company_info(
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """Return editable company metadata."""
    values = CompanyInfoRepository.get_all()
    fields: dict[str, object] = {
        key: values[key] for key in COMPANY_INFO_KEYS if values.get(key)
    }
    fields["f_skatt"] = (values.get("f_skatt") or "").strip().lower() == "true"
    return CompanyInfoResponse.model_validate(fields)


@router.put("", response_model=CompanyInfoResponse)
async def update_company_info(
    payload: CompanyInfoUpdate,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """Update editable company metadata."""
    sent = payload.model_fields_set
    values = payload.model_dump()
    updates = {key: values[key] for key in COMPANY_INFO_KEYS if key in sent}
    if "f_skatt" in sent:
        f_skatt = values["f_skatt"]
        updates["f_skatt"] = None if f_skatt is None else str(f_skatt).lower()
    CompanyInfoRepository.set_values(updates)
    get_db().commit()

    return await get_company_info(actor=actor, api_key=api_key)
