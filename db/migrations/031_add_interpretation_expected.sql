-- Migration 031: underlagstolkning — the computed `expected` is stored
-- (SPEC-underlagstolkning.md §5, §8, §12.6 e)
--
-- 030 keeps `expected_voucher_id` but not the comparison `tolka_underlag`
-- computed against that voucher. The read path (§8) shall show what the
-- agent compared with, as a snapshot, and never recompute it against
-- today's ledger -- so the comparison is stored here, as JSON in the tool's
-- `expected` form (§6.5, §7.4 plus `is_best_match`). NULL for older rows,
-- for interpretations without `expected_voucher_id` and in another currency
-- (§7.1).
--
-- The column is covered by 030's two triggers unchanged: they fire on any
-- UPDATE or DELETE of the table, whatever the column. 030 is applied and is
-- not edited (AGENTS.md); hence a file of its own.

ALTER TABLE intake_interpretations ADD COLUMN expected_json TEXT;

INSERT OR IGNORE INTO schema_version (version) VALUES (31);
