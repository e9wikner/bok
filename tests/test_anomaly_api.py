"""Tests for anomaly detection API routes."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_anomaly_list_endpoint(client):
    """Test that anomaly list endpoint exists."""
    with patch("services.anomaly_detection.AnomalyDetectionService.analyze") as mock_analyze:
        mock_analyze.return_value = []
        response = client.get("/api/v1/anomalies")
        assert response.status_code in [200, 500]


def test_anomaly_summary_endpoint(client):
    """Test that anomaly summary endpoint exists."""
    with patch("services.anomaly_detection.AnomalyDetectionService.get_summary") as mock_summary:
        mock_summary.return_value = {
            "total_anomalies": 0,
            "by_severity": {},
            "by_type": {},
            "top_anomalies": [],
        }
        response = client.get("/api/v1/anomalies/summary")
        assert response.status_code in [200, 500]


def test_voucher_anomaly_check_endpoint(client):
    """Test that single voucher anomaly check endpoint exists."""
    with patch("services.anomaly_detection.AnomalyDetectionService.analyze_voucher") as mock_check:
        mock_check.return_value = []
        response = client.get("/api/v1/anomalies/voucher/test-voucher-id")
        assert response.status_code in [200, 500]


def test_anomaly_types_endpoint(client):
    """Test that anomaly types list endpoint works."""
    response = client.get("/api/v1/anomalies/types")
    assert response.status_code == 200
    data = response.json()
    assert "types" in data
    assert "unusual_amount" in data["types"]


def test_anomaly_thresholds_update_endpoint(client):
    """Test that thresholds update endpoint works."""
    response = client.put(
        "/api/v1/anomalies/thresholds?unusual_amount_z_score=3.0&balance_change_pct=300"
    )
    assert response.status_code == 200
    data = response.json()
    assert "thresholds" in data
    assert data["thresholds"]["unusual_amount_z_score"] == 3.0


def test_anomaly_endpoint_with_filters(client):
    """Test anomaly endpoint with query filters."""
    with patch("services.anomaly_detection.AnomalyDetectionService.analyze") as mock_analyze:
        mock_analyze.return_value = []
        response = client.get(
            "/api/v1/anomalies?period_id=test-period&rule_types=unusual_amount,duplicate_entry&min_score=0.5"
        )
        assert response.status_code in [200, 500]


def test_anomaly_response_structure():
    """Test anomaly response structure matches expected format."""
    from services.anomaly_detection import Anomaly, AnomalyType, AnomalySeverity
    
    a = Anomaly(
        id="test-123",
        anomaly_type=AnomalyType.UNUSUAL_AMOUNT,
        severity=AnomalySeverity.WARNING,
        entity_type="voucher",
        entity_id="v-1",
        title="Test",
        description="Test",
        score=0.8,
    )
    
    d = a.to_dict()
    assert "id" in d
    assert "type" in d
    assert "severity" in d
    assert "entity_type" in d
    assert "entity_id" in d
    assert "title" in d
    assert "description" in d
    assert "score" in d
    assert "details" in d
    assert "detected_at" in d
    assert "resolved" in d
