# fakturering F1 — uppgifter

Spec: `docs/redesign/SPEC-fakturering-f1.md`. Beslut 1–8 i §1 tas först. Tester först, en
uppgift i taget.

- [ ] 1. `tests/test_fakturering_f1.py`: testfall 1–32 och 39–40 ur §13, alla röda (xfail).
- [ ] 2. Migration `039_invoice_proposals.sql`: `invoice_drafts.revision` och
      `thread_invoice_drafts` med index (§4). `InvoiceDraftRepository.update` och
      `update_status('rejected')` räknar upp revisionen. `InvoiceProposalRepository` med
      övergångarna i §4.3.
- [ ] 3. `InvoiceIssueService.check(draft)` utbruten ur `issue`, och kontokonteringen ur
      `create_booking_for_invoice` utbruten till en funktion (§5.3, §6.1). F0:s testfall
      1–15 gröna.
- [ ] 4. `las_kunder` och `las_fakturor` sist i `_TOOL_SPECS` (§5.1, §5.2). Testfall 1–4.
- [ ] 5. `InvoiceProposalService.propose` och `foresla_faktura`, med kroppen i §6.1,
      `possible_duplicates` och idempotensen (§5.3). Testfall 5–12.
- [ ] 6. `andra_fakturautkast`: ändra, förkasta, uppspelning (§5.4). `on_draft_changed` från
      `PUT` och `reject` (§4.4). Testfall 13–18 och 23.
- [ ] 7. `/issue`: `expected_revision`, `409 draft_changed`, `on_issuing` i transaktionen och
      `on_issued`/`on_issue_failed` efter (§7, §9). Kvittot (§8.1). Testfall 19–22 och 24–30.
- [ ] 8. `GET /drafts` med `kind` och fakturaraderna, `count_waiting`, `/overview` betala
      (§10.1, §10.3). Testfall 31–32.
- [ ] 9. Agentinstruktionen (§11). Kör `tests/test_agent_entrypoint.py`.
- [ ] 10. Klienten: `typer.ts`/`parse.ts` för `kind: "invoice"` och kvittots två fält, med
      fixtur. Testfall 33.
- [ ] 11. `FakturaForslag`, `FakturaRad` och `useUtfardaFaktura` (§6.2, §6.3, §7.1).
      `Öppna PDF` i kvittot (§8.2). Testfall 34–36.
- [ ] 12. Vyn: `lasvy: false`, sektionerna, den optimistiska raden, status, fot och
      platshållare (§10.2). Testfall 37–38.
- [ ] 13. Testfall 39 (hela flödet, skriptat). black, isort, flake8, pytest, `npm test`,
      lint, `tsc`, `NEXT_PUBLIC_SKAL=1 npm run build`.
- [ ] 14. Uppdatera `docs/oppna-beslut.md` (F1 byggd, frågorna i §12) och `AGENTS.md` om
      revisionen. Ta bort spec och uppgiftslista ur trädet efter bygget, som efter F0.
- [ ] 15. På hubbabubba: en riktig faktura genom tråden med en riktig LLM, och PDF:en mot
      förlagan.
