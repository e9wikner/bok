"""AI Learning service - learns from user corrections to improve categorization.

This service implements ML-lite functionality that learns from user corrections
to automatically suggest better account codes for future transactions.
"""

import re
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from domain.models import Voucher, LearningRule
from repositories.learning_repo import LearningRepository
from repositories.voucher_repo import VoucherRepository
from services.categorization import CategorizationService


class LearningService:
    """Service for learning from corrections and applying learned rules."""
    
    # Confidence threshold for auto-applying learned rules
    CONFIDENCE_THRESHOLD = 0.8
    
    def __init__(self):
        self.rules = LearningRepository()
        self.categorization = CategorizationService()
        self.vouchers = VoucherRepository()
    
    def learn_from_correction(
        self,
        original_voucher: Voucher,
        corrected_voucher: Voucher,
        correction_reason: Optional[str] = None,
        corrected_by: Optional[str] = None,
    ) -> LearningRule:
        """Learn from a user correction.
        
        1. Compare original and corrected voucher
        2. Identify what changed (account, amount, VAT, etc.)
        3. Create/update learning rule
        4. Save to correction_history
        """
        # Analyze what changed
        analysis = self.analyze_correction(original_voucher, corrected_voucher)
        
        if not analysis or analysis.get('change_type') is None:
            raise ValueError("Could not identify changes between vouchers")
        
        change_type = analysis['change_type']
        
        # Extract pattern from description
        pattern_type, pattern_value = self._extract_pattern(
            original_voucher.description,
            analysis.get('pattern_detected')
        )
        
        # Create or update learning rule
        rule = self.rules.create_rule(
            pattern_type=pattern_type,
            pattern_value=pattern_value,
            original_account=analysis.get('original_account'),
            corrected_account=analysis['corrected_account'],
            description=self._generate_rule_description(
                original_voucher.description,
                analysis.get('original_account'),
                analysis['corrected_account'],
                change_type
            ),
            source_voucher_id=original_voucher.id,
            created_by=corrected_by or 'system',
        )
        
        # Record correction history
        self.rules.create_correction_history(
            original_voucher_id=original_voucher.id,
            corrected_voucher_id=corrected_voucher.id,
            learning_rule_id=rule.id,
            original_data=analysis.get('original_data'),
            corrected_data=analysis.get('corrected_data'),
            change_type=change_type,
            was_successful=None,  # Will be updated later based on user feedback
            corrected_by=corrected_by,
            correction_reason=correction_reason,
        )
        
        return rule
    
    def analyze_correction(self, original: Voucher, corrected: Voucher) -> Optional[Dict]:
        """Analyze the difference between two vouchers.
        
        Returns:
            {
                'change_type': 'account',  # or 'amount', 'vat', 'multiple'
                'original_account': '5410',
                'corrected_account': '5610',
                'pattern_detected': 'resa',  # keyword that triggered the change
                'confidence_delta': 0.1,
                'original_data': {...},
                'corrected_data': {...},
            }
        """
        original_data = self._voucher_to_dict(original)
        corrected_data = self._voucher_to_dict(corrected)
        
        # Compare accounts
        original_accounts = {r.account_code for r in original.rows}
        corrected_accounts = {r.account_code for r in corrected.rows}
        
        # Find changed accounts
        added_accounts = corrected_accounts - original_accounts
        removed_accounts = original_accounts - corrected_accounts
        
        if len(added_accounts) == 1 and len(removed_accounts) == 1:
            # Simple account change
            original_account = list(removed_accounts)[0]
            corrected_account = list(added_accounts)[0]
            
            # Detect pattern from description
            pattern = self._detect_pattern(original.description)
            
            return {
                'change_type': 'account',
                'original_account': original_account,
                'corrected_account': corrected_account,
                'pattern_detected': pattern,
                'confidence_delta': 0.1,
                'original_data': original_data,
                'corrected_data': corrected_data,
            }
        
        # Check for amount changes on same account
        if original_accounts == corrected_accounts:
            for orig_row in original.rows:
                for corr_row in corrected.rows:
                    if orig_row.account_code == corr_row.account_code:
                        if orig_row.debit != corr_row.debit or orig_row.credit != corr_row.credit:
                            return {
                                'change_type': 'amount',
                                'account': orig_row.account_code,
                                'original_amount': orig_row.debit or orig_row.credit,
                                'corrected_amount': corr_row.debit or corr_row.credit,
                                'pattern_detected': self._detect_pattern(original.description),
                                'confidence_delta': 0.05,
                                'original_data': original_data,
                                'corrected_data': corrected_data,
                            }
        
        # Multiple changes
        if len(added_accounts) > 0 or len(removed_accounts) > 0:
            return {
                'change_type': 'multiple',
                'original_accounts': list(original_accounts),
                'corrected_accounts': list(corrected_accounts),
                'pattern_detected': self._detect_pattern(original.description),
                'confidence_delta': 0.05,
                'original_data': original_data,
                'corrected_data': corrected_data,
            }
        
        return None
    
    def apply_learning(
        self,
        transaction_description: str,
        suggested_account: Optional[str] = None,
        counterparty: Optional[str] = None,
        amount: Optional[int] = None,
    ) -> Optional[Tuple[str, float, str]]:
        """Apply learned rules to suggest account.
        
        Returns:
            Tuple of (corrected_account, confidence, rule_id) or None
        """
        # Find matching rules
        matching_rules = self.rules.find_matching_rules(
            description=transaction_description,
            counterparty=counterparty,
            amount=amount,
            original_account=suggested_account,
        )
        
        if not matching_rules:
            return None
        
        # Get highest confidence rule
        best_rule = matching_rules[0]
        
        if best_rule.confidence < self.CONFIDENCE_THRESHOLD:
            return None
        
        # Update usage
        self.rules.increment_usage(best_rule.id, was_successful=True)
        
        return (best_rule.corrected_account, best_rule.confidence, best_rule.id)
    
    def get_learning_stats(self) -> Dict:
        """Get statistics for dashboard.
        
        Returns:
            {
                'total_rules': int,
                'active_rules': int,
                'avg_confidence': float,
                'golden_rules': int,
                'recent_corrections': int,
                'top_rules': List[LearningRule],
            }
        """
        stats = self.rules.get_stats()
        
        # Get top rules
        top_rules = self.rules.list_rules(active_only=True, limit=10)
        
        return {
            **stats,
            'top_rules': top_rules,
        }
    
    def export_rules(self, format: str = 'json') -> str:
        """Export rules for backup or sharing."""
        rules = self.rules.list_rules(active_only=False, limit=10000)
        
        if format == 'json':
            export_data = {
                'exported_at': datetime.now().isoformat(),
                'rules': [
                    {
                        'id': r.id,
                        'pattern_type': r.pattern_type,
                        'pattern_value': r.pattern_value,
                        'original_account': r.original_account,
                        'corrected_account': r.corrected_account,
                        'description': r.description,
                        'confidence': r.confidence,
                        'is_golden': r.is_golden,
                    }
                    for r in rules
                ]
            }
            return json.dumps(export_data, indent=2, ensure_ascii=False)
        
        raise ValueError(f"Unsupported format: {format}")
    
    def import_rules(self, rules_data: str, format: str = 'json') -> int:
        """Import rules from backup or another company.
        
        Returns:
            Number of rules imported
        """
        if format != 'json':
            raise ValueError(f"Unsupported format: {format}")
        
        data = json.loads(rules_data)
        rules = data.get('rules', [])
        
        imported_count = 0
        for rule_data in rules:
            # Check if similar rule already exists
            existing = self.rules._find_existing_rule(
                rule_data['pattern_type'],
                rule_data['pattern_value'],
                rule_data.get('original_account'),
                rule_data['corrected_account']
            )
            
            if not existing:
                self.rules.create_rule(
                    pattern_type=rule_data['pattern_type'],
                    pattern_value=rule_data['pattern_value'],
                    original_account=rule_data.get('original_account'),
                    corrected_account=rule_data['corrected_account'],
                    description=rule_data.get('description'),
                    created_by='import',
                )
                imported_count += 1
        
        return imported_count
    
    def _voucher_to_dict(self, voucher: Voucher) -> Dict:
        """Convert voucher to dictionary for storage."""
        return {
            'id': voucher.id,
            'description': voucher.description,
            'rows': [
                {
                    'account_code': r.account_code,
                    'debit': r.debit,
                    'credit': r.credit,
                    'description': r.description,
                }
                for r in voucher.rows
            ]
        }
    
    def _detect_pattern(self, description: str) -> Optional[str]:
        """Detect the key pattern from a description."""
        if not description:
            return None
        
        description_lower = description.lower()
        
        # Common Swedish business keywords
        keywords = {
            'resa': ['resa', 'resor', 'tåg', 'flyg', 'hotell', 'uber', 'taxi'],
            'mat': ['restaurang', 'lunch', 'fika', 'mat', 'pizza', 'burger'],
            'kontor': ['kontor', 'kontors', 'papper', 'pennor', 'stol', 'bord'],
            'it': ['programvara', 'licens', 'server', 'hosting', 'cloud', 'software'],
            'marknadsföring': ['annons', 'marketing', 'seo', 'google ads', 'facebook'],
            'lön': ['lön', 'löne', 'pension', 'försäkring', 'arbetsgivar'],
            'fordon': ['bil', 'fordon', 'bensin', 'diesel', 'parkering', 'leasing'],
            'telefon': ['telefon', 'mobil', 'bredband', 'internet', 'tele2', 'telia'],
        }
        
        for pattern, words in keywords.items():
            if any(word in description_lower for word in words):
                return pattern
        
        return None
    
    def _extract_pattern(self, description: str, detected_pattern: Optional[str]) -> Tuple[str, str]:
        """Extract pattern type and value from description."""
        if detected_pattern:
            return ('keyword', detected_pattern)
        
        # Try to extract meaningful words
        words = description.lower().split()
        # Filter out common stop words
        stop_words = {'från', 'till', 'den', 'det', 'en', 'ett', 'och', 'för', 'med', 'av', 'på', 'i', 'om'}
        meaningful = [w for w in words if w not in stop_words and len(w) > 2]
        
        if meaningful:
            return ('keyword', meaningful[0])
        
        return ('regex', '.*')  # Fallback
    
    def _generate_rule_description(
        self,
        transaction_desc: str,
        original_account: Optional[str],
        corrected_account: str,
        change_type: str
    ) -> str:
        """Generate human-readable description for a rule."""
        if change_type == 'account':
            if original_account:
                return f"Ändra från konto {original_account} till {corrected_account} för '{transaction_desc[:30]}...'"
            else:
                return f"Bokför på konto {corrected_account} för '{transaction_desc[:30]}...'"
        elif change_type == 'amount':
            return f"Justera belopp för '{transaction_desc[:30]}...'"
        else:
            return f"Korrigera '{transaction_desc[:30]}...'"
    
    def confirm_rule(self, rule_id: str, confirmed_by: str) -> bool:
        """Confirm a rule as correct (sets is_golden)."""
        return self.rules.confirm_rule(rule_id, confirmed_by)
    
    def deactivate_rule(self, rule_id: str) -> bool:
        """Deactivate an incorrect rule."""
        return self.rules.deactivate_rule(rule_id)
