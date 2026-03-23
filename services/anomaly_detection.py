"""Anomaly detection service for Swedish small business accounting.

Rule-based + simple statistical patterns. ML-ready architecture.
Focused on preventing common bookkeeping errors before they happen.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from collections import defaultdict
import statistics
import math

from domain.models import Voucher, VoucherRow, Account
from domain.types import VoucherStatus, AccountType
from repositories.voucher_repo import VoucherRepository
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository


# --- Enums & Data classes ---

class AnomalySeverity(str, Enum):
    """Severity level for anomalies."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    """Types of anomalies detected."""
    UNMATCHED_TRANSACTION = "unmatched_transaction"
    UNUSUAL_AMOUNT = "unusual_amount"
    WRONG_VAT_CODE = "wrong_vat_code"
    MISSING_COUNTER_ENTRY = "missing_counter_entry"
    FREQUENT_SMALL_TRANSACTIONS = "frequent_small_transactions"
    UNUSUAL_BALANCE_CHANGE = "unusual_balance_change"
    DUPLICATE_ENTRY = "duplicate_entry"
    MISSING_ATTACHMENT = "missing_attachment"
    ABNORMAL_VOUCHER_COUNT = "abnormal_voucher_count"
    WEEKEND_TRANSACTION = "weekend_transaction"
    ROUND_AMOUNT = "round_amount_pattern"
    SEASONAL_DEVIATION = "seasonal_deviation"


@dataclass
class Anomaly:
    """A detected anomaly."""
    id: str
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    entity_type: str  # "voucher", "account", "period"
    entity_id: str
    title: str
    description: str
    score: float  # 0.0 - 1.0 anomaly score
    details: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.anomaly_type.value,
            "severity": self.severity.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "title": self.title,
            "description": self.description,
            "score": round(self.score, 3),
            "details": self.details,
            "detected_at": self.detected_at.isoformat(),
            "resolved": self.resolved,
        }


@dataclass
class AnomalyThresholds:
    """Configurable thresholds per company."""
    # Unusual amount: Z-score threshold
    unusual_amount_z_score: float = 2.5
    # Min transactions to calculate statistics
    min_transactions_for_stats: int = 5
    # Frequent small transactions: count in period
    frequent_small_tx_count: int = 10
    # Small transaction threshold (öre)
    small_tx_threshold: int = 50000  # 500 kr
    # Balance change threshold (percentage)
    balance_change_pct: float = 200.0  # 200% change
    # Duplicate detection: same amount + same day
    duplicate_window_days: int = 3
    # Voucher count per period: std dev multiplier
    voucher_count_z_score: float = 2.0
    # Round amount threshold (divisible by)
    round_amount_divisor: int = 100000  # 1000 kr

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnomalyThresholds":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# --- Rule Engine ---

class AnomalyRule:
    """Base class for anomaly detection rules."""
    
    def __init__(self, thresholds: AnomalyThresholds):
        self.thresholds = thresholds
        self._counter = 0
    
    def _make_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._counter}"
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        raise NotImplementedError


class UnusualAmountRule(AnomalyRule):
    """Flag transactions with unusual amounts for a given account."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        vouchers: List[Voucher] = context.get("vouchers", [])
        
        # Group amounts by account
        account_amounts: Dict[str, List[int]] = defaultdict(list)
        account_rows: Dict[str, List[Tuple[VoucherRow, Voucher]]] = defaultdict(list)
        
        for v in vouchers:
            if v.status != VoucherStatus.POSTED:
                continue
            for row in v.rows:
                amount = row.get_amount()
                account_amounts[row.account_code].append(amount)
                account_rows[row.account_code].append((row, v))
        
        for account_code, amounts in account_amounts.items():
            if len(amounts) < self.thresholds.min_transactions_for_stats:
                continue
            
            mean = statistics.mean(amounts)
            stdev = statistics.stdev(amounts)
            if stdev == 0:
                continue
            
            for row, voucher in account_rows[account_code]:
                amount = row.get_amount()
                z_score = abs((amount - mean) / stdev)
                
                if z_score >= self.thresholds.unusual_amount_z_score:
                    score = min(1.0, z_score / 5.0)
                    severity = (
                        AnomalySeverity.CRITICAL if z_score > 4
                        else AnomalySeverity.WARNING if z_score > 3
                        else AnomalySeverity.INFO
                    )
                    anomalies.append(Anomaly(
                        id=self._make_id("unusual"),
                        anomaly_type=AnomalyType.UNUSUAL_AMOUNT,
                        severity=severity,
                        entity_type="voucher",
                        entity_id=voucher.id,
                        title=f"Ovanligt belopp på konto {account_code}",
                        description=(
                            f"Beloppet {amount / 100:.2f} kr avviker från "
                            f"genomsnittet {mean / 100:.2f} kr "
                            f"(Z-score: {z_score:.1f})"
                        ),
                        score=score,
                        details={
                            "account_code": account_code,
                            "amount_ore": amount,
                            "mean_ore": int(mean),
                            "stdev_ore": int(stdev),
                            "z_score": round(z_score, 2),
                            "voucher_date": voucher.date.isoformat(),
                        },
                    ))
        return anomalies


