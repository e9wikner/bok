"""`foresla_bolagsinformation`: company details proposed as a decision card.

The details end up on every invoice the company issues (seat, VAT number,
bankgiro, F-skatt), so the agent never writes them itself. It proposes them as
a decision card in the thread and the human's press writes them. The values are
stored with the card (migration 042), so what is written is exactly what the
human saw.

Fill-only by default: a value goes into a field that is empty. A field that
already holds a different value is a separate step. The card then has a second
option, "Fyll i och skriv över", that lists what it replaces, and the first
option leaves those fields alone.

The press (`on_decision_answered`, called by `POST /decisions/{id}/answer`
after the answer has committed):

- the fill option -> the empty fields are filled, a receipt is written;
- the overwrite option -> the empty fields are filled and the stated ones
  replaced, a receipt is written;
- any other option -> declined, nothing written;
- free text -> nothing yet. The agent's turn reads the answer and, if it is a
  yes, proposes again, which supersedes this card.

A field that was filled by someone else after the card was raised is left
alone by the fill option, so the press never overwrites what it did not show.

Layering (AGENTS.md): no SQL here, no HTTP.
"""

import logging
from typing import Any, Dict, List, Mapping, Optional

from db.database import db
from domain.models import CompanyInfoProposal, Decision, Thread, ThreadPost
from domain.validation import ValidationError
from repositories.company_info_proposal_repo import CompanyInfoProposalRepository
from repositories.company_info_repo import CompanyInfoRepository
from repositories.thread_repo import ThreadRepository

logger = logging.getLogger(__name__)

FILL_OPTION_TITLE = "Fyll i uppgifterna"
FILL_EMPTY_OPTION_TITLE = "Fyll i tomma fält"
OVERWRITE_OPTION_TITLE = "Fyll i och skriv över"
DECLINE_OPTION_TITLE = "Inte nu"

#: Keys of `company_info`, in the order a card lists them, with their labels.
FIELD_LABELS: Dict[str, str] = {
    "name": "Företagsnamn",
    "org_number": "Organisationsnummer",
    "contact_name": "Kontaktperson",
    "address": "Adress",
    "postnr": "Postnummer",
    "postort": "Postort",
    "email": "E-post",
    "phone": "Telefon",
    "website": "Webbplats",
    "seat": "Säte",
    "vat_number": "Momsnummer",
    "bankgiro": "Bankgiro",
    "plusgiro": "Plusgiro",
    "f_skatt": "F-skatt",
}


