"""Repository for `account_sru_mappings` (migrations 009/010)."""

import uuid
from datetime import datetime
from typing import Dict

from db.database import db


class SruMappingRepository:
    """SQL against the year-specific SRU mappings. Does not commit."""

    @staticmethod
    def copy(from_fiscal_year_id: str, to_fiscal_year_id: str) -> int:
        """Copy one year's saved mappings to another that has none.

        Returns the number of rows copied."""
        now = datetime.now().isoformat()
        rows = db.execute(
            "SELECT account_code, sru_field FROM account_sru_mappings "
            "WHERE fiscal_year_id = ? ORDER BY account_code",
            (from_fiscal_year_id,),
        ).fetchall()
        for row in rows:
            db.execute(
                """
                INSERT OR IGNORE INTO account_sru_mappings
                    (id, fiscal_year_id, account_code, sru_field,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    to_fiscal_year_id,
                    row["account_code"],
                    row["sru_field"],
                    now,
                    now,
                ),
            )
        return len(rows)

    @staticmethod
    def for_year(fiscal_year_id: str) -> Dict[str, str]:
        """A year's saved mappings, ``{account_code: sru_field}``."""
        rows = db.execute(
            "SELECT account_code, sru_field FROM account_sru_mappings "
            "WHERE fiscal_year_id = ? ORDER BY account_code",
            (fiscal_year_id,),
        ).fetchall()
        return {row["account_code"]: row["sru_field"] for row in rows}

    @staticmethod
    def replace(fiscal_year_id: str, mappings: Dict[str, str]) -> None:
        """Replace a year's saved mappings with ``mappings``."""
        now = datetime.now().isoformat()
        db.execute(
            "DELETE FROM account_sru_mappings WHERE fiscal_year_id = ?",
            (fiscal_year_id,),
        )
        db.executemany(
            """
            INSERT INTO account_sru_mappings
                (id, fiscal_year_id, account_code, sru_field,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (str(uuid.uuid4()), fiscal_year_id, code, field, now, now)
                for code, field in sorted(mappings.items())
            ],
        )
