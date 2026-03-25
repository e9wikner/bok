"""Automatic transaction categorization engine.

This service automatically categorizes bank transactions into the correct
BAS 2026 account codes. It uses a multi-layered approach:

1. Exact counterpart matching (highest priority)
2. Keyword rules (configurable, pre-loaded with Swedish business patterns)
3. Regex pattern matching
4. Amount-range based rules
5. Learned patterns from user corrections (ML-lite)

The engine learns from corrections: when a user overrides a suggestion,
the system creates or updates a learned rule for future matching.
"""

import re
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

from db.database import db
from services.bank_integration import BankTransaction, BankIntegrationService


@dataclass
class CategorizationResult:
    """Result of categorizing a transaction."""
    account_code: str
    account_name: Optional[str] = None
    vat_code: Optional[str] = None
    description: str = ""
    confidence: float = 0.0
    rule_id: Optional[str] = None
    rule_type: Optional[str] = None


@dataclass
class CategorizationRule:
    """A rule for automatic categorization."""
    id: str
    rule_type: str
    priority: int
    match_description: Optional[str] = None
    match_counterpart: Optional[str] = None
    match_amount_min: Optional[int] = None
    match_amount_max: Optional[int] = None
    match_is_expense: Optional[int] = None
    target_account_code: str = ""
    target_vat_code: Optional[str] = None
    target_description_template: Optional[str] = None
    confidence: float = 1.0
    times_used: int = 0
    times_overridden: int = 0
    source: str = "manual"
    active: bool = True


