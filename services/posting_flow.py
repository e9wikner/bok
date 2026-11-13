"""Posting a draft and posting a correction, each in one transaction.

(The agent's own create-and-post path is `services/voucher_posting.py`.)

`post` is `POST /vouchers/{id}/post`: the posting, a thread draft's hooks
(`DraftService.on_posting`: its row goes `posted`, its underlag and bank
transactions are linked) and whatever the caller records with it, all
committed together or not at all. Anything raised -- `source_already_booked`
included -- rolls the whole posting back, so no number is taken. The
receipt post and its publication run after the commit (`after_posting`).

`post_correction` is `POST /vouchers/{id}/correct`: the B-series voucher, its
correction history and what the caller records, likewise in one transaction.

`record` is the route's idempotency row. It runs inside the transaction so
that a committed posting always has its key, and a key never outlives a
rolled-back posting.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from db.database import db
from domain.models import Voucher
from domain.validation import ValidationError
from services.draft_service import DraftService
from services.ledger import LedgerService, run_statement_match_after_posting

logger = logging.getLogger(__name__)

Record = Callable[[Voucher], None]


def post(voucher_id: str, *, actor: str, record: Record) -> Voucher:
    """Post *voucher_id*. A `ValidationError` is raised after the rollback,
    once the thread has been told (`after_failed_posting`)."""
    ledger = LedgerService()
    try:
        with db.transaction():
            voucher = ledger.post_voucher(voucher_id, actor=actor, _commit=False)
            DraftService().on_posting(voucher, actor=actor, _commit=False)
            record(voucher)
    except ValidationError as e:
        if e.code == "already_posted":
            # Posted by an earlier request whose receipt may have failed.
            after_posting(voucher_id, actor)
        else:
            after_failed_posting(voucher_id, e, actor)
        raise

    after_posting(voucher_id, actor)
    return voucher


def post_correction(
    voucher_id: str,
    *,
    corrected_rows: List[Dict[str, Any]],
    reason: Optional[str],
    actor: str,
    record: Record,
) -> Voucher:
    """Create and post the B-series correction of *voucher_id*."""
    with db.transaction():
        correction = LedgerService().create_posted_correction(
            original_voucher_id=voucher_id,
            corrected_rows=corrected_rows,
            reason=reason,
            actor=actor,
            _commit=False,
        )
        record(correction)
    return correction


def after_posting(voucher_id: str, actor: str) -> None:
    """Steps 4-5 of posting a thread draft: the `receipt` post and its
    publication. A no-op for any other voucher, and for one whose receipt is
    already written, so it is called after every posting and on every replay
    of one.

    Best-effort by design: the posting is committed, and a failure in the
    thread layer must not turn a successful posting into an error. A replay
    with the same key resumes it.
    """
    try:
        voucher = LedgerService().vouchers.get(voucher_id)
        if voucher is not None and voucher.status.value == "posted":
            DraftService().on_posted(voucher, actor=actor)
    except Exception:
        logger.exception("Receipt for posted voucher %s failed", voucher_id)
    run_statement_match_after_posting()


def after_failed_posting(voucher_id: str, error: ValidationError, actor: str) -> None:
    """A failed posting of a thread draft: one `error` post per draft and
    code, in its own transaction, after the posting's rollback. A no-op for
    any other voucher.

    Best-effort, like `after_posting`: the HTTP answer is the refusal, and a
    failure in the thread layer must not change it. Network errors and 5xx
    never reach here -- the server does not know about the first, and the
    second is not a refusal.
    """
    try:
        DraftService().on_posting_failed(voucher_id, error, actor=actor)
    except Exception:
        logger.exception("Error post for voucher %s failed", voucher_id)
