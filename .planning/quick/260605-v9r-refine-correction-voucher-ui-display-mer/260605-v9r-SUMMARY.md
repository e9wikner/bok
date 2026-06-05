---
status: complete
---

# Summary

## What was done
- Backend API now exposes `original_data` and `corrected_data` in the voucher source context `correction_chain`.
- B-series correction vouchers are hidden from the vouchers list.
- Voucher detail page for corrected originals now shows three tabs in the rows card:
  - **Original**: the original rows as posted
  - **Netto**: the corrected rows (the intended final accounting state)
  - **Ändringar**: a per-account diff showing before/after and deltas
- B-series correction vouchers viewed directly show a banner linking to the original.
- The old `CorrectionChainSection` was replaced with a compact `CorrectionMetaSection`.

## Files changed
- `api/routes/vouchers.py`
- `frontend-v3/lib/api.ts`
- `frontend-v3/app/vouchers/page.tsx`
- `frontend-v3/app/vouchers/[id]/page.tsx`

## Verification
- 254 backend tests passed
- Frontend TypeScript `tsc --noEmit` clean
- Frontend ESLint clean
