"""Learning repository - data access for AI learning rules and corrections."""

from typing import Optional, List
from datetime import datetime
import uuid
import json
from db.database import db
from domain.models import LearningRule, CorrectionHistory


class LearningRepository:
    """Manage learning rules and correction history for ML-lite functionality."""
    
    @staticmethod
    def create_rule(
        pattern_type: str,
        pattern_value: str,
        corrected_account: str,
        original_account: Optional[str] = None,
        description: Optional[str] = None,
        source_voucher_id: Optional[str] = None,
        created_by: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> LearningRule:
        """Create new learning rule or update existing if pattern matches."""
        # Check if rule with same pattern already exists
        existing = LearningRepository._find_existing_rule(
            pattern_type, pattern_value, original_account, corrected_account
        )
        
        if existing:
            # Update existing rule - increase confidence and usage
            new_confidence = min(0.95, existing.confidence + 0.05)
            new_usage = existing.usage_count + 1
            
            db.execute(
                """UPDATE learning_rules 
                   SET confidence = ?, usage_count = ?, last_used = ?
                   WHERE id = ?""",
                (new_confidence, new_usage, datetime.now(), existing.id)
            )
            db.commit()
            
            return LearningRepository.get_rule(existing.id)
        
        # Create new rule
        rule_id = str(uuid.uuid4())
        now = datetime.now()
        
        sql = """
        INSERT INTO learning_rules 
        (id, company_id, pattern_type, pattern_value, original_account, corrected_account,
         description, confidence, usage_count, success_count, source_voucher_id, created_by,
         created_at, is_active, is_golden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        db.execute(sql, (
            rule_id, company_id, pattern_type, pattern_value, original_account,
            corrected_account, description, 0.5, 1, 1, source_voucher_id, created_by,
            now, True, False
        ))
        db.commit()
        
        return LearningRule(
            id=rule_id,
            pattern_type=pattern_type,
            pattern_value=pattern_value,
            original_account=original_account,
            corrected_account=corrected_account,
            company_id=company_id,
            description=description,
            confidence=0.5,
            usage_count=1,
            success_count=1,
            source_voucher_id=source_voucher_id,
            created_by=created_by,
            created_at=now,
            is_active=True,
            is_golden=False,
        )
    
    @staticmethod
    def _find_existing_rule(
        pattern_type: str,
        pattern_value: str,
        original_account: Optional[str],
        corrected_account: str
    ) -> Optional[LearningRule]:
        """Find existing rule with exact same pattern."""
        sql = """
        SELECT * FROM learning_rules 
        WHERE pattern_type = ? AND pattern_value = ? AND corrected_account = ?
        AND (original_account = ? OR (original_account IS NULL AND ? IS NULL))
        AND is_active = 1
        LIMIT 1
        """
        cursor = db.execute(sql, (pattern_type, pattern_value, corrected_account, 
                                  original_account, original_account))
        row = cursor.fetchone()
        
        if row:
            return LearningRepository._row_to_rule(row)
        return None
    
    @staticmethod
    def find_matching_rules(
        description: str,
        counterparty: Optional[str] = None,
        amount: Optional[int] = None,
        original_account: Optional[str] = None,
    ) -> List[LearningRule]:
        """Find rules that match a transaction description.
        
        Returns rules sorted by confidence (highest first).
        """
        description_lower = description.lower()
        rules = []
        
        # Get all active rules
        cursor = db.execute(
            "SELECT * FROM learning_rules WHERE is_active = 1 ORDER BY confidence DESC"
        )
        
        for row in cursor.fetchall():
            rule = LearningRepository._row_to_rule(row)
            
            # Check if rule matches
            if LearningRepository._rule_matches(rule, description_lower, counterparty, amount, original_account):
                rules.append(rule)
        
        return rules
    
    @staticmethod
    def _rule_matches(
        rule: LearningRule,
        description: str,
        counterparty: Optional[str],
        amount: Optional[int],
        original_account: Optional[str]
    ) -> bool:
        """Check if a rule matches the given transaction data."""
        import re
        
        # Check original account if specified
        if rule.original_account is not None and original_account is not None:
            if rule.original_account != original_account:
                return False
        
        # Match based on pattern type
        if rule.pattern_type == 'keyword':
            return rule.pattern_value.lower() in description
        
        elif rule.pattern_type == 'regex':
            try:
                return bool(re.search(rule.pattern_value, description, re.IGNORECASE))
            except re.error:
                return False
        
        elif rule.pattern_type == 'counterparty':
            if counterparty:
                return rule.pattern_value.lower() in counterparty.lower()
            return False
        
        elif rule.pattern_type == 'amount_range':
            if amount is not None:
                try:
                    # Format: "1000-5000" (in öre)
                    parts = rule.pattern_value.split('-')
                    min_amount = int(parts[0])
                    max_amount = int(parts[1]) if len(parts) > 1 else float('inf')
                    return min_amount <= amount <= max_amount
                except (ValueError, IndexError):
                    return False
            return False
        
        elif rule.pattern_type == 'composite':
            # Composite patterns are JSON with multiple conditions
            try:
                conditions = json.loads(rule.pattern_value)
                if 'keyword' in conditions:
                    if conditions['keyword'].lower() not in description:
                        return False
                if 'counterparty' in conditions and counterparty:
                    if conditions['counterparty'].lower() not in counterparty.lower():
                        return False
                if 'amount_min' in conditions and amount is not None:
                    if amount < int(conditions['amount_min']):
                        return False
                if 'amount_max' in conditions and amount is not None:
                    if amount > int(conditions['amount_max']):
                        return False
                return True
            except json.JSONDecodeError:
                return False
        
        return False
    
    @staticmethod
    def get_rule(rule_id: str) -> Optional[LearningRule]:
        """Get a learning rule by ID."""
        cursor = db.execute(
            "SELECT * FROM learning_rules WHERE id = ? LIMIT 1",
            (rule_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return LearningRepository._row_to_rule(row)
        return None
    
    @staticmethod
    def list_rules(
        active_only: bool = True,
        min_confidence: float = 0.0,
        pattern_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[LearningRule]:
        """List all learning rules with optional filters."""
        sql = "SELECT * FROM learning_rules WHERE confidence >= ?"
        params = [min_confidence]
        
        if active_only:
            sql += " AND is_active = 1"
        
        if pattern_type:
            sql += " AND pattern_type = ?"
            params.append(pattern_type)
        
        sql += " ORDER BY confidence DESC, usage_count DESC LIMIT ?"
        params.append(limit)
        
        cursor = db.execute(sql, tuple(params))
        return [LearningRepository._row_to_rule(row) for row in cursor.fetchall()]
    
    @staticmethod
    def increment_usage(rule_id: str, was_successful: bool = True) -> bool:
        """Increment usage count and update confidence."""
        rule = LearningRepository.get_rule(rule_id)
        if not rule:
            return False
        
        new_usage = rule.usage_count + 1
        new_success = rule.success_count + (1 if was_successful else 0)
        
        # Confidence increases with successful usage
        if was_successful:
            confidence_delta = 0.02
        else:
            confidence_delta = -0.05  # Penalty for failed usage
        
        new_confidence = max(0.1, min(0.95, rule.confidence + confidence_delta))
        
        db.execute(
            """UPDATE learning_rules 
               SET usage_count = ?, success_count = ?, confidence = ?, last_used = ?
               WHERE id = ?""",
            (new_usage, new_success, new_confidence, datetime.now(), rule_id)
        )
        db.commit()
        
        return True
    
    @staticmethod
    def deactivate_rule(rule_id: str) -> bool:
        """Deactivate a rule that proved to be incorrect."""
        db.execute(
            "UPDATE learning_rules SET is_active = 0 WHERE id = ?",
            (rule_id,)
        )
        db.commit()
        return True
    
    @staticmethod
    def confirm_rule(rule_id: str, confirmed_by: str) -> bool:
        """Mark a rule as confirmed (golden) by an accountant."""
        db.execute(
            """UPDATE learning_rules 
               SET is_golden = 1, last_confirmed = ?, confidence = 1.0
               WHERE id = ?""",
            (datetime.now(), rule_id)
        )
        db.commit()
        return True
    
    @staticmethod
    def create_correction_history(
        original_voucher_id: str,
        learning_rule_id: Optional[str] = None,
        corrected_voucher_id: Optional[str] = None,
        original_data: Optional[dict] = None,
        corrected_data: Optional[dict] = None,
        change_type: Optional[str] = None,
        was_successful: Optional[bool] = None,
        corrected_by: Optional[str] = None,
        correction_reason: Optional[str] = None,
    ) -> CorrectionHistory:
        """Create a correction history entry."""
        history_id = str(uuid.uuid4())
        now = datetime.now()
        
        original_json = json.dumps(original_data) if original_data else None
        corrected_json = json.dumps(corrected_data) if corrected_data else None
        
        sql = """
        INSERT INTO correction_history
        (id, learning_rule_id, original_voucher_id, corrected_voucher_id,
         original_data, corrected_data, change_type, was_successful,
         corrected_by, correction_reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        db.execute(sql, (
            history_id, learning_rule_id, original_voucher_id, corrected_voucher_id,
            original_json, corrected_json, change_type, was_successful,
            corrected_by, correction_reason, now
        ))
        db.commit()
        
        return CorrectionHistory(
            id=history_id,
            original_voucher_id=original_voucher_id,
            learning_rule_id=learning_rule_id,
            corrected_voucher_id=corrected_voucher_id,
            original_data=original_data,
            corrected_data=corrected_data,
            change_type=change_type,
            was_successful=was_successful,
            corrected_by=corrected_by,
            correction_reason=correction_reason,
            created_at=now,
        )
    
    @staticmethod
    def get_correction_history(rule_id: Optional[str] = None, voucher_id: Optional[str] = None) -> List[CorrectionHistory]:
        """Get correction history for a rule or voucher."""
        if rule_id:
            cursor = db.execute(
                "SELECT * FROM correction_history WHERE learning_rule_id = ? ORDER BY created_at DESC",
                (rule_id,)
            )
        elif voucher_id:
            cursor = db.execute(
                "SELECT * FROM correction_history WHERE original_voucher_id = ? ORDER BY created_at DESC",
                (voucher_id,)
            )
        else:
            cursor = db.execute(
                "SELECT * FROM correction_history ORDER BY created_at DESC LIMIT 100"
            )
        
        return [LearningRepository._row_to_history(row) for row in cursor.fetchall()]
    
    @staticmethod
    def get_stats() -> dict:
        """Get statistics about learning rules."""
        total = db.execute("SELECT COUNT(*) as cnt FROM learning_rules").fetchone()
        active = db.execute("SELECT COUNT(*) as cnt FROM learning_rules WHERE is_active = 1").fetchone()
        golden = db.execute("SELECT COUNT(*) as cnt FROM learning_rules WHERE is_golden = 1").fetchone()
        
        avg_confidence = db.execute(
            "SELECT AVG(confidence) as avg FROM learning_rules WHERE is_active = 1"
        ).fetchone()
        
        recent_corrections = db.execute(
            "SELECT COUNT(*) as cnt FROM correction_history WHERE created_at > datetime('now', '-30 days')"
        ).fetchone()
        
        total_corrections = db.execute(
            "SELECT COUNT(*) as cnt FROM correction_history"
        ).fetchone()
        
        return {
            "total_rules": total["cnt"] if total else 0,
            "active_rules": active["cnt"] if active else 0,
            "golden_rules": golden["cnt"] if golden else 0,
            "avg_confidence": avg_confidence["avg"] if avg_confidence and avg_confidence["avg"] else 0.0,
            "recent_corrections": recent_corrections["cnt"] if recent_corrections else 0,
            "total_corrections": total_corrections["cnt"] if total_corrections else 0,
        }
    
    @staticmethod
    def _row_to_rule(row) -> LearningRule:
        """Convert database row to LearningRule object."""
        return LearningRule(
            id=row["id"],
            pattern_type=row["pattern_type"],
            pattern_value=row["pattern_value"],
            original_account=row["original_account"],
            corrected_account=row["corrected_account"],
            company_id=row["company_id"],
            description=row["description"],
            confidence=row["confidence"],
            usage_count=row["usage_count"],
            success_count=row["success_count"],
            source_voucher_id=row["source_voucher_id"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
            last_confirmed=datetime.fromisoformat(row["last_confirmed"]) if row["last_confirmed"] else None,
            is_active=bool(row["is_active"]),
            is_golden=bool(row["is_golden"]),
        )
    
    @staticmethod
    def _row_to_history(row) -> CorrectionHistory:
        """Convert database row to CorrectionHistory object."""
        original_data = None
        corrected_data = None
        
        if row["original_data"]:
            try:
                original_data = json.loads(row["original_data"])
            except json.JSONDecodeError:
                pass
        
        if row["corrected_data"]:
            try:
                corrected_data = json.loads(row["corrected_data"])
            except json.JSONDecodeError:
                pass
        
        return CorrectionHistory(
            id=row["id"],
            original_voucher_id=row["original_voucher_id"],
            learning_rule_id=row["learning_rule_id"],
            corrected_voucher_id=row["corrected_voucher_id"],
            original_data=original_data,
            corrected_data=corrected_data,
            change_type=row["change_type"],
            was_successful=bool(row["was_successful"]) if row["was_successful"] is not None else None,
            corrected_by=row["corrected_by"],
            correction_reason=row["correction_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
