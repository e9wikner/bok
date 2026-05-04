"""Domain models for accounting pattern analysis."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List, Dict, Any


@dataclass
class AccountingPattern:
    id: str
    name: str
    status: str
    match_type: str
    match_config: Dict[str, Any]
    voucher_template: Dict[str, Any]
    confidence: float = 0.0
    source: str = "analysis"
    sample_count: int = 0
    last_analyzed_at: Optional[datetime] = None
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


@dataclass
class AccountingPatternExample:
    id: str
    pattern_id: str
    voucher_id: str
    match_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AccountingPatternEvaluation:
    id: str
    name: str
    baseline_rule_ids: List[str]
    candidate_rule_ids: List[str]
    summary: Dict[str, Any]
    fiscal_year_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    status: str = "completed"
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class AccountingPatternEvaluationCase:
    id: str
    evaluation_id: str
    voucher_id: str
    actual_result: Dict[str, Any]
    baseline_result: Optional[Dict[str, Any]]
    candidate_result: Optional[Dict[str, Any]]
    baseline_score: float
    candidate_score: float
    winner: str
    notes: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
