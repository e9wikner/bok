"""Domain types for `underlagstolkning` (SPEC-underlagstolkning.md §5-§7).

An `Interpretation` is one row of `intake_interpretations` (migration 030):
what the model read from an underlag (`vendor` … `lines`, claims) and what
the server computed from it at that moment (`checks`, `confidence`, `match`,
`candidates`, facts). It is never rewritten; a new interpretation of the
same source is a new row.

No logic here beyond (de)serialising the `*_json` columns. Computing the
checks, the confidence, the ranking and the hypothesis live in
`services/interpretation.py`; the SQL in `repositories/interpretation_repo.py`.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Mapping, Optional

# §6.4: three levels, not a number.
Confidence = Literal["high", "medium", "low"]

# §7.4: `exact` when `diff_ore = 0` and `date_diff_days <= 3`.
MatchKind = Literal["exact", "amount_diff"]

# §6.3: the values each check can take.
LinesSumCheck = Literal["ok", "mismatch", "not_applicable"]
VatRateCheck = Literal["ok", "mismatch", "not_applicable"]
VatShareCheck = Literal["ok", "implausible", "not_applicable"]
TextLayerCheck = Literal["agrees", "disagrees", "not_available"]
DateCheck = Literal["ok", "future", "missing"]
CurrencyCheck = Literal["sek", "not_sek"]


@dataclass(frozen=True)
class Checks:
    """The server's checks of what the model read (§6.3), stored as
    `checks_json`. Computed by `services.interpretation.run_checks`; the
    confidence is derived from them, never from the model (§6.4)."""

    lines_sum: LinesSumCheck
    vat_rate: VatRateCheck
    vat_share: VatShareCheck
    text_layer: TextLayerCheck
    date: DateCheck
    currency: CurrencyCheck

    def to_dict(self) -> Dict[str, str]:
        """As stored in `checks_json` and returned by the tool, in §6.3's
        order."""
        return asdict(self)


@dataclass
class Candidate:
    """A posted voucher without underlag that the document was compared
    with (§7.2-§7.3). Dates are ISO strings, as in the JSON the tool
    returns (§6.5); amounts in öre.

    `amounts` is `{"document_ore", "voucher_ore"}`, `vat` is
    `{"document_ore", "voucher_ore", "equal"}`, `bank_transaction` is the
    linked bank event (`id`, `date`, `amount_ore`, `counterpart_name`, …) or
    `None`."""

    voucher_id: str
    voucher_number: Optional[str]
    voucher_date: str
    voucher_description: Optional[str]
    amounts: Dict[str, int]
    diff_ore: int
    date_diff_days: Optional[int]
    vat: Dict[str, Any]
    bank_transaction: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Candidate":
        return cls(**dict(data))


@dataclass
class Match(Candidate):
    """The unambiguous best candidate (§7.4): a `Candidate` plus `kind` and
    the server's `hypothesis` (`{"text", "basis", "lines"}`, §7.5) or
    `None`. `diff_ore` is document − voucher."""

    kind: MatchKind = "amount_diff"
    hypothesis: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        # §7.4's key order: `kind` first.
        data = asdict(self)
        return {"kind": data.pop("kind"), **data}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Match":
        return cls(**dict(data))


@dataclass
class Interpretation:
    """One `intake_interpretations` row (§5)."""

    intake_source_id: str
    total_ore: int
    checks: Dict[str, str]
    confidence: Confidence
    actor: str
    vendor: Optional[str] = None
    document_date: Optional[date] = None
    currency: str = "SEK"
    vat_ore: Optional[int] = None
    lines: List[Dict[str, Any]] = field(default_factory=list)
    match: Optional[Match] = None
    candidates: List[Candidate] = field(default_factory=list)
    expected_voucher_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    thread_id: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

    # -- (de)serialisation of the *_json columns ---------------------------

    def json_columns(self) -> Dict[str, Optional[str]]:
        """`lines_json`, `checks_json`, `match_json` and `candidates_json`
        as stored. `match_json` is `NULL` when there is no unambiguous
        match."""
        return {
            "lines_json": _dumps(self.lines),
            "checks_json": _dumps(self.checks),
            "match_json": _dumps(self.match.to_dict()) if self.match else None,
            "candidates_json": _dumps([c.to_dict() for c in self.candidates]),
        }

    @staticmethod
    def from_json_columns(
        *,
        lines_json: Optional[str],
        checks_json: str,
        match_json: Optional[str],
        candidates_json: Optional[str],
    ) -> Dict[str, Any]:
        """The inverse of `json_columns`, as keyword arguments for
        `Interpretation(...)`."""
        match = json.loads(match_json) if match_json else None
        return {
            "lines": json.loads(lines_json or "[]"),
            "checks": json.loads(checks_json),
            "match": Match.from_dict(match) if match is not None else None,
            "candidates": [
                Candidate.from_dict(c) for c in json.loads(candidates_json or "[]")
            ],
        }


def _dumps(value: Any) -> str:
    # Swedish text (`”Pant”`, `Förbrukningsinventarier`) stored as written.
    return json.dumps(value, ensure_ascii=False)
