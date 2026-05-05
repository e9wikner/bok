"""Analyze historical vouchers into agent-usable accounting patterns."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
import re

from domain.accounting_pattern_models import AccountingPattern
from domain.models import Voucher
from domain.types import VoucherSeries, VoucherStatus
from repositories.account_repo import AccountRepository
from repositories.accounting_pattern_repo import AccountingPatternRepository
from repositories.voucher_repo import VoucherRepository


STOPWORDS = {
    "och",
    "till",
    "fran",
    "från",
    "for",
    "för",
    "med",
    "utan",
    "ver",
    "faktura",
    "invoice",
    "betalning",
    "betald",
    "skickad",
    "se",
    "sek",
    "kr",
    "ab",
    "januari",
    "februari",
    "mars",
    "april",
    "maj",
    "juni",
    "juli",
    "augusti",
    "september",
    "oktober",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "okt",
    "nov",
    "dec",
}


class AccountingPatternAnalysisService:
    """Create and evaluate accounting rules from posted vouchers."""

    def __init__(self):
        self.patterns = AccountingPatternRepository()
        self.vouchers = VoucherRepository()

    def analyze(
        self,
        fiscal_year_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        min_examples: int = 2,
        created_by: str = "system",
    ) -> Dict[str, Any]:
        vouchers = self._load_vouchers(fiscal_year_id, date_from, date_to)
        groups: Dict[Tuple[str, str], List[Voucher]] = defaultdict(list)
        self.patterns.archive_suggested_analysis()

        for voucher in vouchers:
            key = self._description_key(voucher.description)
            if not key:
                continue
            signature = self._signature(voucher)
            if not signature:
                continue
            groups[(key, signature)].append(voucher)

        created = []
        ignored = 0
        for (description_key, signature), examples in groups.items():
            if len(examples) < min_examples:
                ignored += len(examples)
                continue
            pattern = self._build_pattern(
                description_key=description_key,
                signature=signature,
                examples=examples,
                created_by=created_by,
            )
            created.append(pattern)

        return {
            "vouchers_analyzed": len(vouchers),
            "groups_found": len(groups),
            "suggested_created_or_updated": len(created),
            "ignored_vouchers": ignored,
            "min_examples": min_examples,
            "patterns": [self.pattern_to_dict(pattern, include_examples=True) for pattern in created],
        }

    def list_patterns(self, status: Optional[str] = None, include_examples: bool = False) -> List[Dict[str, Any]]:
        return [
            self.pattern_to_dict(pattern, include_examples=include_examples)
            for pattern in self.patterns.list_all(status=status)
        ]

    def get_pattern(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        pattern = self.patterns.get(pattern_id)
        if not pattern:
            return None
        return self.pattern_to_dict(pattern, include_examples=True)

    def approve(self, pattern_id: str, actor: str) -> Optional[Dict[str, Any]]:
        pattern = self.patterns.approve(pattern_id, actor)
        return self.pattern_to_dict(pattern, include_examples=True) if pattern else None

    def reject(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        pattern = self.patterns.reject(pattern_id)
        return self.pattern_to_dict(pattern, include_examples=True) if pattern else None

    def evaluate(
        self,
        name: str,
        fiscal_year_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        candidate_rule_ids: Optional[List[str]] = None,
        include_all_suggested: bool = True,
        created_by: str = "system",
    ) -> Dict[str, Any]:
        vouchers = self._load_vouchers(fiscal_year_id, date_from, date_to)
        active = self.patterns.list_all(status="active")
        suggested = self.patterns.list_all(status="suggested")

        if candidate_rule_ids:
            allowed = set(candidate_rule_ids)
            suggested = [pattern for pattern in suggested if pattern.id in allowed]
        elif not include_all_suggested:
            suggested = []

        baseline_rules = active
        candidate_rules = active + suggested

        cases = []
        for voucher in vouchers:
            actual = self._actual_result(voucher)
            baseline = self._apply_rules(voucher, baseline_rules)
            candidate = self._apply_rules(voucher, candidate_rules)
            baseline_score = self._score(actual, baseline)
            candidate_score = self._score(actual, candidate)
            winner = self._winner(baseline_score, candidate_score)
            cases.append(
                {
                    "voucher": voucher,
                    "actual": actual,
                    "baseline": baseline,
                    "candidate": candidate,
                    "baseline_score": baseline_score,
                    "candidate_score": candidate_score,
                    "winner": winner,
                }
            )

        summary = self._evaluation_summary(cases)
        evaluation = self.patterns.create_evaluation(
            name=name,
            baseline_rule_ids=[pattern.id for pattern in baseline_rules],
            candidate_rule_ids=[pattern.id for pattern in candidate_rules],
            fiscal_year_id=fiscal_year_id,
            date_from=date_from,
            date_to=date_to,
            summary=summary,
            created_by=created_by,
        )
        for case in cases:
            self.patterns.add_evaluation_case(
                evaluation_id=evaluation.id,
                voucher_id=case["voucher"].id,
                actual_result=case["actual"],
                baseline_result=case["baseline"],
                candidate_result=case["candidate"],
                baseline_score=case["baseline_score"],
                candidate_score=case["candidate_score"],
                winner=case["winner"],
            )

        return self.evaluation_to_dict(evaluation)

    def list_evaluations(self) -> List[Dict[str, Any]]:
        return [self.evaluation_to_dict(item) for item in self.patterns.list_evaluations()]

    def get_evaluation(self, evaluation_id: str) -> Optional[Dict[str, Any]]:
        evaluation = self.patterns.get_evaluation(evaluation_id)
        return self.evaluation_to_dict(evaluation) if evaluation else None

    def list_evaluation_cases(
        self, evaluation_id: str, winner: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        cases = self.patterns.list_evaluation_cases(evaluation_id, winner=winner, limit=limit)
        return [
            {
                "id": case.id,
                "evaluation_id": case.evaluation_id,
                "voucher_id": case.voucher_id,
                "actual_result": case.actual_result,
                "baseline_result": case.baseline_result,
                "candidate_result": case.candidate_result,
                "baseline_score": case.baseline_score,
                "candidate_score": case.candidate_score,
                "winner": case.winner,
                "notes": case.notes,
                "created_at": case.created_at,
            }
            for case in cases
        ]

    def pattern_to_dict(self, pattern: AccountingPattern, include_examples: bool = False) -> Dict[str, Any]:
        accounts_by_code = AccountRepository.get_all_as_dict(active_only=False)
        data = {
            "id": pattern.id,
            "name": pattern.name,
            "status": pattern.status,
            "match_type": pattern.match_type,
            "match_config": pattern.match_config,
            "voucher_template": self._enrich_template_accounts(pattern.voucher_template, accounts_by_code),
            "confidence": pattern.confidence,
            "source": pattern.source,
            "sample_count": pattern.sample_count,
            "last_analyzed_at": pattern.last_analyzed_at,
            "created_by": pattern.created_by,
            "created_at": pattern.created_at,
            "updated_at": pattern.updated_at,
            "approved_by": pattern.approved_by,
            "approved_at": pattern.approved_at,
        }
        if include_examples:
            data["examples"] = self.patterns.list_examples(pattern.id)
        return data

    def _enrich_template_accounts(
        self,
        voucher_template: Dict[str, Any],
        accounts_by_code: Dict[str, Any],
    ) -> Dict[str, Any]:
        enriched = dict(voucher_template or {})
        rows = []
        for row in enriched.get("rows", []):
            enriched_row = dict(row)
            account_code = str(enriched_row.get("account", ""))
            account = accounts_by_code.get(account_code)
            if account:
                enriched_row["account_name"] = account.name
            rows.append(enriched_row)
        enriched["rows"] = rows
        return enriched

    def evaluation_to_dict(self, evaluation) -> Dict[str, Any]:
        return {
            "id": evaluation.id,
            "name": evaluation.name,
            "baseline_rule_ids": evaluation.baseline_rule_ids,
            "candidate_rule_ids": evaluation.candidate_rule_ids,
            "fiscal_year_id": evaluation.fiscal_year_id,
            "date_from": evaluation.date_from,
            "date_to": evaluation.date_to,
            "status": evaluation.status,
            "summary": evaluation.summary,
            "created_by": evaluation.created_by,
            "created_at": evaluation.created_at,
            "completed_at": evaluation.completed_at,
        }

    def _load_vouchers(
        self,
        fiscal_year_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[Voucher]:
        vouchers, _ = self.vouchers.list_all(
            status=VoucherStatus.POSTED.value,
            fiscal_year_id=fiscal_year_id,
            exclude_series=[VoucherSeries.IB.value],
        )
        filtered = []
        for voucher in vouchers:
            if date_from and voucher.date < date_from:
                continue
            if date_to and voucher.date > date_to:
                continue
            if not voucher.rows or not voucher.is_balanced():
                continue
            filtered.append(voucher)
        return filtered

    def _build_pattern(
        self,
        description_key: str,
        signature: str,
        examples: List[Voucher],
        created_by: str,
    ) -> AccountingPattern:
        gross_values = [self._gross(voucher) for voucher in examples]
        min_amount = min(gross_values)
        max_amount = max(gross_values)
        confidence = self._confidence(gross_values, len(examples))
        template = self._template_from_examples(examples, signature)
        match_config = {
            "description_key": description_key,
            "description_contains": description_key.split(),
            "amount_min": int(min_amount * 0.8),
            "amount_max": int(max_amount * 1.2),
            "direction": self._direction(examples[0]),
        }
        name = self._human_name(description_key)
        return self.patterns.create_or_update_suggestion(
            name=name,
            match_type="description",
            match_config=match_config,
            voucher_template=template,
            confidence=confidence,
            sample_count=len(examples),
            example_voucher_ids=[voucher.id for voucher in examples[:20]],
            created_by=created_by,
        )

    def _template_from_examples(self, examples: List[Voucher], signature: str) -> Dict[str, Any]:
        buckets: Dict[Tuple[str, str], List[float]] = defaultdict(list)
        for voucher in examples:
            gross = self._gross(voucher)
            if gross <= 0:
                continue
            per_voucher: Dict[Tuple[str, str], int] = defaultdict(int)
            for row in voucher.rows:
                side = "debit" if row.debit > 0 else "credit"
                amount = row.debit or row.credit
                per_voucher[(row.account_code, side)] += amount
            for key, amount in per_voucher.items():
                buckets[key].append(amount / gross)

        rows = []
        for (account, side), ratios in sorted(buckets.items()):
            rows.append(
                {
                    "account": account,
                    "side": side,
                    "amount": "ratio",
                    "ratio": round(sum(ratios) / len(ratios), 8),
                }
            )
        return {"signature": signature, "rows": rows}

    def _apply_rules(self, voucher: Voucher, rules: List[AccountingPattern]) -> Optional[Dict[str, Any]]:
        for pattern in sorted(rules, key=lambda item: (item.confidence, item.sample_count), reverse=True):
            if self._matches(voucher, pattern):
                return self._render_pattern(voucher, pattern)
        return None

    def _matches(self, voucher: Voucher, pattern: AccountingPattern) -> bool:
        config = pattern.match_config
        description = self._normalized_text(voucher.description)
        terms = config.get("description_contains") or []
        if terms and not all(term in description for term in terms):
            return False
        gross = self._gross(voucher)
        if config.get("amount_min") is not None and gross < config["amount_min"]:
            return False
        if config.get("amount_max") is not None and gross > config["amount_max"]:
            return False
        direction = config.get("direction")
        if direction and direction != self._direction(voucher):
            return False
        return True

    def _render_pattern(self, voucher: Voucher, pattern: AccountingPattern) -> Dict[str, Any]:
        gross = self._gross(voucher)
        rows = []
        for row in pattern.voucher_template.get("rows", []):
            amount = int(round(gross * float(row.get("ratio", 0))))
            rows.append(
                {
                    "account": row["account"],
                    "debit": amount if row["side"] == "debit" else 0,
                    "credit": amount if row["side"] == "credit" else 0,
                }
            )
        rows = self._balance_rendered_rows(rows)
        return {
            "pattern_id": pattern.id,
            "pattern_name": pattern.name,
            "description": voucher.description,
            "rows": self._normalized_rows(rows),
            "balanced": sum(row["debit"] for row in rows) == sum(row["credit"] for row in rows),
        }

    def _balance_rendered_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        debit_total = sum(row["debit"] for row in rows)
        credit_total = sum(row["credit"] for row in rows)
        diff = debit_total - credit_total
        if diff == 0:
            return rows
        target_side = "credit" if diff > 0 else "debit"
        candidates = [row for row in rows if row[target_side] > 0]
        if candidates:
            candidates[-1][target_side] += abs(diff)
        return rows

    def _actual_result(self, voucher: Voucher) -> Dict[str, Any]:
        return {
            "description": voucher.description,
            "rows": self._normalized_rows(
                [
                    {"account": row.account_code, "debit": row.debit, "credit": row.credit}
                    for row in voucher.rows
                ]
            ),
            "balanced": voucher.is_balanced(),
        }

    def _score(self, actual: Dict[str, Any], predicted: Optional[Dict[str, Any]]) -> float:
        if not predicted or not predicted.get("balanced"):
            return 0.0
        actual_rows = actual["rows"]
        predicted_rows = predicted["rows"]
        actual_keys = {(row["account"], "debit" if row["debit"] else "credit") for row in actual_rows}
        predicted_keys = {(row["account"], "debit" if row["debit"] else "credit") for row in predicted_rows}
        if not actual_keys:
            return 0.0

        account_side_score = len(actual_keys & predicted_keys) / len(actual_keys | predicted_keys)
        amount_scores = []
        predicted_by_key = {
            (row["account"], "debit" if row["debit"] else "credit"): row["debit"] or row["credit"]
            for row in predicted_rows
        }
        for row in actual_rows:
            key = (row["account"], "debit" if row["debit"] else "credit")
            actual_amount = row["debit"] or row["credit"]
            predicted_amount = predicted_by_key.get(key)
            if predicted_amount is None or actual_amount == 0:
                amount_scores.append(0.0)
            else:
                amount_scores.append(max(0.0, 1.0 - abs(actual_amount - predicted_amount) / actual_amount))
        amount_score = sum(amount_scores) / len(amount_scores) if amount_scores else 0.0
        return round(account_side_score * 0.65 + amount_score * 0.35, 4)

    def _evaluation_summary(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(cases)
        baseline_exact = sum(1 for case in cases if case["baseline_score"] >= 0.999)
        candidate_exact = sum(1 for case in cases if case["candidate_score"] >= 0.999)
        baseline_matched = sum(1 for case in cases if case["baseline_score"] > 0)
        candidate_matched = sum(1 for case in cases if case["candidate_score"] > 0)
        baseline_avg = sum(case["baseline_score"] for case in cases) / total if total else 0
        candidate_avg = sum(case["candidate_score"] for case in cases) / total if total else 0
        improvements = sum(1 for case in cases if case["candidate_score"] > case["baseline_score"] + 0.0001)
        regressions = sum(1 for case in cases if case["candidate_score"] + 0.0001 < case["baseline_score"])
        unchanged = total - improvements - regressions
        return {
            "cases_total": total,
            "baseline": {
                "matched": baseline_matched,
                "exact": baseline_exact,
                "average_score": round(baseline_avg, 4),
            },
            "candidate": {
                "matched": candidate_matched,
                "exact": candidate_exact,
                "average_score": round(candidate_avg, 4),
            },
            "delta": {
                "matched": candidate_matched - baseline_matched,
                "exact": candidate_exact - baseline_exact,
                "average_score": round(candidate_avg - baseline_avg, 4),
            },
            "regressions": regressions,
            "improvements": improvements,
            "unchanged": unchanged,
        }

    def _winner(self, baseline_score: float, candidate_score: float) -> str:
        if candidate_score > baseline_score + 0.0001:
            return "candidate"
        if candidate_score + 0.0001 < baseline_score:
            return "regression"
        if candidate_score == 0 and baseline_score == 0:
            return "none"
        return "unchanged"

    def _signature(self, voucher: Voucher) -> str:
        parts = set()
        for row in voucher.rows:
            side = "D" if row.debit > 0 else "C"
            parts.add(f"{row.account_code}:{side}")
        return "|".join(sorted(parts))

    def _description_key(self, description: str) -> str:
        tokens = [
            token
            for token in self._normalized_text(description).split()
            if len(token) >= 3 and token not in STOPWORDS and not token.isdigit()
        ]
        return " ".join(tokens[:4])

    def _normalized_text(self, text: str) -> str:
        normalized = text.lower()
        normalized = re.sub(r"\b\d{4}-?\d{2}-?\d{2}\b", " ", normalized)
        normalized = re.sub(r"#?\d+([,.]\d+)?", " ", normalized)
        normalized = re.sub(r"[^a-zåäö0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _human_name(self, description_key: str) -> str:
        return " ".join(token.capitalize() for token in description_key.split())

    def _gross(self, voucher: Voucher) -> int:
        return max(voucher.get_total_debit(), voucher.get_total_credit())

    def _direction(self, voucher: Voucher) -> str:
        cash_accounts = {"1910", "1920", "1930", "1940", "1941", "1942", "1950"}
        for row in voucher.rows:
            if row.account_code in cash_accounts:
                if row.credit > 0:
                    return "expense"
                if row.debit > 0:
                    return "income"
        return "transfer"

    def _confidence(self, gross_values: List[int], sample_count: int) -> float:
        if not gross_values:
            return 0.0
        min_amount = min(gross_values)
        max_amount = max(gross_values)
        variability = 0.0 if max_amount == 0 else (max_amount - min_amount) / max_amount
        sample_score = min(1.0, sample_count / 6)
        stability_score = max(0.0, 1.0 - variability)
        return round(0.55 + sample_score * 0.25 + stability_score * 0.20, 4)

    def _normalized_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        aggregated: Dict[Tuple[str, str], int] = defaultdict(int)
        for row in rows:
            account = str(row["account"])
            debit = int(row.get("debit") or 0)
            credit = int(row.get("credit") or 0)
            if debit:
                aggregated[(account, "debit")] += debit
            if credit:
                aggregated[(account, "credit")] += credit

        return sorted(
            [
                {
                    "account": account,
                    "debit": amount if side == "debit" else 0,
                    "credit": amount if side == "credit" else 0,
                }
                for (account, side), amount in aggregated.items()
            ],
            key=lambda row: (row["account"], row["credit"], row["debit"]),
        )
