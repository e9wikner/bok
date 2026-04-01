"""Dependency injection for FastAPI."""

from fastapi import Depends, Header, HTTPException, status
from typing import Optional
from config import settings
from services.ledger import LedgerService


def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
    """Verify API key from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Expect: "Bearer <api-key>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = parts[1]

    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return api_key


def get_ledger_service() -> LedgerService:
    """Get ledger service instance."""
    return LedgerService()


def get_current_actor(api_key: str = Depends(verify_api_key)) -> str:
    """Get current actor (user) from API key."""
    return "api"
