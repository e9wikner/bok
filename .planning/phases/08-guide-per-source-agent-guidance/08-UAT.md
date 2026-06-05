---
status: complete
phase: 08-guide-per-source-agent-guidance
source:
  - .planning/phases/08-guide-per-source-agent-guidance/08-01-SUMMARY.md
  - .planning/phases/08-guide-per-source-agent-guidance/08-02-SUMMARY.md
  - .planning/phases/08-guide-per-source-agent-guidance/08-03-SUMMARY.md
started: "2026-06-05T14:45:00Z"
updated: "2026-06-05T14:49:00Z"
---

## Current Test

[testing complete]

## Tests

### 1. Upload Source With Agent Guidance
expected: On the intake upload page, the voucher-source card shows a textarea labeled "Meddelande till agent" directly below "Kort förklaring". Typing guidance there and uploading a receipt/invoice succeeds, resets the form, and the uploaded source keeps that guidance for later review.
result: pass

### 2. Review And Edit Guidance On Voucher Source Detail
expected: Opening the uploaded voucher source detail page shows a "Meddelande till agent" card with the saved guidance. If the source is pending or processing, "Redigera meddelande" opens an editor, "Spara meddelande" saves changes, and the updated text appears without a page refresh.
result: pass

### 3. Processed Source Guidance Is Locked
expected: After the source is processed, the detail page still shows the saved guidance but no longer allows editing. If a stale save is attempted after processing, the UI shows "Meddelandet kan inte ändras eftersom underlaget redan har behandlats."
result: pass

### 4. Agent Queue Receives Guidance
expected: The agent pending-intake queue includes the uploaded voucher source with a "guidance" field containing the user message. Bank input items in the same queue include "guidance": null, and no bank input detail page shows a guidance editor.
result: pass

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