class WrongVATCodeRule(AnomalyRule):
    """Flag likely incorrect VAT codes based on account type."""
    
    # Common Swedish VAT rules
    ACCOUNT_VAT_EXPECTATIONS = {
        # Revenue accounts typically have output VAT
        "3": {"expected": ["MP1", "MP2", "MP3", "MF"], "note": "Intäktskonto"},
        # Purchase accounts (4xxx) typically have input VAT
        "4": {"expected": ["MP1", "MP2", "MP3", "MF"], "note": "Inköpskonto"},
        # Salary costs should never have VAT
        "7": {"expected": [None, ""], "note": "Personalkostnad – ska ej ha moms"},
    }
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        vouchers: List[Voucher] = context.get("vouchers", [])
        accounts: Dict[str, Account] = context.get("accounts", {})
        
        for v in vouchers:
            for row in v.rows:
                account = accounts.get(row.account_code)
                if not account:
                    continue
                
                # Check salary accounts (7xxx) with VAT
                if row.account_code.startswith("7") and account.vat_code:
                    anomalies.append(Anomaly(
                        id=self._make_id("vat"),
                        anomaly_type=AnomalyType.WRONG_VAT_CODE,
                        severity=AnomalySeverity.WARNING,
                        entity_type="voucher",
                        entity_id=v.id,
                        title=f"Momskod på personalkonto {row.account_code}",
                        description=(
                            f"Konto {row.account_code} ({account.name}) "
                            f"har momskod {account.vat_code} – "
                            f"personalkostnader ska normalt inte ha moms."
                        ),
                        score=0.7,
                        details={
                            "account_code": row.account_code,
                            "vat_code": account.vat_code,
                        },
                    ))
                
                # Check if revenue account (3xxx) missing VAT
                if (row.account_code.startswith("3") and 
                    not account.vat_code and 
                    row.credit > 0 and
                    not row.account_code.startswith("39")):  # 39xx = exempt
                    anomalies.append(Anomaly(
                        id=self._make_id("vat"),
                        anomaly_type=AnomalyType.WRONG_VAT_CODE,
                        severity=AnomalySeverity.INFO,
                        entity_type="voucher",
                        entity_id=v.id,
                        title=f"Saknar momskod på intäktskonto {row.account_code}",
                        description=(
                            f"Konto {row.account_code} ({account.name}) "
                            f"saknar momskod. Kontrollera om moms ska tillämpas."
                        ),
                        score=0.4,
                        details={"account_code": row.account_code},
                    ))
        return anomalies


