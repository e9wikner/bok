-- Migration 029: flode-verifikationer — spårbarheten ett förslag bär
-- (SPEC-flode-verifikationer.md §5.2, §6.1)
--
-- `foresla_verifikation` tar samma spårbarhetsfält som `posta_verifikation`
-- (`intake_source_ids`, `bank_input_ids`, `bank_transaction_ids`), och ett
-- förslag som postas ska bära exakt det en direkt postning hade burit. Men
-- länkarna (`voucher_intake_sources`, `voucher_bank_inputs`,
-- `voucher_bank_transactions`) får bara skrivas mot en postad verifikation:
-- att länka markerar underlaget som bearbetat och banktransaktionen som
-- bokförd. Fram till postningen måste id:na därför ligga någonstans, och
-- `vouchers` får ingen kolumn om trådar (§6.1). De ligger här, som JSON
-- `{"intake_source_ids": [...], "bank_input_ids": [...],
-- "bank_transaction_ids": [...]}`, och länkas i postningens transaktion (F8).
--
-- 028 är redan tillämpad och ändras inte (AGENTS.md); därför en egen fil.

ALTER TABLE thread_drafts ADD COLUMN traceability_json TEXT;

INSERT OR IGNORE INTO schema_version (version) VALUES (29);
