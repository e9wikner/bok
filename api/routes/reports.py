"""API routes for reports."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import (
    TrialBalanceResponse,
    TrialBalanceRow,
    AccountLedgerResponse,
    AccountLedgerRow,
    AuditHistoryResponse,
    AuditLogEntryResponse,
)
from api.deps import get_ledger_service
from services.ledger import LedgerService

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def get_trial_balance(
    period_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    Get trial balance (råbalans) for a period.
    
    Includes all accounts with debit/credit balances.
    """
    try:
        period = ledger.periods.get_period(period_id)
        if not period:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Period not found"
            )
        
        balances = ledger.get_trial_balance(period_id)
        all_accounts = ledger.accounts.get_all_as_dict()
        
        rows = []
        total_debit = 0
        total_credit = 0
        
        for account_code in sorted(balances.keys()):
            balance = balances[account_code]
            debit = balance["debit"]
            credit = balance["credit"]
            net_balance = debit - credit
            
            rows.append(TrialBalanceRow(
                account_code=account_code,
                debit=debit,
                credit=credit,
                balance=net_balance
            ))
            
            total_debit += debit
            total_credit += credit
        
        return TrialBalanceResponse(
            period_id=period_id,
            period=f"{period.year}-{period.month:02d}",
            as_of=period.end_date,
            rows=rows,
            total_debit=total_debit,
            total_credit=total_credit
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/account/{account_code}", response_model=AccountLedgerResponse)
async def get_account_ledger(
    account_code: str,
    period_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    Get account ledger (huvudbok) for a specific account.
    
    Shows all transactions for the account in systematic order.
    """
    try:
        account = ledger.accounts.get(account_code)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_code} not found"
            )
        
        period = ledger.periods.get_period(period_id)
        if not period:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Period not found"
            )
        
        ledger_rows = ledger.get_account_ledger(account_code, period_id)
        
        ending_balance = 0
        if ledger_rows:
            ending_balance = ledger_rows[-1]["balance"]
        
        return AccountLedgerResponse(
            account_code=account_code,
            account_name=account.name,
            period_id=period_id,
            rows=[
                AccountLedgerRow(
                    date=r["date"],
                    voucher_series=r["voucher_series"],
                    voucher_number=r["voucher_number"],
                    description=r["description"],
                    debit=r["debit"],
                    credit=r["credit"],
                    balance=r["balance"]
                )
                for r in ledger_rows
            ],
            ending_balance=ending_balance
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/audit/{entity_type}/{entity_id}", response_model=AuditHistoryResponse)
async def get_audit_history(
    entity_type: str,
    entity_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
):
    """
    Get audit trail (behandlingshistorik) for an entity.
    
    Shows all changes to the entity with timestamps and actors.
    """
    try:
        entries = ledger.audit.get_history(entity_type, entity_id)
        
        return AuditHistoryResponse(
            entity_type=entity_type,
            entity_id=entity_id,
            entries=[
                AuditLogEntryResponse(
                    id=entry.id,
                    entity_type=entry.entity_type,
                    entity_id=entry.entity_id,
                    action=entry.action.value,
                    actor=entry.actor,
                    payload=entry.payload,
                    timestamp=entry.timestamp
                )
                for entry in entries
            ]
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
