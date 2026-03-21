"""API routes for accounts."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from api.schemas import AccountResponse, AccountListResponse, CreateAccountRequest
from api.deps import get_ledger_service
from services.ledger import LedgerService
from domain.validation import ValidationError

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: CreateAccountRequest,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Create a new account (typically for extending BAS 2026)."""
    try:
        account = ledger.accounts.create(
            code=request.code,
            name=request.name,
            account_type=request.account_type,
            vat_code=request.vat_code,
            sru_code=request.sru_code,
            active=request.active,
        )
        return _account_to_response(account)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": e.message, "code": e.code, "details": e.details}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    active_only: bool = True,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    List all accounts (BAS 2026 Chart of Accounts).
    
    Filter by active status.
    """
    try:
        accounts = ledger.accounts.list_all(active_only=active_only)
        return AccountListResponse(
            accounts=[_account_to_response(a) for a in accounts],
            total=len(accounts)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{code}", response_model=AccountResponse)
async def get_account(
    code: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Get account by code."""
    try:
        account = ledger.accounts.get(code)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {code} not found"
            )
        return _account_to_response(account)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _account_to_response(account) -> AccountResponse:
    """Convert domain Account to response."""
    return AccountResponse(
        code=account.code,
        name=account.name,
        account_type=account.account_type.value,
        vat_code=account.vat_code,
        sru_code=account.sru_code,
        active=account.active
    )
