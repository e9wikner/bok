"""Content selection for one intake source (docs/redesign/SPEC-agentruntime.md §6.3).

This module decides what an `IntakeSource` actually costs to send an LLM, and
implements SPEC §6.3's three-step order:

1. A PDF with a readable text layer whose own numbers reconcile -> only the
   extracted text, as a `text` content block (a few hundred tokens).
2. Step 1 gave nothing, or the numbers don't reconcile, and the adapter can
   read a `document` block -> the raw PDF bytes as a `document` block (the
   adapter/API rasterizes the pages; 6,000-7,800 tokens/page).
3. Same as step 2, but the adapter has no `document` block capability ->
   abstention: `DocumentUnreadableError` with a human-readable reason meant
   for a `registrera_avstaende` motivation (A7).

Images (`IntakeService.ALLOWED_MIME_TYPES`'s four image types) always go as
an `image` content block, on both protocol paths -- there is no text-layer
question for an image, so that branch never escalates.

This module is a pure content-selection function, not a repository or
service wrapper: it takes `file_bytes` and a mime type as explicit
parameters instead of reading `IntakeService` internals itself. The future
`hamta_underlagsfil` tool (A7) is what calls
`IntakeService.resolve_source_file`, reads the bytes, and hands them here.

Layering (see CLAUDE.md): no SQL, no `db.execute`, no HTTP exceptions here --
this sits in `services/` next to other modules with no DB access of their
own. It also never imports `anthropic` or `openai` (SPEC §4, §10): it
produces protocol-agnostic content-block dicts (the same Anthropic-native
shapes already used in `services/llm/messages.py`, per SPEC §4's decision
that `messages`/`tools` are Anthropic wire shapes throughout), it never calls
an SDK.

`pdf2image` (poppler in the container) and PyMuPDF/`fitz` (AGPL) are
deliberately not used anywhere in this module -- `pypdf` is the only PDF
dependency, precisely so runtime PDF handling never needs poppler in the
image or an AGPL dependency in the tree (SPEC §2).
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pypdf import PdfReader

from domain.models import IntakeSource
from services.llm import LLMCapabilities

#: One Anthropic-native content block, e.g. {"type": "text", "text": ...} or
#: {"type": "image"/"document", "source": {...}}. Matches the shapes already
#: produced/consumed in services/llm/messages.py.
ContentBlock = dict[str, Any]

#: The four image mime types IntakeService accepts, i.e. everything in
#: IntakeService.ALLOWED_MIME_TYPES except "application/pdf". Not imported
#: from IntakeService directly to keep this module free of any dependency on
#: services/intake.py -- it only needs to know which mime types are images.
_IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)

_PDF_MIME_TYPE = "application/pdf"


class DocumentUnreadableError(Exception):
    """Raised when a source cannot be turned into any content block.

    This is step 3 of SPEC §6.3: the extracted text was missing or didn't
    reconcile, and the adapter in use has no `document` block fallback
    (`capabilities.pdf_document_blocks is False` -- the Chat Completions
    path). `reason` is written to be usable, verbatim or near-verbatim, as
    the motivation text on a `registrera_avstaende` call (A7) -- it must
    read sensibly to a human reviewing an abstained intake source, not just
    to a developer reading a stack trace.
    """

    def __init__(self, source_id: str, reason: str) -> None:
        super().__init__(reason)
        self.source_id = source_id
        self.reason = reason


# ---------------------------------------------------------------------------
# Step 1a: PDF text-layer extraction
# ---------------------------------------------------------------------------


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract the text layer from PDF bytes via `pypdf`, or "" if there isn't one.

    "No text layer" is treated uniformly as an empty string: extraction
    raising (a malformed or unusual PDF `pypdf` can't parse), or every page
    returning only whitespace (a scanned/rasterized PDF with no text
    operators at all). Callers never need to distinguish the two -- both
    mean "fall through to step 2 of SPEC §6.3".
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return ""
    text = "\n".join(pages_text)
    return text if text.strip() else ""


# ---------------------------------------------------------------------------
# Step 1b: the reconciliation heuristic (SPEC §6.3, "Avstämningen...")
# ---------------------------------------------------------------------------
#
# This is a label-based regex heuristic over free-form Swedish invoice text,
# not a general NLP solution -- it is only as good as the label list and
# amount regex below, and both are a deliberately small, common set rather
# than an exhaustive one. Its job is narrow: decide whether the *extracted
# text itself* is internally consistent enough to send as-is, before any LLM
# sees it. It is NOT the full SPEC §6.3 rule ("beloppen den postar ska finnas
# ordagrant i den extraherade texten, och netto + moms ska gå ihop med
# totalen") -- that full rule also requires checking the amounts the *agent
# proposes to post* against this text, which is a session-level concern for
# the agent's own posting path (A8, not built here). What this function
# checks is only the second half, and only against numbers already present
# in the text: does a labeled net + a labeled VAT amount reconcile with a
# labeled total, if such a labeled breakdown can be found at all.


class ReconciliationState(Enum):
    """The three possible outcomes of `reconciliation_result`.

    NOT_APPLICABLE is deliberately not a failure: a receipt without a clean
    net/VAT/total layout, or a foreign document, gives us nothing to
    cross-check, but that is not evidence the text extraction is corrupted.
    Only a *found* breakdown that fails to add up (DOES_NOT_RECONCILE) is
    evidence of the "columns got scrambled" failure mode SPEC §6.3 warns
    about, and only that state should trigger escalation to step 2.
    """

    NOT_APPLICABLE = "not_applicable"
    RECONCILES = "reconciles"
    DOES_NOT_RECONCILE = "does_not_reconcile"


@dataclass(frozen=True)
class ReconciliationResult:
    """Outcome of checking extracted text for a labeled net/VAT/total breakdown.

    `net_ore`, `vat_ore` (summed across every VAT-labeled amount found) and
    `total_ore` are populated whenever a full triple was found (i.e. `state`
    is RECONCILES or DOES_NOT_RECONCILE), in integer öre -- this codebase's
    amount convention -- so a caller can log or display the mismatch. All
    three are `None` when `state` is NOT_APPLICABLE.
    """

    state: ReconciliationState
    net_ore: int | None = field(default=None)
    vat_ore: int | None = field(default=None)
    total_ore: int | None = field(default=None)

    @property
    def checked(self) -> bool:
        """Whether a labeled triple was found at all (see module docstring)."""
        return self.state is not ReconciliationState.NOT_APPLICABLE

    @property
    def reconciles(self) -> bool:
        """Whether a found triple adds up. False (not "unknown") when NOT_APPLICABLE
        as well as when DOES_NOT_RECONCILE -- callers that care about the
        distinction should check `state`/`checked` instead.
        """
        return self.state is ReconciliationState.RECONCILES


#: Rounding tolerance for net + vat == total, in öre (SPEC §6.3: "±1 öre").
_RECONCILIATION_TOLERANCE_ORE = 1

# Common Swedish invoice labels for each role. Matched case-insensitively,
# word-boundary-anchored on the left so e.g. "moms" doesn't match inside an
# unrelated word. This list is intentionally small -- SPEC's task note says
# a "reasonably small set of common labels is fine" -- and is expected to
# grow only if a real invoice format is seen that isn't covered.
_NET_LABELS = (
    "nettobelopp",
    "netto",
)
_VAT_LABELS = (
    "utgående moms",
    "varav moms",
    "moms",
)
_TOTAL_LABELS = (
    "summa att betala",
    "belopp att betala",
    "att betala",
    "totalt",
    "total",
    "summa",
)

# A Swedish-formatted SEK amount: thousands separated by a space (or,
# tolerated, a plain '.'), decimals with a comma (`1 234,56`), or a plain
# dot-decimal fallback (`1234.56`), or a bare integer (`1234`) -- each
# optionally followed by "kr" or "SEK". This is a heuristic regex over
# free-form extracted text, not a general number parser: it does not
# attempt to handle every locale variant, negative amounts, or currencies
# other than SEK.
#
# The digit alternatives are wrapped in an atomic group `(?>...)` (Python
# 3.11+; CI runs 3.11 per .github/workflows/tests.yml) specifically so the
# trailing `(?!\s*%)` guard can reject a whole number outright instead of
# `\d+` backtracking down to a shorter, still-plausible-looking prefix.
# Without the atomic group, a line like "Moms 25%: 250,00 kr" would match
# "2" (backtracked from "25" once "%" is seen) instead of skipping past
# "25%" entirely to the real amount, "250,00", that follows it.
_AMOUNT_PATTERN = re.compile(
    r"""
    (?P<amount>
        (?>
            \d{1,3}(?:[ .]\d{3})*,\d{2}   # 1 234,56  /  1.234,56
            | \d+,\d{2}                    #    123,45
            | \d+\.\d{2}                   #    123.45
            | \d{1,3}(?:[ .]\d{3})+        # 1 234     (thousands, no decimals)
            | \d+                          #     123
        )
    )
    (?!\s*%)
    \s*(?:kr\b|SEK\b)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# One label pattern per role, built from the label tuples above, sorted
