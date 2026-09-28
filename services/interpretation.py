"""`underlagstolkning`: the server's reading of what the model read from an
underlag (docs/redesign/SPEC-underlagstolkning.md).

For now only the matching windows (§7.2). They are part of what a match
*is*, not something to deploy differently, so they live here and not in
`config.py`; `VoucherRepository.match_candidates` takes them as arguments
and has no defaults of its own. The checks, the confidence, the ranking and
the hypothesis (U3, U5) and the orchestration (U6) come later.
"""

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
