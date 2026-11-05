"""Riksbank's daily rates and converting a foreign amount (migration 045,
`services/exchange_rates.py`, `domain/exchange_rate.py`). Riksbank is never
called: every test hands the service its own fetcher."""

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from db.database import db
from domain.exchange_rate import check_settles_converted, format_amount
from domain.validation import ValidationError
from services.exchange_rates import ExchangeRateService

# 2026-10-10 and -11 are a Saturday and a Sunday.
_EUR = [
    {"date": "2026-10-08", "value": 11.194},
    {"date": "2026-10-09", "value": 11.1675},
]


class _Fetcher:
    def __init__(self, observations=None, error=None):
        self.observations = observations if observations is not None else _EUR
        self.error = error
        self.calls = []

    def __call__(self, series, from_date, to_date):
        self.calls.append((series, from_date, to_date))
        if self.error is not None:
            raise self.error
        return self.observations


def test_a_weekend_takes_the_last_banking_day_before_it(test_db):
    fetch = _Fetcher()
    rate = ExchangeRateService(fetch).rate("EUR", date(2026, 10, 11))

    assert rate.observation_date == date(2026, 10, 9)
    assert rate.requested_date == date(2026, 10, 11)
    assert rate.rate == Decimal("11.1675")
    assert rate.series_id == "SEKEURPMI"
    assert rate.source == "Sveriges Riksbank"
    assert rate.source_url.endswith("/Observations/SEKEURPMI/2026-10-09/2026-10-09")
    series, from_date, to_date = fetch.calls[0]
    assert series == "SEKEURPMI" and to_date == date(2026, 10, 11)
    assert from_date < date(2026, 10, 4)


def test_a_stored_rate_is_not_fetched_again(test_db):
    fetch = _Fetcher()
    service = ExchangeRateService(fetch)
    first = service.rate("EUR", date(2026, 10, 11))
    second = service.rate("eur", date(2026, 10, 11))

    assert first == second
    assert len(fetch.calls) == 1


def test_a_small_rate_converts_without_losing_ore(test_db):
    fetch = _Fetcher([{"date": "2026-10-12", "value": 0.06314}])
    conversion = ExchangeRateService(fetch).convert(
        "JPY", Decimal("3000"), date(2026, 10, 12)
    )
    # 3000 × 0.06314 = 189.42 kr
    assert conversion.sek_ore == 18942


def test_rounding_is_half_up_to_the_ore(test_db):
    fetch = _Fetcher([{"date": "2026-10-09", "value": 11.1675}])
    conversion = ExchangeRateService(fetch).convert(
        "EUR", Decimal("20.00"), date(2026, 10, 9)
    )
    # 20 × 11.1675 = 223.35 kr exactly
    assert conversion.sek_ore == 22335
    line = conversion.comment_line()
    assert line.startswith("Omräknat 20,00 EUR × 11,1675 SEK/EUR = 223,35 kr.")
    assert "Riksbankens dagliga mittkurs (serie SEKEURPMI) för 2026-10-09" in line
    assert "Källa: Sveriges Riksbank" in line


def test_the_comment_says_when_the_rate_is_from_an_earlier_day(test_db):
    conversion = ExchangeRateService(_Fetcher()).convert(
        "EUR", Decimal("20"), date(2026, 10, 11)
    )
    assert "för 2026-10-09, senaste bankdag före köpdatum 2026-10-11" in (
        conversion.comment_line()
    )


def test_riksbank_unreachable_is_a_domain_error_and_nothing_is_stored(test_db):
    fetch = _Fetcher(
        error=ValidationError("exchange_rate_unavailable", "Riksbank is down")
    )
    with pytest.raises(ValidationError) as excinfo:
        ExchangeRateService(fetch).rate("EUR", date(2026, 10, 9))
    assert excinfo.value.code == "exchange_rate_unavailable"
    count = db.execute("SELECT COUNT(*) AS n FROM exchange_rates").fetchone()["n"]
    assert count == 0


def test_no_observation_in_the_window_is_refused(test_db):
    with pytest.raises(ValidationError) as excinfo:
        ExchangeRateService(_Fetcher([])).rate("EUR", date(2026, 10, 9))
    assert excinfo.value.code == "exchange_rate_missing"


@pytest.mark.parametrize(
    "currency, on_date, code",
    [
        ("SEK", date(2026, 10, 9), "invalid_currency"),
        ("EU", date(2026, 10, 9), "invalid_currency"),
        ("EUR", date(2099, 1, 1), "exchange_rate_in_future"),
    ],
)
def test_bad_requests_are_refused_before_fetching(test_db, currency, on_date, code):
    fetch = _Fetcher()
    with pytest.raises(ValidationError) as excinfo:
        ExchangeRateService(fetch).rate(currency, on_date)
    assert excinfo.value.code == code
    assert fetch.calls == []


def test_stored_rates_are_append_only(test_db):
    ExchangeRateService(_Fetcher()).rate("EUR", date(2026, 10, 9))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE exchange_rates SET rate = '1'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM exchange_rates")


def test_the_settlement_row_must_carry_the_converted_amount(test_db):
    conversion = ExchangeRateService(_Fetcher()).convert(
        "EUR", Decimal("20.00"), date(2026, 10, 9)
    )
    ok = [
        {"account": "6540", "debit": 22335},
        {"account": "2820", "credit": 22335},
    ]
    check_settles_converted(conversion, ok)
    # One öre of slack.
    check_settles_converted(conversion, [{"account": "1930", "credit": 22334}])

    with pytest.raises(ValidationError) as excinfo:
        check_settles_converted(
            conversion,
            # The base on 4598 has the amount but settles nothing.
            [
                {"account": "2820", "credit": 22000},
                {"account": "4598", "credit": 22335},
            ],
        )
    assert excinfo.value.code == "fx_amount_mismatch"
    assert excinfo.value.payload["sek_ore"] == 22335


def test_swedish_amount_format():
    assert format_amount(Decimal("1234567.5")) == "1 234 567,50"
    assert format_amount(Decimal("0.05")) == "0,05"
