"""`GET /api/v1/audit/log`: the audit trail, newest first, a page at a time."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.database import db


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


def _log(n_vouchers: int, n_periods: int) -> None:
    """Write entries with distinct timestamps, oldest first: vouchers, then periods."""
    start = datetime(2026, 1, 1, 12, 0, 0)
    # Entity types of the test's own, so whatever the fixture logged is outside them.
    rows = [("t_voucher", "created")] * n_vouchers + [
        ("t_period", "locked")
    ] * n_periods
    for i, (entity_type, action) in enumerate(rows):
        db.execute(
            "INSERT INTO audit_log (id, entity_type, entity_id, action, actor, payload, timestamp)"
            " VALUES (?, ?, ?, ?, 'test', NULL, ?)",
            (
                f"a{i:03}",
                entity_type,
                f"e{i:03}",
                action,
                (start + timedelta(minutes=i)).isoformat(),
            ),
        )
    db.commit()


def _ids(response) -> list:
    return [e["entity_id"] for e in response.json()["entries"]]


def test_pages_back_through_the_whole_trail(client, auth_headers):
    _log(5, 0)

    first = client.get(
        "/api/v1/audit/log?limit=2&entity_type=t_voucher", headers=auth_headers
    )
    assert first.status_code == 200
    assert _ids(first) == ["e004", "e003"]
    assert first.json()["has_more"] is True

    last = client.get(
        "/api/v1/audit/log?limit=2&offset=4&entity_type=t_voucher", headers=auth_headers
    )
    assert _ids(last) == ["e000"]
    assert last.json()["has_more"] is False


def test_filters_before_the_limit(client, auth_headers):
    """The newest entries are periods; a voucher page still holds vouchers,
    not an empty page cut from the periods."""
    _log(3, 4)

    vouchers = client.get(
        "/api/v1/audit/log?limit=2&entity_type=t_voucher", headers=auth_headers
    )
    assert _ids(vouchers) == ["e002", "e001"]
    assert vouchers.json()["has_more"] is True

    both = client.get(
        "/api/v1/audit/log?limit=10&entity_type=t_voucher&entity_type=t_period",
        headers=auth_headers,
    )
    assert len(_ids(both)) == 7

    locked = client.get(
        "/api/v1/audit/log?action=locked&entity_type=t_period", headers=auth_headers
    )
    assert _ids(locked) == ["e006", "e005", "e004", "e003"]
