"""SRU mapping diff against the BAS standard and inheritance report (#47)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from domain.sru_fields import (
    MAPPING_DIFFERS_FROM_STANDARD,
    MAPPING_MISSING,
    MAPPING_OK,
    MAPPING_UNKNOWN_FIELD,
    is_known_mapping_field,
    mapping_status,
    matches_standard,
)
from repositories.account_repo import AccountRepository
from repositories.opening_balance_repo import OpeningBalanceRepository
from repositories.period_repo import PeriodRepository
from repositories.sru_mapping_repo import SruMappingRepository


def _status(**kwargs):
    base = dict(
        has_balance=True,
        derived=False,
        current_field=None,
        previous_field=None,
        standard_field="7281",
        year_has_saved_mappings=False,
    )
    base.update(kwargs)
    return mapping_status(**base)


class TestMappingStatus:
    def test_no_previous_is_ok(self):
        assert _status() == MAPPING_OK

    def test_previous_equal_to_standard_is_ok(self):
        assert _status(previous_field="7281") == MAPPING_OK

    def test_previous_other_than_standard_differs(self):
        assert (
            _status(previous_field="7369", standard_field="7368")
            == MAPPING_DIFFERS_FROM_STANDARD
        )

    def test_previous_without_standard_differs(self):
        assert (
            _status(previous_field="7281", standard_field=None, has_balance=False)
            == MAPPING_DIFFERS_FROM_STANDARD
        )

    def test_unknown_previous_field(self):
        assert _status(previous_field="9999") == MAPPING_UNKNOWN_FIELD

    def test_unknown_current_field(self):
        assert (
            _status(current_field="12345", year_has_saved_mappings=True)
            == MAPPING_UNKNOWN_FIELD
        )

    def test_unknown_wins_over_differs(self):
        # 9999 is both unlike the standard and unknown; unknown is reported.
        assert _status(previous_field="9999") == MAPPING_UNKNOWN_FIELD

    def test_balance_without_any_field_is_missing(self):
        assert _status(standard_field=None) == MAPPING_MISSING

    def test_missing_wins_over_unknown(self):
        assert (
            _status(
                previous_field="9999",
                standard_field=None,
            )
            == MAPPING_MISSING
        )

    def test_saved_year_mapping_without_the_account_is_missing(self):
        # The export reads only the saved mapping once a year has one.
        assert _status(year_has_saved_mappings=True) == MAPPING_MISSING

    def test_no_balance_is_never_missing(self):
        assert _status(has_balance=False, standard_field=None) == MAPPING_OK

    def test_derived_result_account_is_never_missing(self):
        assert _status(derived=True, standard_field=None) == MAPPING_OK

    def test_single_half_of_sign_split_standard_matches(self):
        assert matches_standard("7411", "7411/7510")
        assert matches_standard("7510", "7411/7510")
        assert not matches_standard("7412", "7411/7510")

    def test_known_fields(self):
        assert is_known_mapping_field("7281")
        assert is_known_mapping_field("7411/7510")
        assert is_known_mapping_field("7450/7550")
        assert is_known_mapping_field("7416/7520")
        assert not is_known_mapping_field("9999")
        assert not is_known_mapping_field("7650")  # INK2S, derived


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def years(test_db):
    """2025 (with a saved mapping) and 2026 (none), balances on 2026."""
    for code, name, kind in [
        ("1930", "Företagskonto", "asset"),
        ("1300", "Konto utan standard", "asset"),
        ("1510", "Kundfordringar", "asset"),
        ("2510", "Skatteskulder", "liability"),
        ("2610", "Utgående moms 25%", "vat_out"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, kind)
    previous = PeriodRepository.create_fiscal_year(date(2025, 1, 1), date(2025, 12, 31))
    current = PeriodRepository.create_fiscal_year(date(2026, 1, 1), date(2026, 12, 31))
    # 2026's IB is carried forward from 2025.
    OpeningBalanceRepository.replace_stated(
        previous.id,
        {"1930": 10000, "1300": 5000, "2610": -15000},
        actor="test",
    )
    SruMappingRepository.replace(
        previous.id,
        {"1930": "7281", "1510": "9999", "2510": "7369", "1300": "7281"},
    )
    test_db.commit()
    return previous, current


def _rows(body):
    return {row["account_code"]: row for row in body["rows"]}


def test_diff_derives_status_per_account(client, auth_headers, years):
    previous, current = years

    resp = client.get(
        f"/api/v1/fiscal-years/{current.id}/sru-mappings/diff", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["fiscal_year_id"] == current.id
    assert body["previous_fiscal_year_id"] == previous.id
    rows = _rows(body)
    assert rows["1930"] == {
        "account_code": "1930",
        "account_name": "Företagskonto",
        "has_balance": True,
        "current_field": None,
        "previous_field": "7281",
        "standard_field": "7281",
        "status": "ok",
    }
    assert rows["2510"]["status"] == "differs_from_standard"
    assert rows["2510"]["standard_field"] == "7368"
    assert rows["1510"]["status"] == "unknown_field"
    # Balance, no saved mapping this year, no standard: the export drops it.
    assert rows["1300"]["has_balance"] is True
    assert rows["1300"]["standard_field"] is None
    assert rows["1300"]["status"] == "missing"
    # No previous mapping, standard applies.
    assert rows["2610"]["previous_field"] is None
    assert rows["2610"]["status"] == "ok"


def test_diff_without_previous_year(client, auth_headers, years):
    previous, _ = years

    resp = client.get(
        f"/api/v1/fiscal-years/{previous.id}/sru-mappings/diff", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["previous_fiscal_year_id"] is None
    rows = _rows(body)
    assert rows["1930"]["current_field"] == "7281"
    assert rows["1930"]["previous_field"] is None


def test_diff_unknown_year_is_404(client, auth_headers, test_db):
    resp = client.get(
        "/api/v1/fiscal-years/nope/sru-mappings/diff", headers=auth_headers
    )
    assert resp.status_code == 404


def test_diff_requires_auth(client, years):
    _, current = years
    resp = client.get(f"/api/v1/fiscal-years/{current.id}/sru-mappings/diff")
    assert resp.status_code == 401


def test_inherit_dry_run_reports_and_writes_nothing(client, auth_headers, years):
    previous, current = years
    SruMappingRepository.replace(current.id, {"1930": "7281"})

    resp = client.post(
        f"/api/v1/fiscal-years/{current.id}/sru-mappings/inherit-previous",
        params={"dry_run": "true"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["fiscal_year_id"] == current.id
    assert body["source_fiscal_year_id"] == previous.id
    assert body["copied"] == 4
    assert body["dry_run"] is True
    review = {item["account_code"]: item for item in body["needs_review"]}
    assert review["2510"]["status"] == "differs_from_standard"
    assert review["2510"]["previous_field"] == "7369"
    assert review["2510"]["standard_field"] == "7368"
    assert review["1510"]["status"] == "unknown_field"
    # 2610 carries a balance; once 2025's mapping is inherited it has none.
    assert review["2610"]["status"] == "missing"
    assert "1930" not in review
    # 1300 is mapped by the inherited mapping, though not by the standard.
    assert review["1300"]["status"] == "differs_from_standard"
    assert SruMappingRepository.for_year(current.id) == {"1930": "7281"}


def test_inherit_writes_and_reports_the_same(client, auth_headers, years):
    previous, current = years
    url = f"/api/v1/fiscal-years/{current.id}/sru-mappings/inherit-previous"

    dry = client.post(url, params={"dry_run": "true"}, headers=auth_headers).json()
    real = client.post(url, headers=auth_headers)

    assert real.status_code == 200
    body = real.json()
    assert body["dry_run"] is False
    assert body["copied"] == 4
    assert body["needs_review"] == dry["needs_review"]
    assert SruMappingRepository.for_year(current.id) == SruMappingRepository.for_year(
        previous.id
    )


def test_inherit_without_previous_year_is_404(client, auth_headers, years):
    previous, _ = years
    resp = client.post(
        f"/api/v1/fiscal-years/{previous.id}/sru-mappings/inherit-previous",
        params={"dry_run": "true"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