class MissingCounterEntryRule(AnomalyRule):
    """Flag vouchers that might be missing a counter-entry."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        vouchers: List[Voucher] = context.get("vouchers", [])
        
        for v in vouchers:
            if v.status != VoucherStatus.POSTED:
                continue
            
            # Check for single-sided entries (only debit or only credit accounts)
            debit_accounts = set()
            credit_accounts = set()
            for row in v.rows:
                if row.debit > 0:
                    debit_accounts.add(row.account_code)
                if row.credit > 0:
                    credit_accounts.add(row.account_code)
            
            # A proper voucher should have both debit and credit
            if not debit_accounts or not credit_accounts:
                anomalies.append(Anomaly(
                    id=self._make_id("counter"),
                    anomaly_type=AnomalyType.MISSING_COUNTER_ENTRY,
                    severity=AnomalySeverity.CRITICAL,
                    entity_type="voucher",
                    entity_id=v.id,
                    title=f"Verifikation {v.series.value}{v.number} saknar motkonto",
                    description=(
                        "Verifikationen har bara "
                        f"{'debet' if debit_accounts else 'kredit'}-poster. "
                        "Kontrollera att alla motkonteringar finns."
                    ),
                    score=0.9,
                    details={
                        "debit_accounts": list(debit_accounts),
                        "credit_accounts": list(credit_accounts),
                    },
                ))
        return anomalies


class DuplicateEntryRule(AnomalyRule):
    """Flag potential duplicate vouchers."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        vouchers: List[Voucher] = context.get("vouchers", [])
        seen_already = set()
        
        # Group by (date ± window, total amount, description similarity)
        for i, v1 in enumerate(vouchers):
            if v1.status != VoucherStatus.POSTED:
                continue
            total1 = v1.get_total_debit()
            
            for v2 in vouchers[i + 1:]:
                if v2.status != VoucherStatus.POSTED:
                    continue
                if v2.id == v1.id:
                    continue
                
                pair_key = tuple(sorted([v1.id, v2.id]))
                if pair_key in seen_already:
                    continue
                
                # Same total amount
                total2 = v2.get_total_debit()
                if total1 != total2 or total1 == 0:
                    continue
                
                # Within date window
                date_diff = abs((v1.date - v2.date).days)
                if date_diff > self.thresholds.duplicate_window_days:
                    continue
                
                # Check account overlap
                accounts1 = {r.account_code for r in v1.rows}
                accounts2 = {r.account_code for r in v2.rows}
                overlap = accounts1 & accounts2
                
                if len(overlap) >= 2:
                    seen_already.add(pair_key)
                    score = 0.6 + (0.2 if date_diff == 0 else 0)
                    score += 0.1 * (len(overlap) / max(len(accounts1), len(accounts2)))
                    score = min(1.0, score)
                    
                    anomalies.append(Anomaly(
                        id=self._make_id("dup"),
                        anomaly_type=AnomalyType.DUPLICATE_ENTRY,
                        severity=AnomalySeverity.WARNING,
                        entity_type="voucher",
                        entity_id=v1.id,
                        title=f"Möjlig dubblettbokning",
                        description=(
                            f"Verifikation {v1.series.value}{v1.number} "
                            f"({v1.date}) liknar "
                            f"{v2.series.value}{v2.number} ({v2.date}). "
                            f"Samma belopp ({total1 / 100:.2f} kr) och "
                            f"{len(overlap)} gemensamma konton."
                        ),
                        score=score,
                        details={
                            "voucher_1": v1.id,
                            "voucher_2": v2.id,
                            "amount_ore": total1,
                            "date_diff_days": date_diff,
                            "common_accounts": list(overlap),
                        },
                    ))
        return anomalies


