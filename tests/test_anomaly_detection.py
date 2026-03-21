"""Tests for anomaly detection service."""

import pytest
from datetime import date, datetime
from unittest.mock import MagicMock

from services.anomaly_detection import (
    AnomalyDetectionService,
    AnomalyThresholds,
    AnomalySeverity,
    AnomalyType,
)
from domain.models import Voucher, VoucherRow
from domain.types import VoucherStatus, VoucherSeries


def test_anomaly_thresholds_defaults():
    """Test default anomaly thresholds."""
    t = AnomalyThresholds()
    assert t.unusual_amount_z_score == 2.5
    assert t.min_transactions_for_stats == 5
    assert t.frequent_small_tx_count == 10


def test_anomaly_thresholds_from_dict():
    """Test loading thresholds from dict."""
    data = {"unusual_amount_z_score": 3.0, "custom_field": "ignored"}
    t = AnomalyThresholds.from_dict(data)
    assert t.unusual_amount_z_score == 3.0


def test_anomaly_to_dict():
    """Test anomaly serialization."""
    from services.anomaly_detection import Anomaly
    
    a = Anomaly(
        id="test-123",
        anomaly_type=AnomalyType.UNUSUAL_AMOUNT,
        severity=AnomalySeverity.WARNING,
        entity_type="voucher",
        entity_id="v-1",
        title="Test anomaly",
        description="Test description",
        score=0.75,
        details={"key": "value"},
    )
    
    d = a.to_dict()
    assert d["type"] == "unusual_amount"
    assert d["severity"] == "warning"
    assert d["score"] == 0.75


def test_wrong_vat_code_rule():
    """Test VAT code anomaly detection for salary accounts."""
    from services.anomaly_detection import WrongVATCodeRule
    
    rule = WrongVATCodeRule(AnomalyThresholds())
    
    # Mock voucher with salary account (7xxx) having VAT
    mock_account = MagicMock()
    mock_account.vat_code = "MP1"  # Wrong for salary
    
    context = {
        "vouchers": [],  # Would need real vouchers
        "accounts": {"7010": mock_account},
    }
    
    # Rule should check and return appropriate anomalies
    # This is a basic structure test
    result = rule.check(context)
    assert isinstance(result, list)


def test_duplicate_entry_rule():
    """Test duplicate detection rule."""
    from services.anomaly_detection import DuplicateEntryRule
    
    rule = DuplicateEntryRule(AnomalyThresholds(duplicate_window_days=3))
    
    # Create two vouchers with same amount and date
    v1 = Voucher(
        id="v1",
        series=VoucherSeries.A,
        number=1,
        date=date(2025, 3, 15),
        period_id="p1",
        description="Test",
        status=VoucherStatus.POSTED,
        rows=[
            VoucherRow(id="r1", voucher_id="v1", account_code="1930", debit=10000, credit=0),
            VoucherRow(id="r2", voucher_id="v1", account_code="3010", debit=0, credit=10000),
        ],
    )
    v2 = Voucher(
        id="v2",
        series=VoucherSeries.A,
        number=2,
        date=date(2025, 3, 15),  # Same date
        period_id="p1",
        description="Test 2",
        status=VoucherStatus.POSTED,
        rows=[
            VoucherRow(id="r3", voucher_id="v2", account_code="1930", debit=10000, credit=0),
            VoucherRow(id="r4", voucher_id="v2", account_code="3010", debit=0, credit=10000),
        ],
    )
    
    context = {"vouchers": [v1, v2]}
    result = rule.check(context)
    
    # Should detect potential duplicate
    assert len(result) > 0
    assert result[0].anomaly_type == AnomalyType.DUPLICATE_ENTRY


def test_missing_counter_entry_rule():
    """Test missing counter-entry detection."""
    from services.anomaly_detection import MissingCounterEntryRule
    
    rule = MissingCounterEntryRule(AnomalyThresholds())
    
    # Voucher with only debit entries
    v = Voucher(
        id="v1",
        series=VoucherSeries.A,
        number=1,
        date=date(2025, 3, 15),
        period_id="p1",
        description="One-sided",
        status=VoucherStatus.POSTED,
        rows=[
            VoucherRow(id="r1", voucher_id="v1", account_code="1930", debit=10000, credit=0),
            VoucherRow(id="r2", voucher_id="v1", account_code="1510", debit=5000, credit=0),
        ],
    )
    
    context = {"vouchers": [v]}
    result = rule.check(context)
    
    assert len(result) > 0
    assert result[0].anomaly_type == AnomalyType.MISSING_COUNTER_ENTRY


def test_weekend_transaction_rule():
    """Test weekend transaction detection."""
    from services.anomaly_detection import WeekendTransactionRule
    
    rule = WeekendTransactionRule(AnomalyThresholds())
    
    # Saturday transaction
    v = Voucher(
        id="v1",
        series=VoucherSeries.A,
        number=1,
        date=date(2025, 3, 15),  # Saturday
        period_id="p1",
        description="Weekend",
        status=VoucherStatus.POSTED,
        rows=[],
    )
    
    context = {"vouchers": [v]}
    result = rule.check(context)
    
    assert len(result) > 0
    assert result[0].anomaly_type == AnomalyType.WEEKEND_TRANSACTION


def test_anomaly_types_enum():
    """Test that all anomaly types are defined."""
    types = [
        AnomalyType.UNMATCHED_TRANSACTION,
        AnomalyType.UNUSUAL_AMOUNT,
        AnomalyType.WRONG_VAT_CODE,
        AnomalyType.MISSING_COUNTER_ENTRY,
        AnomalyType.FREQUENT_SMALL_TRANSACTIONS,
        AnomalyType.UNUSUAL_BALANCE_CHANGE,
        AnomalyType.DUPLICATE_ENTRY,
        AnomalyType.MISSING_ATTACHMENT,
        AnomalyType.ABNORMAL_VOUCHER_COUNT,
        AnomalyType.WEEKEND_TRANSACTION,
        AnomalyType.ROUND_AMOUNT,
        AnomalyType.SEASONAL_DEVIATION,
    ]
    for t in types:
        assert isinstance(t.value, str)


def test_anomaly_severity_levels():
    """Test severity levels."""
    assert AnomalySeverity.INFO.value == "info"
    assert AnomalySeverity.WARNING.value == "warning"
    assert AnomalySeverity.CRITICAL.value == "critical"
