"""Auth routes — login and /me."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from services.auth import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MeResponse(BaseModel):
    username: str


# ------------------------------------------------------------------
# Dependency: extract JWT from Authorization header
# ------------------------------------------------------------------

def get_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    """Extract token from 'Authorization: Bearer <token>' header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Authenticate and receive a JWT access token."""
    svc = AuthService()
    token = svc.login(body.username, body.password)
    me = svc.get_me(token)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut(username=me["username"]),
    )


@router.post("/logout")
async def logout():
    """Logout endpoint. JWT is stateless so just return 200 OK."""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=MeResponse)
async def get_me(token: str = Depends(get_bearer_token)):
    """Return the currently authenticated user's profile."""
    svc = AuthService()
    return svc.get_me(token)
