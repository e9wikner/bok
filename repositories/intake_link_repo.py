"""Repositories for `intake_link_basis` and `voucher_source_references`
(migration 032, SPEC-flode-underlag.md §5).

All SQL for the two tables lives here -- see AGENTS.md's layering rule.
Same `@staticmethod` form and `_commit: bool = True` convention as
`repositories/interpretation_repo.py`.

Append-only: there is `insert` and there are reads, and nothing else. The
schema's triggers refuse a rewrite or a removal anyway; the repositories do
not offer one either (the second of three layers).
"""

from datetime import datetime
from typing import Any, Optional

from db.database import db
from domain.intake_link import IntakeLinkBasis, VoucherSourceReference


class IntakeLinkRepository:
    """`intake_link_basis`: insert and read only."""

    @staticmethod
    def insert(basis: IntakeLinkBasis, _commit: bool = True) -> IntakeLinkBasis:
        """Insert one row as given, `created_at` included."""
        db.execute(
            """
            INSERT INTO intake_link_basis
            (intake_source_id, voucher_id, basis, interpretation_id,
             decision_id, actor, agent_run_id, thread_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                basis.intake_source_id,
                basis.voucher_id,
                basis.basis,
                basis.interpretation_id,
                basis.decision_id,
                basis.actor,
                basis.agent_run_id,
                basis.thread_id,
                basis.created_at.isoformat(sep=" "),
            ),
        )
        if _commit:
            db.commit()
        return basis

    @staticmethod
    def get_for_source(source_id: str) -> Optional[IntakeLinkBasis]:
        """The basis of *source_id*'s link, or `None` when it was not linked
        after the fact (never, or by a posting)."""
        row = db.execute(
            "SELECT * FROM intake_link_basis WHERE intake_source_id = ?",
            (source_id,),
        ).fetchone()
        return _row_to_basis(row) if row else None

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[IntakeLinkBasis]:
        """The link *decision_id* was the basis of, or `None`. A decision is
        about one source (§6.4), so it bases at most one link."""
        row = db.execute(
            "SELECT * FROM intake_link_basis WHERE decision_id = ? "
            "ORDER BY created_at, rowid LIMIT 1",
            (decision_id,),
        ).fetchone()
        return _row_to_basis(row) if row else None


class VoucherSourceReferenceRepository:
    """`voucher_source_references`: insert and read only."""

    @staticmethod
    def insert(
        ref: VoucherSourceReference, _commit: bool = True
    ) -> VoucherSourceReference:
        db.execute(
            """
            INSERT INTO voucher_source_references
            (voucher_id, intake_source_id, via_voucher_id, decision_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ref.voucher_id,
                ref.intake_source_id,
                ref.via_voucher_id,
                ref.decision_id,
                ref.created_at.isoformat(sep=" "),
            ),
        )
        if _commit:
            db.commit()
        return ref

    @staticmethod
    def get_for_voucher(voucher_id: str) -> Optional[VoucherSourceReference]:
        """The reference *voucher_id* (A-121) carries, or `None`."""
        row = db.execute(
            "SELECT * FROM voucher_source_references WHERE voucher_id = ?",
            (voucher_id,),
        ).fetchone()
        if row is None:
            return None
        return VoucherSourceReference(
            voucher_id=row["voucher_id"],
            intake_source_id=row["intake_source_id"],
            via_voucher_id=row["via_voucher_id"],
            decision_id=row["decision_id"],
            created_at=_parse_datetime(row["created_at"]),
        )


def _row_to_basis(row) -> IntakeLinkBasis:
    return IntakeLinkBasis(
        intake_source_id=row["intake_source_id"],
        voucher_id=row["voucher_id"],
        basis=row["basis"],
        interpretation_id=row["interpretation_id"],
        decision_id=row["decision_id"],
        actor=row["actor"],
        agent_run_id=row["agent_run_id"],
        thread_id=row["thread_id"],
        created_at=_parse_datetime(row["created_at"]),
    )


def _parse_datetime(value: Any) -> datetime:
    """`created_at` is `NOT NULL` in the schema."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
