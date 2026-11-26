"""API routes for accounts."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_current_actor, get_ledger_service
from api.schemas import AccountListResponse, AccountResponse, CreateAccountRequest
from domain.validation import ValidationError
from services.ledger import LedgerService

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: CreateAccountRequest,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    """Create a new account (typically for extending BAS 2026).

    An existing code gets `409 account_exists`; it is never overwritten.
    """
    try:
        account = ledger.create_account(
            code=request.code,
            name=request.name,
            account_type=request.account_type,
            vat_code=request.vat_code,
            sru_code=request.sru_code,
            active=request.active,
            actor=actor,
        )
    except ValidationError as exc:
        if exc.code != "account_exists":
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": exc.message, "code": exc.code},
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


@router.get("/with-transactions", response_model=dict)
async def list_accounts_with_transactions(
    fiscal_year_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Codes of the accounts with a posted transaction in the fiscal year."""
    return {
        "fiscal_year_id": fiscal_year_id,
        "codes": ledger.accounts.codes_with_transactions(fiscal_year_id),
    }


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
