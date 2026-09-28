"""Repository for `intake_interpretations` (migrations 030 and 031,
SPEC-underlagstolkning.md §5).

All SQL for `intake_interpretations` lives here — see AGENTS.md's layering
rule. Same `@staticmethod` form and `_commit: bool = True` convention as
`repositories/thread_draft_repo.py`.

Append-only: there is `insert` and there are reads, and nothing else. The
schema's triggers refuse a rewrite or a removal anyway; the repository does
not offer one either (§5, the second of three layers). A new interpretation
of the same source is a new row, and the latest one counts: latest is
`ORDER BY created_at, rowid`, so two interpretations inserted within the
same `created_at` still have one unambiguous latest -- the one inserted
last.
"""

from datetime import date, datetime
from typing import Any, Optional

from db.database import db
from domain.interpretation import Interpretation


class InterpretationRepository:
    """Manage `intake_interpretations` persistence (insert and read only)."""

    @staticmethod
    def insert(interpretation: Interpretation, _commit: bool = True) -> Interpretation:
        """Insert one row as given, `id` and `created_at` included."""
        columns = interpretation.json_columns()
        db.execute(
            """
            INSERT INTO intake_interpretations
            (id, intake_source_id, vendor, document_date, currency, total_ore,
             vat_ore, lines_json, checks_json, confidence, match_json,
             candidates_json, expected_voucher_id, expected_json, actor,
             agent_run_id, thread_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interpretation.id,
                interpretation.intake_source_id,
                interpretation.vendor,
                (
                    interpretation.document_date.isoformat()
                    if interpretation.document_date
                    else None
                ),
                interpretation.currency,
                interpretation.total_ore,
                interpretation.vat_ore,
                columns["lines_json"],
                columns["checks_json"],
                interpretation.confidence,
                columns["match_json"],
                columns["candidates_json"],
                interpretation.expected_voucher_id,
                columns["expected_json"],
                interpretation.actor,
                interpretation.agent_run_id,
                interpretation.thread_id,
                interpretation.created_at.isoformat(sep=" "),
            ),
        )
        if _commit:
            db.commit()
        return interpretation

    @staticmethod
    def latest_for_source(source_id: str) -> Optional[Interpretation]:
        """The interpretation that counts for `source_id`, or `None` when it
        was never interpreted."""
        row = db.execute(
            "SELECT * FROM intake_interpretations WHERE intake_source_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        return InterpretationRepository._row_to_interpretation(row) if row else None

    @staticmethod
    def count_for_source(source_id: str) -> int:
        """How many interpretations `source_id` has; `superseded_count` in
        §8 is this minus one."""
        return db.execute(
            "SELECT COUNT(*) AS n FROM intake_interpretations "
            "WHERE intake_source_id = ?",
            (source_id,),
        ).fetchone()["n"]

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _row_to_interpretation(row) -> Interpretation:
        return Interpretation(
            id=row["id"],
            intake_source_id=row["intake_source_id"],
            vendor=row["vendor"],
            document_date=_parse_date(row["document_date"]),
            currency=row["currency"],
            total_ore=row["total_ore"],
            vat_ore=row["vat_ore"],
            confidence=row["confidence"],
            expected_voucher_id=row["expected_voucher_id"],
            actor=row["actor"],
            agent_run_id=row["agent_run_id"],
            thread_id=row["thread_id"],
            created_at=_parse_datetime(row["created_at"]),
            **Interpretation.from_json_columns(
                lines_json=row["lines_json"],
                checks_json=row["checks_json"],
                match_json=row["match_json"],
                candidates_json=row["candidates_json"],
                expected_json=row["expected_json"],
            ),
        )


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _parse_datetime(value: Any) -> datetime:
    """`created_at` is `NOT NULL` in the schema."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