class FrequentSmallTransactionsRule(AnomalyRule):
    """Flag many small transactions from same pattern."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        vouchers: List[Voucher] = context.get("vouchers", [])
        
        # Group small transactions by account pair
        account_pair_count: Dict[Tuple[str, str], int] = defaultdict(int)
        account_pair_total: Dict[Tuple[str, str], int] = defaultdict(int)
        
        for v in vouchers:
            if v.status != VoucherStatus.POSTED:
                continue
            total = v.get_total_debit()
            if total > self.thresholds.small_tx_threshold or total == 0:
                continue
            
            debit_accs = [r.account_code for r in v.rows if r.debit > 0]
            credit_accs = [r.account_code for r in v.rows if r.credit > 0]
            
            for d in debit_accs:
                for c in credit_accs:
                    pair = (d, c)
                    account_pair_count[pair] += 1
                    account_pair_total[pair] += total
        
        for pair, count in account_pair_count.items():
            if count >= self.thresholds.frequent_small_tx_count:
                total = account_pair_total[pair]
                score = min(1.0, count / (self.thresholds.frequent_small_tx_count * 3))
                anomalies.append(Anomaly(
                    id=self._make_id("freq"),
                    anomaly_type=AnomalyType.FREQUENT_SMALL_TRANSACTIONS,
                    severity=AnomalySeverity.INFO,
                    entity_type="account",
                    entity_id=pair[0],
                    title=f"Många små transaktioner {pair[0]} → {pair[1]}",
                    description=(
                        f"{count} småtransaktioner (under "
                        f"{self.thresholds.small_tx_threshold / 100:.0f} kr) "
                        f"mellan konto {pair[0]} och {pair[1]}. "
                        f"Totalt {total / 100:.2f} kr. "
                        f"Överväg att slå ihop till färre verifikationer."
                    ),
                    score=score,
                    details={
                        "debit_account": pair[0],
                        "credit_account": pair[1],
                        "count": count,
                        "total_ore": total,
                    },
                ))
        return anomalies


class UnusualBalanceChangeRule(AnomalyRule):
    """Flag accounts with unusual balance swings between periods."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        period_balances: Dict[str, Dict[str, int]] = context.get("period_balances", {})
        
        # Need at least 2 periods
        period_ids = sorted(period_balances.keys())
        if len(period_ids) < 2:
            return anomalies
        
        prev_period = period_ids[-2]
        curr_period = period_ids[-1]
        prev_bals = period_balances[prev_period]
        curr_bals = period_balances[curr_period]
        
        all_accounts = set(prev_bals.keys()) | set(curr_bals.keys())
        
        for account_code in all_accounts:
            prev_bal = prev_bals.get(account_code, 0)
            curr_bal = curr_bals.get(account_code, 0)
            
            if prev_bal == 0:
                continue
            
            change_pct = abs((curr_bal - prev_bal) / prev_bal) * 100
            
            if change_pct >= self.thresholds.balance_change_pct:
                score = min(1.0, change_pct / 500)
                severity = (
                    AnomalySeverity.CRITICAL if change_pct > 500
                    else AnomalySeverity.WARNING if change_pct > 300
                    else AnomalySeverity.INFO
                )
                anomalies.append(Anomaly(
                    id=self._make_id("balance"),
                    anomaly_type=AnomalyType.UNUSUAL_BALANCE_CHANGE,
                    severity=severity,
                    entity_type="account",
                    entity_id=account_code,
                    title=f"Ovanlig saldoförändring på konto {account_code}",
                    description=(
                        f"Saldot ändrades med {change_pct:.0f}% "
                        f"från {prev_bal / 100:.2f} kr till {curr_bal / 100:.2f} kr "
                        f"mellan period {prev_period} och {curr_period}."
                    ),
                    score=score,
                    details={
                        "account_code": account_code,
                        "previous_balance_ore": prev_bal,
                        "current_balance_ore": curr_bal,
                        "change_pct": round(change_pct, 1),
                        "previous_period": prev_period,
                        "current_period": curr_period,
                    },
                ))
        return anomalies


