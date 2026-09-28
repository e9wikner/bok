"""`tolka_underlag`'s orchestration (SPEC-underlagstolkning.md §6, §7).

`InterpretationService.interpret` takes what the model read from an
underlag, runs the checks (§6.3-§6.4), matches it against the ledger
(§7), saves one `intake_interpretations` row and answers in §6.5's form.
Read-only against the books: nothing here writes to `vouchers`,
`voucher_intake_sources`, `attachments` or `intake_sources` (testfall 33).

The pure logic -- checks, confidence, ranking, `expected`, hypothesis --
is `services/interpretation.py`, which reads no file and has no database.
This module is the part that does: it fetches the source, reads its text
layer, asks the repositories for candidates and saves the row. Still no
SQL of its own (AGENTS.md's layering; spec §4).
"""

from datetime import date
from typing import Any, Dict, Optional, Protocol

from domain.interpretation import Interpretation
from domain.types import IntakeStatus
from domain.validation import ValidationError
from repositories.intake_repo import IntakeRepository
from repositories.interpretation_repo import InterpretationRepository
from repositories.voucher_repo import VoucherRepository
from services.agent_documents import extract_pdf_text
from services.intake import IntakeError, IntakeService
from services.interpretation import (
    DATE_WINDOW_DAYS_AFTER,
    DATE_WINDOW_DAYS_BEFORE,
    MatchRead,
    amount_window_ore,
    confidence,
    expected,
    match_document,
    run_checks,
)

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


class InterpretationService:
    """Interpret one underlag: check, match, save, answer."""

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
        interpretation = InterpretationRepository.insert(
            Interpretation(
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
                actor=actor,
                agent_run_id=agent_run_id,
                thread_id=thread_id,
            )
        )
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

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _source(source_id: str):
        source = IntakeRepository.get_source(source_id)
        if source is None:
            raise IntakeError(
                "source_not_found", "Intake source not found", f"source_id={source_id}"
            )
        if source.status == IntakeStatus.DELETED:
            raise IntakeError(
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
