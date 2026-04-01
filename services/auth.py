"""Authentication service — user registration, login, and JWT management."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext

from config import settings
from db.database import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Handles user registration, login, and JWT operations."""

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def _verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    # ------------------------------------------------------------------
    # JWT helpers
    # ------------------------------------------------------------------

    def create_jwt(self, user_id: str, email: str) -> str:
        """Encode a JWT with user_id and email, valid for jwt_expire_days days."""
        expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
        payload = {
            "sub": user_id,
            "email": email,
            "exp": expire,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def verify_jwt(self, token: str) -> dict:
        """Decode and validate a JWT.  Raises HTTP 401 on any error."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # ------------------------------------------------------------------
    # User helpers
    # ------------------------------------------------------------------

    def _get_user_by_email(self, email: str) -> Optional[dict]:
        cursor = db.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _get_user_by_id(self, user_id: str) -> Optional[dict]:
        cursor = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, email: str, password: str, full_name: Optional[str] = None) -> dict:
        """Register a new user.

        Returns a user dict (without password_hash).
        Raises HTTP 409 if email already exists.
        """
        # Check for duplicate
        if self._get_user_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user_id = str(uuid.uuid4())
        password_hash = self._hash_password(password)

        with db.transaction():
            db.execute(
                """
                INSERT INTO users (id, email, password_hash, full_name)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, email, password_hash, full_name),
            )

        return {
            "id": user_id,
            "email": email,
            "full_name": full_name,
        }

    def login(self, email: str, password: str) -> str:
        """Verify credentials and return a JWT.

        Raises HTTP 401 on bad credentials or inactive account.
        """
        user = self._get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.get("is_active", 1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not self._verify_password(password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return self.create_jwt(user["id"], user["email"])

    def get_me(self, token: str) -> dict:
        """Decode JWT and return user info."""
        payload = self.verify_jwt(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = self._get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
        }