class CategorizationService:
    """Automatically categorizes bank transactions into BAS accounts."""

    def __init__(self):
        self.bank_service = BankIntegrationService()

    def categorize_transaction(self, transaction: BankTransaction) -> Optional[CategorizationResult]:
        """Categorize a single bank transaction.
        
        Tries rules in priority order, returns first match with confidence.
        First checks learned rules from user corrections, then falls back to standard rules.
        """
        is_expense = transaction.amount < 0
        description = (transaction.description or "").lower()
        counterpart = (transaction.counterpart_name or "").lower()
        amount = abs(transaction.amount)

        # 1. Check learned rules first (highest confidence)
        from services.learning import LearningService
        learning_service = LearningService()
        learned_result = learning_service.apply_learning(
            transaction_description=transaction.description or "",
            counterparty=transaction.counterpart_name,
            amount=amount,
        )

        if learned_result:
            learned_account, confidence, rule_id = learned_result
            # Get account name
            account_row = db.execute(
                "SELECT name FROM accounts WHERE code = ?",
                (learned_account,)
            ).fetchone()

            return CategorizationResult(
                account_code=learned_account,
                account_name=account_row["name"] if account_row else None,
                description=transaction.description or "",
                confidence=confidence,
                rule_id=rule_id,
                rule_type="learned",
            )

        # 2. Fall back to standard categorization rules
        rules = self._get_active_rules()
        best_match: Optional[CategorizationResult] = None
        best_priority = 999999

        for rule in rules:
            # Check expense/income filter
            if rule.match_is_expense is not None:
                if (rule.match_is_expense == 1) != is_expense:
                    continue

            # Check amount range
            if rule.match_amount_min is not None and amount < rule.match_amount_min:
                continue
            if rule.match_amount_max is not None and amount > rule.match_amount_max:
                continue

            matched = False

            # Counterpart matching (exact, case-insensitive)
            if rule.match_counterpart:
                if rule.match_counterpart.lower() in counterpart:
                    matched = True

            # Description matching (keyword or regex)
            if rule.match_description:
                pattern = rule.match_description.lower()
                if rule.rule_type == "regex":
                    try:
                        if re.search(pattern, description):
                            matched = True
                    except re.error:
                        pass
                else:
                    # Keyword matching: support | for OR
                    keywords = pattern.split("|")
                    if any(kw.strip() in description for kw in keywords):
                        matched = True

            if matched and rule.priority < best_priority:
                # Build description from template
                desc = rule.target_description_template or transaction.description or ""
                desc = desc.replace("{counterpart}", transaction.counterpart_name or "")
                desc = desc.replace("{description}", transaction.description or "")
                desc = desc.replace("{amount}", f"{abs(transaction.amount) / 100:.2f}")

                # Get account name
                account_row = db.execute(
                    "SELECT name FROM accounts WHERE code = ?",
                    (rule.target_account_code,)
                ).fetchone()

                best_match = CategorizationResult(
                    account_code=rule.target_account_code,
                    account_name=account_row["name"] if account_row else None,
                    vat_code=rule.target_vat_code,
                    description=desc,
                    confidence=rule.confidence,
                    rule_id=rule.id,
                    rule_type=rule.rule_type,
                )
                best_priority = rule.priority

        return best_match

    def categorize_pending(self, auto_book: bool = False) -> Dict:
        """Categorize all pending bank transactions.
        
        Args:
            auto_book: If True, automatically create vouchers for high-confidence matches
            
        Returns:
            Summary of categorization results
        """
        pending = self.bank_service.get_transactions(status="pending")
        
        results = {
            "total": len(pending),
            "categorized": 0,
            "high_confidence": 0,
            "low_confidence": 0,
            "uncategorized": 0,
            "auto_booked": 0,
            "details": [],
        }

        for tx in pending:
            result = self.categorize_transaction(tx)
            
            if result:
                results["categorized"] += 1
                
                if result.confidence >= 0.8:
                    results["high_confidence"] += 1
                    status = "categorized"
                else:
                    results["low_confidence"] += 1
                    status = "categorized"

                self.bank_service.update_transaction_status(
                    tx.id,
                    status=status,
                    account_code=result.account_code,
                    confidence=result.confidence,
                )

                # Track rule usage
                if result.rule_id:
                    db.execute(
                        "UPDATE categorization_rules SET times_used = times_used + 1, updated_at = ? WHERE id = ?",
                        (datetime.now().isoformat(), result.rule_id)
                    )
                    db.commit()

                # Auto-book high confidence transactions
                if auto_book and result.confidence >= 0.9:
                    try:
                        voucher_id = self._auto_book_transaction(tx, result)
                        if voucher_id:
                            results["auto_booked"] += 1
                            self.bank_service.update_transaction_status(
                                tx.id, status="booked", voucher_id=voucher_id
                            )
                    except Exception:
                        # Don't fail batch on single booking error
                        pass

                results["details"].append({
                    "transaction_id": tx.id,
                    "description": tx.description,
                    "amount_sek": tx.amount / 100,
                    "suggested_account": result.account_code,
                    "account_name": result.account_name,
                    "confidence": result.confidence,
                    "status": status,
                })
            else:
                results["uncategorized"] += 1
                results["details"].append({
                    "transaction_id": tx.id,
                    "description": tx.description,
                    "amount_sek": tx.amount / 100,
                    "suggested_account": None,
                    "confidence": 0,
                    "status": "pending",
                })

        return results

    def learn_from_correction(
        self,
        transaction_id: str,
        correct_account_code: str,
        correct_vat_code: Optional[str] = None,
    ) -> str:
        """Learn from a user correction to improve future categorization.
        
        When a user overrides the AI's suggestion, we:
        1. Record the override on the old rule
        2. Create/update a learned rule for the pattern
        """
        tx = self.bank_service.get_transaction(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} not found")

        # If there was a previous suggestion, mark it as overridden
        if tx.suggested_account_code and tx.suggested_account_code != correct_account_code:
            # Find the rule that made the suggestion
            # and increment its override count
            rules = self._get_active_rules()
            for rule in rules:
                if rule.id == tx.suggested_account_code:
                    db.execute(
                        "UPDATE categorization_rules SET times_overridden = times_overridden + 1 WHERE id = ?",
                        (rule.id,)
                    )
                    break

        # Create or update a learned rule based on the counterpart
        counterpart = tx.counterpart_name
        description = tx.description

        # Use counterpart if available, otherwise use description keywords
        match_field = "match_counterpart" if counterpart else "match_description"
        match_value = counterpart or description

        if match_value:
            # Check if we already have a learned rule for this pattern
            existing = db.execute(
                f"""SELECT id, times_used FROM categorization_rules 
                    WHERE source = 'learned' AND {match_field} = ? AND target_account_code = ?""",
                (match_value, correct_account_code)
            ).fetchone()

            if existing:
                # Strengthen existing rule
                rule_id = existing["id"]
                new_confidence = min(0.95, 0.7 + (existing["times_used"] * 0.05))
                db.execute(
                    """UPDATE categorization_rules 
                       SET times_used = times_used + 1, confidence = ?, updated_at = ? 
                       WHERE id = ?""",
                    (new_confidence, datetime.now().isoformat(), rule_id)
                )
            else:
                # Create new learned rule
                rule_id = str(uuid.uuid4())
                db.execute(
                    """INSERT INTO categorization_rules 
                       (id, rule_type, priority, {match_field}, match_is_expense,
                        target_account_code, target_vat_code, confidence, source)
                       VALUES (?, 'learned', 50, ?, ?, ?, ?, 0.7, 'learned')""".format(match_field=match_field),
                    (rule_id, match_value, 1 if tx.amount < 0 else 0,
                     correct_account_code, correct_vat_code)
                )

            db.commit()

        # Update the transaction
        self.bank_service.update_transaction_status(
            transaction_id,
            status="categorized",
            account_code=correct_account_code,
            confidence=1.0,
        )

        return rule_id if match_value else ""

    def add_rule(
        self,
        rule_type: str,
        match_description: Optional[str] = None,
        match_counterpart: Optional[str] = None,
        match_is_expense: Optional[bool] = None,
        match_amount_min: Optional[float] = None,
        match_amount_max: Optional[float] = None,
        target_account_code: str = "",
        target_vat_code: Optional[str] = None,
        target_description_template: Optional[str] = None,
        priority: int = 50,
    ) -> str:
        """Add a new categorization rule."""
        rule_id = str(uuid.uuid4())
        
        is_expense_int = None
        if match_is_expense is not None:
            is_expense_int = 1 if match_is_expense else 0

        amount_min = int(match_amount_min * 100) if match_amount_min is not None else None
        amount_max = int(match_amount_max * 100) if match_amount_max is not None else None

        with db.transaction():
            db.execute(
                """INSERT INTO categorization_rules 
                   (id, rule_type, priority, match_description, match_counterpart,
                    match_amount_min, match_amount_max, match_is_expense,
                    target_account_code, target_vat_code, target_description_template,
                    confidence, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, 'manual')""",
                (rule_id, rule_type, priority, match_description, match_counterpart,
                 amount_min, amount_max, is_expense_int,
                 target_account_code, target_vat_code, target_description_template)
            )
        
        return rule_id

    def get_rules(self, include_inactive: bool = False) -> List[CategorizationRule]:
        """Get all categorization rules."""
        sql = "SELECT * FROM categorization_rules"
        if not include_inactive:
            sql += " WHERE active = 1"
        sql += " ORDER BY priority ASC, times_used DESC"
        
        rows = db.execute(sql).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def get_stats(self) -> Dict:
        """Get categorization statistics."""
        total = db.execute("SELECT COUNT(*) as cnt FROM bank_transactions").fetchone()
        by_status = db.execute("""
            SELECT status, COUNT(*) as cnt 
            FROM bank_transactions 
            GROUP BY status
        """).fetchall()
        
        rules = db.execute("""
            SELECT source, COUNT(*) as cnt, SUM(times_used) as total_uses
            FROM categorization_rules WHERE active = 1
            GROUP BY source
        """).fetchall()
        
        return {
            "transactions": {
                "total": total["cnt"] if total else 0,
                "by_status": {r["status"]: r["cnt"] for r in by_status},
            },
            "rules": {
                "by_source": {r["source"]: {"count": r["cnt"], "total_uses": r["total_uses"] or 0} for r in rules},
            }
        }

    def _auto_book_transaction(self, tx: BankTransaction, result: CategorizationResult) -> Optional[str]:
        """Create a voucher from a categorized bank transaction.
        
        Uses the ledger service to create a proper double-entry voucher.
        """
        from services.ledger import LedgerService
        
        ledger = LedgerService()
        amount = abs(tx.amount)
        is_expense = tx.amount < 0
        
        # Determine the period
        period = ledger.periods.find_period_for_date(tx.transaction_date)
        if not period or not period.is_open():
            return None

        # Build voucher rows
        rows = []
        
        if is_expense:
            # Expense: Debit expense account, Credit bank account (1930)
            rows.append({
                "account_code": result.account_code,
                "debit": amount,
                "credit": 0,
                "description": result.description,
            })
            
            # Add VAT row if applicable
            if result.vat_code and result.vat_code != "MF":
                vat_rates = {"MP1": 0.25, "MP2": 0.12, "MP3": 0.06}
                vat_rate = vat_rates.get(result.vat_code, 0)
                if vat_rate > 0:
                    # Recalculate: amount includes VAT
                    net_amount = int(amount / (1 + vat_rate))
                    vat_amount = amount - net_amount
                    
                    # Adjust expense row
                    rows[0]["debit"] = net_amount
                    
                    # Add VAT row (ingående moms)
                    vat_account = {"MP1": "2640", "MP2": "2640", "MP3": "2640"}.get(result.vat_code, "2640")
                    rows.append({
                        "account_code": vat_account,
                        "debit": vat_amount,
                        "credit": 0,
                        "description": f"Ingående moms {int(vat_rate*100)}%",
                    })
            
            # Credit bank account
            rows.append({
                "account_code": "1930",  # Företagskonto
                "debit": 0,
                "credit": amount,
                "description": result.description,
            })
        else:
            # Income: Debit bank account (1930), Credit revenue account
            rows.append({
                "account_code": "1930",
                "debit": amount,
                "credit": 0,
                "description": result.description,
            })
            
            # Add VAT row if applicable
            if result.vat_code and result.vat_code != "MF":
                vat_rates = {"MP1": 0.25, "MP2": 0.12, "MP3": 0.06}
                vat_rate = vat_rates.get(result.vat_code, 0)
                if vat_rate > 0:
                    net_amount = int(amount / (1 + vat_rate))
                    vat_amount = amount - net_amount
                    
                    # Revenue (net)
                    rows.append({
                        "account_code": result.account_code,
                        "debit": 0,
                        "credit": net_amount,
                        "description": result.description,
                    })
                    
                    # Utgående moms
                    vat_account = {"MP1": "2610", "MP2": "2620", "MP3": "2630"}.get(result.vat_code, "2610")
                    rows.append({
                        "account_code": vat_account,
                        "debit": 0,
                        "credit": vat_amount,
                        "description": f"Utgående moms {int(vat_rate*100)}%",
                    })
                else:
                    rows.append({
                        "account_code": result.account_code,
                        "debit": 0,
                        "credit": amount,
                        "description": result.description,
                    })
            else:
                rows.append({
                    "account_code": result.account_code,
                    "debit": 0,
                    "credit": amount,
                    "description": result.description,
                })

        voucher = ledger.create_voucher(
            series="A",
            date=tx.transaction_date,
            period_id=period.id,
            description=f"Bank: {result.description}",
            rows_data=rows,
            created_by="auto-categorization",
        )
        
        # Auto-post the voucher
        ledger.post_voucher(voucher.id)
        
        return voucher.id

    def _get_active_rules(self) -> List[CategorizationRule]:
        """Get all active rules sorted by priority."""
        rows = db.execute(
            "SELECT * FROM categorization_rules WHERE active = 1 ORDER BY priority ASC"
        ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def _row_to_rule(self, row) -> CategorizationRule:
        return CategorizationRule(
            id=row["id"],
            rule_type=row["rule_type"],
            priority=row["priority"],
            match_description=row["match_description"],
            match_counterpart=row["match_counterpart"],
            match_amount_min=row["match_amount_min"],
            match_amount_max=row["match_amount_max"],
            match_is_expense=row["match_is_expense"],
            target_account_code=row["target_account_code"],
            target_vat_code=row["target_vat_code"],
            target_description_template=row["target_description_template"],
            confidence=row["confidence"],
            times_used=row["times_used"],
            times_overridden=row["times_overridden"],
            source=row["source"],
            active=bool(row["active"]),
        )
