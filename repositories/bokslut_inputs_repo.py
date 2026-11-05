"""Repository for `bokslut_inputs` (migration 044). Append-only."""

import json
import uuid
from typing import Any, Dict, List

from db.database import db


class BokslutInputsRepository:
    """All SQL against `bokslut_inputs`. Does not commit; the caller does."""

    @staticmethod
    def current(fiscal_year_id: str) -> Dict[str, Any]:
        """The latest value per key. A key whose latest row is NULL is absent."""
        rows = db.execute(
            """
            SELECT b.key, b.value_json
            FROM bokslut_inputs b
            WHERE b.fiscal_year_id = ?
              AND b.seq = (
                  SELECT MAX(seq) FROM bokslut_inputs x
                  WHERE x.fiscal_year_id = b.fiscal_year_id AND x.key = b.key
              )
            """,
            (fiscal_year_id,),
        ).fetchall()
        return {
            row["key"]: json.loads(row["value_json"])
            for row in rows
            if row["value_json"] is not None
        }

    @staticmethod
    def append(fiscal_year_id: str, key: str, value: Any, actor: str) -> None:
        seq_row = db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS s FROM bokslut_inputs "
            "WHERE fiscal_year_id = ? AND key = ?",
            (fiscal_year_id, key),
        ).fetchone()
        db.execute(
            """
            INSERT INTO bokslut_inputs
                (id, fiscal_year_id, key, value_json, created_by, seq)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                fiscal_year_id,
                key,
                None if value is None else json.dumps(value, ensure_ascii=False),
                actor,
                seq_row["s"] + 1,
            ),
        )

    @staticmethod
    def history(fiscal_year_id: str) -> List[Dict[str, Any]]:
        rows = db.execute(
            """
            SELECT key, value_json, created_by, created_at
            FROM bokslut_inputs WHERE fiscal_year_id = ?
            ORDER BY created_at, key, seq
            """,
            (fiscal_year_id,),
        ).fetchall()
        return [
            {
                "key": r["key"],
                "value": (
                    None if r["value_json"] is None else json.loads(r["value_json"])
                ),
                "created_by": r["created_by"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
