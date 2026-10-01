"""`foresla_rakenskapsar`: a new fiscal year proposed as a decision card.

An underlag dated outside every fiscal year cannot be booked, and the agent
may not date it into another year to make it fit
(`FiscalYearService.check_underlag_dates`). Instead it proposes the year: a
decision card in the thread with two options, "Skapa räkenskapsåret" and
"Inte nu". The dates are the server's (`FiscalYearService.suggest`, or the
agent's own checked by `validate_new`) and are stored with the card
(migration 041), so the year created is exactly the one the human saw.

Both entry points reach it. In a thread turn the card goes in that thread. The
intake pass (a dropzone file) has no thread, so the card goes in the current
fiscal year's Verifikationer thread, and the file waits: it is out of the
pass's queue until the card is answered, so it neither ends in `_Problem/` nor
costs a reading every pass.

The press (`on_decision_answered`, called by `POST /decisions/{id}/answer`
after the answer has committed):

- the create option -> the year and its periods are created, a receipt is
  written in the thread, and the waiting underlag are back in the queue;
- any other option -> declined; a waiting dropzone underlag is recorded as
  failed, with the reason, so it shows in the decision queue;
- free text -> nothing yet. The agent's turn reads the answer and, on a yes,
  proposes again, which supersedes this card with a new one.

Layering (AGENTS.md): no SQL here, no HTTP.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from config import settings
from db.database import db
from domain.models import Decision, FiscalYearProposal, Thread, ThreadPost
from domain.types import IntakeStatus, ThreadViewKey
from domain.validation import ValidationError
from repositories.decision_repo import DecisionRepository
from repositories.fiscal_year_proposal_repo import FiscalYearProposalRepository
from repositories.intake_repo import IntakeRepository
from repositories.thread_repo import ThreadRepository
from services.fiscal_years import FiscalYearService

logger = logging.getLogger(__name__)

#: The view whose thread gets the card when the intake pass raises it.
VOUCHERS_VIEW = ThreadViewKey.BOCKER_VERIFIKATIONER.value

CREATE_OPTION_TITLE = "Skapa räkenskapsåret"

#: Underlag not yet booked, whose date can still keep them out of the books.
_UNBOOKED_STATUSES = (
    IntakeStatus.PENDING.value,
    IntakeStatus.FAILED.value,
    IntakeStatus.NEEDS_ATTENTION.value,
)
DECLINE_OPTION_TITLE = "Inte nu"


def _span(start: date, end: date) -> str:
    return f"{start.isoformat()} – {end.isoformat()}"


class FiscalYearProposalService:
    def __init__(self) -> None:
        self.fiscal_years = FiscalYearService()

    # -- the tool ----------------------------------------------------------

    def propose(
        self,
        thread: Optional[Thread],
        *,
        document_date: date,
        source_ids: Sequence[str] = (),
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        actor: str,
    ) -> Dict[str, Any]:
        """Raise the card, or join the one already pending for the year.

        `thread` is the turn's; `None` is the intake pass, and the card goes
        in the Verifikationer thread. A pending card whose decision is still
        open gets the new underlag and is answered once, for all of them; one
        answered in free text is superseded by a new card carrying them over.
        """
        sources = self._sources(source_ids)
        start, end = self._dates(document_date, start_date, end_date)
        target = thread or self._vouchers_thread()

        existing = FiscalYearProposalRepository.find_pending(start, end)
        carried: List[str] = []
        if existing is not None:
            decision = DecisionRepository.get(existing.decision_id)
            if decision is not None and decision.status == "open":
                FiscalYearProposalRepository.add_sources(
                    existing.id, [s.id for s in sources]
                )
                proposal = FiscalYearProposalRepository.get(existing.id)
                assert proposal is not None
                return self._result(proposal, existing_card=True)
            FiscalYearProposalRepository.resolve(existing.id, "superseded", actor=actor)
            carried = existing.source_ids

        seq_before = ThreadRepository.last_seq(target.id)
        decision = self._raise_card(target, start, end, document_date, sources, actor)
        try:
            with db.transaction():
                proposal = FiscalYearProposalRepository.create(
                    decision_id=decision.id,
                    create_option_id=decision.options[0].id,
                    thread_id=target.id,
                    start_date=start,
                    end_date=end,
                    document_date=document_date,
                    created_by=actor,
                    _commit=False,
                )
                FiscalYearProposalRepository.add_sources(
                    proposal.id,
                    list(dict.fromkeys(carried + [s.id for s in sources])),
                    _commit=False,
                )
        except Exception:
            # The card and its row are two transactions (DecisionService owns
            # its own): a card without its row could be pressed to no effect,
            # so it leaves the queue.
            from services.decision_service import DecisionService

            DecisionService().supersede(decision.id)
            raise

        if thread is None:
            # Outside a turn nothing else tells a watching client.
            _publish(ThreadRepository.list_posts(target.id, since=seq_before))
        stored = FiscalYearProposalRepository.get(proposal.id)
        assert stored is not None
        return self._result(stored, existing_card=False)

    # -- the press ---------------------------------------------------------

    def on_decision_answered(
        self, decision: Decision, *, actor: str
    ) -> Optional[ThreadPost]:
        """What the answer to a fiscal-year card does; `None` for any other
        decision. Returns the post it wrote, already published."""
        proposal = FiscalYearProposalRepository.get_by_decision(decision.id)
        if proposal is None or proposal.status != "pending":
            return None
        if decision.answer_option_id is None:
            return None  # free text: the agent's turn takes it from here
        if decision.answer_option_id == proposal.create_option_id:
            return self._create(proposal, actor)
        self._decline(proposal, actor)
        return None

    def _create(self, proposal: FiscalYearProposal, actor: str) -> ThreadPost:
        try:
            with db.transaction():
                fiscal_year = self.fiscal_years.create(
                    proposal.start_date, proposal.end_date, actor=actor, _commit=False
                )
                FiscalYearProposalRepository.resolve(
                    proposal.id,
                    "created",
                    actor=actor,
                    fiscal_year_id=fiscal_year.id,
                    _commit=False,
                )
                post = ThreadRepository.add_post(
                    thread_id=proposal.thread_id,
                    post_type="receipt",
                    actor=actor,
                    body=_receipt_body(proposal),
                    _commit=False,
                )
        except ValidationError as exc:
            # The books changed since the card was raised (a year created by
            # hand, an SIE4 import). The underlag go back in the queue, where
            # the agent sees the books as they are now.
            FiscalYearProposalRepository.resolve(proposal.id, "superseded", actor=actor)
            post = ThreadRepository.add_post(
                thread_id=proposal.thread_id,
                post_type="error",
                actor=actor,
                body={
                    "cause": (
                        f"Räkenskapsåret {_span(proposal.start_date, proposal.end_date)}"
                        f" kunde inte skapas: {exc.message}."
                    ),
                    "consequence": "Inget räkenskapsår skapades och inget bokfördes.",
                    "retry_draft_id": None,
                },
            )
            _publish([post])
            self._wake_pass(proposal)
            return post

        _publish([post])
        self._wake_pass(proposal)
        return post

    def _decline(self, proposal: FiscalYearProposal, actor: str) -> None:
        from services.intake import IntakeService

        FiscalYearProposalRepository.resolve(proposal.id, "declined", actor=actor)
        span = _span(proposal.start_date, proposal.end_date)
        intake = IntakeService()
        for source_id in proposal.source_ids:
            source = IntakeRepository.get_source(source_id)
            if source is None or source.status != IntakeStatus.PENDING:
                continue
            if IntakeRepository.is_in_a_thread(source_id):
                continue  # the thread's turn answers for its own files
            intake.record_failed(
                source_id,
                summary="Räkenskapsår saknas",
                error_detail=(
                    f"Underlaget är daterat utanför alla räkenskapsår. "
                    f"Räkenskapsåret {span} skapades inte: användaren valde "
                    f"att inte skapa det."
                ),
                actor=actor,
            )

    # -- reading -----------------------------------------------------------

    @staticmethod
    def source_date_warning(source_id: str) -> Optional[Dict[str, Any]]:
        """Why an unbooked underlag's date keeps it out of the books, or
        `None`: `waiting_for_fiscal_year` (a card is waiting for an answer)
        or `outside_fiscal_years` (its interpreted date is in no year, and
        nothing has been proposed)."""
        proposal = FiscalYearProposalRepository.pending_for_source(source_id)
        if proposal is not None:
            span = _span(proposal.start_date, proposal.end_date)
            return {
                "code": "waiting_for_fiscal_year",
                "message": (
                    f"Väntar på räkenskapsår {span}: svara på frågan i "
                    "Verifikationer."
                ),
                "decision_id": proposal.decision_id,
                "fiscal_year": {
                    "start_date": proposal.start_date.isoformat(),
                    "end_date": proposal.end_date.isoformat(),
                },
            }
        from repositories.interpretation_repo import InterpretationRepository

        interpretation = InterpretationRepository.latest_for_source(source_id)
        if interpretation is None or interpretation.document_date is None:
            return None
        if FiscalYearService.containing(interpretation.document_date) is not None:
            return None
        return {
            "code": "outside_fiscal_years",
            "message": (
                f"Daterat {interpretation.document_date.isoformat()}, utanför "
                "alla räkenskapsår. Det kan inte bokföras förrän året finns."
            ),
            "document_date": interpretation.document_date.isoformat(),
        }

    def date_warnings(self) -> Dict[str, Any]:
        """Underlag and statement transactions the books cannot hold because
        of their date -- for the dropzone status, so they never just go
        quiet."""
        from repositories.bank_input_repo import BankInputRepository

        underlag = []
        for source in IntakeRepository.list_by_statuses(_UNBOOKED_STATUSES):
            warning = self.source_date_warning(source.id)
            if warning is not None:
                underlag.append(
                    {
                        "source_id": source.id,
                        "original_filename": source.original_filename,
                        "status": source.status.value,
                        **warning,
                    }
                )
        return {
            "underlag": underlag,
            "bank_transactions_outside_fiscal_years": (
                BankInputRepository.count_transactions_outside_fiscal_years()
            ),
        }

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _sources(source_ids: Sequence[str]) -> list:
        sources = []
        for source_id in dict.fromkeys(source_ids):
            source = IntakeRepository.get_source(source_id)
            if source is None or source.status == IntakeStatus.DELETED:
                raise ValidationError(
                    "source_not_found",
                    f"No intake source {source_id}",
                    f"source_id={source_id}",
                )
            sources.append(source)
        return sources

    def _dates(
        self,
        document_date: date,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> tuple:
        if (start_date is None) != (end_date is None):
            raise ValidationError(
                "invalid_tool_arguments",
                "Give both start_date and end_date, or neither",
                f"start_date={start_date}, end_date={end_date}",
            )
        if start_date is None or end_date is None:
            return self.fiscal_years.suggest(document_date)
        existing = self.fiscal_years.containing(document_date)
        if existing is not None:
            # Same refusal as `suggest`'s, with the year in the payload.
            self.fiscal_years.suggest(document_date)
        self.fiscal_years.validate_new(start_date, end_date)
        if not start_date <= document_date <= end_date:
            raise ValidationError(
                "document_date_outside_proposal",
                f"{document_date} is not in {start_date} - {end_date}",
                f"document_date={document_date}",
            )
        return start_date, end_date

    @staticmethod
    def _vouchers_thread() -> Thread:
        current = FiscalYearService.current()
        if current is None:
            raise ValidationError(
                "no_fiscal_year",
                "The books have no fiscal year to hang a thread off; the "
                "first one is created in settings",
            )
        return ThreadRepository.get_or_create(
            view_key=VOUCHERS_VIEW,
            fiscal_year_id=current.id,
            model=settings.llm_default_model,
        )

    @staticmethod
    def _raise_card(
        thread: Thread,
        start: date,
        end: date,
        document_date: date,
        sources: list,
        actor: str,
    ) -> Decision:
        from services.decision_service import DecisionService

        if len(sources) == 1:
            subject = f"Underlaget {sources[0].original_filename} är daterat"
        elif sources:
            subject = f"{len(sources)} underlag är daterade, det första"
        else:
            subject = "Underlaget är daterat"
        years = FiscalYearService.list_ascending()
        neighbour = (
            f"Det följer direkt på {_span(years[-1].start_date, years[-1].end_date)}"
            if years and start > years[-1].end_date
            else "Det slutar dagen innan det första räkenskapsåret börjar"
        )
        return DecisionService().create(
            thread,
            title=f"Skapa räkenskapsår {_span(start, end)}?",
            reason=(
                f"{subject} {document_date.isoformat()}, och det datumet ligger "
                "inte i något räkenskapsår. Utan räkenskapsår kan det inte "
                "bokföras."
            ),
            consequence=(
                "Året skapas med en period per månad, och underlaget bokförs "
                "sedan i det."
            ),
            kind="approval",
            source=(
                {"kind": "intake_source", "id": sources[0].id, "date": document_date}
                if sources
                else None
            ),
            options=[
                {
                    "title": CREATE_OPTION_TITLE,
                    "rationale": f"{neighbour}, och omfattar {_span(start, end)}.",
                    "recommended": True,
                },
                {
                    "title": DECLINE_OPTION_TITLE,
                    "rationale": "Inget räkenskapsår skapas, och underlaget "
                    "bokförs inte.",
                    "is_exit": True,
                },
            ],
            actor=actor,
        )

    @staticmethod
    def _result(proposal: FiscalYearProposal, *, existing_card: bool) -> dict:
        return {
            "proposal_id": proposal.id,
            "decision_id": proposal.decision_id,
            "start_date": proposal.start_date.isoformat(),
            "end_date": proposal.end_date.isoformat(),
            "status": proposal.status,
            "existing_card": existing_card,
            "waiting_source_ids": proposal.source_ids,
        }

    @staticmethod
    def _wake_pass(proposal: FiscalYearProposal) -> None:
        """The waiting dropzone underlag are back in the queue: ask the
        intake pass to run, if it is running. Never fatal."""
        if not proposal.source_ids or not settings.agent_runtime_enabled:
            return
        try:
            from services.agent_runtime import get_runner

            runner = get_runner()
            if runner.running:
                runner.trigger_pass_now()
        except Exception:
            logger.exception("Could not wake the intake pass")


def _receipt_body(proposal: FiscalYearProposal) -> dict:
    span = _span(proposal.start_date, proposal.end_date)
    waiting = len(proposal.source_ids)
    note = "En period per månad."
    if waiting:
        note += (
            f" {waiting} underlag väntade på året och bokförs nu."
            if waiting > 1
            else " Underlaget som väntade på året bokförs nu."
        )
    return {
        "title": f"Räkenskapsår {span} skapat",
        "labels": ["räkenskapsår", str(proposal.start_date.year)],
        "rows": [],
        "voucher_id": None,
        "note": note,
    }


def _publish(posts: List[ThreadPost]) -> None:
    """`message.completed` for posts written outside a turn. Never fatal: the
    posts are stored and the next read shows them."""
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
            logger.exception("Post %s was not published", post.id)