# longest-first so e.g. "utgående moms" is tried before the bare "moms" it
# contains.
_LABEL_TO_AMOUNT_GAP = 40  # max characters between a label and its amount


def _label_pattern(labels: tuple[str, ...]) -> re.Pattern[str]:
    ordered = sorted(labels, key=len, reverse=True)
    alternation = "|".join(re.escape(label) for label in ordered)
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)


_NET_PATTERN = _label_pattern(_NET_LABELS)
_VAT_PATTERN = _label_pattern(_VAT_LABELS)
_TOTAL_PATTERN = _label_pattern(_TOTAL_LABELS)


def _parse_amount_to_ore(raw: str) -> int | None:
    """Parse a matched Swedish-formatted amount string into integer öre."""
    cleaned = raw.strip()
    cleaned = re.sub(r"(?i)\s*(kr|SEK)\s*$", "", cleaned).strip()
    if not cleaned:
        return None
    if "," in cleaned:
        # Comma is the decimal separator; strip any space/dot thousands
        # separators before it.
        integer_part, _, decimal_part = cleaned.rpartition(",")
        integer_part = integer_part.replace(" ", "").replace(".", "")
        decimal_part = (decimal_part + "00")[:2]
    elif "." in cleaned and len(cleaned.split(".")[-1]) == 2:
        # Plain dot-decimal, e.g. "123.45" -- but not "1.234" (thousands).
        integer_part, _, decimal_part = cleaned.rpartition(".")
        integer_part = integer_part.replace(" ", "")
    else:
        integer_part = cleaned.replace(" ", "").replace(".", "")
        decimal_part = "00"
    if not integer_part.isdigit() or not decimal_part.isdigit():
        return None
    return int(integer_part) * 100 + int(decimal_part)


