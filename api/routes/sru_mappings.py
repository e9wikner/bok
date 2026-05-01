"""API routes for SRU mappings (INK2 tax declaration support).

SRU = Skatteverkets Rapporterings-Utbyte
Maps accounts to Swedish tax declaration (INK2) fields.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel

from api.deps import get_current_actor, verify_api_key
from db.database import get_db
from repositories.period_repo import PeriodRepository

router = APIRouter(prefix="/api/v1/fiscal-years", tags=["sru-mappings"])


class SRUMappingCreate(BaseModel):
    """Create or update SRU mapping."""
    # account_id is a historical API field name; both values are account codes (e.g. "1920").
    account_id: Optional[str] = None
    account_code: Optional[str] = None
    sru_field: str


class SRUMappingResponse(BaseModel):
    """SRU mapping response."""
    id: Optional[str] = None
    fiscal_year_id: str
    account_id: str
    account_code: str
    account_name: str
    sru_field: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


def _default_sru_mapping_for_account(account_code: str) -> Optional[str]:
    """Return the default SRU field for an account according to the app's fallback mapping."""
    from services.sru_export import DEFAULT_SRU_MAPPINGS

    try:
        account_number = int(account_code)
    except ValueError:
        return None

    for sru_field, account_numbers in DEFAULT_SRU_MAPPINGS.items():
        if account_number in account_numbers:
            return sru_field
    return None


def _mapping_account_code(mapping: SRUMappingCreate) -> str:
    """Return account code from either legacy or current request field."""
    account_code = mapping.account_code or mapping.account_id
    if not account_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="account_code or account_id is required",
        )
    return account_code


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


@router.get("/{fiscal_year_id}/sru-mappings/default", response_model=List[SRUMappingResponse])
async def list_default_sru_mappings(
    fiscal_year_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """List default SRU mappings for all accounts, without reading saved overrides."""
    db = get_db()

    cursor = db.execute(
        """
        SELECT code, name
        FROM accounts
        ORDER BY code
        """
    )

    mappings = []
    for row in cursor.fetchall():
        sru_field = _default_sru_mapping_for_account(row["code"])
        if not sru_field:
            continue
        mappings.append({
            "id": None,
            "fiscal_year_id": fiscal_year_id,
            "account_id": row["code"],
            "account_code": row["code"],
            "account_name": row["name"],
            "sru_field": sru_field,
            "created_at": None,
            "updated_at": None,
        })

    return mappings


@router.post("/{fiscal_year_id}/sru-mappings/inherit-previous", status_code=status.HTTP_200_OK)
async def inherit_previous_year_sru_mappings(
    fiscal_year_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """Replace this year's saved mappings with mappings from the closest previous fiscal year."""
    import uuid
    from datetime import datetime

    current_year = PeriodRepository.get_fiscal_year(fiscal_year_id)
    if not current_year:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")

    previous_year = next(
        (
            year
            for year in sorted(
                PeriodRepository.list_fiscal_years(),
                key=lambda fy: fy.end_date,
                reverse=True,
            )
            if year.end_date < current_year.start_date
        ),
        None,
    )
    if not previous_year:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Det finns inget tidigare räkenskapsår att ärva mappning från",
        )

    db = get_db()
    rows = db.execute(
        """
        SELECT account_code, sru_field
        FROM account_sru_mappings
        WHERE fiscal_year_id = ?
        ORDER BY account_code
        """,
        (previous_year.id,),
    ).fetchall()

    now = datetime.now().isoformat()
    with db.transaction():
        db.execute(
            "DELETE FROM account_sru_mappings WHERE fiscal_year_id = ?",
            (fiscal_year_id,),
        )
        for row in rows:
            db.execute(
                """
                INSERT INTO account_sru_mappings (id, fiscal_year_id, account_code, sru_field, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), fiscal_year_id, row["account_code"], row["sru_field"], now, now),
            )

    return {
        "fiscal_year_id": fiscal_year_id,
        "source_fiscal_year_id": previous_year.id,
        "copied": len(rows),
    }


@router.post("/{fiscal_year_id}/sru-mappings/reset-default", status_code=status.HTTP_200_OK)
async def reset_sru_mappings_to_default(
    fiscal_year_id: str,
    actor: str = Depends(get_current_actor),
    api_key: str = Depends(verify_api_key),
):
    """Remove all saved mappings for a fiscal year so default mapping is used."""
    db = get_db()
    cursor = db.execute(
        "DELETE FROM account_sru_mappings WHERE fiscal_year_id = ?",
        (fiscal_year_id,),
    )
    db.commit()
    return {
        "fiscal_year_id": fiscal_year_id,
        "deleted": cursor.rowcount,
    }


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
    account_code = _mapping_account_code(mapping)

    account = db.execute(
        "SELECT code FROM accounts WHERE code = ?",
        (account_code,)
    ).fetchone()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    # Check if mapping already exists
    existing = db.execute(
        "SELECT id FROM account_sru_mappings WHERE fiscal_year_id = ? AND account_code = ?",
        (fiscal_year_id, account_code)
    ).fetchone()
    
    now = datetime.now().isoformat()
    
    if existing:
        # Update existing
        db.execute(
            """
            UPDATE account_sru_mappings 
            SET sru_field = ?, updated_at = ?
            WHERE fiscal_year_id = ? AND account_code = ?
            """,
            (mapping.sru_field, now, fiscal_year_id, account_code)
        )
        db.commit()
        return {
            "id": existing["id"],
            "fiscal_year_id": fiscal_year_id,
            "account_id": account_code,
            "account_code": account_code,
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
            (mapping_id, fiscal_year_id, account_code, mapping.sru_field, now, now)
        )
        db.commit()
        return {
            "id": mapping_id,
            "fiscal_year_id": fiscal_year_id,
            "account_id": account_code,
            "account_code": account_code,
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
            "id": row["code"],
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
    incoming_account_codes = [_mapping_account_code(mapping) for mapping in mappings]
    
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

        for mapping, account_code in zip(mappings, incoming_account_codes):
            account = db.execute(
                "SELECT code FROM accounts WHERE code = ?",
                (account_code,)
            ).fetchone()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account {account_code} not found"
                )

            # Check if mapping exists
            existing = db.execute(
                "SELECT id FROM account_sru_mappings WHERE fiscal_year_id = ? AND account_code = ?",
                (fiscal_year_id, account_code)
            ).fetchone()
            
            if existing:
                # Update
                db.execute(
                    """
                    UPDATE account_sru_mappings 
                    SET sru_field = ?, updated_at = ?
                    WHERE fiscal_year_id = ? AND account_code = ?
                    """,
                    (mapping.sru_field, now, fiscal_year_id, account_code)
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
                    (mapping_id, fiscal_year_id, account_code, mapping.sru_field, now, now)
                )
                created_count += 1
    
    return {
        "created": created_count,
        "updated": updated_count,
        "total": len(mappings)
    }
