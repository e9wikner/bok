# fakturering F0 — uppgifter

Spec: `docs/redesign/SPEC-fakturering.md`. Tester först, en uppgift i taget.

- [x] 1. `tests/test_fakturering_f0.py`: testfall 1–15 ur §9, alla röda.
- [x] 2. Migration `038_invoice_issue.sql`: nya kolumner på utkast, fakturor och
      rader (nummer, adress, leverans, enhet, `quantity_centi`) och triggers
      (§4). Testfall 8 grönt.
- [x] 3. Ta bort `db.commit()` ur fakturarepona och `InvoiceService` på
      utfärdandevägen. `test_invoices.py`/`test_invoice_drafts.py` ska
      fortfarande gå igenom.
- [x] 4. Decimalt antal och enhet i utkast och förhandsberäkning (§4.2).
      Testfall 12.
- [x] 5. `CompanyInfo` ur `company_info`, med nya nycklar `seat` och `f_skatt`,
      och fullständighetskontroll (§6). Testfall 11.
- [x] 6. Mallen `templates/pdf/invoice.html` efter förlagan (§6.1), med ett
      inbäddat monospace-typsnitt. Testfall 13 och 15.
- [x] 7. `InvoiceIssueService.issue` i en transaktion (§5), med PDF lagrad och
      kopplad som underlag. Testfall 1–7.
- [x] 8. Routes: `POST /invoice-drafts/{id}/issue` (JWT, felmappning) och
      `GET /invoices/{id}/pdf`. Ta bort `POST /invoices`, `/send`, `/book` och
      `/invoice-drafts/{id}/send` (§7). Testfall 9, 10 och 14.
- [x] 9. Agentinstruktionen i `docs/to_agent/` (§8). Kör
      `tests/test_agent_entrypoint.py`.
- [x] 10. Frontend (gamla sidor): nya fält i utkastformuläret, `/issue`, PDF-länk.
- [ ] 11. black, isort, flake8, pytest. Uppdatera `AGENTS.md`: utfärdade
      fakturor är append-only.
- [ ] 12. Fyll i `company_info` på hubbabubba (säte, momsnummer, bankgiro,
      F-skatt) och kör kontrollen i §7.
