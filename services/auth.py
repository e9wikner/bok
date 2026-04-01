"""Authentication service — validates credentials against environment variables."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

from config import settings


class AuthService:
    """Validates login against AUTH_USERNAME / AUTH_PASSWORD env vars and issues JWTs."""

    def create_jwt(self, username: str) -> str:
        """Encode a JWT valid for jwt_expire_days days."""
        expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
        payload = {
            "sub": username,
            "exp": expire,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def verify_jwt(self, token: str) -> dict:
        """Decode and validate a JWT. Raises HTTP 401 on any error."""
        try:
            return jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
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

    def login(self, username: str, password: str) -> str:
        """Verify credentials against env vars and return a JWT."""
        if username != settings.auth_username or password != settings.auth_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return self.create_jwt(username)

    def get_me(self, token: str) -> dict:
        """Decode JWT and return user info."""
        payload = self.verify_jwt(token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"username": username}
