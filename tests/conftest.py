"""Test configuration and fixtures."""

import pytest
import tempfile
import os
from datetime import date
from db.database import db
from services.ledger import LedgerService
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository


@pytest.fixture(scope="function")
def test_db():
    """Create temporary test database."""
    # Create temp db file
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Use temp db
    db.db_path = path
    db.connection = None
    
    # Initialize
    db.init_db()
    
    yield db
    
    # Cleanup
    db.disconnect()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def ledger_service(test_db):
    """Create ledger service with test database."""
    service = LedgerService()
    
    # Load default accounts
    default_accounts = [
        ("1510", "Kundfordringar", "asset"),
        ("3011", "Försäljning tjänster", "revenue"),
        ("2610", "Utgående moms", "vat_out"),
    ]
    
    for code, name, acc_type in default_accounts:
        AccountRepository.create(code, name, acc_type)
    
    return service


@pytest.fixture
def fiscal_year(ledger_service):
    """Create a test fiscal year."""
    return ledger_service.periods.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31)
    )


@pytest.fixture
def test_period(ledger_service, fiscal_year):
    """Create a test period."""
    return ledger_service.periods.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31)
    )
