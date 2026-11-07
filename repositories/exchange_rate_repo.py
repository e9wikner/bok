"""`exchange_rates` (migration 045): the Riksbank rates the server fetched.

Append-only: insert and read, nothing else (the triggers refuse the rest).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from db.database import db
from domain.exchange_rate import ExchangeRate


class ExchangeRateRepository:
    @staticmethod
    def get(currency: str, requested_date: date) -> Optional[ExchangeRate]:
        row = db.execute(
            "SELECT * FROM exchange_rates WHERE currency = ? AND requested_date = ?",
            (currency, requested_date.isoformat()),
        ).fetchone()
        return ExchangeRateRepository._to_rate(row) if row else None

    @staticmethod
    def add(rate: ExchangeRate) -> ExchangeRate:
        """Store a fetched rate. A second fetch for the same day (two posts
        at once) keeps the first: `INSERT OR IGNORE` and read it back."""
        db.execute(
            """
            INSERT OR IGNORE INTO exchange_rates
            (id, currency, requested_date, observation_date, rate, series_id,
             source, source_url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                rate.currency,
                rate.requested_date.isoformat(),
                rate.observation_date.isoformat(),
                str(rate.rate),
                rate.series_id,
                rate.source,
                rate.source_url,
                datetime.now(),
            ),
        )
        db.commit()
        stored = ExchangeRateRepository.get(rate.currency, rate.requested_date)
        assert stored is not None
        return stored

    @staticmethod
    def _to_rate(row) -> ExchangeRate:
        fetched = row["fetched_at"]
        return ExchangeRate(
            id=row["id"],
            currency=row["currency"],
            requested_date=date.fromisoformat(row["requested_date"]),
            observation_date=date.fromisoformat(row["observation_date"]),
            rate=Decimal(row["rate"]),
            series_id=row["series_id"],
            source=row["source"],
            source_url=row["source_url"],
            fetched_at=(
                fetched
                if isinstance(fetched, datetime) or fetched is None
                else datetime.fromisoformat(fetched)
            ),
        )
