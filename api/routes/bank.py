"""API routes for bank integration and transaction management."""

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field

from services.bank_integration import BankIntegrationService
from services.categorization import CategorizationService
from domain.validation import ValidationError

router = APIRouter(prefix="/api/v1/bank", tags=["bank"])

bank_service = BankIntegrationService()
cat_service = CategorizationService()


# --- Schemas ---

class BankConnectionCreate(BaseModel):
    """Create a new bank connection."""
    provider: str = Field(default="manual", description="Provider: tink, plaid, manual")
    bank_name: str = Field(..., description="Bank name (e.g. Nordea, SEB, Handelsbanken)")
    account_number: Optional[str] = Field(None, description="Masked account number")
    iban: Optional[str] = None
    currency: str = "SEK"
    sync_from_date: Optional[str] = Field(None, description="Import transactions from this date (YYYY-MM-DD)")


class TransactionImport(BaseModel):
    """Import bank transactions."""
    transactions: List[dict] = Field(..., description="List of transaction objects")


class TransactionCorrection(BaseModel):
    """Correct a transaction's categorization."""
    account_code: str = Field(..., description="Correct BAS account code")
    vat_code: Optional[str] = Field(None, description="Correct VAT code (MP1, MP2, MP3, MF)")


class RuleCreate(BaseModel):
    """Create a new categorization rule."""
    rule_type: str = Field(default="keyword", description="keyword, regex, counterpart, amount_range")
    match_description: Optional[str] = None
    match_counterpart: Optional[str] = None
    match_is_expense: Optional[bool] = None
    match_amount_min: Optional[float] = None
    match_amount_max: Optional[float] = None
    target_account_code: str = Field(..., description="Target BAS account code")
    target_vat_code: Optional[str] = None
    target_description_template: Optional[str] = None
    priority: int = 50


# --- Connection endpoints ---

@router.post("/connections", status_code=201)
async def create_connection(data: BankConnectionCreate):
    """Register a new bank connection."""
    try:
        sync_date = date.fromisoformat(data.sync_from_date) if data.sync_from_date else None
        conn = bank_service.create_connection(
            provider=data.provider,
            bank_name=data.bank_name,
            account_number=data.account_number,
            iban=data.iban,
            currency=data.currency,
            sync_from_date=sync_date,
        )
        return {
            "id": conn.id,
            "provider": conn.provider,
            "bank_name": conn.bank_name,
            "status": conn.status,
            "message": "Bank connection created. Import transactions via POST /api/v1/bank/connections/{id}/import"
        }
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/connections")
async def list_connections():
    """List all bank connections."""
    connections = bank_service.get_connections()
    return {
        "connections": [
            {
                "id": c.id,
                "provider": c.provider,
                "bank_name": c.bank_name,
                "account_number": c.account_number,
                "status": c.status,
                "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
                "currency": c.currency,
            }
            for c in connections
        ]
    }


