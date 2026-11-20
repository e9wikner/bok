"""Granskning: an external agent's review report (docs/granskning.md).

An agent reads the books through the API with the read-only review key,
reviews a fiscal year by the instruction in `docs/to_reviewer/`, and uploads
a report. Bok runs no review itself: this service validates the upload,
stores it append-only (migration 055) and reads it back for the UI.

The review is the board's own control (ABL 8 kap. 4 §). It is not a
statutory audit and is never named as one.

A report is all or nothing. Before anything is written:

- the fiscal year exists,
- every voucher id -- in `examined_voucher_ids` and in each finding's
  `voucher_ids` -- is a posted voucher in that year (`invalid_voucher_id`,
  with the ids that are not), so a report cannot point at a made-up voucher,
- severities, areas and text lengths are what `ReviewReportIn` allows.

The agent chooses the report's id. The same id with the same body is a
replay and returns the stored report; the same id with another body is
`review_report_id_conflict`.
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from db.database import db
from domain.models import FiscalYear, ReviewFinding, ReviewReport
from repositories.period_repo import PeriodRepository
from repositories.review_repository import ReviewedVoucher, ReviewRepository
from repositories.system_instructions import get_reviewer_instructions

SEVERITIES = ("material", "should_fix", "observation")
AREAS = (
    "moms",
    "periodisering",
    "privat",
    "underlag",
    "avstamning",
    "bokslut",
    "forvaltning",
    "ovrigt",
)
Severity = Literal["material", "should_fix", "observation"]
Area = Literal[
    "moms",
    "periodisering",
    "privat",
    "underlag",
    "avstamning",
    "bokslut",
    "forvaltning",
    "ovrigt",
]
_SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITIES)}

# Upper bounds for what one upload may carry.
NAME_MAX = 200
SHA_MAX = 128
SUMMARY_MAX = 100_000
TITLE_MAX = 300
DESCRIPTION_MAX = 20_000
RULE_MAX = 500
CORRECTION_MAX = 10_000
FINDINGS_MAX = 1_000
FINDING_VOUCHERS_MAX = 1_000
EXAMINED_MAX = 20_000
VOUCHER_ID_MAX = 100


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewerIn(_Strict):
    """Which agent and model made the review, as the agent states it."""

    agent: str = Field(..., min_length=1, max_length=NAME_MAX)
    model: str = Field(..., min_length=1, max_length=NAME_MAX)


class ReviewFindingIn(_Strict):
    """One anmärkning."""

    severity: Severity = Field(
        ...,
        description=(
            "material: affects the annual report, the tax return or legal "
            "compliance; should_fix: an error that should be corrected; "
            "observation: a remark"
        ),
    )
    area: Area
    title: str = Field(..., min_length=1, max_length=TITLE_MAX)
    description: str = Field(..., min_length=1, max_length=DESCRIPTION_MAX)
    rule: Optional[str] = Field(
        None, max_length=RULE_MAX, description="The rule, e.g. 'ML 1 kap. 2 §'"
    )
    voucher_ids: List[str] = Field(
        default_factory=list,
        max_length=FINDING_VOUCHERS_MAX,
        description="Posted vouchers in the fiscal year the finding rests on",
    )
    amount_ore: Optional[int] = Field(None, description="An amount in öre")
    suggested_correction: Optional[str] = Field(None, max_length=CORRECTION_MAX)

    @field_validator("rule", "suggested_correction")
    @classmethod
    def _blank_is_none(cls, value: Optional[str]) -> Optional[str]:
        return value or None


class ReviewReportIn(_Strict):
    """`POST /api/v1/review/reports`: a granskningsrapport."""

    id: str = Field(
        ...,
        description=(
            "A UUID the agent creates. Sending the same id again returns the "
            "stored report instead of a duplicate."
        ),
    )
    fiscal_year_id: str = Field(..., min_length=1, max_length=VOUCHER_ID_MAX)
    reviewer: ReviewerIn
    instruction_sha256: str = Field(
        ...,
        min_length=1,
        max_length=SHA_MAX,
        description="instruction_sha256 from GET /api/v1/review/instructions",
    )
    summary_markdown: str = Field(..., min_length=1, max_length=SUMMARY_MAX)
    examined_voucher_ids: List[str] = Field(
        default_factory=list,
        max_length=EXAMINED_MAX,
        description="The vouchers the agent actually examined",
    )
    findings: List[ReviewFindingIn] = Field(
        default_factory=list,
        max_length=FINDINGS_MAX,
        description="May be empty: no findings is a valid outcome",
    )

    @field_validator("id")
    @classmethod
    def _uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError:
            raise ValueError("id must be a UUID")


@dataclass
class ReviewError(Exception):
    """`code` is the API's error code; `status` the HTTP status it maps to."""

    code: str
    message: str
    status: int = 422
    payload: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


