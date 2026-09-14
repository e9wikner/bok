"""Dependency injection for FastAPI."""

import logging
import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from config import settings
from services.auth import AuthService
from services.ledger import LedgerService

logger = logging.getLogger(__name__)


async def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
    """Verify API key or JWT token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Expect: "Bearer <api-key-or-jwt>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    # Accept static API key
    if token == settings.api_key:
        return token

    # Accept valid JWT token
    try:
        AuthService().verify_jwt(token)
        return token
    except HTTPException:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key or token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_ledger_service() -> LedgerService:
    """Get ledger service instance."""
    return LedgerService()


async def get_current_actor(api_key: str = Depends(verify_api_key)) -> str:
    """Get current actor (user) from API key."""
    return "api"


async def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> Optional[str]:
    """Read the optional Idempotency-Key header.

    Transition rule (c) in SPEC-idempotens §8: the header is optional for now.
    A call without one runs the old way and is logged, so the gap is visible
    before the key becomes mandatory.
    """
    if idempotency_key is None:
        logger.info("idempotency_key_missing")
        return None

    try:
        uuid.UUID(idempotency_key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Idempotency-Key must be a UUID",
                "code": "invalid_idempotency_key",
                "details": f"received={idempotency_key}",
            },
        )
    return idempotency_key
