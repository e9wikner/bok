-- Migration 053: drop tables no code reads or writes
--
-- These were created for features that were never built or have since been
-- removed, and nothing in the application has touched them for a long time:
--
--   annual_reports, income_statements, balance_sheets, cash_flows,
--   report_audit         003's K2 report store. The annual report is built
--                        on read by `services/arsredovisning.py`; the
--                        placeholder K2 routes are gone.
--   api_keys, agent_operations, openapi_specs
--                        003's per-key agent registry. Access is the single
--                        `BOKFOERING_API_KEY` from `config.py`.
--   user_tenants         007/008's multi-tenant mapping, unused since the
--                        tenant layer was removed.
--   vat_reports          002's VAT report store; declarations live in
--                        `vat_declarations`.
--   categorization_rules 005's rule table for the removed
--                        `services/categorization.py`.
--
-- None of them holds räkenskapsinformation, and no view or trigger names
-- them. Tables that reference another are dropped before it.

BEGIN;

DROP TABLE IF EXISTS income_statements;
DROP TABLE IF EXISTS balance_sheets;
DROP TABLE IF EXISTS cash_flows;
DROP TABLE IF EXISTS report_audit;
DROP TABLE IF EXISTS annual_reports;

DROP TABLE IF EXISTS agent_operations;
DROP TABLE IF EXISTS openapi_specs;
DROP TABLE IF EXISTS api_keys;

DROP TABLE IF EXISTS user_tenants;
DROP TABLE IF EXISTS vat_reports;
DROP TABLE IF EXISTS categorization_rules;

COMMIT;
