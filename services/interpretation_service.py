"""`tolka_underlag`'s orchestration (SPEC-underlagstolkning.md §6, §7).

`InterpretationService.interpret` takes what the model read from an
underlag, runs the checks (§6.3-§6.4), matches it against the ledger
(§7), saves one `intake_interpretations` row and answers in §6.5's form.
`InterpretationService.latest` is the read path behind
`GET /api/v1/intake/{id}/interpretation` (§8); `interpret` is also behind
its `POST`, for a session without the tool (§12.6 f).
Read-only against the books: nothing here writes to `vouchers`,
`voucher_intake_sources`, `attachments` or `intake_sources` (testfall 33).
In a thread it also writes the comparison post(s) of
SPEC-flode-underlag.md §9.1 -- a post in the thread, not the books.

The pure logic -- checks, confidence, ranking, `expected`, hypothesis --
is `services/interpretation.py`, which reads no file and has no database.
This module is the part that does: it fetches the source, reads its text
layer, asks the repositories for candidates and saves the row. Still no
SQL of its own (AGENTS.md's layering; spec §4).
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Protocol

from db.database import db
from domain.interpretation import Interpretation
from domain.models import ThreadPost
from domain.types import IntakeStatus
from domain.validation import ValidationError
from repositories.intake_repo import IntakeRepository
from repositories.interpretation_repo import InterpretationRepository
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.agent_documents import extract_pdf_text
from services.intake import IntakeConflictError, IntakeError, IntakeService
from services.interpretation import (
    DATE_WINDOW_DAYS_AFTER,
    DATE_WINDOW_DAYS_BEFORE,
    MatchRead,
    amount_window_ore,
    comparison_body,
    comparison_parts,
    confidence,
    expected,
    match_document,
    run_checks,
)

logger = logging.getLogger(__name__)

_PDF_MIME_TYPE = "application/pdf"


class InterpretArgs(MatchRead, Protocol):
    """`TolkaUnderlagArgs` as the service sees it: the read plus the source
    and the voucher the agent expected. A protocol so the service does not
    import the tool module (`services/agent_tools.py` imports this one,
    deferred, in its handler)."""

    @property
    def source_id(self) -> str: ...

    @property
    def expected_voucher_id(self) -> Optional[str]: ...


class InterpretationNotFoundError(IntakeError):
    """§8's two 404s: `source_not_found` and `interpretation_not_found`."""


