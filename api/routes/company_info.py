"""API routes for company metadata."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_actor, verify_api_key
from db.database import get_db

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


class CompanyInfoUpdate(BaseModel):
    name: str
    org_number: str
    contact_name: Optional[str] = None
    address: Optional[str] = None
    postnr: Optional[str] = None
    postort: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


COMPANY_INFO_KEYS = [
    "name",
    "org_number",
    "contact_name",
    "address",
    "postnr",
    "postort",
    "email",
    "phone",
]


def _read_company_info() -> dict:
    db = get_db()
    rows = db.execute("SELECT key, value FROM company_info").fetchall()
    values = {row["key"]: row["value"] for row in rows}
    return {key: values.get(key) for key in COMPANY_INFO_KEYS}


@router.get("", response_model=CompanyInfoResponse)
async def get_company_info(
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """Return editable company metadata."""
    values = _read_company_info()
    return CompanyInfoResponse(
        name=values.get("name") or "",
        org_number=values.get("org_number") or "",
        contact_name=values.get("contact_name"),
        address=values.get("address"),
        postnr=values.get("postnr"),
        postort=values.get("postort"),
        email=values.get("email"),
        phone=values.get("phone"),
    )


@router.put("", response_model=CompanyInfoResponse)
async def update_company_info(
    payload: CompanyInfoUpdate,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """Update editable company metadata."""
    db = get_db()
    values = payload.model_dump()
    for key in COMPANY_INFO_KEYS:
        value = values.get(key)
        if value is None:
            db.execute("DELETE FROM company_info WHERE key = ?", (key,))
            continue

        normalized = value.strip() if isinstance(value, str) else value
        if normalized == "":
            db.execute("DELETE FROM company_info WHERE key = ?", (key,))
            continue

        db.execute(
            """
            INSERT INTO company_info (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, normalized),
        )
    db.commit()

    return await get_company_info(actor=actor, api_key=api_key)
