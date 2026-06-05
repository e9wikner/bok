---
phase: quick
plan: "01"
subsystem: ledger
status: completed
commit: fde0e95
---

# Quick Fix Summary: B-Series Correction Voucher Date Inheritance

## What Was Fixed

B-series correction vouchers were being created with the current date (`datetime.now().date()` or `now.date()`). They now inherit the date from the original voucher being corrected (`original.date`).

## Files Changed

| File | Method / Area | Change |
|------|---------------|--------|
| `repositories/voucher_repo.py` | `create_correction_voucher` | Two occurrences of `now.date()` replaced with `original.date` |
| `services/ledger.py` | `suggest_correction_voucher` | `datetime.now().date()` replaced with `original.date` |

## Why It Matters

Swedish bookkeeping compliance (BFL / BFNAR) requires correction vouchers to be dated to the original period. Using the current date could place corrections in the wrong accounting period, violating durability and auditability rules.

## Commit

- **Hash:** `fde0e95`
- **Message:** `fix(ledger): B-series correction vouchers use original voucher date`
