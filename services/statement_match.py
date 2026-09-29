"""Account statements (CSV) as underlag for posted vouchers.

A transaction on an imported statement is the underlag of the posted voucher
it belongs to (`domain/statement_coverage.py`). This service finds that
voucher and links the two:

- **Automatically**, after a statement is imported and after a voucher is
  posted (`run`): a transaction is linked when exactly one posted voucher
  has the same net amount on the statement's account *and* the same date.
  Overlapping exports need no handling here -- the import already keeps one
  transaction per real transaction (`BankIntegrationService.import_csv`).
- **By the agent**, after asking the user (`koppla_banktransaktion` ->
  `link`): when several vouchers fit, or the dates differ by a few days.

A link is written to the existing traceability tables
(`voucher_bank_transactions`, `voucher_bank_inputs`), which migration 035
made append-only. It never creates or changes a voucher.

No SQL here (AGENTS.md): it lives in `repositories/bank_input_repo.py`.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from db.database import db
from domain.statement_coverage import (
    INPUT_VAT_RANGE,
    is_input_vat_account,
    is_statement_account,
)
from domain.types import AuditAction, VoucherStatus
from repositories.audit_repo import AuditRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.voucher_repo import VoucherRepository
from services.bank_inputs import BankInputConflictError, BankTransactionNotFoundError

logger = logging.getLogger(__name__)

#: `linked_by` for the links this service makes on its own.
AUTO_MATCH_ACTOR = "statement_match"

#: How far a voucher's date may lie from the transaction's and still be
#: offered as a candidate. Only a same-day match is linked without asking.
CANDIDATE_WINDOW_DAYS = 5


@dataclass(frozen=True)
class StatementCandidate:
    voucher_id: str
    voucher_number: str
    voucher_date: str
    description: str
    date_diff_days: int

    def to_dict(self) -> dict:
        return {
            "voucher_id": self.voucher_id,
            "voucher_number": self.voucher_number,
            "voucher_date": self.voucher_date,
            "description": self.description,
            "date_diff_days": self.date_diff_days,
        }


@dataclass(frozen=True)
class TransactionMatch:
    """`exact`: one voucher, same day -- linked without asking.
    `candidates`: several, or a few days apart -- the user decides.
    `none`: nothing fits."""

    bank_transaction_id: str
    account_code: str
    date: str
    amount_ore: int
    description: Optional[str]
    kind: str
    candidates: list[StatementCandidate] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bank_transaction_id": self.bank_transaction_id,
            "account_code": self.account_code,
            "date": self.date,
            "amount_ore": self.amount_ore,
            "description": self.description,
            "match": self.kind,
            "candidates": [c.to_dict() for c in self.candidates],
        }


def _number(row: dict) -> str:
    return f"{row['series']}-{row['number']}"


class StatementMatchService:
    """Match statement transactions to posted vouchers, and link them."""

    def __init__(self) -> None:
        self.inputs = BankInputRepository()

    # --- matching ---------------------------------------------------------

    def match_transaction(self, tx: dict) -> TransactionMatch:
        """Classify one unlinked transaction (a row of
        `list_unlinked_transactions_with_account`)."""
        tx_date = date.fromisoformat(str(tx["transaction_date"])[:10])
        window = timedelta(days=CANDIDATE_WINDOW_DAYS)
        rows = self.inputs.list_statement_match_vouchers(
            account_code=tx["account_code"],
            amount_ore=tx["amount"],
            date_from=(tx_date - window).isoformat(),
            date_to=(tx_date + window).isoformat(),
            input_vat_range=INPUT_VAT_RANGE,
        )
        candidates = sorted(
            (
                StatementCandidate(
                    voucher_id=row["id"],
                    voucher_number=_number(row),
                    voucher_date=str(row["date"])[:10],
                    description=row["description"],
                    date_diff_days=abs(
                        (date.fromisoformat(str(row["date"])[:10]) - tx_date).days
                    ),
                )
                for row in rows
            ),
            key=lambda c: (c.date_diff_days, c.voucher_date, c.voucher_number),
        )
        same_day = [c for c in candidates if c.date_diff_days == 0]
        if len(candidates) == 1 and len(same_day) == 1:
            kind = "exact"
        elif candidates:
            kind = "candidates"
        else:
            kind = "none"
        return TransactionMatch(
            bank_transaction_id=tx["id"],
            account_code=tx["account_code"],
            date=tx_date.isoformat(),
            amount_ore=tx["amount"],
            description=tx.get("description"),
            kind=kind,
            candidates=candidates,
        )

    def open_transactions(self) -> list[TransactionMatch]:
        """Every unlinked transaction on a statement account, classified."""
        return [
            self.match_transaction(tx)
            for tx in self.inputs.list_unlinked_transactions_with_account()
            if is_statement_account(tx["account_code"])
        ]

    def run(self, actor: str = AUTO_MATCH_ACTOR) -> dict:
        """Link every `exact` match. Returns what was linked and what is left
        for the user to decide."""
        linked: list[dict] = []
        undecided: list[dict] = []
        unmatched = 0
        for match in self.open_transactions():
            if match.kind == "exact":
                # A link made earlier in this run may have covered the
                # voucher's account; classify again before linking.
                fresh = self.inputs.get_transaction_with_account(
                    match.bank_transaction_id
                )
                if fresh is None:
                    continue
                again = self.match_transaction(
                    {**fresh, "account_code": match.account_code}
                )
                if again.kind != "exact":
                    continue
                candidate = again.candidates[0]
                self._write_link(
                    match.bank_transaction_id,
                    candidate.voucher_id,
                    account_code=match.account_code,
                    actor=actor,
                    basis="exact_match",
                )
                linked.append(
                    {
                        "bank_transaction_id": match.bank_transaction_id,
                        "voucher_id": candidate.voucher_id,
                        "voucher_number": candidate.voucher_number,
                        "account_code": match.account_code,
                    }
                )
            elif match.kind == "candidates":
                undecided.append(match.to_dict())
            else:
                unmatched += 1
        if linked:
            logger.info("statement_match linked %d transaction(s)", len(linked))
        return {
            "linked": linked,
            "undecided": undecided,
            "unmatched_count": unmatched,
        }

    def run_quietly(self, actor: str = AUTO_MATCH_ACTOR) -> None:
        """`run`, for the hooks after an import or a posting: whatever goes
        wrong here must not fail what already succeeded."""
        try:
            self.run(actor=actor)
        except Exception:  # pragma: no cover - defensive
            logger.exception("statement_match run failed")

    # --- linking ----------------------------------------------------------

    def link(
        self,
        bank_transaction_id: str,
        voucher_id: str,
        *,
        actor: str,
        thread_id: Optional[str] = None,
    ) -> dict:
        """Link one transaction to one posted voucher, after the user
        decided. The amount must still agree; the date may differ.

        Raises `BankTransactionNotFoundError` or `BankInputConflictError`
        (with a code) and writes nothing when a check fails."""
        tx = self.inputs.get_transaction_with_account(bank_transaction_id)
        if tx is None:
            raise BankTransactionNotFoundError(bank_transaction_id)
        account_code = tx["account_code"] or ""

        if tx["linked_voucher_id"] is not None:
            if tx["linked_voucher_id"] == voucher_id:
                voucher = VoucherRepository.get(voucher_id)
                return self._result(tx, voucher, replayed=True)
            raise BankInputConflictError(
                "bank_transaction_already_linked",
                "Bank transaction is already linked to another voucher",
                f"bank_transaction_id={bank_transaction_id}",
            )
        if tx["matched_voucher_id"] is not None:
            raise BankInputConflictError(
                "bank_transaction_already_matched",
                "Bank transaction is already matched to a voucher",
                f"bank_transaction_id={bank_transaction_id}",
            )
        if not is_statement_account(account_code):
            raise BankInputConflictError(
                "not_a_statement_account",
                "Only transactions on 1630 or 1900-1989 can be a voucher's underlag",
                f"account_code={account_code}",
            )

        voucher = VoucherRepository.get(voucher_id)
        if voucher is None:
            raise BankInputConflictError(
                "voucher_not_found", "Voucher not found", f"voucher_id={voucher_id}"
            )
        if voucher.status != VoucherStatus.POSTED:
            raise BankInputConflictError(
                "voucher_not_posted",
                "Only a posted voucher can get a statement as underlag",
                f"voucher_id={voucher_id}",
            )
        if any(is_input_vat_account(r.account_code) for r in voucher.rows):
            raise BankInputConflictError(
                "statement_not_underlag_for_purchase",
                "A voucher with input VAT needs its invoice or receipt, "
                "not a statement",
                f"voucher_id={voucher_id}",
            )
        account_rows = [r for r in voucher.rows if r.account_code == account_code]
        if not account_rows:
            raise BankInputConflictError(
                "voucher_has_no_row_on_account",
                "The voucher has no row on the statement's account",
                f"voucher_id={voucher_id}, account_code={account_code}",
            )
        net = sum(r.debit - r.credit for r in account_rows)
        if net != tx["amount"]:
            raise BankInputConflictError(
                "amount_mismatch",
                "The voucher's amount on the account differs from the transaction",
                f"voucher_net_ore={net}, transaction_ore={tx['amount']}",
            )
        if self.inputs.voucher_link_on_account(voucher_id, account_code):
            raise BankInputConflictError(
                "voucher_account_already_covered",
                "The voucher already has a transaction on this account",
                f"voucher_id={voucher_id}, account_code={account_code}",
            )

        self._write_link(
            bank_transaction_id,
            voucher_id,
            account_code=account_code,
            actor=actor,
            basis="decision",
            thread_id=thread_id,
        )
        return self._result(tx, VoucherRepository.get(voucher_id), replayed=False)

    def _write_link(
        self,
        bank_transaction_id: str,
        voucher_id: str,
        *,
        account_code: str,
        actor: str,
        basis: str,
        thread_id: Optional[str] = None,
    ) -> None:
        input_ids = self.inputs.list_input_ids_for_transaction(bank_transaction_id)
        with db.transaction():
            self.inputs.create_voucher_bank_transaction_link(
                voucher_id=voucher_id,
                bank_transaction_id=bank_transaction_id,
                linked_by=actor,
                _commit=False,
            )
            for bank_input_id in input_ids:
                self.inputs.create_voucher_bank_input_link(
                    voucher_id=voucher_id,
                    bank_input_id=bank_input_id,
                    linked_by=actor,
                    _commit=False,
                )
            self.inputs.mark_transactions_booked(
                [bank_transaction_id], voucher_id=voucher_id, _commit=False
            )
            AuditRepository.log(
                entity_type="voucher",
                entity_id=voucher_id,
                action=AuditAction.STATEMENT_LINKED.value,
                actor=actor,
                payload={
                    "bank_transaction_id": bank_transaction_id,
                    "bank_input_ids": input_ids,
                    "account_code": account_code,
                    "basis": basis,
                    "thread_id": thread_id,
                },
                _commit=False,
            )

    def _result(self, tx: dict, voucher, *, replayed: bool) -> dict:
        refreshed = VoucherRepository.get(voucher.id) if voucher else None
        return {
            "bank_transaction_id": tx["id"],
            "account_code": tx["account_code"],
            "voucher_id": voucher.id if voucher else None,
            "voucher_number": (
                f"{voucher.series.value}-{voucher.number}" if voucher else None
            ),
            "replayed": replayed,
            "missing_attachment": (refreshed.missing_attachment if refreshed else None),
            "missing_statement_accounts": (
                refreshed.missing_statement_accounts if refreshed else []
            ),
        }
