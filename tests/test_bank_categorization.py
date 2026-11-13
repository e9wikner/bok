"""Tests for bank integration and compliance services."""

import os
import tempfile
import uuid

import pytest

from db.database import db
from services.bank_integration import BankIntegrationService
from services.compliance import ComplianceService


@pytest.fixture(autouse=True)
def setup_db():
    """Set up a fresh test database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Patch global db
    old_path = db.db_path
    db.db_path = path
    # Reset thread-local connection
    db._local = __import__("threading").local()

    db.init_db()

    yield db

    db.disconnect()
    db.db_path = old_path
    db._local = __import__("threading").local()
    if os.path.exists(path):
        os.remove(path)


class TestBankIntegration:
    """Test bank connection and transaction import."""

    def test_create_connection(self):
        service = BankIntegrationService()
        conn = service.create_connection(
            provider="manual",
            bank_name="Nordea",
            account_number="****1234",
            currency="SEK",
        )
        assert conn.id is not None
        assert conn.bank_name == "Nordea"
        assert conn.status == "active"

    def test_list_connections(self):
        service = BankIntegrationService()
        service.create_connection(provider="manual", bank_name="SEB")
        service.create_connection(provider="manual", bank_name="Nordea")

        connections = service.get_connections()
        assert len(connections) == 2

    def test_import_transactions(self):
        service = BankIntegrationService()
        conn = service.create_connection(provider="manual", bank_name="SEB")

        transactions = [
            {
                "date": "2026-01-15",
                "amount": -500.0,
                "description": "TELIA MOBILRÄKNING",
                "external_id": "tx-001",
            },
            {
                "date": "2026-01-16",
                "amount": 10000.0,
                "description": "Swish betalning från kund",
                "external_id": "tx-002",
            },
            {
                "date": "2026-01-17",
                "amount": -2500.0,
                "description": "Hyra lokal januari",
                "external_id": "tx-003",
            },
        ]

        imported, skipped = service.import_transactions(conn.id, transactions)
        assert imported == 3
        assert skipped == 0

        # Test deduplication
        imported2, skipped2 = service.import_transactions(conn.id, transactions)
        assert imported2 == 0
        assert skipped2 == 3

    def test_get_transactions(self):
        service = BankIntegrationService()
        conn = service.create_connection(provider="manual", bank_name="Handelsbanken")

        service.import_transactions(
            conn.id,
            [
                {"date": "2026-02-01", "amount": -100.0, "description": "Test expense"},
                {"date": "2026-02-02", "amount": 200.0, "description": "Test income"},
            ],
        )

        all_tx = service.get_transactions()
        assert len(all_tx) == 2

        pending = service.get_transactions(status="pending")
        assert len(pending) == 2

    def test_csv_import(self):
        service = BankIntegrationService()
        conn = service.create_connection(provider="manual", bank_name="Swedbank")

        csv_content = """Datum;Belopp;Text;Mottagare
2026-01-10;-350,50;Circle K bensin;Circle K
2026-01-11;5000,00;Swish från kund;Johan AB
2026-01-12;-1200,00;Telia faktura;Telia"""

        result = service.import_csv(conn.id, csv_content)
        assert result.imported_count == 3


class TestCompliance:
    """Test BFL compliance checks."""

    def test_run_checks_empty_db(self):
        service = ComplianceService()
        results = service.run_all_checks()
        assert results["checks_run"] == 8
        assert isinstance(results["total_open"], int)

    def test_get_open_issues(self):
        service = ComplianceService()
        issues = service.get_open_issues()
        assert isinstance(issues, list)

    def test_acknowledge_and_resolve(self):
        service = ComplianceService()

        issue_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO compliance_checks
               (id, check_type, severity, status, title, description)
               VALUES (?, 'test', 'warning', 'open', 'Test issue', 'Test description')""",
            (issue_id,),
        )
        db.commit()

        service.acknowledge_issue(issue_id)
        issues = service.get_open_issues()
        assert not any(i.id == issue_id for i in issues)

    def test_resolve_issue(self):
        service = ComplianceService()

        issue_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO compliance_checks
               (id, check_type, severity, status, title, description)
               VALUES (?, 'test2', 'error', 'open', 'Test 2', 'Desc 2')""",
            (issue_id,),
        )
        db.commit()

        service.resolve_issue(issue_id, resolved_by="test")
        issues = service.get_open_issues()
        assert not any(i.id == issue_id for i in issues)

    def test_false_positive(self):
        service = ComplianceService()

        issue_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO compliance_checks
               (id, check_type, severity, status, title, description)
               VALUES (?, 'test3', 'info', 'open', 'FP test', 'FP desc')""",
            (issue_id,),
        )
        db.commit()

        service.mark_false_positive(issue_id)
        issues = service.get_open_issues()
        assert not any(i.id == issue_id for i in issues)

    def test_severity_filter(self):
        service = ComplianceService()

        for sev in ["critical", "error", "warning"]:
            issue_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO compliance_checks
                   (id, check_type, severity, status, title, description)
                   VALUES (?, ?, ?, 'open', ?, 'Test')""",
                (issue_id, f"test_{sev}", sev, f"Test {sev}"),
            )
        db.commit()

        critical = service.get_open_issues(severity="critical")
        assert len(critical) == 1
        assert critical[0].severity == "critical"

    def test_issue_resolves_when_condition_is_gone(self):
        """A period that gets locked takes its 'ej stängd' issue with it."""
        service = ComplianceService()
        db.execute("""INSERT INTO fiscal_years (id, start_date, end_date)
               VALUES ('fy-old', '2020-01-01', '2020-12-31')""")
        db.execute(
            """INSERT INTO periods (id, fiscal_year_id, year, month, start_date, end_date)
               VALUES ('p-old', 'fy-old', 2020, 1, '2020-01-01', '2020-01-31')"""
        )
        db.commit()

        service.run_all_checks()
        open_ = [i for i in service.get_open_issues() if i.entity_id == "p-old"]
        assert len(open_) == 1
        assert "/api/v1" not in open_[0].recommendation

        db.execute("UPDATE periods SET locked = 1 WHERE id = 'p-old'")
        db.commit()
        service.run_all_checks()
        assert not any(i.entity_id == "p-old" for i in service.get_open_issues())
        row = db.execute(
            "SELECT status, resolved_by FROM compliance_checks WHERE entity_id = 'p-old'"
        ).fetchone()
        assert (row["status"], row["resolved_by"]) == ("resolved", "system")

    def test_manual_issue_is_not_auto_resolved(self):
        service = ComplianceService()
        issue_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO compliance_checks
               (id, check_type, severity, status, title, description)
               VALUES (?, 'large_amount', 'info', 'open', 'Stor', 'Desc')""",
            (issue_id,),
        )
        db.commit()
        service.run_all_checks()
        assert any(i.id == issue_id for i in service.get_open_issues())
