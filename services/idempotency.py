"""Idempotency for irreversible writes.

Domain logic only: the outcomes below are decisions, not HTTP statuses.
Mapping them onto responses belongs in `api/routes/`.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from repositories.idempotency_repo import IdempotencyRepository


@dataclass
class IdempotencyOutcome:
    """What the caller should do with a request that carries a key."""

    PROCEED = "proceed"
    REPLAY = "replay"
    MISMATCH = "mismatch"
    IN_FLIGHT = "in_flight"

    kind: str
    response_status: Optional[int] = None
    response_payload: Optional[Any] = None
    original_fingerprint: Optional[str] = None
    entity_id: Optional[str] = None


class IdempotencyService:
    """Reserve, replay and complete idempotency keys."""

    def __init__(self):
        self.keys = IdempotencyRepository

    def fingerprint(self, body: dict) -> str:
        """sha256 over the canonicalised request body.

        Sorted keys, no whitespace, UTF-8. The actor is not part of it: the
        same intent is the same intent however the caller happens to be named.
        """
        canonical = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def begin(
        self,
        key: str,
        endpoint: str,
        body: dict,
        actor: str,
    ) -> IdempotencyOutcome:
        """Decide what happens to a request carrying this key (§6, step 2)."""
        fingerprint = self.fingerprint(body)
        existing = self.keys.get(key, endpoint)

        if existing is None:
            if self.keys.reserve(key, endpoint, fingerprint, actor):
                return IdempotencyOutcome(kind=IdempotencyOutcome.PROCEED)
            # Lost the race to a concurrent request holding the same key.
            existing = self.keys.get(key, endpoint)
            if existing is None:
                return IdempotencyOutcome(kind=IdempotencyOutcome.IN_FLIGHT)

        if existing.state == "completed":
            if existing.request_fingerprint != fingerprint:
                return IdempotencyOutcome(
                    kind=IdempotencyOutcome.MISMATCH,
                    original_fingerprint=existing.request_fingerprint,
                )
            return IdempotencyOutcome(
                kind=IdempotencyOutcome.REPLAY,
                response_status=existing.response_status,
                response_payload=json.loads(existing.response_body or "null"),
                entity_id=existing.entity_id,
            )

        return IdempotencyOutcome(kind=IdempotencyOutcome.IN_FLIGHT)

    def complete(
        self,
        key: str,
        endpoint: str,
        response_status: int,
        response_payload: Any,
        entity_type: str,
        entity_id: str,
        _commit: bool = True,
    ) -> None:
        """Store the outcome. Call inside the transaction that does the write."""
        self.keys.complete(
            key=key,
            endpoint=endpoint,
            response_status=response_status,
            response_body=json.dumps(response_payload, ensure_ascii=False),
            entity_type=entity_type,
            entity_id=entity_id,
            _commit=_commit,
        )

    def release(self, key: str, endpoint: str) -> None:
        """Drop a reservation whose work failed, so a retry starts clean."""
        self.keys.release(key, endpoint)
