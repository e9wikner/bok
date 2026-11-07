"""`underlagstolkning`: the server's reading of what the model read from an
underlag (docs/redesign/SPEC-underlagstolkning.md).

The matching windows (§7.2), the checks and confidence (§6.3-§6.4), and
the ranking, `match`, `expected` and the hypothesis (§7.3-§7.5). The
windows are part of what a match *is*, not something to deploy
differently, so they live here and not in `config.py`;
`VoucherRepository.match_candidates` takes them as arguments and has no
defaults of its own. The orchestration -- fetching the source, reading
its text layer, asking for candidates, saving -- is
`services/interpretation_service.py`.

Pure logic: no SQL, no HTTP, no file reading. The caller hands in the
already extracted text layer and the candidate rows.
"""

from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from itertools import combinations
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from domain.interpretation import (
    Candidate,
    Checks,
    Confidence,
    CurrencyCheck,
    DateCheck,
    Expected,
    LinesSumCheck,
    Match,
    MatchKind,
    TextLayerCheck,
    VatRateCheck,
    VatShareCheck,
)
from repositories.voucher_repo import MatchCandidateRow
from services.agent_documents import ReconciliationState, reconciliation_result

# §7.2: the voucher's date in [document_date − 3, document_date + 7] days.
# Asymmetric: a card purchase is drawn 0-3 banking days after the purchase,
# and the bank date is almost never before the receipt's date.
DATE_WINDOW_DAYS_BEFORE = 3
DATE_WINDOW_DAYS_AFTER = 7

# §7.2: |diff| <= max(5 000 öre, 10 % of total_ore). Integer percent, so the
# window stays in whole öre. Without `document_date` the window is 0: only
# the exact amount matches.
AMOUNT_WINDOW_MIN_ORE = 5000
AMOUNT_WINDOW_PERCENT = 10


