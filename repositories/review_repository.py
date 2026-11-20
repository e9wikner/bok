"""Repository for review reports (migration 055, docs/granskning.md §5).

All SQL for `review_reports`, `review_findings`, `review_finding_vouchers`
and `review_examined_vouchers` lives here -- AGENTS.md's layering rule. The
four tables are append-only: insert and read, nothing else (the triggers
refuse the rest). The inserts do not commit; `ReviewService` writes a report
in one transaction.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set

from db.database import db
from domain.models import ReviewFinding, ReviewReport
from repositories.dates import as_date, req_datetime

#: Ids per `IN (...)` query, well under SQLite's parameter limit.
_CHUNK = 500


@dataclass(frozen=True)
class ReviewedVoucher:
    """The voucher fields a review report shows beside an id."""

    id: str
    series: str
    number: Optional[int]
    date: Optional[datetime.date]
    description: str


@dataclass(frozen=True)
class ReportSummaryRow:
    """A report with its counts, for the list."""

    report: ReviewReport
    severity_counts: Dict[str, int]
    examined_voucher_count: int


@dataclass(frozen=True)
class FlaggedVoucherRow:
    """One finding's reference to one voucher, for the coverage."""

    report_id: str
    finding_id: str
    severity: str
    voucher_id: str


def _chunks(ids: Sequence[str]) -> Iterable[Sequence[str]]:
    for start in range(0, len(ids), _CHUNK):
        yield ids[start : start + _CHUNK]


def _row_to_report(row) -> ReviewReport:
    return ReviewReport(
        id=row["id"],
        fiscal_year_id=row["fiscal_year_id"],
        reviewer_agent=row["reviewer_agent"],
        reviewer_model=row["reviewer_model"],
        instruction_sha256=row["instruction_sha256"],
        summary_markdown=row["summary_markdown"],
        uploaded_by=row["uploaded_by"],
        uploaded_at=req_datetime(row["uploaded_at"]),
    )


