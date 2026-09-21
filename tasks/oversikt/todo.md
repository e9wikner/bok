# Uppgifter: modul `oversikt`

Spec: `docs/redesign/SPEC-oversikt.md` · Plan: `tasks/oversikt/plan.md`
Testerna skrivs **före** implementationen (§7). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §7.

---

- [x] **O1 — laga `_check_missing_attachments` (gate: buggfix, ingen ny yta)**
  - Acceptans: joinen går mot `attachments`, inte mot `voucher_attachments` som inte finns.
    Den nakna `except Exception: pass` är borta — ett trasigt schema ska synas. Tröskeln
    `> 50000` är öre = 500 kr och matchar titeln; den lämnas orörd. Sväljen på
    `services/compliance.py:381` i `_check_unbooked_bank_transactions` rörs **inte**.
  - Verifiera: testfall 1, 2, 3. Sedan **hela** `pytest tests/ -v` grön.
  - Filer: `services/compliance.py`, `tests/test_oversikt.py`
  - Obs: landas ensam. Kontrollen har aldrig producerat en issue — första riktiga körningen kan
    ge en vägg av varningar mot seedad data. Det är rätt utfall; nämn det för beställaren.

- [x] **O2 — `missing_attachment` och `age_days` på verifikationen**
  - Acceptans: båda härledda, aldrig lagrade. `missing_attachment` är
    `NOT EXISTS (SELECT 1 FROM attachments a WHERE a.voucher_id = vouchers.id)`, `age_days` är
    dygn sedan verifikationens **datum** (inte `posted_at`). Joinade i sidfrågan i `list_all`,
    aldrig hämtade per rad. Två nya fält på `VoucherResponse`.
  - Verifiera: testfall 4, 5, 15. Testfall 15 räknar `db.execute`-anrop före och efter.
  - Filer: `repositories/voucher_repo.py`, `api/schemas.py`, `api/routes/vouchers.py`,
    `tests/test_oversikt.py`
  - Obs: `list_all` gör redan N+1 (`voucher_repo.py:224-229` hämtar `id` och kallar `get()` per
    rad). Laga det om det faller ut naturligt — gör det under inga omständigheter värre.

- [x] **O3 — `?missing_attachment=true&sort_by=age`**
  - Acceptans: filtret följer `where_clauses`/`params`-mönstret i `voucher_repo.py:165-230`.
    `age` läggs till i sorterings**vitlistan** på `voucher_repo.py:208` — vitlistan är gränsen
    mot SQL-injektion i `ORDER BY` och ska förbli en vitlista. `missing_attachment` gäller bara
    postade verifikationer; ett utkast utan bilaga är inte en komplettering.
  - Verifiera: testfall 6, 7, 8, 9.
  - Filer: `repositories/voucher_repo.py`, `api/routes/vouchers.py`, `tests/test_oversikt.py`
  - Obs: `api/routes/vouchers.py:682` har två skilda kodvägar, och `period_id`-grenen ignorerar
    tyst `limit`/`offset`/`search`/`sort_*`. Det nya filtret ska bete sig lika i båda grenarna
    **eller** ge `400` i den som inte kan hedra det. Tyst ignorering är inte ett alternativ.

- [x] **O4 — `GET /api/v1/overview`**
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

---

## Avvikelse från specen: var de härledda fälten beräknas

Specens §3 och O2 säger "joinade i sidfrågan i `list_all`, aldrig hämtade per rad". De ligger i
stället i `VoucherRepository.get`, i den `SELECT * FROM vouchers WHERE id = ?` som redan fanns.

Skälet är att kravet bakom formuleringen är framgångskriterium 8 — *antalet SQL-anrop per listad
verifikation är oförändrat eller lägre* — och `list_all` hämtar sidan som `SELECT id` och anropar
sedan `get()` per rad. Att beräkna fälten i båda frågorna hade räknat samma två värden två
gånger; att beräkna dem bara i sidfrågan hade lämnat `GET /vouchers/{id}` och
`list_for_period` utan dem, och `VoucherResponse` kräver dem överallt.