def _norm(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip() if value is not None else ""


def _show(key: str, value: str) -> str:
    if key == "f_skatt":
        return "Ja" if value == "true" else "Nej"
    return value


def _lines(values: Mapping[str, str]) -> str:
    return "; ".join(f"{FIELD_LABELS[k]} {_show(k, v)}" for k, v in values.items())


class CompanyInfoProposalService:
    # -- the tool ----------------------------------------------------------

    def propose(
        self, thread: Thread, *, fields: Mapping[str, Any], actor: str
    ) -> Dict[str, Any]:
        """Raise the card for the fields the user gave. A field equal to the
        stored value is left out; if nothing is left, no card is raised. A
        pending card is superseded by the new one."""
        wanted = {
            key: _norm(value)
            for key, value in fields.items()
            if key in FIELD_LABELS and _norm(value) != ""
        }
        if not wanted:
            raise ValidationError(
                "no_company_fields",
                "Give at least one company field",
                "Nothing to propose",
            )
        stored = CompanyInfoRepository.get_all()
        fill: Dict[str, str] = {}
        overwrite: Dict[str, str] = {}
        for key in FIELD_LABELS:
            if key not in wanted:
                continue
            current = _norm(stored.get(key))
            if key == "f_skatt" and current == "false":
                current = ""  # `false` is the default, not a statement
            if current == wanted[key]:
                continue
            (overwrite if current else fill)[key] = wanted[key]
        if not fill and not overwrite:
            return {"status": "unchanged", "decision_id": None, "proposal_id": None}

        for pending in CompanyInfoProposalRepository.list_pending():
            from services.decision_service import DecisionService

            CompanyInfoProposalRepository.resolve(pending.id, "superseded", actor=actor)
            DecisionService().supersede(pending.decision_id)

        decision = self._raise_card(thread, fill, overwrite, stored, actor)
        options = decision.options
        if fill and overwrite:
            fill_id: Optional[str] = options[0].id
            overwrite_id: Optional[str] = options[1].id
        elif fill:
            fill_id, overwrite_id = options[0].id, None
        else:
            fill_id, overwrite_id = None, options[0].id
        try:
            proposal = CompanyInfoProposalRepository.create(
                decision_id=decision.id,
                thread_id=thread.id,
                fill_option_id=fill_id,
                overwrite_option_id=overwrite_id,
                fill_values=fill,
                overwrite_values=overwrite,
                created_by=actor,
            )
        except Exception:
            # A card without its row could be pressed to no effect.
            from services.decision_service import DecisionService

            DecisionService().supersede(decision.id)
            raise
        return {
            "status": "pending",
            "proposal_id": proposal.id,
            "decision_id": decision.id,
            "fill": fill,
            "overwrite": overwrite,
        }

    # -- the press ---------------------------------------------------------

    def on_decision_answered(
        self, decision: Decision, *, actor: str
    ) -> Optional[ThreadPost]:
        """What the answer to a company-info card does; `None` for any other
        decision. Returns the post it wrote, already published."""
        proposal = CompanyInfoProposalRepository.get_by_decision(decision.id)
        if proposal is None or proposal.status != "pending":
            return None
        option_id = decision.answer_option_id
        if option_id is None:
            return None  # free text: the agent's turn takes it from here
        if option_id in (proposal.fill_option_id, proposal.overwrite_option_id):
            return self._apply(
                proposal,
                overwrite=option_id == proposal.overwrite_option_id,
                actor=actor,
            )
        CompanyInfoProposalRepository.resolve(proposal.id, "declined", actor=actor)
        return None

    def _apply(
        self, proposal: CompanyInfoProposal, *, overwrite: bool, actor: str
    ) -> ThreadPost:
        stored = CompanyInfoRepository.get_all()
        writes: Dict[str, str] = {}
        skipped: List[str] = []
        for key, value in proposal.fill_values.items():
            current = _norm(stored.get(key))
            if key == "f_skatt" and current == "false":
                current = ""
            if current and current != value:
                skipped.append(key)  # filled by someone else since the card
            else:
                writes[key] = value
        if overwrite:
            writes.update(proposal.overwrite_values)
        with db.transaction():
            CompanyInfoRepository.set_values(writes)
            CompanyInfoProposalRepository.resolve(
                proposal.id, "applied", actor=actor, _commit=False
            )
            post = ThreadRepository.add_post(
                thread_id=proposal.thread_id,
                post_type="receipt",
                actor=actor,
                body=_receipt_body(writes, skipped),
                _commit=False,
            )
        _publish([post])
        return post

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _raise_card(
        thread: Thread,
        fill: Mapping[str, str],
        overwrite: Mapping[str, str],
        stored: Mapping[str, str],
        actor: str,
    ) -> Decision:
        from services.decision_service import DecisionService

        parts = []
        if fill:
            parts.append(f"Läggs till: {_lines(fill)}.")
        if overwrite:
            replaced = "; ".join(
                f"{FIELD_LABELS[k]} {_show(k, _norm(stored.get(k)))} → {_show(k, v)}"
                for k, v in overwrite.items()
            )
            parts.append(f"Ersätter det som står: {replaced}.")
        if fill and overwrite:
            options = [
                {
                    "title": FILL_EMPTY_OPTION_TITLE,
                    "rationale": "Skriver bara i tomma fält. Det som redan står "
                    "ändras inte.",
                    "recommended": True,
                },
                {
                    "title": OVERWRITE_OPTION_TITLE,
                    "rationale": "Fyller i tomma fält och ersätter de redan "
                    "ifyllda fälten ovan.",
                },
            ]
        elif fill:
            options = [
                {
                    "title": FILL_OPTION_TITLE,
                    "rationale": "Skriver uppgifterna i tomma fält.",
                    "recommended": True,
                }
            ]
        else:
            options = [
                {
                    "title": OVERWRITE_OPTION_TITLE,
                    "rationale": "Ersätter de redan ifyllda fälten ovan.",
                    "recommended": True,
                }
            ]
        options.append(
            {
                "title": DECLINE_OPTION_TITLE,
                "rationale": "Inga bolagsuppgifter ändras.",
                "is_exit": True,
            }
        )
        return DecisionService().create(
            thread,
            title="Spara bolagsuppgifterna?",
            reason=" ".join(parts),
            consequence=(
                "Uppgifterna står på fakturorna som utfärdas härefter. Utfärdade "
                "fakturor ändras inte."
            ),
            kind="approval",
            options=options,
            actor=actor,
        )


def _receipt_body(writes: Mapping[str, str], skipped: List[str]) -> dict:
    note = _lines(writes) + "." if writes else "Inget skrevs."
    if skipped:
        names = ", ".join(FIELD_LABELS[k] for k in skipped)
        note += f" Hoppade över {names}: fältet hade fyllts i under tiden."
    return {
        "title": "Bolagsuppgifterna sparade",
        "labels": ["bolagsuppgifter"],
        "rows": [],
        "voucher_id": None,
        "note": note,
    }


def _publish(posts: List[ThreadPost]) -> None:
    """`message.completed` for posts written outside a turn. Never fatal."""
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