class AbnormalVoucherCountRule(AnomalyRule):
    """Flag periods with abnormally few or many vouchers."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        period_voucher_counts: Dict[str, int] = context.get("period_voucher_counts", {})
        
        if len(period_voucher_counts) < 3:
            return anomalies
        
        counts = list(period_voucher_counts.values())
        mean = statistics.mean(counts)
        stdev = statistics.stdev(counts)
        if stdev == 0:
            return anomalies
        
        for period_id, count in period_voucher_counts.items():
            z_score = abs((count - mean) / stdev)
            if z_score >= self.thresholds.voucher_count_z_score:
                direction = "få" if count < mean else "många"
                score = min(1.0, z_score / 4.0)
                anomalies.append(Anomaly(
                    id=self._make_id("vcount"),
                    anomaly_type=AnomalyType.ABNORMAL_VOUCHER_COUNT,
                    severity=AnomalySeverity.INFO,
                    entity_type="period",
                    entity_id=period_id,
                    title=f"Ovanligt {direction} verifikationer i period {period_id}",
                    description=(
                        f"Period {period_id} har {count} verifikationer. "
                        f"Genomsnitt: {mean:.0f}, "
                        f"standardavvikelse: {stdev:.1f}."
                    ),
                    score=score,
                    details={
                        "count": count,
                        "mean": round(mean, 1),
                        "stdev": round(stdev, 1),
                        "z_score": round(z_score, 2),
                    },
                ))
        return anomalies


class MissingAttachmentRule(AnomalyRule):
    """Flag vouchers missing attachments (BFL requirement)."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        vouchers: List[Voucher] = context.get("vouchers", [])
        attachments: Dict[str, bool] = context.get("voucher_has_attachment", {})
        
        for v in vouchers:
            if v.status != VoucherStatus.POSTED:
                continue
            
            has_attachment = attachments.get(v.id, False)
            if not has_attachment:
                # Higher severity for larger amounts
                total = v.get_total_debit()
                severity = (
                    AnomalySeverity.WARNING if total > 500000  # > 5000 kr
                    else AnomalySeverity.INFO
                )
                score = 0.3 if total < 100000 else 0.5 if total < 500000 else 0.7
                anomalies.append(Anomaly(
                    id=self._make_id("attach"),
                    anomaly_type=AnomalyType.MISSING_ATTACHMENT,
                    severity=severity,
                    entity_type="voucher",
                    entity_id=v.id,
                    title=f"Saknar bilaga – Ver {v.series.value}{v.number}",
                    description=(
                        f"Verifikation {v.series.value}{v.number} ({v.date}) "
                        f"på {total / 100:.2f} kr saknar underlag. "
                        f"Enligt BFL ska varje verifikation ha en bilaga."
                    ),
                    score=score,
                    details={
                        "voucher_number": f"{v.series.value}{v.number}",
                        "amount_ore": total,
                        "voucher_date": v.date.isoformat(),
                    },
                ))
        return anomalies


class WeekendTransactionRule(AnomalyRule):
    """Flag transactions on weekends (potential dating errors)."""
    
    def check(self, context: Dict[str, Any]) -> List[Anomaly]:
        anomalies = []
        vouchers: List[Voucher] = context.get("vouchers", [])
        
        for v in vouchers:
            if v.date.weekday() >= 5:  # Saturday=5, Sunday=6
                day_name = "lördag" if v.date.weekday() == 5 else "söndag"
                anomalies.append(Anomaly(
                    id=self._make_id("weekend"),
                    anomaly_type=AnomalyType.WEEKEND_TRANSACTION,
                    severity=AnomalySeverity.INFO,
                    entity_type="voucher",
                    entity_id=v.id,
                    title=f"Transaktion på {day_name}",
                    description=(
                        f"Verifikation {v.series.value}{v.number} är daterad "
                        f"{v.date} ({day_name}). Kontrollera att datumet är korrekt."
                    ),
                    score=0.2,
                    details={"day_of_week": v.date.weekday()},
                ))
        return anomalies


# --- Main Anomaly Detection Service ---