def _unique(ids: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(ids))


def _voucher_json(voucher_id: str, voucher: Optional[ReviewedVoucher]) -> dict:
    if voucher is None:
        return {
            "id": voucher_id,
            "series": None,
            "number": None,
            "voucher_number": None,
            "date": None,
            "description": None,
        }
    return {
        "id": voucher.id,
        "series": voucher.series,
        "number": voucher.number,
        "voucher_number": (
            f"{voucher.series}-{voucher.number}" if voucher.number is not None else None
        ),
        "date": voucher.date.isoformat() if voucher.date else None,
        "description": voucher.description,
    }


def _counts(severity_counts: Dict[str, int]) -> Dict[str, int]:
    return {severity: severity_counts.get(severity, 0) for severity in SEVERITIES}


def _fiscal_year_json(fy: FiscalYear) -> dict:
    return {
        "id": fy.id,
        "start_date": fy.start_date.isoformat(),
        "end_date": fy.end_date.isoformat(),
        "locked": fy.locked,
        # An ongoing year has no closing entries and statements only up to
        # now; the instruction tells the reviewer to review it so far.
        "ended": fy.end_date < date.today(),
    }


def current_instruction_sha256() -> str:
    return get_reviewer_instructions()["sha256"]


class ReviewService:
    # -- upload ----------------------------------------------------------------

    def submit(self, report: ReviewReportIn, uploaded_by: str) -> tuple[dict, bool]:
        """Store *report*: `(the stored report, True)` when written now,
        `(the stored report, False)` for a replay of the same id and body."""
        existing = ReviewRepository.get_report(report.id)
        if existing is not None:
            return self._replay(existing, report), False

        fiscal_year = PeriodRepository.get_fiscal_year(report.fiscal_year_id)
        if fiscal_year is None:
            raise ReviewError(
                "fiscal_year_not_found",
                f"Unknown fiscal year: {report.fiscal_year_id!r}",
            )

        referenced = _unique(
            [
                *report.examined_voucher_ids,
                *(vid for finding in report.findings for vid in finding.voucher_ids),
            ]
        )
        valid = ReviewRepository.posted_voucher_ids_in_year(fiscal_year.id, referenced)
        invalid = [voucher_id for voucher_id in referenced if voucher_id not in valid]
        if invalid:
            raise ReviewError(
                "invalid_voucher_id",
                "Every voucher id must be a posted voucher in the fiscal year",
                payload={"invalid_voucher_ids": invalid},
            )

        stored = ReviewReport(
            id=report.id,
            fiscal_year_id=fiscal_year.id,
            reviewer_agent=report.reviewer.agent,
            reviewer_model=report.reviewer.model,
            instruction_sha256=report.instruction_sha256,
            summary_markdown=report.summary_markdown,
            uploaded_by=uploaded_by,
            uploaded_at=datetime.now(),
        )
        try:
            with db.transaction():
                ReviewRepository.insert_report(stored)
                for position, finding in enumerate(report.findings, start=1):
                    ReviewRepository.insert_finding(
                        ReviewFinding(
                            id=str(uuid.uuid4()),
                            report_id=stored.id,
                            position=position,
                            severity=finding.severity,
                            area=finding.area,
                            title=finding.title,
                            description=finding.description,
                            rule=finding.rule,
                            amount_ore=finding.amount_ore,
                            suggested_correction=finding.suggested_correction,
                            voucher_ids=_unique(finding.voucher_ids),
                        )
                    )
                ReviewRepository.insert_examined(
                    stored.id, _unique(report.examined_voucher_ids)
                )
        except sqlite3.IntegrityError:
            # Two uploads of one id at the same moment: the other one won.
            raced = ReviewRepository.get_report(report.id)
            if raced is None:
                raise
            return self._replay(raced, report), False
        return self.get(stored.id), True

    def _replay(self, existing: ReviewReport, report: ReviewReportIn) -> dict:
        if self._stored_body(existing) != self._sent_body(report):
            raise ReviewError(
                "review_report_id_conflict",
                "A report with this id is already stored with other content",
                status=409,
                payload={"report_id": existing.id},
            )
        return self.get(existing.id)

    @staticmethod
    def _sent_body(report: ReviewReportIn) -> dict:
        return {
            "fiscal_year_id": report.fiscal_year_id,
            "agent": report.reviewer.agent,
            "model": report.reviewer.model,
            "instruction_sha256": report.instruction_sha256,
            "summary_markdown": report.summary_markdown,
            "examined": sorted(set(report.examined_voucher_ids)),
            "findings": [
                {
                    "severity": f.severity,
                    "area": f.area,
                    "title": f.title,
                    "description": f.description,
                    "rule": f.rule,
                    "amount_ore": f.amount_ore,
                    "suggested_correction": f.suggested_correction,
                    "voucher_ids": sorted(set(f.voucher_ids)),
                }
                for f in report.findings
            ],
        }

    @staticmethod
    def _stored_body(report: ReviewReport) -> dict:
        return {
            "fiscal_year_id": report.fiscal_year_id,
            "agent": report.reviewer_agent,
            "model": report.reviewer_model,
            "instruction_sha256": report.instruction_sha256,
            "summary_markdown": report.summary_markdown,
            "examined": sorted(ReviewRepository.examined_voucher_ids(report.id)),
            "findings": [
                {
                    "severity": f.severity,
                    "area": f.area,
                    "title": f.title,
                    "description": f.description,
                    "rule": f.rule,
                    "amount_ore": f.amount_ore,
                    "suggested_correction": f.suggested_correction,
                    "voucher_ids": sorted(f.voucher_ids),
                }
                for f in ReviewRepository.list_findings(report.id)
            ],
        }

    # -- reads -----------------------------------------------------------------

    @staticmethod
    def _report_head(
        report: ReviewReport, current_sha: str, severity_counts: Dict[str, int]
    ) -> dict:
        counts = _counts(severity_counts)
        return {
            "id": report.id,
            "fiscal_year_id": report.fiscal_year_id,
            "reviewer": {
                "agent": report.reviewer_agent,
                "model": report.reviewer_model,
            },
            "instruction_sha256": report.instruction_sha256,
            "instruction_outdated": report.instruction_sha256 != current_sha,
            "uploaded_by": report.uploaded_by,
            "uploaded_at": report.uploaded_at.isoformat(),
            "counts": counts,
            "finding_count": sum(counts.values()),
        }

    def list_reports(self, fiscal_year_id: Optional[str]) -> dict:
        """The reports, newest first; every year's when *fiscal_year_id* is
        `None`."""
        current_sha = current_instruction_sha256()
        rows = ReviewRepository.list_reports(fiscal_year_id)
        return {
            "fiscal_year_id": fiscal_year_id,
            "current_instruction_sha256": current_sha,
            "total": len(rows),
            "reports": [
                {
                    **self._report_head(row.report, current_sha, row.severity_counts),
                    "examined_voucher_count": row.examined_voucher_count,
                }
                for row in rows
            ],
        }

    def get(self, report_id: str) -> dict:
        report = ReviewRepository.get_report(report_id)
        if report is None:
            raise ReviewError(
                "review_report_not_found", f"Unknown report: {report_id!r}", 404
            )
        findings = ReviewRepository.list_findings(report.id)
        examined = ReviewRepository.examined_voucher_ids(report.id)
        vouchers = ReviewRepository.vouchers(
            [*examined, *(vid for f in findings for vid in f.voucher_ids)]
        )
        severity_counts: Dict[str, int] = {}
        for finding in findings:
            severity_counts[finding.severity] = (
                severity_counts.get(finding.severity, 0) + 1
            )
        return {
            **self._report_head(report, current_instruction_sha256(), severity_counts),
            "summary_markdown": report.summary_markdown,
            "examined_voucher_count": len(examined),
            "examined_vouchers": [_voucher_json(v, vouchers.get(v)) for v in examined],
            "findings": [
                {
                    "id": f.id,
                    "position": f.position,
                    "severity": f.severity,
                    "area": f.area,
                    "title": f.title,
                    "description": f.description,
                    "rule": f.rule,
                    "amount_ore": f.amount_ore,
                    "suggested_correction": f.suggested_correction,
                    "voucher_ids": f.voucher_ids,
                    "vouchers": [
                        _voucher_json(v, vouchers.get(v)) for v in f.voucher_ids
                    ],
                }
                for f in findings
            ],
        }

    def coverage(self, fiscal_year: FiscalYear) -> dict:
        """Per voucher that a report examined or flagged: how many reports
        examined it and which reports flagged it, with what severity.

        A report that flags a voucher has examined it, whether or not it
        listed it in `examined_voucher_ids`. Flagged vouchers come first,
        the most often flagged first; the rest in date order.
        """
        reports = {
            row.report.id: row.report
            for row in ReviewRepository.list_reports(fiscal_year.id)
        }
        examined_by: Dict[str, set] = {}
        for report_id, voucher_id in ReviewRepository.examined_pairs(fiscal_year.id):
            examined_by.setdefault(voucher_id, set()).add(report_id)

        flagged: Dict[str, Dict[str, dict]] = {}
        for row in ReviewRepository.flagged_rows(fiscal_year.id):
            examined_by.setdefault(row.voucher_id, set()).add(row.report_id)
            report = reports[row.report_id]
            entry = flagged.setdefault(row.voucher_id, {}).setdefault(
                row.report_id,
                {
                    "report_id": row.report_id,
                    "agent": report.reviewer_agent,
                    "model": report.reviewer_model,
                    "severities": [],
                    "finding_ids": [],
                },
            )
            if row.severity not in entry["severities"]:
                entry["severities"].append(row.severity)
            entry["finding_ids"].append(row.finding_id)

        vouchers = ReviewRepository.vouchers(list(examined_by))
        items = []
        for voucher_id, report_ids in examined_by.items():
            flagged_by = sorted(
                flagged.get(voucher_id, {}).values(),
                key=lambda e: reports[e["report_id"]].uploaded_at,
            )
            for entry in flagged_by:
                entry["severities"].sort(key=_SEVERITY_RANK.__getitem__)
            items.append(
                {
                    **_voucher_json(voucher_id, vouchers.get(voucher_id)),
                    "examined_count": len(report_ids),
                    "flagged_count": len(flagged_by),
                    "flagged_by": flagged_by,
                }
            )

        def order(item: dict) -> tuple:
            worst = min(
                (
                    _SEVERITY_RANK[s]
                    for entry in item["flagged_by"]
                    for s in entry["severities"]
                ),
                default=len(SEVERITIES),
            )
            return (
                -item["flagged_count"],
                worst,
                item["date"] or "",
                item["series"] or "",
                item["number"] or 0,
            )

        items.sort(key=order)
        return {
            "fiscal_year_id": fiscal_year.id,
            "report_count": len(reports),
            "reports": [
                {
                    "id": r.id,
                    "agent": r.reviewer_agent,
                    "model": r.reviewer_model,
                    "uploaded_at": r.uploaded_at.isoformat(),
                }
                for r in sorted(reports.values(), key=lambda r: r.uploaded_at)
            ],
            "vouchers": items,
        }

    # -- the instruction -------------------------------------------------------

    @staticmethod
    def fiscal_year(fiscal_year_id: Optional[str]) -> FiscalYear:
        """*fiscal_year_id*'s year, or the latest when it is `None`."""
        if fiscal_year_id is not None:
            fy = PeriodRepository.get_fiscal_year(fiscal_year_id)
            if fy is None:
                raise ReviewError(
                    "fiscal_year_not_found",
                    f"Unknown fiscal year: {fiscal_year_id!r}",
                    404,
                )
            return fy
        years = PeriodRepository.list_fiscal_years()
        if not years:
            raise ReviewError("fiscal_year_not_found", "There is no fiscal year", 404)
        return max(years, key=lambda fy: fy.start_date)

    def instructions(self, fiscal_year_id: Optional[str]) -> dict:
        from repositories.agent_instruction_repo import AgentInstructionRepository

        fy = self.fiscal_year(fiscal_year_id)
        instruction = get_reviewer_instructions()
        company = AgentInstructionRepository.read_active("accounting_company")
        years = sorted(PeriodRepository.list_fiscal_years(), key=lambda y: y.start_date)
        return {
            "fiscal_year": _fiscal_year_json(fy),
            "fiscal_years": [_fiscal_year_json(y) for y in years],
            "instructions_markdown": instruction["content_markdown"],
            "instruction_sha256": instruction["sha256"],
            "read_endpoints": read_endpoints(fy.id),
            "company_instructions": {
                "content_markdown": company["content_markdown"],
                "version": company["version"],
                "updated_at": company["updated_at"],
                "is_default": company["is_default"],
            },
            "upload": {"method": "POST", "path": "/api/v1/review/reports"},
            "report_schema": ReviewReportIn.model_json_schema(),
        }


