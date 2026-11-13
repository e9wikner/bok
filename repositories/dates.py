"""Date and timestamp columns as SQLite hands them back.

A column comes back already parsed (the connection's converters) or as ISO
text, depending on how it was declared and written. These turn either into a
`date` or `datetime`. The `as_` functions pass `None` through; the `req_`
functions are for `NOT NULL` columns and refuse it.
"""

from datetime import date, datetime
from typing import Any, Optional


def as_datetime(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def req_datetime(value: Any) -> datetime:
    parsed = as_datetime(value)
    if parsed is None:
        raise ValueError("a NOT NULL timestamp column was NULL")
    return parsed


def as_date(value: Any) -> Optional[date]:
    """A date; a timestamp is cut to its day."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def req_date(value: Any) -> date:
    parsed = as_date(value)
    if parsed is None:
        raise ValueError("a NOT NULL date column was NULL")
    return parsed
