"""Tests for bank integration, categorization, and compliance services."""

import pytest
import tempfile
import os
import uuid
from datetime import date, datetime

from db.database import db
from services.bank_integration import BankIntegrationService
from services.categorization import CategorizationService
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
    db._local = __import__('threading').local()
    
    db.init_db()
    
    yield db
    
    db.disconnect()
    db.db_path = old_path
    db._local = __import__('threading').local()
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
            {"date": "2026-01-15", "amount": -500.0, "description": "TELIA MOBILRÄKNING",
             "external_id": "tx-001"},
            {"date": "2026-01-16", "amount": 10000.0, "description": "Swish betalning från kund",
             "external_id": "tx-002"},
            {"date": "2026-01-17", "amount": -2500.0, "description": "Hyra lokal januari",
             "external_id": "tx-003"},
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
        
        service.import_transactions(conn.id, [
            {"date": "2026-02-01", "amount": -100.0, "description": "Test expense"},
            {"date": "2026-02-02", "amount": 200.0, "description": "Test income"},
        ])
        
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
        
        imported, skipped = service.import_csv(conn.id, csv_content)
        assert imported == 3

    def test_pending_count(self):
        service = BankIntegrationService()
        conn = service.create_connection(provider="manual", bank_name="Test")
        
        service.import_transactions(conn.id, [
            {"date": "2026-01-01", "amount": -100.0, "description": "Test"},
        ])
        
        assert service.get_pending_count() == 1

    def test_sync_summary(self):
        service = BankIntegrationService()
        conn = service.create_connection(provider="manual", bank_name="Test")
        service.import_transactions(conn.id, [
            {"date": "2026-01-01", "amount": -100.0, "description": "Test"},
        ])
        
        summary = service.get_sync_summary()
        assert summary["total_pending"] == 1
        assert len(summary["connections"]) == 1


class TestCategorization:
    """Test automatic categorization engine."""

    def _create_tx(self, description, amount=-500.0, counterpart=None):
        """Helper to create a transaction and return it."""
        bank = BankIntegrationService()
        conn = bank.create_connection(provider="manual", bank_name="Test")
        bank.import_transactions(conn.id, [{
            "date": "2026-01-15",
            "amount": amount,
            "description": description,
            "counterpart_name": counterpart,
            "external_id": str(uuid.uuid4()),
        }])
        return bank.get_transactions(status="pending")[0]

    def test_categorize_telecom(self):
        cat = CategorizationService()
        tx = self._create_tx("TELIA MOBILRÄKNING JAN")
        result = cat.categorize_transaction(tx)
        assert result is not None
        assert result.account_code == "6211"

    def test_categorize_rent(self):
        cat = CategorizationService()
        tx = self._create_tx("Hyra kontor januari", amount=-15000.0)
        result = cat.categorize_transaction(tx)
        assert result is not None
        assert result.account_code == "5010"

    def test_categorize_fuel(self):
        cat = CategorizationService()
        tx = self._create_tx("CIRCLE K STOCKHOLM", amount=-850.0)
        result = cat.categorize_transaction(tx)
        assert result is not None
        assert result.account_code == "5611"

    def test_categorize_swish_income(self):
        cat = CategorizationService()
        tx = self._create_tx("Swish betalning kund", amount=5000.0)
        result = cat.categorize_transaction(tx)
        assert result is not None
        assert result.account_code == "3011"

    def test_categorize_insurance(self):
        cat = CategorizationService()
        tx = self._create_tx("Trygg-Hansa företagsförsäkring", amount=-3500.0)
        result = cat.categorize_transaction(tx)
        assert result is not None
        assert result.account_code == "6310"

    def test_categorize_software(self):
        cat = CategorizationService()
        tx = self._create_tx("GITHUB SUBSCRIPTION", amount=-90.0)
        result = cat.categorize_transaction(tx)
        assert result is not None
        assert result.account_code == "6540"

    def test_categorize_bank_fee(self):
        cat = CategorizationService()
        tx = self._create_tx("Bankavgift kontoavgift", amount=-99.0)
        result = cat.categorize_transaction(tx)
        assert result is not None
        assert result.account_code == "6570"

    def test_uncategorized_transaction(self):
        cat = CategorizationService()
        tx = self._create_tx("XYZZY MYSTERIOUS PAYMENT", amount=-1234.0)
        result = cat.categorize_transaction(tx)
        # Unknown transactions should return None
        assert result is None

    def test_categorize_pending_batch(self):
        bank = BankIntegrationService()
        cat = CategorizationService()
        conn = bank.create_connection(provider="manual", bank_name="Test")
        
        bank.import_transactions(conn.id, [
            {"date": "2026-01-01", "amount": -500.0, "description": "Telia telefon", "external_id": "b1"},
            {"date": "2026-01-02", "amount": -15000.0, "description": "Hyra lokal", "external_id": "b2"},
            {"date": "2026-01-03", "amount": 8000.0, "description": "Swish betalning", "external_id": "b3"},
            {"date": "2026-01-04", "amount": -300.0, "description": "Random obscure text", "external_id": "b4"},
        ])
        
        results = cat.categorize_pending()
        assert results["total"] == 4
        assert results["categorized"] >= 3

    def test_add_custom_rule(self):
        cat = CategorizationService()
        rule_id = cat.add_rule(
            rule_type="keyword",
            match_description="coworking",
            match_is_expense=True,
            target_account_code="5010",
            target_vat_code="MF",
            priority=10,
        )
        assert rule_id is not None
        
        rules = cat.get_rules()
        custom = [r for r in rules if r.id == rule_id]
        assert len(custom) == 1

    def test_stats(self):
        cat = CategorizationService()
        stats = cat.get_stats()
        assert "transactions" in stats
        assert "rules" in stats


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
            (issue_id,)
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
            (issue_id,)
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
            (issue_id,)
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
                (issue_id, f"test_{sev}", sev, f"Test {sev}")
            )
        db.commit()
        
        critical = service.get_open_issues(severity="critical")
        assert len(critical) == 1
        assert critical[0].severity == "critical"
