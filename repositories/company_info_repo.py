"""Repository for company metadata (`company_info`, key/value, migration 004)."""

from typing import Dict, Mapping, Optional

from db.database import db


class CompanyInfoRepository:
    """All SQL against `company_info`. Does not commit; the caller does."""

    @staticmethod
    def get_all() -> Dict[str, str]:
        rows = db.execute("SELECT key, value FROM company_info").fetchall()
        return {row["key"]: row["value"] for row in rows}

    @staticmethod
    def set_values(values: Mapping[str, Optional[str]]) -> None:
        """Write the given keys. `None` or an empty string removes the key."""
        for key, value in values.items():
            normalized = value.strip() if isinstance(value, str) else value
            if normalized is None or normalized == "":
                db.execute("DELETE FROM company_info WHERE key = ?", (key,))
                continue
            db.execute(
                """
                INSERT INTO company_info (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, normalized),
            )
