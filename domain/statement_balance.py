"""The balance an account statement (CSV) states, for reconciliation.

A statement says what the bank or Skatteverket holds on the account. Bok
compares it with the ledger on the same day (`services/bank_reconciliation.py`):
a difference is something not booked, booked twice or booked on the wrong
account.

Two shapes are read, the two the supported exports carry:

- **An explicit closing line**, Skatteverket's skattekonto:
  `"";"Utgående saldo 2026-11-05";"";"71 111"`. The date is in the text.
- **A balance header before the transactions**, Länsförsäkringar:
  `"Kontonummer";"Kontonamn";"";"Saldo";...` and the values on the next line.
  The balance is the account's at export, so it includes every transaction
  in the file; its day is the latest booking date among them.

Anything else gives `None`: no guessed balance. A statement without one
simply has no reconciliation.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_CLOSING = re.compile(r"utgående saldo\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
# Column names that hold a transaction's booking date, in the order to try.
_DATE_COLUMNS = ("Bokföringsdatum", "Bokföringsdag", "Datum", "Transaktionsdatum")


@dataclass(frozen=True)
class StatementBalance:
    day: date
    balance_ore: int


def _ore(text: str) -> Optional[int]:
    cleaned = (text or "").strip().replace(" ", "").replace(" ", "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", ".").replace("−", "-")
    try:
        return int((Decimal(cleaned) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _rows(csv_content: str) -> list[list[str]]:
    first = csv_content.splitlines()[0] if csv_content.splitlines() else ""
    delimiter = ";" if first.count(";") >= first.count(",") else ","
    return [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(csv_content), delimiter=delimiter)
    ]


def _closing_line(rows: list[list[str]]) -> Optional[StatementBalance]:
    for row in reversed(rows):
        for index, cell in enumerate(row):
            match = _CLOSING.search(cell)
            if not match:
                continue
            amounts = [a for a in (_ore(c) for c in row[index + 1 :]) if a is not None]
            if amounts:
                return StatementBalance(date.fromisoformat(match.group(1)), amounts[-1])
    return None


def _balance_header(rows: list[list[str]]) -> Optional[StatementBalance]:
    """`Saldo` in a header row above the transactions' own header."""
    for index, row in enumerate(rows[:-1]):
        if "Saldo" not in row or any(c in row for c in _DATE_COLUMNS):
            continue
        balance = _ore(rows[index + 1][row.index("Saldo")])
        if balance is None:
            return None
        days = _transaction_days(rows[index + 2 :])
        return StatementBalance(max(days), balance) if days else None
    return None


def _transaction_days(rows: list[list[str]]) -> list[date]:
    for index, row in enumerate(rows):
        column = next((row.index(c) for c in _DATE_COLUMNS if c in row), None)
        if column is None:
            continue
        return [
            date.fromisoformat(r[column])
            for r in rows[index + 1 :]
            if len(r) > column and _ISO.fullmatch(r[column])
        ]
    return []


def statement_balance(csv_content: str) -> Optional[StatementBalance]:
    """The balance *csv_content* states and its day, or `None`."""
    rows = _rows(csv_content)
    return _closing_line(rows) or _balance_header(rows)
