"""API routes for accounts."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_ledger_service
from api.schemas import AccountListResponse, AccountResponse, CreateAccountRequest
from services.ledger import LedgerService

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: CreateAccountRequest,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Create a new account (typically for extending BAS 2026)."""
    account = ledger.accounts.create(
        code=request.code,
        name=request.name,
        account_type=request.account_type,
        vat_code=request.vat_code,
        sru_code=request.sru_code,
        active=request.active,
    )
    return _account_to_response(account)


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    active_only: bool = True,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    List all accounts (BAS 2026 Chart of Accounts).

    Filter by active status.
    """
    accounts = ledger.accounts.list_all(active_only=active_only)
    return AccountListResponse(
        accounts=[_account_to_response(a) for a in accounts], total=len(accounts)
    )


@router.get("/{code}", response_model=AccountResponse)
async def get_account(
    code: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Get account by code."""
    account = ledger.accounts.get(code)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {code} not found",
        )
    return _account_to_response(account)


def _account_to_response(account) -> AccountResponse:
    """Convert domain Account to response."""
    return AccountResponse(
        code=account.code,
        name=account.name,
        account_type=account.account_type.value,
        vat_code=account.vat_code,
        sru_code=account.sru_code,
        active=account.active,
    )
