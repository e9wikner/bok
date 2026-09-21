# Uppgifter: modul `oversikt`

Spec: `docs/redesign/SPEC-oversikt.md` · Plan: `tasks/oversikt/plan.md`
Testerna skrivs **före** implementationen (§7). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §7.

---

- [ ] **O1 — laga `_check_missing_attachments` (gate: buggfix, ingen ny yta)**
  - Acceptans: joinen går mot `attachments`, inte mot `voucher_attachments` som inte finns.
    Den nakna `except Exception: pass` är borta — ett trasigt schema ska synas. Tröskeln
    `> 50000` är öre = 500 kr och matchar titeln; den lämnas orörd. Sväljen på
    `services/compliance.py:381` i `_check_unbooked_bank_transactions` rörs **inte**.
  - Verifiera: testfall 1, 2, 3. Sedan **hela** `pytest tests/ -v` grön.
  - Filer: `services/compliance.py`, `tests/test_oversikt.py`
  - Obs: landas ensam. Kontrollen har aldrig producerat en issue — första riktiga körningen kan
    ge en vägg av varningar mot seedad data. Det är rätt utfall; nämn det för beställaren.

- [ ] **O2 — `missing_attachment` och `age_days` på verifikationen**
  - Acceptans: båda härledda, aldrig lagrade. `missing_attachment` är
    `NOT EXISTS (SELECT 1 FROM attachments a WHERE a.voucher_id = vouchers.id)`, `age_days` är
    dygn sedan verifikationens **datum** (inte `posted_at`). Joinade i sidfrågan i `list_all`,
    aldrig hämtade per rad. Två nya fält på `VoucherResponse`.
  - Verifiera: testfall 4, 5, 15. Testfall 15 räknar `db.execute`-anrop före och efter.
  - Filer: `repositories/voucher_repo.py`, `api/schemas.py`, `api/routes/vouchers.py`,
    `tests/test_oversikt.py`
  - Obs: `list_all` gör redan N+1 (`voucher_repo.py:224-229` hämtar `id` och kallar `get()` per
    rad). Laga det om det faller ut naturligt — gör det under inga omständigheter värre.

- [ ] **O3 — `?missing_attachment=true&sort_by=age`**
  - Acceptans: filtret följer `where_clauses`/`params`-mönstret i `voucher_repo.py:165-230`.
    `age` läggs till i sorterings**vitlistan** på `voucher_repo.py:208` — vitlistan är gränsen
    mot SQL-injektion i `ORDER BY` och ska förbli en vitlista. `missing_attachment` gäller bara
    postade verifikationer; ett utkast utan bilaga är inte en komplettering.
  - Verifiera: testfall 6, 7, 8, 9.
  - Filer: `repositories/voucher_repo.py`, `api/routes/vouchers.py`, `tests/test_oversikt.py`
  - Obs: `api/routes/vouchers.py:682` har två skilda kodvägar, och `period_id`-grenen ignorerar
    tyst `limit`/`offset`/`search`/`sort_*`. Det nya filtret ska bete sig lika i båda grenarna
    **eller** ge `400` i den som inte kan hedra det. Tyst ignorering är inte ett alternativ.

- [ ] **O4 — `GET /api/v1/overview`**
  - Acceptans: svaret i §5 — `fiscal_year`, `period_state`, och `pages` som en **lista** i
    ordningen `bocker`, `betala`, `bokslut`, var och en med `waiting`, `meta` och samma fyra
    räknare. Servern bestämmer `waiting` och formulerar `meta`; klienten räknar ingenting.
    `open_decisions` och `payroll_waiting` är approximationer och står som approximationer i
    koden, med `beslut` respektive lönens fyra spår namngivna som slutlig hemvist.
    `GET /overview` skriver ingenting — till skillnad från `POST /compliance/check`.
  - Verifiera: testfall 10, 11, 12, 13, 14.
  - Filer: `api/routes/overview.py`, `services/overview.py`, `api/schemas.py`, `api/main.py`,
    `tests/test_oversikt.py`
  - Obs: minsta mallen är `api/routes/compliance.py`. `overdue_invoices` finns färdigräknad i
    `api/routes/invoices.py:182` — återanvänd predikatet, skriv inte ett andra.

- [ ] **O5 — regression och lint**
  - Acceptans: alla nio framgångskriterier i §8 uppfyllda. Ingen migration, ingen ny tabell,
    ingen ny kolumn, ingen ändrad trigger.
  - Verifiera: `pytest tests/ -v` och `black . && isort . && flake8 && mypy .`.
    `black`/`isort`/`flake8` ska vara **rena**; `mypy` har 61 pre-existerande fel i repot
    (`tasks/idempotens/todo.md`) — modulens egna filer lägger inte till ett enda. Läs
    jobboutputen i CI, bocken betyder inget (`continue-on-error: true`).
  - Filer: inga nya.

---

**Utanför scope:** `GET /decisions` (`beslut`), lönens fyra spår, all frontend, en persistent
kompletteringsflagga, och trösklarna som gör `age_days` gult eller rött.

**Fråga först** (§6): en persistent flagga, en ändring i `014`:s triggers, en fjärde sida, eller
en femte räknare.
