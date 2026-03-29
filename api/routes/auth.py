"""Auth routes — register, login, and /me."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr

from services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None


class TenantOut(BaseModel):
    id: str
    role: str
    name: Optional[str] = None
    org_number: Optional[str] = None


class RegisterResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    tenants: list[TenantOut]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    tenants: list[TenantOut]


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    tenants: list[TenantOut]


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

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest):
    """Register a new user account."""
    svc = AuthService()
    result = svc.register(body.email, body.password, body.full_name)
    return result


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Authenticate and receive a JWT access token."""
    svc = AuthService()
    token = svc.login(body.email, body.password)
    me = svc.get_me(token)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut(id=me["id"], email=me["email"], full_name=me.get("full_name")),
        tenants=[TenantOut(**t) for t in me["tenants"]],
    )


@router.post("/logout")
async def logout():
    """Logout endpoint. JWT is stateless so just return 200 OK."""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=MeResponse)
async def get_me(token: str = Depends(get_bearer_token)):
    """Return the currently authenticated user's profile and tenants."""
    svc = AuthService()
    result = svc.get_me(token)
    return result
