"""How a corrected voucher reads.

For a voucher with a posted correction, and for a correction itself: what
kind of correction it is (makulering or ändring), the net per account before
and after, and when, by whom and why -- the same facts iOrdning's margin
note shows beside a struck-out row. Derived on read from posted vouchers and
`correction_history`; nothing is stored and no posted voucher is touched.
"""

from typing import Dict, List, Optional, Sequence

from domain.correction_effect import correction_effect
from domain.models import Voucher, VoucherRow
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.voucher_repo import VoucherRepository


def _label(voucher: Voucher) -> str:
    number = voucher.number if voucher.number is not None else "?"
    return f"{voucher.series.value}-{number}"


def correction_title(kind: str, original: Voucher) -> str:
    """The display title of a correction: `Makulering av A-53: …`."""
    word = "Makulering" if kind == "makulering" else "Ändring"
    return f"{word} av {_label(original)}: {original.description}"


def correction_summaries(
    vouchers: Sequence[Voucher], account_names: Optional[dict] = None
) -> Dict[str, dict]:
    """`{voucher_id: summary}` for every voucher in `vouchers` that has been
    corrected or is a correction; the others are left out. A handful of
    queries for the whole page, not one per voucher."""
    involved = [v for v in vouchers if v.corrected_by or v.correction_of]
    if not involved:
        return {}

    originals: Dict[str, Voucher] = {v.id: v for v in involved if v.corrected_by}
    for missing in {
        v.correction_of for v in involved if v.correction_of
    } - originals.keys():
        original = VoucherRepository.get(missing or "")
        if original is not None:
            originals[original.id] = original

    # The page usually holds the corrections already; read them only for an
    # original whose posted corrections are not all on it.
    on_page: Dict[str, List[Voucher]] = {}
    for v in vouchers:
        if v.correction_of and v.is_posted():
            on_page.setdefault(v.correction_of, []).append(v)
    corrections: Dict[str, List[Voucher]] = {}
    to_read = []
    for original_id, original in originals.items():
        found = on_page.get(original_id, [])
        if len(found) == original.correction_count:
            corrections[original_id] = sorted(
                found, key=lambda c: (c.posted_at or c.created_at, c.number or 0)
            )
        else:
            to_read.append(original_id)
    corrections.update(VoucherRepository.list_posted_corrections(to_read))

    wanted = [c.id for cs in corrections.values() for c in cs] + [
        v.id for v in involved if v.correction_of
    ]
    history = {
        entry.corrected_voucher_id: entry
        for entry in AccountingCorrectionRepository.for_corrections(wanted)
    }

    if account_names is None:
        from repositories.account_repo import AccountRepository

        account_names = AccountRepository.get_all_as_dict()

    result: Dict[str, dict] = {}
    for voucher in involved:
        if voucher.correction_of:
            original = originals.get(voucher.correction_of)
            if original is None:
                continue
            posted = corrections.get(original.id, [])
            earlier = (
                posted[: [c.id for c in posted].index(voucher.id)]
                if voucher.id in [c.id for c in posted]
                else posted
            )
            before_rows = _rows(original, earlier)
            correction = voucher
            applied = voucher.rows
        else:
            original = voucher
            posted = corrections.get(voucher.id, [])
            if not posted:
                continue
            before_rows = list(voucher.rows)
            correction = posted[-1]
            applied = [row for c in posted for row in c.rows]

        effect = correction_effect(before_rows, applied)
        entry = history.get(correction.id)
        result[voucher.id] = {
            "kind": effect.kind,
            "title": correction_title(effect.kind, original),
            "original": _ref(original),
            "original_description": original.description,
            "correction": _ref(correction),
            "correction_date": correction.date,
            "correction_status": correction.status.value,
            "posted_at": correction.posted_at,
            "actor": getattr(entry, "corrected_by", None) or correction.created_by,
            "reason": getattr(entry, "correction_reason", None)
            or correction.description,
            "before_total": effect.before_total,
            "after_total": effect.after_total,
            "accounts": [
                {
                    "account_code": a.account_code,
                    "account_name": (
                        account_names[a.account_code].name
                        if a.account_code in account_names
                        else None
                    ),
                    "before": a.before,
                    "after": a.after,
                }
                for a in effect.accounts
            ],
        }
    return result


def _rows(original: Voucher, corrections: List[Voucher]) -> List[VoucherRow]:
    return list(original.rows) + [row for c in corrections for row in c.rows]


def _ref(voucher: Voucher) -> dict:
    return {"id": voucher.id, "series": voucher.series.value, "number": voucher.number}
