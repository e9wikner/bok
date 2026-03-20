"""Tests for ledger service (core accounting logic)."""

import pytest
from datetime import date
from domain.validation import ValidationError


def test_create_voucher_and_post(ledger_service, test_period):
    """Test creating and posting a voucher."""
    # Create voucher
    voucher = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 20),
        period_id=test_period.id,
        description="Test transaction",
        rows_data=[
            {"account": "1510", "debit": 10000, "credit": 0},
            {"account": "3011", "debit": 0, "credit": 10000},
        ],
        created_by="test"
    )
    
    assert voucher.id is not None
    assert voucher.series.value == "A"
    assert voucher.number == 1
    assert len(voucher.rows) == 2
    assert voucher.status.value == "draft"
    assert voucher.is_balanced()
    
    # Post voucher
    posted = ledger_service.post_voucher(voucher.id, actor="test")
    
    assert posted.status.value == "posted"
    assert posted.posted_at is not None


def test_voucher_balance_validation(ledger_service, test_period):
    """Test that unbalanced vouchers are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        ledger_service.create_voucher(
            series="A",
            date=date(2026, 3, 20),
            period_id=test_period.id,
            description="Unbalanced",
            rows_data=[
                {"account": "1510", "debit": 10000, "credit": 0},
                {"account": "3011", "debit": 0, "credit": 5000},  # Not balanced!
            ],
            created_by="test"
        )
    
    assert exc_info.value.code == "balance_error"


def test_trial_balance(ledger_service, test_period):
    """Test trial balance calculation."""
    # Create and post some vouchers
    v1 = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 1),
        period_id=test_period.id,
        description="Invoice",
        rows_data=[
            {"account": "1510", "debit": 12500000, "credit": 0},  # 125,000 kr
            {"account": "3011", "debit": 0, "credit": 10000000},  # 100,000 kr
            {"account": "2610", "debit": 0, "credit": 2500000},   # 25,000 kr
        ],
        created_by="test"
    )
    ledger_service.post_voucher(v1.id, actor="test")
    
    # Get trial balance
    balances = ledger_service.get_trial_balance(test_period.id)
    
    assert balances["1510"]["debit"] == 12500000
    assert balances["1510"]["credit"] == 0
    assert balances["3011"]["debit"] == 0
    assert balances["3011"]["credit"] == 10000000
    assert balances["2610"]["debit"] == 0
    assert balances["2610"]["credit"] == 2500000


def test_lock_period(ledger_service, test_period):
    """Test period locking (varaktighet requirement)."""
    # Lock period
    locked = ledger_service.lock_period(test_period.id, actor="test")
    
    assert locked.locked is True
    assert locked.locked_at is not None
    
    # Try to add voucher to locked period
    with pytest.raises(ValidationError) as exc_info:
        ledger_service.create_voucher(
            series="A",
            date=date(2026, 3, 20),
            period_id=test_period.id,
            description="Should fail",
            rows_data=[
                {"account": "1510", "debit": 10000, "credit": 0},
                {"account": "3011", "debit": 0, "credit": 10000},
            ],
            created_by="test"
        )
    
    assert exc_info.value.code == "period_locked"


def test_correction_voucher(ledger_service, test_period):
    """Test creating correction voucher (B-series)."""
    # Create and post original voucher
    original = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 1),
        period_id=test_period.id,
        description="Original",
        rows_data=[
            {"account": "1510", "debit": 10000, "credit": 0},
            {"account": "3011", "debit": 0, "credit": 10000},
        ],
        created_by="test"
    )
    ledger_service.post_voucher(original.id, actor="test")
    
    # Create correction (reverse original + post corrected)
    correction = ledger_service.create_correction(
        original_voucher_id=original.id,
        correction_rows=[
            {"account": "1510", "debit": 0, "credit": 10000},  # Reverse
            {"account": "3011", "debit": 10000, "credit": 0},  # Reverse
            {"account": "1510", "debit": 15000, "credit": 0},  # Corrected
            {"account": "3011", "debit": 0, "credit": 15000},  # Corrected
        ],
        actor="test"
    )
    
    assert correction.series.value == "B"
    assert correction.number == 1
    assert correction.correction_of == original.id
    assert correction.is_balanced()


def test_account_ledger(ledger_service, test_period):
    """Test account ledger (hovedbok) retrieval."""
    # Create and post voucher
    voucher = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 20),
        period_id=test_period.id,
        description="Test",
        rows_data=[
            {"account": "1510", "debit": 10000, "credit": 0},
            {"account": "3011", "debit": 0, "credit": 10000},
        ],
        created_by="test"
    )
    ledger_service.post_voucher(voucher.id, actor="test")
    
    # Get ledger for account 1510
    ledger_rows = ledger_service.get_account_ledger("1510", test_period.id)
    
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["debit"] == 10000
    assert ledger_rows[0]["credit"] == 0
    assert ledger_rows[0]["balance"] == 10000


def test_audit_history(ledger_service, test_period):
    """Test audit trail logging."""
    # Create and post voucher
    voucher = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 20),
        period_id=test_period.id,
        description="Test",
        rows_data=[
            {"account": "1510", "debit": 10000, "credit": 0},
            {"account": "3011", "debit": 0, "credit": 10000},
        ],
        created_by="test"
    )
    ledger_service.post_voucher(voucher.id, actor="test")
    
    # Get audit history
    history = ledger_service.get_audit_history("voucher", voucher.id)
    
    assert len(history) >= 2  # At least created + posted
    assert history[0]["action"] == "created"
    assert any(h["action"] == "posted" for h in history)
