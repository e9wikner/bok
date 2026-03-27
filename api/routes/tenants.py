"""Tenant management admin endpoints."""

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List

from config import settings

router = APIRouter(prefix="/api/v1/admin/tenants", tags=["admin"])


class CreateTenantRequest(BaseModel):
    id: str
    name: str
    api_key: str
    org_number: Optional[str] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    org_number: Optional[str] = None
    api_key: str
    created_at: Optional[str] = None
    is_active: int = 1


def _verify_admin_key(authorization: Optional[str] = Header(None)) -> str:
    """Verify admin API key."""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API not configured (set ADMIN_API_KEY)",
        )
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )
    if parts[1] != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )
    return parts[1]


def _get_registry():
    from db.tenant_registry import TenantRegistry
    return TenantRegistry()


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    request: CreateTenantRequest,
    admin_key: str = Header(None, alias="authorization"),
):
    _verify_admin_key(admin_key)
    registry = _get_registry()

    if registry.tenant_exists(request.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant '{request.id}' already exists",
        )

    tenant = registry.create_tenant(
        tenant_id=request.id,
        name=request.name,
        api_key=request.api_key,
        org_number=request.org_number,
    )

    # Trigger DB initialization for the new tenant
    from db.tenant_context import set_current_tenant
    token = set_current_tenant(request.id)
    from db.database import db
    db.init_db()

    # Load default accounts
    from repositories.account_repo import AccountRepository
    _load_default_accounts_for_tenant(AccountRepository)

    set_current_tenant(settings.default_tenant_id)

    return TenantResponse(**tenant)


@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    admin_key: str = Header(None, alias="authorization"),
):
    _verify_admin_key(admin_key)
    registry = _get_registry()
    tenants = registry.list_tenants()
    return [TenantResponse(**t) for t in tenants]


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    admin_key: str = Header(None, alias="authorization"),
):
    _verify_admin_key(admin_key)
    registry = _get_registry()
    tenant = registry.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )
    return TenantResponse(**tenant)


@router.delete("/{tenant_id}", status_code=204)
async def deactivate_tenant(
    tenant_id: str,
    admin_key: str = Header(None, alias="authorization"),
):
    _verify_admin_key(admin_key)
    registry = _get_registry()
    if not registry.deactivate_tenant(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )


def _load_default_accounts_for_tenant(AccountRepository):
    """Load BAS 2026 default accounts for a new tenant."""
    default_accounts = [
        ("1000", "Kassa", "asset"),
        ("1010", "PlusGiro", "asset"),
        ("1200", "Kundfordringar", "asset"),
        ("1510", "Kundfordringar konsult", "asset"),
        ("1710", "Inventarier", "asset"),
        ("2000", "Leverantörskulder", "liability"),
        ("2610", "Utgående moms 25%", "vat_out"),
        ("2620", "Utgående moms 12%", "vat_out"),
        ("2630", "Utgående moms 6%", "vat_out"),
        ("2640", "Ingående moms", "vat_in"),
        ("2740", "Privat uttag", "liability"),
        ("2900", "Aktiekapital", "equity"),
        ("2950", "Balanserat resultat", "equity"),
        ("3010", "Försäljning tjänster 25%", "revenue"),
        ("3011", "Försäljning tjänster 25%", "revenue"),
        ("3020", "Försäljning tjänster 12%", "revenue"),
        ("3030", "Försäljning tjänster 6%", "revenue"),
        ("4010", "Personalkostnader", "expense"),
        ("4020", "Hyra kontorslokal", "expense"),
        ("4030", "Tele och Internet", "expense"),
        ("4040", "Resor", "expense"),
        ("5010", "Förbrukningsmaterial", "expense"),
        ("5020", "Telefon och post", "expense"),
        ("6000", "Övriga driftskostnader", "expense"),
        ("8000", "Avskrivning möbler", "expense"),
    ]
    for code, name, account_type in default_accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code=code, name=name, account_type=account_type)
