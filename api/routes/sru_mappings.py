"""API routes for SRU mappings (INK2 tax declaration support).

SRU = Skatteverkets Rapporterings-Utbyte
Maps accounts to Swedish tax declaration (INK2) fields.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel

from api.deps import get_current_actor, verify_api_key
from db.database import get_db

router = APIRouter(prefix="/api/v1/fiscal-years", tags=["sru-mappings"])


class SRUMappingCreate(BaseModel):
    """Create or update SRU mapping."""
    # Historical name kept for API compatibility; value is the account code (e.g. "1920").
    account_id: str
    sru_field: str


class SRUMappingResponse(BaseModel):
    """SRU mapping response."""
    id: str
    fiscal_year_id: str
    account_id: str
    account_code: str
    account_name: str
    sru_field: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.get("/{fiscal_year_id}/sru-mappings", response_model=List[SRUMappingResponse])
async def list_sru_mappings(
    fiscal_year_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    List all SRU mappings for a fiscal year.
    
    Returns account-to-SRU-field mappings used for INK2 tax declaration.
    """
    db = get_db()
    
    cursor = db.execute(
        """
        SELECT 
            m.id,
            m.fiscal_year_id,
            m.account_code as account_id,
            a.code as account_code,
            a.name as account_name,
            m.sru_field,
            m.created_at,
            m.updated_at
        FROM account_sru_mappings m
        JOIN accounts a ON m.account_code = a.code
        WHERE m.fiscal_year_id = ?
        ORDER BY a.code
        """,
        (fiscal_year_id,)
    )
    
    mappings = []
    for row in cursor.fetchall():
        mappings.append({
            "id": row["id"],
            "fiscal_year_id": row["fiscal_year_id"],
            "account_id": row["account_id"],
            "account_code": row["account_code"],
            "account_name": row["account_name"],
            "sru_field": row["sru_field"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    
    return mappings


@router.post("/{fiscal_year_id}/sru-mappings", status_code=status.HTTP_201_CREATED)
async def create_sru_mapping(
    fiscal_year_id: str,
    mapping: SRUMappingCreate,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    Create or update SRU mapping for an account.
    
    Maps an account to a specific INK2/SRU field number.
    If mapping exists, it will be updated.
    """
    import uuid
    from datetime import datetime
    
    db = get_db()

    account = db.execute(
        "SELECT code FROM accounts WHERE code = ?",
        (mapping.account_id,)
    ).fetchone()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    # Check if mapping already exists
    existing = db.execute(
        "SELECT id FROM account_sru_mappings WHERE fiscal_year_id = ? AND account_code = ?",
        (fiscal_year_id, mapping.account_id)
    ).fetchone()
    
    now = datetime.now().isoformat()
    
    if existing:
        # Update existing
        db.execute(
            """
            UPDATE account_sru_mappings 
            SET sru_field = ?, updated_at = ?
            WHERE id = ?
            """,
            (mapping.sru_field, now, existing["id"])
        )
        db.commit()
        return {
            "id": existing["id"],
            "fiscal_year_id": fiscal_year_id,
            "account_id": mapping.account_id,
            "sru_field": mapping.sru_field,
            "created_at": now,
            "updated_at": now,
        }
    else:
        # Create new
        mapping_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO account_sru_mappings (id, fiscal_year_id, account_code, sru_field, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mapping_id, fiscal_year_id, mapping.account_id, mapping.sru_field, now, now)
        )
        db.commit()
        return {
            "id": mapping_id,
            "fiscal_year_id": fiscal_year_id,
            "account_id": mapping.account_id,
            "sru_field": mapping.sru_field,
            "created_at": now,
            "updated_at": now,
        }


@router.delete("/{fiscal_year_id}/sru-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sru_mapping(
    fiscal_year_id: str,
    mapping_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    Delete SRU mapping.
    """
    db = get_db()
    
    cursor = db.execute(
        "DELETE FROM account_sru_mappings WHERE id = ? AND fiscal_year_id = ?",
        (mapping_id, fiscal_year_id)
    )
    db.commit()
    
    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SRU mapping not found"
        )
    
    return None


@router.get("/{fiscal_year_id}/sru-mappings/by-field/{sru_field}")
async def get_accounts_by_sru_field(
    fiscal_year_id: str,
    sru_field: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    Get all accounts mapped to a specific SRU field.
    
    Useful for calculating totals for INK2 declaration fields.
    """
    db = get_db()
    
    cursor = db.execute(
        """
        SELECT 
            a.id,
            a.code,
            a.name,
            a.account_type,
            m.sru_field
        FROM account_sru_mappings m
        JOIN accounts a ON m.account_code = a.code
        WHERE m.fiscal_year_id = ? AND m.sru_field = ?
        ORDER BY a.code
        """,
        (fiscal_year_id, sru_field)
    )
    
    accounts = []
    for row in cursor.fetchall():
        accounts.append({
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "account_type": row["account_type"],
            "sru_field": row["sru_field"],
        })
    
    return {
        "sru_field": sru_field,
        "fiscal_year_id": fiscal_year_id,
        "accounts": accounts,
        "count": len(accounts)
    }


@router.post("/{fiscal_year_id}/sru-mappings/bulk", status_code=status.HTTP_201_CREATED)
async def bulk_create_sru_mappings(
    fiscal_year_id: str,
    mappings: List[SRUMappingCreate],
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """
    Bulk create/update SRU mappings.
    
    Efficiently create or update multiple mappings at once.
    Useful when importing SRU data from SIE4 files.
    """
    import uuid
    from datetime import datetime
    
    db = get_db()
    now = datetime.now().isoformat()
    created_count = 0
    updated_count = 0
    incoming_account_codes = [mapping.account_id for mapping in mappings]
    
    with db.transaction():
        if incoming_account_codes:
            placeholders = ",".join("?" for _ in incoming_account_codes)
            db.execute(
                f"""
                DELETE FROM account_sru_mappings
                WHERE fiscal_year_id = ? AND account_code NOT IN ({placeholders})
                """,
                (fiscal_year_id, *incoming_account_codes)
            )
        else:
            db.execute(
                "DELETE FROM account_sru_mappings WHERE fiscal_year_id = ?",
                (fiscal_year_id,)
            )

        for mapping in mappings:
            account = db.execute(
                "SELECT code FROM accounts WHERE code = ?",
                (mapping.account_id,)
            ).fetchone()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account {mapping.account_id} not found"
                )

            # Check if mapping exists
            existing = db.execute(
                "SELECT id FROM account_sru_mappings WHERE fiscal_year_id = ? AND account_code = ?",
                (fiscal_year_id, mapping.account_id)
            ).fetchone()
            
            if existing:
                # Update
                db.execute(
                    """
                    UPDATE account_sru_mappings 
                    SET sru_field = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (mapping.sru_field, now, existing["id"])
                )
                updated_count += 1
            else:
                # Create
                mapping_id = str(uuid.uuid4())
                db.execute(
                    """
                    INSERT INTO account_sru_mappings (id, fiscal_year_id, account_code, sru_field, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (mapping_id, fiscal_year_id, mapping.account_id, mapping.sru_field, now, now)
                )
                created_count += 1
    
    return {
        "created": created_count,
        "updated": updated_count,
        "total": len(mappings)
    }