class InterpretationService:
    """Interpret one underlag: check, match, save, answer -- and read back
    the latest interpretation (§8)."""

    def interpret(
        self,
        args: InterpretArgs,
        *,
        actor: str,
        thread_id: Optional[str],
        agent_run_id: Optional[str],
        today: Optional[date] = None,
    ) -> Dict[str, Any]:
        """§6.1-§6.5. Raises `IntakeError` `source_not_found` /
        `source_deleted` (§6.3's hard errors) and `ValidationError`
        `expected_voucher_not_found` when `expected_voucher_id` names no
        posted voucher; nothing is saved then. Every other finding is an
        answer, not an error."""
        source = self._source(args.source_id)
        text_layer = self._text_layer(source)
        expected_row = None
        if args.expected_voucher_id is not None:
            expected_row = VoucherRepository.candidate_row(args.expected_voucher_id)
            if expected_row is None:
                raise ValidationError(
                    code="expected_voucher_not_found",
                    message="expected_voucher_id names no posted voucher",
                    details=f"expected_voucher_id={args.expected_voucher_id}",
                )

        checks = run_checks(
            args, text_layer_text=text_layer, today=today or date.today()
        )
        # §7.1: another currency is not matched, so the ledger is not asked.
        rows = (
            VoucherRepository.match_candidates(
                args.document_date,
                args.total_ore,
                date_window=(DATE_WINDOW_DAYS_BEFORE, DATE_WINDOW_DAYS_AFTER),
                amount_window_ore=amount_window_ore(args.total_ore),
            )
            if args.currency == "SEK"
            else []
        )
        matching = match_document(args, rows)
        # `None` in another currency (§7.1), even with `expected_voucher_id`.
        compared = expected(args, expected_row, matching) if expected_row else None

        read = _read(args)
        row = Interpretation(
            intake_source_id=source.id,
            vendor=args.vendor,
            document_date=args.document_date,
            currency=args.currency,
            total_ore=args.total_ore,
            vat_ore=args.vat_ore,
            lines=read["lines"],
            checks=checks.to_dict(),
            confidence=confidence(checks),
            match=matching.match,
            candidates=matching.candidates,
            expected_voucher_id=args.expected_voucher_id,
            expected=compared,
            actor=actor,
            agent_run_id=agent_run_id,
            thread_id=thread_id,
        )
        # SPEC-flode-underlag.md §9.1 (D6): in a thread, the comparison is
        # the server's post, in the same transaction as the interpretation
        # it shows, and published after the commit.
        posts: List[ThreadPost] = []
        with db.transaction():
            interpretation = InterpretationRepository.insert(row, _commit=False)
            if thread_id is not None:
                for part in comparison_parts(matching.match, compared):
                    posts.append(
                        ThreadRepository.add_post(
                            thread_id=thread_id,
                            post_type="receipt",
                            actor=actor,
                            body=comparison_body(
                                part,
                                vendor=args.vendor,
                                document_date=args.document_date,
                            ),
                            _commit=False,
                        )
                    )
        _publish(posts)
        return {
            "interpretation_id": interpretation.id,
            "source_id": source.id,
            "read": read,
            "checks": interpretation.checks,
            "confidence": interpretation.confidence,
            "match": matching.match.to_dict() if matching.match else None,
            "candidates": [c.to_dict() for c in matching.candidates],
            "expected": compared.to_dict() if compared else None,
        }

    def latest(self, source_id: str) -> Dict[str, Any]:
        """§8: the latest interpretation of *source_id*, in §6.5's form plus
        `created_at`, `actor`, `thread_id`, `superseded_count`,
        `source_status` and `match.still_open`. Reads only -- `still_open` is
        derived here, now, and the stored snapshot is returned as stored.

        `expected` is the comparison stored with the row (`expected_json`,
        migration 031), never recomputed against today's ledger, and
        `expected_voucher_id` names the voucher the agent expected. `None`
        for rows from before 031. It carries no `still_open`: §8 adds that
        to `match` only.

        A soft-deleted source is still read, with `source_status =
        "deleted"` (§12.6 h): the interpretation is part of the trail and is
        append-only. Raises
        `InterpretationNotFoundError` `source_not_found` /
        `interpretation_not_found`."""
        source = IntakeRepository.get_source(source_id)
        if source is None:
            raise InterpretationNotFoundError(
                "source_not_found", "Intake source not found", f"source_id={source_id}"
            )
        interpretation = InterpretationRepository.latest_for_source(source_id)
        if interpretation is None:
            raise InterpretationNotFoundError(
                "interpretation_not_found",
                "Intake source has not been interpreted",
                f"source_id={source_id}",
            )
        match = None
        if interpretation.match is not None:
            match = {
                **interpretation.match.to_dict(),
                "still_open": VoucherRepository.match_still_open(
                    interpretation.match.voucher_id, source_id
                ),
            }
        return {
            "interpretation_id": interpretation.id,
            "source_id": interpretation.intake_source_id,
            "read": {
                "vendor": interpretation.vendor,
                "document_date": (
                    interpretation.document_date.isoformat()
                    if interpretation.document_date
                    else None
                ),
                "currency": interpretation.currency,
                "total_ore": interpretation.total_ore,
                "vat_ore": interpretation.vat_ore,
                "lines": interpretation.lines,
            },
            "checks": interpretation.checks,
            "confidence": interpretation.confidence,
            "match": match,
            "candidates": [c.to_dict() for c in interpretation.candidates],
            "expected": (
                interpretation.expected.to_dict() if interpretation.expected else None
            ),
            "expected_voucher_id": interpretation.expected_voucher_id,
            "created_at": interpretation.created_at.isoformat(),
            "actor": interpretation.actor,
            "thread_id": interpretation.thread_id,
            "superseded_count": InterpretationRepository.count_for_source(source_id)
            - 1,
            "source_status": source.status.value,
        }

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _source(source_id: str):
        """§6.3's hard errors, as `IntakeError` subclasses so the POST route
        (§8, U15) maps them like the GET: `source_not_found` is the GET's
        404, `source_deleted` a state conflict (409), as the intake routes
        treat a processed source. The tool sees only the code."""
        source = IntakeRepository.get_source(source_id)
        if source is None:
            raise InterpretationNotFoundError(
                "source_not_found", "Intake source not found", f"source_id={source_id}"
            )
        if source.status == IntakeStatus.DELETED:
            raise IntakeConflictError(
                "source_deleted", "Intake source is deleted", f"source_id={source_id}"
            )
        return source

    @staticmethod
    def _text_layer(source) -> Optional[str]:
        """The server's own reading of the file (§6.3 `text_layer`): the
        PDF's text layer through `extract_pdf_text`, `""` for a scanned PDF,
        `None` for anything that is not a PDF (an image has none)."""
        if source.mime_type != _PDF_MIME_TYPE:
            return None
        intake = IntakeService()
        return extract_pdf_text(intake.resolve_source_file(source).read_bytes())


def _publish(posts: List[ThreadPost]) -> None:
    """`message.completed` for each comparison post, after the commit --
    the same event `DraftService.on_posted` sends for its receipt. A post
    without `run_id`, so the turn's own in-flight message is left alone.
    Never fatal: the posts are stored and the next read shows them."""
    if not posts:
        return
    from services.thread_stream import (
        EVENT_MESSAGE_COMPLETED,
        get_broker,
        post_event_payload,
    )

    for post in posts:
        try:
            get_broker().publish(
                post.thread_id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
            )
        except Exception:
            logger.exception("Comparison post %s was not published", post.id)


def _read(args: MatchRead) -> Dict[str, Any]:
    """§6.5's `read`: what the model sent, field for field and in §6.2's
    order, as JSON -- nothing added, nothing normalised. `source_id` and
    `expected_voucher_id` are not a reading of the document."""
    return {
        "vendor": args.vendor,
        "document_date": (
            args.document_date.isoformat() if args.document_date else None
        ),
        "currency": args.currency,
        "total_ore": args.total_ore,
        "vat_ore": args.vat_ore,
        "lines": [
            {
                "text": line.text,
                "amount_ore": line.amount_ore,
                "vat_rate": line.vat_rate,
            }
            for line in args.lines
        ],
    }
