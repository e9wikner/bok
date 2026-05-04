"""Repository for accounting pattern rules and evaluations."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import uuid

from db.database import db
from domain.accounting_pattern_models import (
    AccountingPattern,
    AccountingPatternEvaluation,
    AccountingPatternEvaluationCase,
)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _loads(data: Optional[str], default: Any) -> Any:
    return json.loads(data) if data else default


class AccountingPatternRepository:
    @staticmethod
    def archive_suggested_analysis() -> None:
        db.execute(
            """
            UPDATE accounting_patterns
            SET status = 'archived', updated_at = ?
            WHERE source = 'analysis' AND status = 'suggested'
            """,
            (datetime.now(),),
        )
        db.commit()

    @staticmethod
    def create_or_update_suggestion(
        name: str,
        match_type: str,
        match_config: Dict[str, Any],
        voucher_template: Dict[str, Any],
        confidence: float,
        sample_count: int,
        example_voucher_ids: List[str],
        created_by: str = "system",
    ) -> AccountingPattern:
        """Create a suggested pattern or refresh an equivalent non-active one."""
        now = datetime.now()
        signature = voucher_template.get("signature")
        existing = None
        rows = db.execute(
            "SELECT * FROM accounting_patterns WHERE source = 'analysis' AND status IN ('suggested', 'archived')"
        ).fetchall()
        for row in rows:
            template = _loads(row["voucher_template_json"], {})
            config = _loads(row["match_config_json"], {})
            if (
                config.get("description_key") == match_config.get("description_key")
                and template.get("signature") == signature
            ):
                existing = row
                break

        if existing:
            pattern_id = existing["id"]
            db.execute(
                """
                UPDATE accounting_patterns
                SET name = ?, status = 'suggested', match_type = ?, match_config_json = ?, voucher_template_json = ?,
                    confidence = ?, sample_count = ?, last_analyzed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    match_type,
                    _json(match_config),
                    _json(voucher_template),
                    confidence,
                    sample_count,
                    now,
                    now,
                    pattern_id,
                ),
            )
            db.execute("DELETE FROM accounting_pattern_examples WHERE pattern_id = ?", (pattern_id,))
        else:
            pattern_id = str(uuid.uuid4())
            db.execute(
                """
                INSERT INTO accounting_patterns
                    (id, name, status, match_type, match_config_json, voucher_template_json,
                     confidence, source, sample_count, last_analyzed_at, created_by, created_at, updated_at)
                VALUES (?, ?, 'suggested', ?, ?, ?, ?, 'analysis', ?, ?, ?, ?, ?)
                """,
                (
                    pattern_id,
                    name,
                    match_type,
                    _json(match_config),
                    _json(voucher_template),
                    confidence,
                    sample_count,
                    now,
                    created_by,
                    now,
                    now,
                ),
            )

        for voucher_id in example_voucher_ids:
            db.execute(
                """
                INSERT OR IGNORE INTO accounting_pattern_examples
                    (id, pattern_id, voucher_id, match_reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    pattern_id,
                    voucher_id,
                    f"Matched description key {match_config.get('description_key')}",
                    now,
                ),
            )
        db.commit()
        return AccountingPatternRepository.get(pattern_id)

    @staticmethod
    def list_all(status: Optional[str] = None) -> List[AccountingPattern]:
        sql = "SELECT * FROM accounting_patterns"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY status, confidence DESC, sample_count DESC, name"
        rows = db.execute(sql, tuple(params)).fetchall()
        return [AccountingPatternRepository._row_to_pattern(row) for row in rows]

    @staticmethod
    def get(pattern_id: str) -> Optional[AccountingPattern]:
        row = db.execute("SELECT * FROM accounting_patterns WHERE id = ?", (pattern_id,)).fetchone()
        return AccountingPatternRepository._row_to_pattern(row) if row else None

    @staticmethod
    def list_examples(pattern_id: str) -> List[Dict[str, Any]]:
        rows = db.execute(
            """
            SELECT e.*, v.series, v.number, v.date, v.description
            FROM accounting_pattern_examples e
            JOIN vouchers v ON v.id = e.voucher_id
            WHERE e.pattern_id = ?
            ORDER BY v.date DESC, v.number DESC
            """,
            (pattern_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "pattern_id": row["pattern_id"],
                "voucher_id": row["voucher_id"],
                "voucher": {
                    "series": row["series"],
                    "number": row["number"],
                    "date": row["date"],
                    "description": row["description"],
                },
                "match_reason": row["match_reason"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def approve(pattern_id: str, actor: str) -> Optional[AccountingPattern]:
        now = datetime.now()
        db.execute(
            """
            UPDATE accounting_patterns
            SET status = 'active', approved_by = ?, approved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (actor, now, now, pattern_id),
        )
        db.commit()
        return AccountingPatternRepository.get(pattern_id)

    @staticmethod
    def reject(pattern_id: str) -> Optional[AccountingPattern]:
        db.execute(
            "UPDATE accounting_patterns SET status = 'rejected', updated_at = ? WHERE id = ?",
            (datetime.now(), pattern_id),
        )
        db.commit()
        return AccountingPatternRepository.get(pattern_id)

    @staticmethod
    def update(
        pattern_id: str,
        name: Optional[str] = None,
        match_config: Optional[Dict[str, Any]] = None,
        voucher_template: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ) -> Optional[AccountingPattern]:
        pattern = AccountingPatternRepository.get(pattern_id)
        if not pattern:
            return None
        db.execute(
            """
            UPDATE accounting_patterns
            SET name = ?, match_config_json = ?, voucher_template_json = ?, confidence = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name if name is not None else pattern.name,
                _json(match_config if match_config is not None else pattern.match_config),
                _json(voucher_template if voucher_template is not None else pattern.voucher_template),
                confidence if confidence is not None else pattern.confidence,
                datetime.now(),
                pattern_id,
            ),
        )
        db.commit()
        return AccountingPatternRepository.get(pattern_id)

    @staticmethod
    def create_evaluation(
        name: str,
        baseline_rule_ids: List[str],
        candidate_rule_ids: List[str],
        summary: Dict[str, Any],
        fiscal_year_id: Optional[str] = None,
        date_from=None,
        date_to=None,
        created_by: str = "system",
    ) -> AccountingPatternEvaluation:
        evaluation_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO accounting_pattern_evaluations
                (id, name, baseline_rule_ids_json, candidate_rule_ids_json, fiscal_year_id,
                 date_from, date_to, status, summary_json, created_by, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                name,
                _json(baseline_rule_ids),
                _json(candidate_rule_ids),
                fiscal_year_id,
                date_from,
                date_to,
                _json(summary),
                created_by,
                now,
                now,
            ),
        )
        db.commit()
        return AccountingPatternRepository.get_evaluation(evaluation_id)

    @staticmethod
    def add_evaluation_case(
        evaluation_id: str,
        voucher_id: str,
        actual_result: Dict[str, Any],
        baseline_result: Optional[Dict[str, Any]],
        candidate_result: Optional[Dict[str, Any]],
        baseline_score: float,
        candidate_score: float,
        winner: str,
        notes: Optional[str] = None,
    ) -> None:
        db.execute(
            """
            INSERT INTO accounting_pattern_evaluation_cases
                (id, evaluation_id, voucher_id, baseline_result_json, candidate_result_json,
                 actual_result_json, baseline_score, candidate_score, winner, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                evaluation_id,
                voucher_id,
                _json(baseline_result) if baseline_result else None,
                _json(candidate_result) if candidate_result else None,
                _json(actual_result),
                baseline_score,
                candidate_score,
                winner,
                notes,
                datetime.now(),
            ),
        )
        db.commit()

    @staticmethod
    def list_evaluations() -> List[AccountingPatternEvaluation]:
        rows = db.execute(
            "SELECT * FROM accounting_pattern_evaluations ORDER BY created_at DESC"
        ).fetchall()
        return [AccountingPatternRepository._row_to_evaluation(row) for row in rows]

    @staticmethod
    def get_evaluation(evaluation_id: str) -> Optional[AccountingPatternEvaluation]:
        row = db.execute(
            "SELECT * FROM accounting_pattern_evaluations WHERE id = ?",
            (evaluation_id,),
        ).fetchone()
        return AccountingPatternRepository._row_to_evaluation(row) if row else None

    @staticmethod
    def list_evaluation_cases(
        evaluation_id: str, winner: Optional[str] = None, limit: int = 100
    ) -> List[AccountingPatternEvaluationCase]:
        sql = "SELECT * FROM accounting_pattern_evaluation_cases WHERE evaluation_id = ?"
        params: list = [evaluation_id]
        if winner:
            sql += " AND winner = ?"
            params.append(winner)
        sql += " ORDER BY candidate_score - baseline_score DESC, created_at LIMIT ?"
        params.append(limit)
        rows = db.execute(sql, tuple(params)).fetchall()
        return [AccountingPatternRepository._row_to_case(row) for row in rows]

    @staticmethod
    def _row_to_pattern(row) -> AccountingPattern:
        return AccountingPattern(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            match_type=row["match_type"],
            match_config=_loads(row["match_config_json"], {}),
            voucher_template=_loads(row["voucher_template_json"], {}),
            confidence=row["confidence"],
            source=row["source"],
            sample_count=row["sample_count"],
            last_analyzed_at=datetime.fromisoformat(row["last_analyzed_at"]) if row["last_analyzed_at"] else None,
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            approved_by=row["approved_by"],
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
        )

    @staticmethod
    def _row_to_evaluation(row) -> AccountingPatternEvaluation:
        return AccountingPatternEvaluation(
            id=row["id"],
            name=row["name"],
            baseline_rule_ids=_loads(row["baseline_rule_ids_json"], []),
            candidate_rule_ids=_loads(row["candidate_rule_ids_json"], []),
            fiscal_year_id=row["fiscal_year_id"],
            date_from=datetime.fromisoformat(row["date_from"]).date() if row["date_from"] else None,
            date_to=datetime.fromisoformat(row["date_to"]).date() if row["date_to"] else None,
            status=row["status"],
            summary=_loads(row["summary_json"], {}),
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    @staticmethod
    def _row_to_case(row) -> AccountingPatternEvaluationCase:
        return AccountingPatternEvaluationCase(
            id=row["id"],
            evaluation_id=row["evaluation_id"],
            voucher_id=row["voucher_id"],
            baseline_result=_loads(row["baseline_result_json"], None),
            candidate_result=_loads(row["candidate_result_json"], None),
            actual_result=_loads(row["actual_result_json"], {}),
            baseline_score=row["baseline_score"],
            candidate_score=row["candidate_score"],
            winner=row["winner"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