def _find_amounts_for_label(text: str, label_pattern: re.Pattern[str]) -> list[int]:
    """Find every amount that follows one of `label_pattern`'s labels within
    `_LABEL_TO_AMOUNT_GAP` characters on the same line.

    Restricted to a single line deliberately: this is what makes a scrambled
    two-column table show up as either a wrong pairing (DOES_NOT_RECONCILE)
    or a missing pairing (excluded here, falling through to NOT_APPLICABLE),
    rather than the regex reaching across the page to find *some* amount
    that happens to make the sums work.
    """
    amounts: list[int] = []
    for line in text.splitlines():
        for label_match in label_pattern.finditer(line):
            window = line[label_match.end() : label_match.end() + _LABEL_TO_AMOUNT_GAP]
            amount_match = _AMOUNT_PATTERN.search(window)
            if amount_match is None:
                continue
            parsed = _parse_amount_to_ore(amount_match.group("amount"))
            if parsed is not None:
                amounts.append(parsed)
    return amounts


def reconciliation_result(text: str) -> ReconciliationResult:
    """Check extracted PDF text for a labeled net/VAT/total breakdown.

    See the module-level comment above this section for exactly what this
    does and doesn't check, and the `ReconciliationState` docstring for why
    "no breakdown found at all" (NOT_APPLICABLE) is not treated as a
    failure -- only a found-and-wrong breakdown is.

    Heuristic, not a general parser (see the label/amount-regex comments
    above): a real invoice whose labels or number formatting fall outside
    the lists/patterns here will come back NOT_APPLICABLE rather than
    RECONCILES, which is the safe direction to be wrong in -- it still lets
    step 1 succeed (see the docstring above), it just doesn't add the extra
    cross-check.
    """
    net_amounts = _find_amounts_for_label(text, _NET_PATTERN)
    vat_amounts = _find_amounts_for_label(text, _VAT_PATTERN)
    total_amounts = _find_amounts_for_label(text, _TOTAL_PATTERN)

    if not net_amounts or not vat_amounts or not total_amounts:
        return ReconciliationResult(state=ReconciliationState.NOT_APPLICABLE)

    net_ore = net_amounts[0]
    vat_ore = sum(vat_amounts)  # multiple VAT lines (e.g. 12% + 25%) are summed
    total_ore = total_amounts[0]

    if abs((net_ore + vat_ore) - total_ore) <= _RECONCILIATION_TOLERANCE_ORE:
        state = ReconciliationState.RECONCILES
    else:
        state = ReconciliationState.DOES_NOT_RECONCILE

    return ReconciliationResult(
        state=state, net_ore=net_ore, vat_ore=vat_ore, total_ore=total_ore
    )


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _text_block(text: str) -> ContentBlock:
    return {"type": "text", "text": text}