Mätt med testfall 15: 3,0 `db.execute`-anrop per listad verifikation före O2 och 3,0 efter.
Uttrycken ligger som `MISSING_ATTACHMENT_SQL` och `AGE_DAYS_SQL` på modulnivå i
`repositories/voucher_repo.py`, så filtret i O3 använder samma predikat som fältet.

N+1:et i `list_all` (`SELECT id` + `get()` per rad) finns kvar. Det blev inte värre, och det
föll inte ut naturligt att laga det här — det kräver att `get()`:s radhämtning skrivs om till en
enda join, vilket är en större ändring än modulen har mandat för.

## Avvikelse från specen: `period_id`-grenens tysta sortering

`missing_attachment` hedras i **båda** grenarna av `api/routes/vouchers.py` — i
`period_id`-grenen som ett Python-filter på samma predikat, med samma innebörd (bara postade).
Ingen tyst ignorering.

Kvar, pre-existerande och inte fördjupat: `period_id`-grenen ignorerar fortfarande tyst
`limit`, `offset`, `search` och `sort_*`. `sort_by=age` beter sig där som `date` och `number`
redan gör. Att laga det är en egen uppgift — den gren som ska svara på `total` korrekt måste
sluta filtrera i Python, och det rör fler anropare än den här modulen.

## Avvikelse från specen: O4 rör fler än fem filer

O4 rör åtta filer, inte fem. De tre extra är små och följer av två krav i specen som drar åt
olika håll än filgränsen:

- `domain/invoice_models.py` + `api/routes/invoices.py` — "återanvänd predikatet, skriv inte ett
  andra". `status == "overdue" or is_overdue()` flyttade till `Invoice.counts_as_overdue()`, som
  både fakturalistans summering och `overdue_invoices` kallar. Testfall 12 hade annars jämfört
  två kopior av samma villkor, vilket inte är ett test.
- `repositories/correction_note_repo.py` (`count_open`) och `repositories/voucher_repo.py`
  (`count_missing_attachments`) — "ingen SQL i servicen som inte går via ett repository".
  `count_pending()` räknar bara `pending`, och `open_decisions` ska räkna `pending` **och**
  `suggested`. Alternativet var SQL i `services/overview.py`, vilket är ett hårdare brott
  (AGENTS.md: all SQL i `repositories/` + `db/`) än en fil till.

Fakturor och lönekörningar räknas däremot i Python över `list_all()` från respektive repository,
så de två filerna behövde inte röras alls.

## Beslut som inte stod i specen

- **`meta`-strängens form** (öppen fråga 1). Servern sätter ihop en fras per nollskild räknare,
  åtskilda med ` · ` — `"3 väntar på dig · 7 saknar underlag"` — och `"Inget väntar"` när sidan
  är tyst. Samma ton som `docs/to_agent/`, och strängen är serverns. Klienten renderar den.
- **`bokslut` räknar noll** (öppen fråga 2). Alla fyra räknare är noll på den sidan, med skälet i
  koden: det som borde räknas där (oavstämd period, osänd momsdeklaration) hör till
  `flode-verifikationer`. En tyst sida är ärligare än en påhittad siffra.
- **Räknarna är installationens, inte räkenskapsårets.** `missing_attachments`,
  `open_decisions`, `overdue_invoices` och `payroll_waiting` räknas över allt som finns, enligt
  antagande 1 (enbolag). `fiscal_year` och `period_state` är däremot det aktuella året och den
  aktuella perioden — det som ligger närmast `today`, annars det senaste.
- **Tomt bolag.** Utan räkenskapsår är `fiscal_year` och `period_state` `null`, och de tre
  sidorna finns ändå med nollställda räknare. Headern kan ritas dag ett.