def read_endpoints(fiscal_year_id: str) -> Dict[str, str]:
    """Where the books are, with the year filled in. Existing read routes
    only -- the review needs no route of its own to read
    (`tests/test_review_instructions.py` checks each against the app)."""
    fy = fiscal_year_id
    return {
        "sie4": f"/api/v1/bokslut/{fy}/filer/bokforing.si",
        "vouchers": (
            f"/api/v1/vouchers?fiscal_year_id={fy}&status=posted"
            "&sort_by=number&sort_order=asc&limit=100&offset=0"
        ),
        "voucher": "/api/v1/vouchers/{voucher_id}",
        "source_context": "/api/v1/vouchers/{voucher_id}/source-context",
        "voucher_audit": "/api/v1/vouchers/{voucher_id}/audit",
        "correction_notes": "/api/v1/vouchers/{voucher_id}/correction-notes",
        "intake_file": "/api/v1/intake/{source_id}/file",
        "bank_input_file": "/api/v1/bank-inputs/{bank_input_id}/file",
        "open_bank_transactions": (
            f"/api/v1/bank-inputs/transactions/open?fiscal_year_id={fy}"
        ),
        "accounts": "/api/v1/accounts",
        "opening_balances": f"/api/v1/fiscal-years/{fy}/opening-balances",
        "balance_sheet": f"/api/v1/reports/balance-sheet?fiscal_year_id={fy}",
        "income_statement": f"/api/v1/reports/income-statement?fiscal_year_id={fy}",
        "general_ledger": (
            f"/api/v1/reports/general-ledger/{{account_code}}?fiscal_year_id={fy}"
        ),
        "bokslut": f"/api/v1/bokslut/{fy}",
        "vat_declaration_eskd": f"/api/v1/bokslut/{fy}/filer/moms.eskd",
        "invoices": f"/api/v1/invoices?fiscal_year_id={fy}",
        "payroll_runs": f"/api/v1/payroll/runs?fiscal_year_id={fy}",
        "accounting_corrections": "/api/v1/accounting-corrections",
        "company_info": "/api/v1/company-info",
    }
