"""Exchange rates and the conversion of a foreign amount (migration 045).

Pure domain: no SQL, no HTTP. `services/exchange_rates.py` fetches and
stores the rates; this module holds what a rate is and how an amount in a
foreign currency becomes kronor and the line that says so on the voucher.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Mapping, Optional

from domain.validation import ValidationError

#: Where a rate comes from, as the voucher's comment names it.
RIKSBANK_SOURCE = "Sveriges Riksbank"

#: Accounts a purchase is settled against: the debt to the person who paid
#: (2820), the supplier (2440), a card (1630) or a bank account (1900-1989).
#: The converted amount must stand on one of them -- a reverse-charge base on
#: 4598 has the same amount but settles nothing.
SETTLEMENT_ACCOUNTS = ("2820", "2440", "1630")
SETTLEMENT_RANGE = ("1900", "1989")


@dataclass(frozen=True)
class ExchangeRate:
    """SEK per one unit of `currency` on `observation_date`."""

    currency: str
    requested_date: date
    observation_date: date
    rate: Decimal
    series_id: str
    source: str
    source_url: str
    fetched_at: Optional[datetime] = None
    id: Optional[str] = None


@dataclass(frozen=True)
class Conversion:
    """A foreign amount converted at one rate: what the voucher books, and
    the line that tells a reader how."""

    currency: str
    amount: Decimal
    rate: ExchangeRate
    sek_ore: int

    def comment_line(self) -> str:
        r = self.rate
        if r.observation_date == r.requested_date:
            when = f"för {r.observation_date.isoformat()}, köpdatum"
        else:
            when = (
                f"för {r.observation_date.isoformat()}, senaste bankdag före "
                f"köpdatum {r.requested_date.isoformat()}"
            )
        return (
            f"Omräknat {format_amount(self.amount)} {self.currency} × "
            f"{format_rate(r.rate)} SEK/{self.currency} = "
            f"{format_amount(Decimal(self.sek_ore) / 100)} kr. "
            f"Riksbankens dagliga mittkurs (serie {r.series_id}) {when}. "
            f"Källa: {r.source}, {r.source_url}"
        )


def convert(currency: str, amount: Decimal, rate: ExchangeRate) -> Conversion:
    """`amount` of `currency` in öre, rounded half up to the nearest öre."""
    if amount <= 0:
        raise ValidationError(
            "invalid_currency_amount",
            "The foreign amount must be greater than zero",
            f"amount={amount}",
        )
    sek_ore = int((amount * rate.rate * 100).quantize(Decimal(1), ROUND_HALF_UP))
    return Conversion(currency=currency, amount=amount, rate=rate, sek_ore=sek_ore)


def is_settlement_account(code: str) -> bool:
    return code in SETTLEMENT_ACCOUNTS or (
        SETTLEMENT_RANGE[0] <= code <= SETTLEMENT_RANGE[1]
    )


def check_settles_converted(
    conversion: Conversion, rows: Iterable[Mapping[str, object]]
) -> None:
    """The voucher must settle exactly the converted amount (one öre of
    slack): the agent may not book its own rate, or the private card's."""
    credits = [
        int(row.get("credit") or 0)  # type: ignore[call-overload]
        for row in rows
        if is_settlement_account(str(row.get("account", "")))
    ]
    if any(abs(credit - conversion.sek_ore) <= 1 for credit in credits):
        return
    raise ValidationError(
        "fx_amount_mismatch",
        (
            f"{format_amount(conversion.amount)} {conversion.currency} is "
            f"{conversion.sek_ore} öre at Riksbank's rate "
            f"{format_rate(conversion.rate.rate)} for "
            f"{conversion.rate.observation_date.isoformat()}; no credit row on "
            "2820, 2440, 1630 or 1900-1989 has that amount"
        ),
        "book the settlement row (2820 for an utlägg) at exactly sek_ore and "
        "derive the other rows from it",
        payload={
            "sek_ore": conversion.sek_ore,
            "rate": str(conversion.rate.rate),
            "observation_date": conversion.rate.observation_date.isoformat(),
        },
    )


def with_conversion_line(conversion: Conversion, comment: Optional[str]) -> str:
    """The server's rate line first, then the agent's own text."""
    line = conversion.comment_line()
    own = (comment or "").strip()
    return f"{line}\n{own}" if own else line


def format_amount(value: Decimal) -> str:
    """1234.5 -> `1 234,50` (Swedish)."""
    quantized = value.quantize(Decimal("0.01"), ROUND_HALF_UP)
    sign = "-" if quantized < 0 else ""
    whole, frac = f"{abs(quantized):.2f}".split(".")
    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{' '.join(groups)},{frac}"


def format_rate(rate: Decimal) -> str:
    """The rate as Riksbank publishes it, with a decimal comma."""
    text = format(rate.normalize(), "f")
    return text.replace(".", ",")