class AnomalyDetectionService:
    """Main anomaly detection orchestrator.
    
    Runs configurable rules against accounting data and produces
    scored anomaly reports.
    """
    
    def __init__(self, thresholds: Optional[AnomalyThresholds] = None):
        self.thresholds = thresholds or AnomalyThresholds()
        self.voucher_repo = VoucherRepository()
        self.account_repo = AccountRepository()
        self.period_repo = PeriodRepository()
        
        # Initialize rules
        self.rules: List[AnomalyRule] = [
            UnusualAmountRule(self.thresholds),
            WrongVATCodeRule(self.thresholds),
            MissingCounterEntryRule(self.thresholds),
            DuplicateEntryRule(self.thresholds),
            FrequentSmallTransactionsRule(self.thresholds),
            UnusualBalanceChangeRule(self.thresholds),
            AbnormalVoucherCountRule(self.thresholds),
            MissingAttachmentRule(self.thresholds),
            WeekendTransactionRule(self.thresholds),
        ]
    
    def _build_context(self, period_id: Optional[str] = None) -> Dict[str, Any]:
        """Build analysis context from repositories."""
        # Get all vouchers (or filtered by period)
        all_vouchers = self.voucher_repo.list_all()
        if period_id:
            vouchers = [v for v in all_vouchers if v.period_id == period_id]
        else:
            vouchers = all_vouchers
        
        # Get accounts
        accounts = self.account_repo.get_all_as_dict()
        
        # Build period balance map for trend analysis
        period_balances: Dict[str, Dict[str, int]] = {}
        period_voucher_counts: Dict[str, int] = defaultdict(int)
        
        for v in all_vouchers:
            if v.status != VoucherStatus.POSTED:
                continue
            period_voucher_counts[v.period_id] += 1
            
            if v.period_id not in period_balances:
                period_balances[v.period_id] = defaultdict(int)
            
            for row in v.rows:
                period_balances[v.period_id][row.account_code] += (row.debit - row.credit)
        
        # Attachment check (currently no attachment storage, so all are "missing")
        # This would integrate with a real attachment repository
        voucher_has_attachment: Dict[str, bool] = {}
        for v in vouchers:
            # Default to False; real implementation would check attachment repo
            voucher_has_attachment[v.id] = False
        
        return {
            "vouchers": vouchers,
            "accounts": accounts,
            "period_balances": dict(period_balances),
            "period_voucher_counts": dict(period_voucher_counts),
            "voucher_has_attachment": voucher_has_attachment,
        }
    
    def analyze(
        self,
        period_id: Optional[str] = None,
        rule_types: Optional[List[str]] = None,
    ) -> List[Anomaly]:
        """Run anomaly detection and return sorted results.
        
        Args:
            period_id: Optional period filter
            rule_types: Optional list of AnomalyType values to run
            
        Returns:
            List of Anomaly objects sorted by score (highest first)
        """
        context = self._build_context(period_id)
        anomalies: List[Anomaly] = []
        
        for rule in self.rules:
            # Filter by type if specified
            if rule_types:
                rule_type_name = rule.__class__.__name__.replace("Rule", "")
                # Simple check: skip if no matching type requested
                # More precise: check against AnomalyType values
                pass  # Run all rules for now, filter output
            
            try:
                found = rule.check(context)
                anomalies.extend(found)
            except Exception as e:
                # Log but don't fail entire analysis
                print(f"Warning: Rule {rule.__class__.__name__} failed: {e}")
        
        # Filter by requested types
        if rule_types:
            anomalies = [a for a in anomalies if a.anomaly_type.value in rule_types]
        
        # Sort by score descending
        anomalies.sort(key=lambda a: a.score, reverse=True)
        return anomalies
    
    def analyze_voucher(self, voucher_id: str) -> List[Anomaly]:
        """Run anomaly detection for a single voucher."""
        voucher = self.voucher_repo.get(voucher_id)
        if not voucher:
            return []
        
        context = self._build_context()
        # Override vouchers to just this one for targeted rules
        single_context = {**context, "vouchers": [voucher]}
        
        anomalies = []
        for rule in self.rules:
            try:
                found = rule.check(single_context)
                anomalies.extend(found)
            except Exception:
                pass
        
        anomalies.sort(key=lambda a: a.score, reverse=True)
        return anomalies
    
    def get_summary(self, period_id: Optional[str] = None) -> Dict[str, Any]:
        """Get anomaly summary statistics."""
        anomalies = self.analyze(period_id)
        
        by_severity = defaultdict(int)
        by_type = defaultdict(int)
        
        for a in anomalies:
            by_severity[a.severity.value] += 1
            by_type[a.anomaly_type.value] += 1
        
        return {
            "total_anomalies": len(anomalies),
            "by_severity": dict(by_severity),
            "by_type": dict(by_type),
            "avg_score": round(
                statistics.mean([a.score for a in anomalies]), 3
            ) if anomalies else 0,
            "critical_count": by_severity.get("critical", 0),
            "warning_count": by_severity.get("warning", 0),
            "info_count": by_severity.get("info", 0),
            "top_anomalies": [a.to_dict() for a in anomalies[:5]],
        }