def amount_window_ore(total_ore: int) -> int:
    """§7.2's amount window for `match_candidates`: max(5 000 öre, 10 % of
    `total_ore`), in whole öre. Without a `document_date` the repository
    ignores it and matches only the exact amount."""
    return max(AMOUNT_WINDOW_MIN_ORE, total_ore * AMOUNT_WINDOW_PERCENT // 100)


# ---------------------------------------------------------------------------
# What the model read (§6.2)
# ---------------------------------------------------------------------------
#
# Protocols with read-only properties rather than a dataclass of our own, so
# U6's Pydantic `TolkaUnderlagArgs` goes into `run_checks` as it is: a
# read-only protocol member is covariant, so `list[TolkaUnderlagLine]`
# satisfies `Sequence[ReadLine]` and `Optional[Literal[25, 12, 6, 0]]`
# satisfies `Optional[int]`. Only the fields the checks use are named.


class ReadLine(Protocol):
    @property
    def amount_ore(self) -> int: ...

    @property
    def vat_rate(self) -> Optional[int]: ...


class Read(Protocol):
    @property
    def document_date(self) -> Optional[date]: ...

    @property
    def currency(self) -> str: ...

    @property
    def total_ore(self) -> int: ...

    @property
    def vat_ore(self) -> Optional[int]: ...

    @property
    def lines(self) -> Sequence[ReadLine]: ...


# ---------------------------------------------------------------------------
# The checks (§6.3) and the confidence (§6.4)
# ---------------------------------------------------------------------------

# ±1 öre per line for `lines_sum` and `vat_rate`.
LINE_TOLERANCE_ORE = 1

# `vat_share`: the Swedish rates in percent of the net, ±0,5 points.
VAT_SHARE_RATES_PERCENT = (25, 12, 6)
VAT_SHARE_TOLERANCE_POINTS = Fraction(1, 2)


def run_checks(read: Read, *, text_layer_text: Optional[str], today: date) -> Checks:
    """Every check of §6.3. None of them rejects the call.

    `text_layer_text` is what `extract_pdf_text` gave for the source, or
    `None` for an image (or anything that is not a PDF). `today` is passed
    in so `date = future` does not depend on the clock."""
    return Checks(
        lines_sum=_lines_sum(read),
        vat_rate=_vat_rate(read),
        vat_share=_vat_share(read),
        text_layer=_text_layer(read, text_layer_text),
        date=_date(read, today),
        currency=_currency(read),
    )


def confidence(checks: Checks) -> Confidence:
    """§6.4, from the checks only. `date = missing` and `currency = not_sek`
    do not lower it."""
    failed = (
        checks.lines_sum == "mismatch"
        or checks.vat_rate == "mismatch"
        or checks.vat_share == "implausible"
        or checks.date == "future"
    )
    if failed:
        return "low"
    if checks.text_layer == "agrees":
        return "high"
    if checks.text_layer == "not_available":
        return "medium"
    return "low"  # disagrees


def _lines_sum(read: Read) -> LinesSumCheck:
    if not read.lines:
        return "not_applicable"
    total = sum(line.amount_ore for line in read.lines)
    tolerance = LINE_TOLERANCE_ORE * len(read.lines)
    return "ok" if abs(total - read.total_ore) <= tolerance else "mismatch"


def _vat_rate(read: Read) -> VatRateCheck:
    """The VAT of each line with a rate, counted backwards from the amount
    incl. VAT, summed exactly and compared with `vat_ore`."""
    rated = [
        (line.amount_ore, line.vat_rate)
        for line in read.lines
        if line.vat_rate is not None
    ]
    if not rated or read.vat_ore is None:
        return "not_applicable"
    vat = sum(
        (Fraction(amount * rate, 100 + rate) for amount, rate in rated), Fraction(0)
    )
    tolerance = LINE_TOLERANCE_ORE * len(rated)
    return "ok" if abs(vat - read.vat_ore) <= tolerance else "mismatch"


def _vat_share(read: Read) -> VatShareCheck:
    """Only without lines: `vat_ore / (total_ore − vat_ore)` near 25, 12 or
    6 %, or 0."""
    if read.lines or read.vat_ore is None:
        return "not_applicable"
    if read.vat_ore == 0:
        return "ok"
    net = read.total_ore - read.vat_ore
    if net <= 0:
        return "implausible"
    share = Fraction(read.vat_ore * 100, net)
    plausible = any(
        abs(share - rate) <= VAT_SHARE_TOLERANCE_POINTS
        for rate in VAT_SHARE_RATES_PERCENT
    )
    return "ok" if plausible else "implausible"


def _text_layer(read: Read, text: Optional[str]) -> TextLayerCheck:
    """The server's own source: the labelled total and VAT that
    `reconciliation_result` finds in the text layer. Only a triple that
    reconciles counts; one that does not add up means the extraction
    scrambled the text, which is then no source to compare with."""
    if not text:
        return "not_available"
    result = reconciliation_result(text)
    if result.state is not ReconciliationState.RECONCILES:
        return "not_available"
    agrees = result.total_ore == read.total_ore and result.vat_ore == read.vat_ore
    return "agrees" if agrees else "disagrees"


def _date(read: Read, today: date) -> DateCheck:
    if read.document_date is None:
        return "missing"
    return "future" if read.document_date > today else "ok"


def _currency(read: Read) -> CurrencyCheck:
    return "sek" if read.currency == "SEK" else "not_sek"


# ---------------------------------------------------------------------------
# The matching (§7.3-§7.5)
# ---------------------------------------------------------------------------
#
# What the matching reads beyond the checks: the vendor and each line's
# text. Protocols again, extending `Read`, so the §6.2 Pydantic model goes
# in as it is.


class MatchReadLine(ReadLine, Protocol):
    @property
    def text(self) -> str: ...


class MatchRead(Read, Protocol):
    @property
    def vendor(self) -> Optional[str]: ...

    @property
    def lines(self) -> Sequence[MatchReadLine]: ...


# §7.3: `candidates` carries at most five.
MAX_CANDIDATES = 5

# §7.4: `exact` when `diff_ore = 0` and `|date_diff_days| <= 3`;
# `exact_no_date` when `diff_ore = 0` and there is no `document_date`.
EXACT_MAX_DATE_DIFF_DAYS = 3

# §7.5: at most three lines, each within ±1 öre.
HYPOTHESIS_MAX_LINES = 3
HYPOTHESIS_TOLERANCE_ORE_PER_LINE = 1


@dataclass(frozen=True)
class Matching:
    """`match` and `candidates` as the tool returns and stores them
    (§6.5): `match` is the unambiguous first candidate or `None`;
    `candidates` the best (at most five) in rank order, `match` first
    when there is one."""

    match: Optional[Match]
    candidates: List[Candidate] = field(default_factory=list)


def match_document(read: MatchRead, rows: Sequence[MatchCandidateRow]) -> Matching:
    """§7.1-§7.4 on the rows `match_candidates` gave. A document in another
    currency than SEK is not matched: no match, no candidates."""
    if read.currency != "SEK":
        return Matching(match=None, candidates=[])
    keyed = _ranked(read, rows)
    candidates = [candidate for _, candidate in keyed[:MAX_CANDIDATES]]
    match = None
    if keyed and (len(keyed) == 1 or keyed[0][0] != keyed[1][0]):
        match = build_match(read, keyed[0][1])
    return Matching(match=match, candidates=candidates)


def rank(read: MatchRead, rows: Sequence[MatchCandidateRow]) -> List[Candidate]:
    """Every row compared with the document (§7.4's fields) and sorted on
    §7.3's keys: `|diff_ore|`, `|date_diff_days|`, then a vendor hit
    first. Stable: rows equal on all three keep the repository's order,
    which is no choice between them -- `match_document` decides that."""
    return [candidate for _, candidate in _ranked(read, rows)]


def build_match(read: MatchRead, candidate: Candidate) -> Match:
    """A `Candidate` as §7.4's `match`: plus `kind` and the server's
    `hypothesis`."""
    return Match(
        **candidate.to_dict(),
        kind=_kind(candidate),
        hypothesis=hypothesis(read.lines, candidate.diff_ore),
    )


def expected(
    read: MatchRead, row: MatchCandidateRow, matching: Matching
) -> Optional[Expected]:
    """§7.3: the full comparison with the voucher the agent expected --
    diff, VAT, hypothesis -- whether or not it is inside the windows, and
    `is_best_match` when it is the unambiguous `match`. It never changes
    the ranking. `None` for a document not in SEK: there is nothing to
    compare an amount in another currency with."""
    if read.currency != "SEK":
        return None
    candidate = _compare(read, row)
    best = matching.match
    return Expected(
        **candidate.to_dict(),
        kind=_kind(candidate),
        hypothesis=hypothesis(read.lines, candidate.diff_ore),
        is_best_match=best is not None and best.voucher_id == row.voucher_id,
    )


def hypothesis(
    lines: Sequence[MatchReadLine], diff_ore: int
) -> Optional[Dict[str, Any]]:
    """§7.5: the smallest set of at most three lines whose amounts sum to
    `diff_ore`, ±1 öre per line, and only if it is the only set of that
    size. One line first, then two, then three; the search of a size stops
    at the second hit, since that already makes it ambiguous. `None` when
    nothing, or more than one set of the smallest size, explains it.

    `lines` in the result are indexes into the document's lines, from 0."""
    if diff_ore == 0:
        return None
    # A zero line explains nothing, and would let a line that is two öre
    # off pass as a pair with it.
    indexed = [(i, line) for i, line in enumerate(lines) if line.amount_ore != 0]
    for size in range(1, HYPOTHESIS_MAX_LINES + 1):
        tolerance = HYPOTHESIS_TOLERANCE_ORE_PER_LINE * size
        hits: List[Tuple[int, ...]] = []
        for combo in combinations(indexed, size):
            if abs(sum(line.amount_ore for _, line in combo) - diff_ore) <= tolerance:
                hits.append(tuple(i for i, _ in combo))
                if len(hits) > 1:
                    return None
        if hits:
            chosen = hits[0]
            return {
                "text": _hypothesis_text(diff_ore, [lines[i].text for i in chosen]),
                "basis": "line_items",
                "lines": list(chosen),
            }
    return None


# -- helpers -----------------------------------------------------------------

_RankKey = Tuple[int, int, bool]


def _ranked(
    read: MatchRead, rows: Sequence[MatchCandidateRow]
) -> List[Tuple[_RankKey, Candidate]]:
    keyed = []
    for row in rows:
        candidate = _compare(read, row)
        key = (
            abs(candidate.diff_ore),
            abs(candidate.date_diff_days or 0),
            not _vendor_hit(read.vendor, row),
        )
        keyed.append((key, candidate))
    keyed.sort(key=lambda pair: pair[0])
    return keyed


def _compare(read: MatchRead, row: MatchCandidateRow) -> Candidate:
    """One row as §7.4's comparison. `diff_ore` is document − voucher;
    `date_diff_days` is voucher − document (positive: booked after the
    receipt, as the window [−3, +7] reads), `None` without a document
    date. `vat.equal` is `None` unless both sides have VAT."""
    date_diff = (
        (row.voucher_date - read.document_date).days
        if read.document_date is not None
        else None
    )
    equal = (
        read.vat_ore == row.vat_ore
        if read.vat_ore is not None and row.vat_ore is not None
        else None
    )
    bank = row.bank_transaction
    return Candidate(
        voucher_id=row.voucher_id,
        voucher_number=row.voucher_number,
        voucher_date=row.voucher_date.isoformat(),
        voucher_description=row.voucher_description,
        amounts={"document_ore": read.total_ore, "voucher_ore": row.voucher_ore},
        diff_ore=read.total_ore - row.voucher_ore,
        date_diff_days=date_diff,
        vat={"document_ore": read.vat_ore, "voucher_ore": row.vat_ore, "equal": equal},
        bank_transaction=(
            {
                "id": bank.id,
                "date": bank.date.isoformat(),
                "amount_ore": bank.amount_ore,
                "counterpart_name": bank.counterpart_name,
                "description": bank.description,
            }
            if bank is not None
            else None
        ),
    )


def _vendor_hit(vendor: Optional[str], row: MatchCandidateRow) -> bool:
    """§7.3's third key: the vendor, case-insensitively, in the voucher's
    description or the linked bank transaction's counterpart or text."""
    if not vendor or not vendor.strip():
        return False
    needle = vendor.strip().casefold()
    bank = row.bank_transaction
    haystacks: List[Optional[str]] = [row.voucher_description]
    if bank is not None:
        haystacks += [bank.counterpart_name, bank.description]
    return any(needle in text.casefold() for text in haystacks if text)


def _kind(candidate: Candidate) -> MatchKind:
    """§7.4. Without a date nothing tells a recurring amount (rent, a
    subscription) from the same purchase, so an exact amount without one
    is its own kind, never `exact` (§12.6 d)."""
    if candidate.diff_ore != 0:
        return "amount_diff"
    if candidate.date_diff_days is None:
        return "exact_no_date"
    if abs(candidate.date_diff_days) <= EXACT_MAX_DATE_DIFF_DAYS:
        return "exact"
    return "amount_diff"


def _hypothesis_text(diff_ore: int, texts: Sequence[str]) -> str:
    quoted = [f"”{text}”" for text in texts]
    if len(quoted) == 1:
        which = f"raden {quoted[0]}"
    else:
        which = f"raderna {', '.join(quoted[:-1])} och {quoted[-1]}"
    return f"Skillnaden på {_format_kr(diff_ore)} kr motsvarar {which} på underlaget."


def _format_kr(value_ore: int) -> str:
    """Swedish amount: space between thousands, comma before öre
    (`1 234,56`). The same format as `services.pdf_export.format_sek`
    (a test holds them together); not imported from there, since that
    module pulls in weasyprint and the report services (about a second
    cold) for one small function."""
    sign = "-" if value_ore < 0 else ""
    kr, ore = divmod(abs(value_ore), 100)
    return f"{sign}{kr:,}".replace(",", " ") + f",{ore:02d}"


# ---------------------------------------------------------------------------
# The comparison in the thread (SPEC-flode-underlag.md §9.1, §9.3, D6, D7)
# ---------------------------------------------------------------------------

#: `JamforelseRader`'s labels for a receipt against a voucher
#: (SPEC-chattyta.md §4.3): the document on the left, the voucher right.
COMPARISON_DOCUMENT_LABEL = "kvitto"


def comparison_rows(part: Candidate) -> List[Dict[str, Any]]:
    """The two numbers per row, as the interpretation stored them: the
    amount including VAT, and the input VAT when both sides have one.
    Shared by the comparison post and the receipt after a link (§9.3: "samma
    som jämförelseinlägget, ur samma tolkning")."""
    rows: List[Dict[str, Any]] = [
        {
            "key": "Belopp",
            "text": "inklusive moms",
            "left_ore": part.amounts["document_ore"],
            "right_ore": part.amounts["voucher_ore"],
        }
    ]
    document_vat = part.vat.get("document_ore")
    voucher_vat = part.vat.get("voucher_ore")
    if document_vat is not None and voucher_vat is not None:
        rows.append(
            {
                "key": "Moms",
                "text": "ingående moms",
                "left_ore": document_vat,
                "right_ore": voucher_vat,
            }
        )
    return rows


def comparison_body(
    part: Candidate,
    *,
    vendor: Optional[str],
    document_date: Optional[date],
) -> Dict[str, Any]:
    """§9.1's `receipt` body for one voucher the underlag was compared
    with: `part` is the interpretation's `match`, its `expected` or a
    candidate. `note` is the server's hypothesis verbatim (§7.5) and only
    that -- left out when there is none (D7). Pure: the caller writes it."""
    number = part.voucher_number or part.voucher_id
    title = " ".join(
        str(piece)
        for piece in ("Kvitto", vendor, document_date, "mot", number)
        if piece is not None and piece != ""
    )
    body: Dict[str, Any] = {
        "title": title,
        "labels": [COMPARISON_DOCUMENT_LABEL, number],
        "rows": comparison_rows(part),
    }
    found = getattr(part, "hypothesis", None)
    if found and found.get("text"):
        body["note"] = found["text"]
    body["voucher_id"] = part.voucher_id
    return body


def comparison_parts(
    match: Optional[Match], compared: Optional[Expected]
) -> List[Candidate]:
    """Which comparisons a thread gets (§9.1): `expected` first -- it is
    what the agent asked for -- then `match` when it is another voucher.
    An `exact` one is skipped: the link that follows carries the rows."""
    parts: List[Candidate] = []
    if compared is not None and compared.kind != "exact":
        parts.append(compared)
    if (
        match is not None
        and match.kind != "exact"
        and (compared is None or match.voucher_id != compared.voucher_id)
    ):
        parts.append(match)
    return parts
