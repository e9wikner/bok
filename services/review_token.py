"""Temporary review keys (docs/granskning.md §3, migration 056).

A logged-in human presses "Kopiera uppdrag till agent" in the Granskning
view. `issue` makes a random key that lives `review_token_ttl_minutes`
(default 60), stores only its sha256, and returns the key once together
with a ready prompt the human pastes into any agent.

The key is a review key: `api/deps.py::_key_kind` calls it `"review"`, so
it reads and uploads a review report and nothing else, exactly like the
static `BOKFOERING_REVIEW_KEY`. Only a human can mint or revoke one; the
routes take `get_human_actor`.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import List

from config import settings
from db.database import db
from domain.types import AuditAction
from repositories.audit_repo import AuditRepository
from repositories.review_token_repository import ReviewToken, ReviewTokenRepository

#: Every temporary key starts with this, so `_key_kind` looks one up only
#: when it can be one.
TOKEN_PREFIX = "bokrev_"
ENTRYPOINT_PATH = "/api/v1/review/entrypoint"


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewTokenError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def build_prompt(
    *,
    entrypoint_url: str,
    fiscal_year_id: str,
    year_label: str,
    token: str,
    expires_at: datetime,
) -> str:
    """The text the human pastes into an agent. Everything the agent needs
    is here; the entrypoint and the instruction say the rest."""
    base = entrypoint_url[: -len(ENTRYPOINT_PATH)]
    until = expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Granska räkenskapsåret {year_label} (fiscal_year_id {fiscal_year_id}) "
        "i bokföringssystemet Bok och ladda upp en granskningsrapport.\n"
        "\n"
        f"Börja här (ingen nyckel behövs): GET {entrypoint_url}\n"
        "Skicka sedan varje anrop med headern:\n"
        f"Authorization: Bearer {token}\n"
        "\n"
        f"Hämta instruktionen med GET {base}/api/v1/review/instructions"
        f"?fiscal_year_id={fiscal_year_id} och följ den. Den beskriver var "
        "böckerna finns och hur rapporten laddas upp "
        f"(POST {base}/api/v1/review/reports).\n"
        "\n"
        "Nyckeln är tillfällig och kan bara läsa böckerna och ladda upp "
        f"rapporten. Den slutar gälla {until}. Ändra ingenting i böckerna."
    )


class ReviewTokenService:
    def issue(
        self, *, created_by: str, fiscal_year_id: str, entrypoint_url: str
    ) -> dict:
        from services.review import ReviewError, ReviewService

        entrypoint_url = entrypoint_url.strip().rstrip("/")
        if not entrypoint_url.endswith(
            ENTRYPOINT_PATH
        ) or not entrypoint_url.startswith(("http://", "https://")):
            raise ReviewTokenError(
                "invalid_entrypoint_url",
                f"entrypoint_url must be an http(s) URL ending in {ENTRYPOINT_PATH}",
            )
        try:
            fy = ReviewService.fiscal_year(fiscal_year_id)
        except ReviewError as exc:
            raise ReviewTokenError(exc.code, exc.message, exc.status) from exc

        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        now = _now()
        expires_at = now + timedelta(minutes=settings.review_token_ttl_minutes)
        try:
            row = ReviewTokenRepository.create(
                token_sha256=_sha256(token),
                fiscal_year_id=fy.id,
                created_by=created_by,
                created_at=now,
                expires_at=expires_at,
                _commit=False,
            )
            AuditRepository.log(
                "review_token",
                row.id,
                AuditAction.REVIEW_TOKEN_ISSUED.value,
                actor=created_by,
                payload={"fiscal_year_id": fy.id, "expires_at": row.expires_at},
                _commit=False,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        label = (
            str(fy.start_date.year)
            if fy.start_date.year == fy.end_date.year
            else f"{fy.start_date.isoformat()}–{fy.end_date.isoformat()}"
        )
        return {
            "id": row.id,
            "token": token,
            "fiscal_year_id": fy.id,
            "expires_at": row.expires_at,
            "prompt": build_prompt(
                entrypoint_url=entrypoint_url,
                fiscal_year_id=fy.id,
                year_label=label,
                token=token,
                expires_at=expires_at,
            ),
        }

    @staticmethod
    def is_valid(token: str) -> bool:
        """Whether *token* is an unexpired, unrevoked temporary review key."""
        if not token.startswith(TOKEN_PREFIX):
            return False
        return ReviewTokenRepository.find_valid(_sha256(token), _now()) is not None

    def revoke(self, token_id: str, *, revoked_by: str) -> ReviewToken:
        token = ReviewTokenRepository.get(token_id)
        if token is None:
            raise ReviewTokenError("review_token_not_found", "No such review key", 404)
        if token.revoked_at is not None:
            return token
        try:
            ReviewTokenRepository.revoke(token_id, revoked_by=revoked_by, _commit=False)
            AuditRepository.log(
                "review_token",
                token_id,
                AuditAction.REVIEW_TOKEN_REVOKED.value,
                actor=revoked_by,
                _commit=False,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        revoked = ReviewTokenRepository.get(token_id)
        assert revoked is not None
        return revoked

    @staticmethod
    def list_active() -> List[dict]:
        return [token_json(t) for t in ReviewTokenRepository.list_active(_now())]


def token_json(t: ReviewToken) -> dict:
    """A key's record. Never the key itself: that is shown once, at issue."""
    return {
        "id": t.id,
        "fiscal_year_id": t.fiscal_year_id,
        "created_by": t.created_by,
        "created_at": t.created_at,
        "expires_at": t.expires_at,
        "revoked_at": t.revoked_at,
    }
