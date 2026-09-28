"""`underlagstolkning`: the server's reading of what the model read from an
underlag (docs/redesign/SPEC-underlagstolkning.md).

The matching windows (§7.2) and the checks and confidence (§6.3-§6.4).
The windows are part of what a match *is*, not something to deploy
differently, so they live here and not in `config.py`;
`VoucherRepository.match_candidates` takes them as arguments and has no
defaults of its own. The ranking and the hypothesis (U5) and the
orchestration (U6) come later.

Pure logic: no SQL, no HTTP, no file reading. The caller hands in the
already extracted text layer.
"""

from datetime import date
from fractions import Fraction
from typing import Optional, Protocol, Sequence

from domain.interpretation import (
    Checks,
    Confidence,
    CurrencyCheck,
    DateCheck,
    LinesSumCheck,
    TextLayerCheck,
    VatRateCheck,
    VatShareCheck,
)
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
