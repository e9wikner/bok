"""Authentication service — validates credentials against environment variables."""

import hmac
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

from config import settings

# Failed-login throttle. There is one configured user and one API process, so
# a single in-memory counter is enough: after MAX_FAILED_LOGINS failures within
# LOGIN_LOCKOUT_SECONDS, every login is refused with 429 until the window ends.
MAX_FAILED_LOGINS = 5
LOGIN_LOCKOUT_SECONDS = 60

_failed_lock = threading.Lock()
_failed_count = 0
_failed_window_start = 0.0


def reset_login_throttle() -> None:
    """Clear the failed-login counter (used by tests)."""
    global _failed_count, _failed_window_start
    with _failed_lock:
        _failed_count = 0
        _failed_window_start = 0.0


def _check_login_throttle() -> None:
    """Raise HTTP 429 while too many recent logins have failed."""
    global _failed_count
    with _failed_lock:
        if _failed_count == 0:
            return
        elapsed = time.monotonic() - _failed_window_start
        if elapsed >= LOGIN_LOCKOUT_SECONDS:
            _failed_count = 0
            return
        if _failed_count >= MAX_FAILED_LOGINS:
            retry_after = max(1, math.ceil(LOGIN_LOCKOUT_SECONDS - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts",
                headers={"Retry-After": str(retry_after)},
            )


def _record_failed_login() -> None:
    """Count one failed login.

    The window starts at the first failure; the failure that reaches the limit
    restarts it, so the lockout lasts a full LOGIN_LOCKOUT_SECONDS.
    """
    global _failed_count, _failed_window_start
    with _failed_lock:
        _failed_count += 1
        if _failed_count == 1 or _failed_count == MAX_FAILED_LOGINS:
            _failed_window_start = time.monotonic()


class AuthService:
    """Validates login against AUTH_USERNAME / AUTH_PASSWORD env vars and issues JWTs."""

    def create_jwt(self, username: str) -> str:
        """Encode a JWT valid for jwt_expire_days days."""
        expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
        payload = {
            "sub": username,
            "exp": expire,
        }
        return jwt.encode(
            payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )

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
        # Checked before the credentials, so a correct password is refused
        # too while the lockout lasts.
        _check_login_throttle()
        # Constant-time comparisons; `&` evaluates both, so a wrong username
        # takes as long as a wrong password.
        if not (
            hmac.compare_digest(
                username.encode("utf-8"), settings.auth_username.encode("utf-8")
            )
            & hmac.compare_digest(
                password.encode("utf-8"), settings.auth_password.encode("utf-8")
            )
        ):
            _record_failed_login()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        reset_login_throttle()
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