@router.get("/connections/{connection_id}")
async def get_connection(connection_id: str):
    """Get a specific bank connection."""
    conn = bank_service.get_connection(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {
        "id": conn.id,
        "provider": conn.provider,
        "bank_name": conn.bank_name,
        "account_number": conn.account_number,
        "iban": conn.iban,
        "status": conn.status,
        "currency": conn.currency,
        "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        "sync_from_date": conn.sync_from_date.isoformat() if conn.sync_from_date else None,
    }


# --- Transaction import ---

@router.post("/connections/{connection_id}/import")
async def import_transactions(connection_id: str, data: TransactionImport):
    """Import bank transactions for a connection.
    
    Each transaction should have:
    - date: YYYY-MM-DD
    - amount: Amount in SEK (negative = expense)  
    - description: Transaction text
    - external_id (optional): Bank's ID for dedup
    - counterpart_name (optional): Counterpart name
    """
    try:
        imported, skipped = bank_service.import_transactions(connection_id, data.transactions)
        return {
            "imported": imported,
            "skipped_duplicates": skipped,
            "total_submitted": len(data.transactions),
            "message": f"Imported {imported} transactions. Run POST /api/v1/bank/categorize to auto-categorize."
        }
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/connections/{connection_id}/import-csv")
async def import_csv(
    connection_id: str,
    file: UploadFile = File(...),
    date_column: str = Query("Datum", description="Column name for date"),
    amount_column: str = Query("Belopp", description="Column name for amount"),
    description_column: str = Query("Text", description="Column name for description"),
    delimiter: str = Query(";", description="CSV delimiter"),
):
    """Import transactions from a Swedish bank CSV file.
    
    Supports common Swedish bank exports (SEB, Nordea, Handelsbanken, Swedbank).
    """
    try:
        content = await file.read()
        csv_text = content.decode("utf-8", errors="replace")
        
        imported, skipped = bank_service.import_csv(
            connection_id, csv_text,
            date_column=date_column,
            amount_column=amount_column,
            description_column=description_column,
            delimiter=delimiter,
        )
        return {
            "imported": imported,
            "skipped_duplicates": skipped,
            "filename": file.filename,
        }
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV import error: {str(e)}")


# --- Transaction listing ---

@router.get("/transactions")
async def list_transactions(
    connection_id: Optional[str] = None,
    status: Optional[str] = Query(None, description="Filter by status: pending, categorized, booked, ignored"),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    """List bank transactions with filters."""
    from_d = date.fromisoformat(from_date) if from_date else None
    to_d = date.fromisoformat(to_date) if to_date else None
    
    transactions = bank_service.get_transactions(
        connection_id=connection_id,
        status=status,
        from_date=from_d,
        to_date=to_d,
        limit=limit,
        offset=offset,
    )
    
    return {
        "count": len(transactions),
        "transactions": [
            {
                "id": tx.id,
                "date": tx.transaction_date.isoformat(),
                "amount_sek": tx.amount / 100,
                "description": tx.description,
                "counterpart": tx.counterpart_name,
                "status": tx.status,
                "suggested_account": tx.suggested_account_code,
                "confidence": tx.suggested_confidence,
                "voucher_id": tx.matched_voucher_id,
            }
            for tx in transactions
        ],
    }


@router.get("/transactions/{tx_id}")
async def get_transaction(tx_id: str):
    """Get a single bank transaction."""
    tx = bank_service.get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "id": tx.id,
        "bank_connection_id": tx.bank_connection_id,
        "date": tx.transaction_date.isoformat(),
        "booking_date": tx.booking_date.isoformat() if tx.booking_date else None,
        "amount_sek": tx.amount / 100,
        "currency": tx.currency,
        "description": tx.description,
        "counterpart_name": tx.counterpart_name,
        "counterpart_account": tx.counterpart_account,
        "reference": tx.reference,
        "status": tx.status,
        "suggested_account": tx.suggested_account_code,
        "confidence": tx.suggested_confidence,
        "voucher_id": tx.matched_voucher_id,
        "categorized_at": tx.categorized_at.isoformat() if tx.categorized_at else None,
        "booked_at": tx.booked_at.isoformat() if tx.booked_at else None,
    }


# --- Categorization ---

@router.post("/categorize")
async def categorize_pending(
    auto_book: bool = Query(False, description="Auto-create vouchers for high-confidence matches (≥90%)"),
):
    """Auto-categorize all pending bank transactions.
    
    Uses rule-based + learned pattern matching to suggest BAS account codes.
    With auto_book=true, high-confidence matches (≥90%) are automatically
    booked as vouchers.
    """
    results = cat_service.categorize_pending(auto_book=auto_book)
    return results


@router.post("/transactions/{tx_id}/correct")
async def correct_transaction(tx_id: str, data: TransactionCorrection):
    """Correct a transaction's categorization (teaches the AI).
    
    When you correct a categorization, the system learns from the correction
    and will apply it to similar future transactions.
    """
    try:
        rule_id = cat_service.learn_from_correction(
            tx_id, data.account_code, data.vat_code
        )
        return {
            "message": "Correction applied and learned",
            "rule_id": rule_id,
            "account_code": data.account_code,
            "vat_code": data.vat_code,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/transactions/{tx_id}/ignore")
async def ignore_transaction(tx_id: str):
    """Mark a transaction as ignored (e.g. internal transfers)."""
    bank_service.update_transaction_status(tx_id, status="ignored")
    return {"message": "Transaction marked as ignored"}


# --- Rules ---

@router.get("/rules")
async def list_rules(include_inactive: bool = False):
    """List all categorization rules."""
    rules = cat_service.get_rules(include_inactive=include_inactive)
    return {
        "count": len(rules),
        "rules": [
            {
                "id": r.id,
                "type": r.rule_type,
                "priority": r.priority,
                "match_description": r.match_description,
                "match_counterpart": r.match_counterpart,
                "target_account": r.target_account_code,
                "target_vat": r.target_vat_code,
                "confidence": r.confidence,
                "times_used": r.times_used,
                "times_overridden": r.times_overridden,
                "source": r.source,
                "active": r.active,
            }
            for r in rules
        ],
    }


@router.post("/rules", status_code=201)
async def create_rule(data: RuleCreate):
    """Create a new categorization rule."""
    rule_id = cat_service.add_rule(
        rule_type=data.rule_type,
        match_description=data.match_description,
        match_counterpart=data.match_counterpart,
        match_is_expense=data.match_is_expense,
        match_amount_min=data.match_amount_min,
        match_amount_max=data.match_amount_max,
        target_account_code=data.target_account_code,
        target_vat_code=data.target_vat_code,
        target_description_template=data.target_description_template,
        priority=data.priority,
    )
    return {"id": rule_id, "message": "Rule created"}


# --- Stats & Summary ---

@router.get("/summary")
async def bank_summary():
    """Get bank integration summary: connections, sync status, pending transactions."""
    sync_summary = bank_service.get_sync_summary()
    cat_stats = cat_service.get_stats()
    pending = bank_service.get_pending_count()
    
    return {
        "pending_transactions": pending,
        "sync": sync_summary,
        "categorization": cat_stats,
    }
