"""Dependency injection for FastAPI."""

import hmac
import logging
import uuid
from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import Depends, Header, HTTPException, Query, Request, status

from config import settings
from domain.models import FiscalYear
from services.auth import AuthService
from services.ledger import LedgerService

logger = logging.getLogger(__name__)

#: The actor a request made with the review key acts as.
REVIEW_KEY_ACTOR = "review_key"

#: The one write the review key may make (docs/granskning.md §3).
REVIEW_KEY_WRITE_ROUTES = frozenset({("POST", "/api/v1/review/reports")})

#: Reads the review key may make: every authenticated GET and HEAD, except
#: these, which write on a read -- they create the default company
#: instruction document the first time it is read
#: (`AgentInstructionRepository.get_active` / `list_versions`). The reviewer
#: gets the company instructions without that write from
#: `GET /api/v1/review/instructions`.
REVIEW_KEY_READ_METHODS = frozenset({"GET", "HEAD"})
REVIEW_KEY_REFUSED_READS = frozenset(
    {
        "/api/v1/agent-instructions/accounting",
        "/api/v1/agent-instructions/accounting/versions",
        "/api/v1/agent-instructions/invoicing",
        "/api/v1/agent-instructions/invoicing/versions",
    }
)

KeyKind = Literal["review", "api"]


def _matches(token: str, key: str) -> bool:
    """Constant-time compare; an unset key never matches, not even an
    empty token."""
    if not key:
        return False
    return hmac.compare_digest(token.encode("utf-8"), key.encode("utf-8"))


def _key_kind(token: str) -> Optional[KeyKind]:
    """Which static key *token* is, if any.

    The review key is checked first: were it set to the same value as the
    API key by mistake, the key is read-only rather than the agent's. A
    temporary review key (`services/review_token.py`) a human copied from
    the Granskning view is a review key too, with the same rights.
    """
    if _matches(token, settings.review_api_key):
        return "review"
    from services.review_token import ReviewTokenService

    if ReviewTokenService.is_valid(token):
        return "review"
    if _matches(token, settings.api_key):
        return "api"
    return None


def _is_review_key(token: str) -> bool:
    """Whether the token is the read-only review key."""
    return _key_kind(token) == "review"


def _route_path(request: Request) -> str:
    """The matched route's path template (`/api/v1/vouchers/{voucher_id}`),
    or the request path if no route is in scope."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path


def review_key_allows(method: str, path: str) -> bool:
    """What the review key may do: read, and upload a review report."""
    method = method.upper()
    if (method, path) in REVIEW_KEY_WRITE_ROUTES:
        return True
    return method in REVIEW_KEY_READ_METHODS and path not in REVIEW_KEY_REFUSED_READS


def _review_key_read_only() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "The review key can only read",
            "code": "review_key_read_only",
            "details": (
                "the review key reads the books and uploads a review report "
                "(POST /api/v1/review/reports); nothing else"
            ),
        },
    )


async def verify_api_key(
    request: Request, authorization: Optional[str] = Header(None)
) -> str:
    """Verify the bearer: the API key, the review key or a JWT.

    The review key gets past only on `GET`/`HEAD` (bar the reads in
    `REVIEW_KEY_REFUSED_READS`) and on `POST /api/v1/review/reports`;
    anything else is `403 review_key_read_only`.
    """
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

    kind = _key_kind(token)
    if kind == "review":
        if not review_key_allows(request.method, _route_path(request)):
            raise _review_key_read_only()
        return token
    if kind == "api":
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
    """Get current actor (user) from API key. The review key is its own
    actor, never the agent's `"api"`."""
    if _is_review_key(api_key):
        return REVIEW_KEY_ACTOR
    return "api"


async def get_human_actor(api_key: str = Depends(verify_api_key)) -> str:
    """The logged-in human, for what only a human may do (opening a locked
    period or fiscal year).

    The agent authenticates with the static API key, the frontend with a
    JWT. A request made with the key is refused, so the agent cannot reach
    these routes through the HTTP API either.
    """
    kind = _key_kind(api_key)
    if kind is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Only a logged-in user can do this",
                "code": "human_only",
                "details": (
                    "the review key only reads; log in to the frontend"
                    if kind == "review"
                    else "the API key is the agent's; log in to the frontend"
                ),
            },
        )
    return _jwt_username(api_key)


def _jwt_username(token: str) -> str:
    username = AuthService().verify_jwt(token).get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


@dataclass(frozen=True)
class Caller:
    """Who is calling: the agent's API key (`human=False`, actor `"api"`),
    the review key (`human=False`, actor `"review_key"`) or a logged-in user
    (`human=True`, actor the username)."""

    actor: str
    human: bool


async def get_caller(api_key: str = Depends(verify_api_key)) -> Caller:
    """For a route that lets a human do on their own what the agent needs a
    decision for (undoing a link, underlag-ersatt)."""
    kind = _key_kind(api_key)
    if kind == "review":
        return Caller(actor=REVIEW_KEY_ACTOR, human=False)
    if kind == "api":
        return Caller(actor="api", human=False)
    return Caller(actor=_jwt_username(api_key), human=True)


async def get_principal(api_key: str = Depends(verify_api_key)) -> str:
    """Which credential made the request, for a row that records it:
    `"review_key"`, `"api_key"` or the logged-in user's name."""
    kind = _key_kind(api_key)
    if kind == "review":
        return REVIEW_KEY_ACTOR
    if kind == "api":
        return "api_key"
    return _jwt_username(api_key)


async def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> Optional[str]:
    """Read the optional Idempotency-Key header.

    Transition rule: the header is optional for now.
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


async def get_fiscal_year_filter(
    fiscal_year_id: Optional[str] = Query(
        None,
        description=(
            "Only what belongs to this fiscal year; omitted, every year. "
            "Unknown id is 404 fiscal_year_not_found."
        ),
    ),
) -> Optional[FiscalYear]:
    """`?fiscal_year_id=` for the lists the year selector narrows. An unknown
    id is 404 -- never a silent fallback to every year or to this year."""
    if fiscal_year_id is None:
        return None
    from repositories.period_repo import PeriodRepository

    fiscal_year = PeriodRepository.get_fiscal_year(fiscal_year_id)
    if fiscal_year is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Unknown fiscal year: {fiscal_year_id!r}",
                "code": "fiscal_year_not_found",
                "details": "fiscal_year_id must name an existing fiscal year.",
            },
        )
    return fiscal_year
