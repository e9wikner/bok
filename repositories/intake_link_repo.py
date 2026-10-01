"""Repositories for `intake_link_basis` and `voucher_source_references`
(migration 032, SPEC-flode-underlag.md §5) and `voucher_intake_unlinks`
(migration 035, underlag-ersatt).

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
from domain.intake_link import IntakeLinkBasis, IntakeUnlink, VoucherSourceReference


class IntakeLinkRepository:
    """`intake_link_basis`: insert and read only."""

    @staticmethod
    def insert(basis: IntakeLinkBasis, _commit: bool = True) -> IntakeLinkBasis:
        """Insert one row as given, `created_at` included. *basis* must name
        its link (`link_id`, migration 035)."""
        if basis.link_id is None:
            raise ValueError("intake_link_basis needs the link it is the basis of")
        db.execute(
            """
            INSERT INTO intake_link_basis
            (link_id, intake_source_id, voucher_id, basis, interpretation_id,
             decision_id, actor, agent_run_id, thread_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                basis.link_id,
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
        """The basis of *source_id*'s current link, or `None` when it has
        none or it was not linked after the fact (by a posting)."""
        row = db.execute(
            """
            SELECT b.* FROM intake_link_basis b
            WHERE b.intake_source_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM voucher_intake_unlinks u WHERE u.link_id = b.link_id
              )
            """,
            (source_id,),
        ).fetchone()
        return _row_to_basis(row) if row else None

    @staticmethod
    def get_for_link(link_id: str) -> Optional[IntakeLinkBasis]:
        """The basis of the link *link_id*, current or undone."""
        row = db.execute(
            "SELECT * FROM intake_link_basis WHERE link_id = ?", (link_id,)
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


class IntakeUnlinkRepository:
    """`voucher_intake_unlinks` (migration 035): insert and read only."""

    @staticmethod
    def insert(unlink: IntakeUnlink, _commit: bool = True) -> IntakeUnlink:
        db.execute(
            """
            INSERT INTO voucher_intake_unlinks
            (link_id, intake_source_id, voucher_id, basis, decision_id, reason,
             actor, agent_run_id, thread_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unlink.link_id,
                unlink.intake_source_id,
                unlink.voucher_id,
                unlink.basis,
                unlink.decision_id,
                unlink.reason,
                unlink.actor,
                unlink.agent_run_id,
                unlink.thread_id,
                unlink.created_at.isoformat(sep=" "),
            ),
        )
        if _commit:
            db.commit()
        return unlink

    @staticmethod
    def get_for_link(link_id: str) -> Optional[IntakeUnlink]:
        row = db.execute(
            "SELECT * FROM voucher_intake_unlinks WHERE link_id = ?", (link_id,)
        ).fetchone()
        return _row_to_unlink(row) if row else None

    @staticmethod
    def get_by_decision(decision_id: str) -> Optional[IntakeUnlink]:
        """The unlink *decision_id* was the basis of, or `None`."""
        row = db.execute(
            "SELECT * FROM voucher_intake_unlinks WHERE decision_id = ? "
            "ORDER BY created_at, rowid LIMIT 1",
            (decision_id,),
        ).fetchone()
        return _row_to_unlink(row) if row else None


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
    def list_through(
        intake_source_id: str, via_voucher_id: str
    ) -> list[VoucherSourceReference]:
        """The references that go through *via_voucher_id*'s link to
        *intake_source_id* (A-121 through A-118's receipt)."""
        rows = db.execute(
            "SELECT * FROM voucher_source_references"
            " WHERE intake_source_id = ? AND via_voucher_id = ?"
            " ORDER BY created_at, rowid",
            (intake_source_id, via_voucher_id),
        ).fetchall()
        return [_row_to_reference(row) for row in rows]

    @staticmethod
    def get_for_voucher(voucher_id: str) -> Optional[VoucherSourceReference]:
        """The reference *voucher_id* (A-121) carries, or `None`."""
        row = db.execute(
            "SELECT * FROM voucher_source_references WHERE voucher_id = ?",
            (voucher_id,),
        ).fetchone()
        return _row_to_reference(row) if row else None


def _row_to_reference(row) -> VoucherSourceReference:
    return VoucherSourceReference(
        voucher_id=row["voucher_id"],
        intake_source_id=row["intake_source_id"],
        via_voucher_id=row["via_voucher_id"],
        decision_id=row["decision_id"],
        created_at=_parse_datetime(row["created_at"]),
    )


def _row_to_unlink(row) -> IntakeUnlink:
    return IntakeUnlink(
        link_id=row["link_id"],
        intake_source_id=row["intake_source_id"],
        voucher_id=row["voucher_id"],
        basis=row["basis"],
        reason=row["reason"],
        actor=row["actor"],
        decision_id=row["decision_id"],
        agent_run_id=row["agent_run_id"],
        thread_id=row["thread_id"],
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
        link_id=row["link_id"],
    )


def _parse_datetime(value: Any) -> datetime:
    """`created_at` is `NOT NULL` in the schema."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