def _image_block(mime_type: str, file_bytes: bytes) -> ContentBlock:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": _b64(file_bytes),
        },
    }


def _document_block(file_bytes: bytes) -> ContentBlock:
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": _PDF_MIME_TYPE,
            "data": _b64(file_bytes),
        },
    }


def _unreadable_reason(
    source: IntakeSource, text: str, result: ReconciliationResult
) -> str:
    if not text:
        return (
            f"Underlaget {source.original_filename!r} är en PDF utan läsbart textlager "
            "(troligen ett skannat kvitto eller foto), och den här modellen kan inte läsa "
            "dokumentblock som reserv. Underlaget kan inte bokföras på denna väg -- "
            "prova ett pass med en modell som stödjer dokumentblock, eller mata in "
            "underlaget manuellt."
        )
    return (
        f"Underlaget {source.original_filename!r} har ett textlager, men de "
        "etiketterade beloppen i texten går inte ihop "
        f"(netto {result.net_ore} öre + moms {result.vat_ore} öre != "
        f"totalt {result.total_ore} öre). Det tyder på att textextraktionen har "
        "kastat om kolumnerna i en tabell, och den här modellen kan inte läsa "
        "dokumentblock som reserv för att läsa sidan som bild i stället. "
        "Underlaget kan inte beläggas säkert på denna väg."
    )


# ---------------------------------------------------------------------------
# Orchestration (SPEC §6.3's three-step order)
# ---------------------------------------------------------------------------


def select_content_for_source(
    source: IntakeSource,
    file_bytes: bytes,
    capabilities: LLMCapabilities,
) -> ContentBlock:
    """Decide what to send the LLM for one intake source (SPEC §6.3).

    Returns exactly one content block -- image, text, or document -- or
    raises `DocumentUnreadableError` when the source cannot be read at all
    on this adapter (step 3). Callers (the future `hamta_underlagsfil` tool,
    A7) wrap the return value in whatever message-content list their
    protocol expects.

    `file_bytes` and `source.mime_type` are taken as explicit inputs rather
    than re-read from `IntakeService` here -- this function has no DB or
    filesystem access of its own (see module docstring).
    """
    mime_type = source.mime_type

    if mime_type in _IMAGE_MIME_TYPES:
        return _image_block(mime_type, file_bytes)

    if mime_type != _PDF_MIME_TYPE:
        # IntakeService.ALLOWED_MIME_TYPES already rejects anything else at
        # upload time; this is a defensive abstention, not an expected path.
        raise DocumentUnreadableError(
            source.id,
            f"Underlaget {source.original_filename!r} har en filtyp ({mime_type!r}) "
            "som agenten inte har stöd för att läsa.",
        )

    text = extract_pdf_text(file_bytes)
    result = reconciliation_result(text)

    text_is_trustworthy = (
        bool(text) and result.state != ReconciliationState.DOES_NOT_RECONCILE
    )
    if text_is_trustworthy:
        return _text_block(text)

    # Step 1 gave nothing, or the labeled amounts don't reconcile -- escalate.
    if capabilities.pdf_document_blocks:
        return _document_block(file_bytes)

    raise DocumentUnreadableError(source.id, _unreadable_reason(source, text, result))