class ReviewRepository:
    """The four review tables, and the voucher reads a review needs."""

    # -- writes (no commit: the caller holds the transaction) -----------------

    @staticmethod
    def insert_report(report: ReviewReport) -> None:
        db.execute(
            """
            INSERT INTO review_reports
            (id, fiscal_year_id, reviewer_agent, reviewer_model,
             instruction_sha256, summary_markdown, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.id,
                report.fiscal_year_id,
                report.reviewer_agent,
                report.reviewer_model,
                report.instruction_sha256,
                report.summary_markdown,
                report.uploaded_by,
                report.uploaded_at,
            ),
        )

    @staticmethod
    def insert_finding(finding: ReviewFinding) -> None:
        db.execute(
            """
            INSERT INTO review_findings
            (id, report_id, position, severity, area, title, description,
             rule, amount_ore, suggested_correction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.id,
                finding.report_id,
                finding.position,
                finding.severity,
                finding.area,
                finding.title,
                finding.description,
                finding.rule,
                finding.amount_ore,
                finding.suggested_correction,
            ),
        )
        db.executemany(
            "INSERT INTO review_finding_vouchers (finding_id, voucher_id) VALUES (?, ?)",
            [(finding.id, voucher_id) for voucher_id in finding.voucher_ids],
        )

    @staticmethod
    def insert_examined(report_id: str, voucher_ids: Sequence[str]) -> None:
        db.executemany(
            "INSERT INTO review_examined_vouchers (report_id, voucher_id) VALUES (?, ?)",
            [(report_id, voucher_id) for voucher_id in voucher_ids],
        )

    # -- reads -----------------------------------------------------------------

    @staticmethod
    def get_report(report_id: str) -> Optional[ReviewReport]:
        row = db.execute(
            "SELECT * FROM review_reports WHERE id = ?", (report_id,)
        ).fetchone()
        return _row_to_report(row) if row else None

    @staticmethod
    def list_reports(fiscal_year_id: Optional[str]) -> List[ReportSummaryRow]:
        """Newest first, with the findings per severity and the number of
        examined vouchers."""
        where = "WHERE r.fiscal_year_id = ?" if fiscal_year_id else ""
        params: tuple = (fiscal_year_id,) if fiscal_year_id else ()
        rows = db.execute(
            f"""
            SELECT r.*,
                   (SELECT COUNT(*) FROM review_examined_vouchers e
                    WHERE e.report_id = r.id) AS examined_count
            FROM review_reports r
            {where}
            ORDER BY r.uploaded_at DESC, r.id
            """,
            params,
        ).fetchall()
        counts: Dict[str, Dict[str, int]] = defaultdict(dict)
        count_rows = db.execute(
            f"""
            SELECT f.report_id, f.severity, COUNT(*) AS n
            FROM review_findings f
            JOIN review_reports r ON r.id = f.report_id
            {where}
            GROUP BY f.report_id, f.severity
            """,
            params,
        ).fetchall()
        for row in count_rows:
            counts[row["report_id"]][row["severity"]] = int(row["n"])
        return [
            ReportSummaryRow(
                report=_row_to_report(row),
                severity_counts=counts.get(row["id"], {}),
                examined_voucher_count=int(row["examined_count"]),
            )
            for row in rows
        ]

    @staticmethod
    def list_findings(report_id: str) -> List[ReviewFinding]:
        """The report's findings in their order, each with its voucher ids."""
        voucher_ids: Dict[str, List[str]] = defaultdict(list)
        for row in db.execute(
            """
            SELECT fv.finding_id, fv.voucher_id
            FROM review_finding_vouchers fv
            JOIN review_findings f ON f.id = fv.finding_id
            JOIN vouchers v ON v.id = fv.voucher_id
            WHERE f.report_id = ?
            ORDER BY v.date, v.series, v.number, v.id
            """,
            (report_id,),
        ).fetchall():
            voucher_ids[row["finding_id"]].append(row["voucher_id"])
        rows = db.execute(
            "SELECT * FROM review_findings WHERE report_id = ? ORDER BY position",
            (report_id,),
        ).fetchall()
        return [
            ReviewFinding(
                id=row["id"],
                report_id=row["report_id"],
                position=int(row["position"]),
                severity=row["severity"],
                area=row["area"],
                title=row["title"],
                description=row["description"],
                rule=row["rule"],
                amount_ore=row["amount_ore"],
                suggested_correction=row["suggested_correction"],
                voucher_ids=voucher_ids.get(row["id"], []),
            )
            for row in rows
        ]

    @staticmethod
    def examined_voucher_ids(report_id: str) -> List[str]:
        """The vouchers the report says it examined, in date order."""
        rows = db.execute(
            """
            SELECT e.voucher_id
            FROM review_examined_vouchers e
            JOIN vouchers v ON v.id = e.voucher_id
            WHERE e.report_id = ?
            ORDER BY v.date, v.series, v.number, v.id
            """,
            (report_id,),
        ).fetchall()
        return [row["voucher_id"] for row in rows]

    @staticmethod
    def examined_pairs(fiscal_year_id: str) -> List[tuple]:
        """(report_id, voucher_id) for every examined voucher in the year's
        reports."""
        rows = db.execute(
            """
            SELECT e.report_id, e.voucher_id
            FROM review_examined_vouchers e
            JOIN review_reports r ON r.id = e.report_id
            WHERE r.fiscal_year_id = ?
            """,
            (fiscal_year_id,),
        ).fetchall()
        return [(row["report_id"], row["voucher_id"]) for row in rows]

    @staticmethod
    def flagged_rows(fiscal_year_id: str) -> List[FlaggedVoucherRow]:
        """Every voucher a finding in the year's reports refers to."""
        rows = db.execute(
            """
            SELECT f.report_id, f.id AS finding_id, f.severity, fv.voucher_id
            FROM review_finding_vouchers fv
            JOIN review_findings f ON f.id = fv.finding_id
            JOIN review_reports r ON r.id = f.report_id
            WHERE r.fiscal_year_id = ?
            ORDER BY f.report_id, f.position
            """,
            (fiscal_year_id,),
        ).fetchall()
        return [
            FlaggedVoucherRow(
                report_id=row["report_id"],
                finding_id=row["finding_id"],
                severity=row["severity"],
                voucher_id=row["voucher_id"],
            )
            for row in rows
        ]

    # -- the vouchers a report refers to --------------------------------------

    @staticmethod
    def posted_voucher_ids_in_year(
        fiscal_year_id: str, voucher_ids: Sequence[str]
    ) -> Set[str]:
        """Those of *voucher_ids* that are posted vouchers in the year."""
        found: Set[str] = set()
        for chunk in _chunks(list(voucher_ids)):
            placeholders = ",".join("?" for _ in chunk)
            rows = db.execute(
                f"""
                SELECT id FROM vouchers
                WHERE fiscal_year_id = ? AND status = 'posted'
                  AND id IN ({placeholders})
                """,
                (fiscal_year_id, *chunk),
            ).fetchall()
            found.update(row["id"] for row in rows)
        return found

    @staticmethod
    def vouchers(voucher_ids: Sequence[str]) -> Dict[str, ReviewedVoucher]:
        """Number, date and description of *voucher_ids*, by id."""
        result: Dict[str, ReviewedVoucher] = {}
        for chunk in _chunks(list(dict.fromkeys(voucher_ids))):
            placeholders = ",".join("?" for _ in chunk)
            rows = db.execute(
                f"""
                SELECT id, series, number, date, description FROM vouchers
                WHERE id IN ({placeholders})
                """,
                tuple(chunk),
            ).fetchall()
            for row in rows:
                result[row["id"]] = ReviewedVoucher(
                    id=row["id"],
                    series=row["series"],
                    number=row["number"],
                    date=as_date(row["date"]),
                    description=row["description"] or "",
                )
        return result
