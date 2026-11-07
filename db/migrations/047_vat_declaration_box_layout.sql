-- Migration 047: momsdeklarationens rutor i `vat_declarations`.
-- Service: services/vat_report.py. Test: tests/test_vat_report.py.
--
-- Kolumnerna sales_12, sales_6 och sales_exempt betydde från början
-- försäljning 12 %, försäljning 6 % och momsfri försäljning. Sedan rutorna
-- rättades är sales_25 ruta 05 (all momspliktig försäljning, oavsett
-- skattesats), sales_12/sales_6/sales_exempt rutorna 06/07/08 (uttag,
-- vinstmarginal, hyresinkomster) och den nya kolumnen sales_other ruta 42.
--
-- Sparade deklarationer skrivs inte om. box_layout säger vilken betydelse
-- en rad har: 1 = den gamla (alla rader före den här migrationen), 2 = den
-- nya. Tjänsten läser en rad med layout 1 som ruta 05 = sales_25 + sales_12
-- + sales_6 och ruta 42 = sales_exempt.

ALTER TABLE vat_declarations ADD COLUMN sales_other INTEGER DEFAULT 0;
ALTER TABLE vat_declarations ADD COLUMN box_layout INTEGER NOT NULL DEFAULT 1;

INSERT OR IGNORE INTO schema_version (version) VALUES (47);
