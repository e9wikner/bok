"""Dependency injection for FastAPI."""

from fastapi import Depends, Header, HTTPException, status
from typing import Optional
from config import settings
from services.auth import AuthService
from services.ledger import LedgerService


def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
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


def get_ledger_service() -> LedgerService:
    """Get ledger service instance."""
    return LedgerService()


def get_current_actor(api_key: str = Depends(verify_api_key)) -> str:
    """Get current actor (user) from API key."""
    return "api"
