"""Riksbank's daily exchange rates, and converting a foreign amount with them.

`hamta_valutakurs` and the `valuta` field on `posta_verifikation` /
`foresla_verifikation` (and `POST /api/v1/agent/vouchers`) come here. The
server looks the rate up itself; it never takes one from the agent. The rate
is Riksbank's daily mid rate (`SEK{CUR}PMI` in the SWEA API), SEK per one
unit of the currency, for the purchase date -- or, on a weekend or a public
holiday, for the last banking day before it. Skatteverket accepts Riksbank's
rates for converting the tax base.

A rate is fetched once per currency and date and then stored
(`exchange_rates`, append-only), so the rate behind a posted voucher can
always be shown again -- and Riksbank's API, which limits requests, is asked
as little as possible.

Layering (AGENTS.md): no SQL here; the HTTP call is to Riksbank, not ours.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, List, Mapping, Optional, Tuple

from pydantic import BaseModel, Field

from domain.exchange_rate import (
    RIKSBANK_SOURCE,
    Conversion,
    ExchangeRate,
    check_settles_converted,
    convert,
    with_conversion_line,
)
from domain.validation import ValidationError
from repositories.exchange_rate_repo import ExchangeRateRepository

logger = logging.getLogger(__name__)

SWEA_BASE_URL = "https://api.riksbank.se/swea/v1"

#: How far back a weekend or a run of holidays may reach for the last
#: banking day. Easter and Christmas never span more than five days.
LOOKBACK_DAYS = 10


class Valuta(BaseModel):
    """Ett köp i utländsk valuta. Servern räknar om med Riksbankens kurs för
    `rate_date` (köp- eller fakturadatum) och skriver kursraden i
    verifikationens kommentar. Kreditraden på 2820 (eller 2440, 1630,
    1900-1989) ska vara exakt det omräknade beloppet."""

    currency: str = Field(..., pattern="^[A-Z]{3}$", description="ISO 4217, t.ex. EUR")
    amount: Decimal = Field(
        ..., gt=0, description="Beloppet i valutan, t.ex. 20.00 -- inte i ören"
    )
    rate_date: date = Field(..., description="Köpdatum eller fakturadatum")


#: Fetch(series_id, from_date, to_date) -> [{"date": "YYYY-MM-DD", "value": n}]
Fetcher = Callable[[str, date, date], List[Mapping[str, Any]]]


def series_id(currency: str) -> str:
    return f"SEK{currency}PMI"


def observations_url(series: str, from_date: date, to_date: date) -> str:
    return (
        f"{SWEA_BASE_URL}/Observations/{series}/"
        f"{from_date.isoformat()}/{to_date.isoformat()}"
    )


def _fetch_from_riksbank(
    series: str, from_date: date, to_date: date
) -> List[Mapping[str, Any]]:
    import httpx

    url = observations_url(series, from_date, to_date)
    try:
        response = httpx.get(url, timeout=10.0, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise ValidationError(
            "exchange_rate_unavailable",
            "Riksbank's exchange-rate service could not be reached",
            f"{type(exc).__name__}: {exc}",
        ) from exc
    if response.status_code == 404:
        raise ValidationError(
            "unknown_currency",
            f"Riksbank publishes no daily rate in series {series}",
            "give the ISO 4217 code of a currency Riksbank quotes against SEK",
        )
    if response.status_code == 429:
        raise ValidationError(
            "exchange_rate_unavailable",
            "Riksbank's exchange-rate service limits requests; try again shortly",
            response.text[:200],
        )
    if response.status_code >= 400:
        raise ValidationError(
            "exchange_rate_unavailable",
            f"Riksbank answered {response.status_code}",
            response.text[:200],
        )
    data = response.json()
    if not isinstance(data, list):
        raise ValidationError(
            "exchange_rate_unavailable",
            "Riksbank's answer was not a list of observations",
            str(data)[:200],
        )
    return data


class ExchangeRateService:
    def __init__(self, fetch: Optional[Fetcher] = None) -> None:
        self._fetch = fetch or _fetch_from_riksbank

    def rate(
        self, currency: str, on_date: date, *, today: Optional[date] = None
    ) -> ExchangeRate:
        """Riksbank's rate for `currency` on `on_date`, or the last banking
        day before it. Stored rates are never fetched again."""
        currency = (currency or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValidationError(
                "invalid_currency",
                "A currency is a three-letter ISO 4217 code",
                f"currency={currency!r}",
            )
        if currency == "SEK":
            raise ValidationError(
                "invalid_currency",
                "SEK needs no conversion",
                "leave out `valuta` for a purchase in kronor",
            )
        if on_date > (today or date.today()):
            raise ValidationError(
                "exchange_rate_in_future",
                f"No rate exists yet for {on_date.isoformat()}",
                "the purchase date cannot be after today",
            )

        stored = ExchangeRateRepository.get(currency, on_date)
        if stored is not None:
            return stored

        series = series_id(currency)
        from_date = on_date - timedelta(days=LOOKBACK_DAYS)
        observations = self._fetch(series, from_date, on_date)
        observation_date, value = _last_on_or_before(observations, on_date)
        if observation_date is None or value is None:
            raise ValidationError(
                "exchange_rate_missing",
                (
                    f"Riksbank has no rate in {series} between "
                    f"{from_date.isoformat()} and {on_date.isoformat()}"
                ),
                "the currency may no longer be quoted; do not guess a rate",
            )
        return ExchangeRateRepository.add(
            ExchangeRate(
                currency=currency,
                requested_date=on_date,
                observation_date=observation_date,
                rate=value,
                series_id=series,
                source=RIKSBANK_SOURCE,
                source_url=observations_url(series, observation_date, observation_date),
            )
        )

    def convert(self, currency: str, amount: Decimal, on_date: date) -> Conversion:
        return convert(currency.strip().upper(), amount, self.rate(currency, on_date))

    def apply(
        self,
        valuta: Optional[Mapping[str, Any]],
        rows: Iterable[Mapping[str, Any]],
        comment: Optional[str],
    ) -> Tuple[Optional[str], Optional[Conversion]]:
        """For a posting or a proposal with `valuta` ({currency, amount,
        rate_date}): convert at Riksbank's rate, require the settlement row
        to carry exactly that amount, and put the server's rate line first
        in the comment. Without `valuta` the comment is the agent's own."""
        own = (comment or "").strip() or None
        if not valuta:
            return own, None
        try:
            amount = Decimal(str(valuta["amount"]))
            currency = str(valuta["currency"])
            rate_date = valuta["rate_date"]
            if isinstance(rate_date, str):
                rate_date = date.fromisoformat(rate_date)
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise ValidationError(
                "invalid_tool_arguments",
                "valuta needs currency, amount and rate_date",
                str(exc),
            ) from exc
        conversion = self.convert(currency, amount, rate_date)
        check_settles_converted(conversion, list(rows))
        return with_conversion_line(conversion, own), conversion


def rate_dict(rate: ExchangeRate) -> dict:
    return {
        "currency": rate.currency,
        "rate": str(rate.rate),
        "requested_date": rate.requested_date.isoformat(),
        "observation_date": rate.observation_date.isoformat(),
        "series_id": rate.series_id,
        "source": rate.source,
        "source_url": rate.source_url,
        "meaning": f"SEK per 1 {rate.currency}, Riksbankens dagliga mittkurs",
    }


def _last_on_or_before(
    observations: Iterable[Mapping[str, Any]], on_date: date
) -> Tuple[Optional[date], Optional[Decimal]]:
    best: Tuple[Optional[date], Optional[Decimal]] = (None, None)
    for item in observations:
        try:
            when = date.fromisoformat(str(item["date"]))
            value = Decimal(str(item["value"]))
        except (KeyError, ValueError, InvalidOperation):
            continue
        if value <= 0 or when > on_date:
            continue
        if best[0] is None or when > best[0]:
            best = (when, value)
    return best
