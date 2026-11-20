"""The four review tables refuse UPDATE and DELETE (migration 055)."""

import sqlite3
import uuid
from datetime import date

import pytest

from db.database import db
from repositories.account_repo import AccountRepository
from services.review import ReviewReportIn, ReviewService, current_instruction_sha256


@pytest.fixture
def stored_report(ledger_service, fiscal_year, test_period):
    for code, kind in [("1930", "asset"), ("5010", "expense")]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, code, kind)
    voucher = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 1),
        period_id=test_period.id,
        description="Hyra",
        rows_data=[
            {"account": "5010", "debit": 100, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 100},
        ],
    )
    ledger_service.post_voucher(voucher.id)
    report = ReviewReportIn.model_validate(
        {
            "id": str(uuid.uuid4()),
            "fiscal_year_id": fiscal_year.id,
            "reviewer": {"agent": "Claude Code", "model": "claude-opus-5-5"},
            "instruction_sha256": current_instruction_sha256(),
            "summary_markdown": "Granskat.",
            "examined_voucher_ids": [voucher.id],
            "findings": [
                {
                    "severity": "observation",
                    "area": "ovrigt",
                    "title": "Iakttagelse",
                    "description": "Text.",
                    "voucher_ids": [voucher.id],
                }
            ],
        }
    )
    stored, created = ReviewService().submit(report, uploaded_by="review_key")
    assert created
    return stored


TABLES = {
    "review_reports": "summary_markdown = 'ändrad'",
    "review_findings": "title = 'ändrad'",
    "review_finding_vouchers": "voucher_id = voucher_id",
    "review_examined_vouchers": "voucher_id = voucher_id",
}


@pytest.mark.parametrize("table, assignment", TABLES.items())
def test_update_is_refused(stored_report, table, assignment):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(f"UPDATE {table} SET {assignment}")
    db.rollback()


@pytest.mark.parametrize("table", TABLES)
def test_delete_is_refused(stored_report, table):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(f"DELETE FROM {table}")
    db.rollback()
    assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
