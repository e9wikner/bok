# Uppgifter: modul `flode-verifikationer`

Spec: `docs/redesign/SPEC-flode-verifikationer.md` · Plan: `tasks/flode-verifikationer/plan.md`
Testerna skrivs **före** implementationen (§14). Ingen uppgift rör mer än 5 filer, testfiler
oräknade. Testfallsnumren syftar på tabellerna i §14. Backendens tester ligger i
`tests/test_numrering.py` (F1–F3) och `tests/test_flode_verifikationer.py` (F5–F12).

---

- [x] **F1 — Migration 027: `vouchers` byggs om, `number` nullbar (gate 1)**
  - Gjort 2026-09-23: 4 tester (testfall 1–4) i `tests/test_numrering.py`, 1 och 2 sedda röda
    först. Varje fall bygger en databas på version 26 med numrerade utkast och kör 027 genom
    `Database.init_db`. Kolumnlistan är 001:s: ingen senare migration lägger till kolumner i
    `vouchers`, och ingen vy eller annan tabells trigger än de två på `voucher_rows` nämner den.
    Testfall 3 visade: `DROP TABLE` stoppas inte av raderingstriggern, men `RENAME` vägras så
    länge triggrarna på `voucher_rows` står kvar (`no such table: main.vouchers`) — 027 droppar
    dem i transaktionen och återskapar alla fyra ordagrant ur 014. Med `foreign_keys` på vägras
    `DROP TABLE` (av `correction_notes`) eller kaskaderar bort `voucher_rows`; att `PRAGMA
    foreign_keys = OFF` verkar genom runnerns `executescript` är bevisat genom att ta bort raden
    (alla fyra föll). Runnern behövde inte ändras. Avvikelser: `PRAGMA foreign_key_check` står
    inte i filen, eftersom `executescript` kastar resultatet; test 1 kräver den tom. Spec §4.2
    (skissen och risktabellen) uppdaterad. Övriga sviten: 106 fel + 6 errors, alla av samma
    orsak — koden ger utkast nummer och `CHECK` avvisar det. Rättas i F2.
  - Acceptans: `db/migrations/027_voucher_number_at_posting.sql` bygger om `vouchers` enligt
    spec §4.2. `number` är nullbar, och `CHECK((status='draft' AND number IS NULL) OR
    (status='posted' AND number IS NOT NULL))` gäller. Utkastens nummer blir `NULL`. Varje postad
    rad kopieras fält för fält. Index och de två triggrarna på `vouchers` ur 014 återskapas
    ordagrant, och triggrarna på `voucher_rows` fungerar som före. `PRAGMA foreign_key_check` är
    tom.
  - Verifiera: testfall 1–4. `pytest tests/` i övrigt får vara rött här, eftersom koden fortfarande
    numrerar utkast. Det rättas i F2, och F1 och F2 landar i samma push.
  - Filer: `db/migrations/027_voucher_number_at_posting.sql`, `tests/test_numrering.py`
  - Obs: börja med `PRAGMA table_info(vouchers)` och
    `grep -n "vouchers" db/migrations/*.sql`, så att kolumnlistan är den faktiska och inte den i
    001. Testfall 3 visar om `DROP TABLE` stoppas av raderingstriggern. Gör den det, droppas
    triggrarna först i samma transaktion (plan, risker).

- [x] **F2 — Numret sätts vid postning (gate 2)**
  - Gjort 2026-09-23: 8 tester (testfall 5–11 och 10b) i `tests/test_numrering.py`, 5–11 sedda
    röda först. `VoucherRepository.post` sätter numret i samma `UPDATE` som statusbytet, med
    `MAX(number) + 1` över postade som underfråga i samma sats och `COALESCE` med ett explicit
    nummer; `WHERE status='draft'` och en `rowcount`-kontroll. `create` och `create_correction`
    skriver inget nummer, och `get_next_number` räknar bara postade. `post_voucher` fick
    parametern `number`, och audit-raden för postningen bär det tilldelade numret. Hela sviten:
    1020 passed. Fyra befintliga tester ändrades, alla för att de förutsatte numrerade utkast (se
    commit). Avvikelser, specen §4.3 uppdaterad: `create_voucher` har inte längre någon
    `number`-parameter (explicit nummer går till `post_voucher`); läsningen är en underfråga i
    `UPDATE`, inte en separat `SELECT`; SIE4-importens skapa och posta är två transaktioner som
    före, inte en; `POST /vouchers` med `number` utan `auto_post` ger `400
    number_requires_auto_post`. `Voucher.number` och `VoucherResponse.number` blev redan här
    `Optional[int]` (annars mypy-fel respektive 500 på utkastsvar) — formateringen är kvar till
    F3. Sex produktionsfiler i stället för tre: `domain/models.py`, `api/schemas.py`,
    `api/routes/vouchers.py` tillkom av de skälen. `mypy .` har samma 61 fel som före.
  - Acceptans: `LedgerService.create_voucher` och `VoucherRepository.create_correction` sätter
    aldrig ett nummer. `post_voucher` tar `MAX(number) + 1` över **postade** i serien och
    räkenskapsåret, eller ett explicit nummer, i samma `UPDATE` som statusbytet, med
    `WHERE status='draft'`. SIE4-importen skickar filens nummer till postningen. Alla befintliga
    vägar som skapar och postar (fakturor, löner, IB, kategorisering, `/correct`, noteringarnas
    `approve`) fungerar oförändrat utifrån sett.
  - Verifiera: testfall 5–11; `pytest tests/ -v` helt grön.
  - Filer: `services/ledger.py`, `repositories/voucher_repo.py`, `services/sie4_import.py`,
    `tests/test_numrering.py`
  - Obs: befintliga tester som läser ett utkasts nummer skrivs om till att läsa numret efter
    postning. Ett test som *förutsätter* att ett utkast har nummer är ett test av det gamla felet.
    Det ska stå i commit-meddelandet vilka som ändrades.

- [x] **F3 — `number: Optional` i backenden, och luckkontrollen per räkenskapsår**
  - Gjort 2026-09-23: 6 tester (testfall 12, 12b, 13, 13b, 13c, 13d) i `tests/test_numrering.py`;
    12 och 13c sedda röda först, 13/13b/13d var gröna redan efter F2 och står kvar som vakt.
    `_check_voucher_sequence` grupperar på `series, fiscal_year_id` och nämner räkenskapsåret
    (datumintervallet) i rubrik och beskrivning. `list_all(sort_by="number")` sorterar
    `number IS NULL` först i nyckeln: utkasten hamnar sist vid både `asc` och `desc`, sinsemellan
    efter serie och datum i den begärda riktningen. Genomgången av varje ställe som läser ett
    nummer: `_voucher_dict`, `VoucherResponse` och noteringarnas ögonblicksbild skickar bara
    vidare och ger `null` för utkast (testat genom `las_verifikationer` och `GET /vouchers`,
    `/vouchers/{id}`, `/vouchers/{id}/audit`); `get_account_ledger`, huvudboken i `reports.py`
    (`_filter_posted_vouchers`), `sie4_export` och `_check_large_amounts` läser bara postade;
    korrigeringstexterna (`06d`) läser originalet, som alla vägar kräver postat (`not_posted`);
    `import_sie4`/`sie4_import` formaterar filens tolkade verifikationer, inte lagrade. Där
    ändrades ingenting. Enda ändringen utöver de två: det tillfälliga valideringsutkastet i
    `_validate_correction_rows` bar `number=0`, nu `None`. Tre produktionsfiler. Hela sviten:
    1026 passed; `mypy .` 61 fel som före. Avvikelser, specen §4.3 och §4.5 uppdaterade:
    `domain/models.py`, `api/schemas.py` och `agent_tools.py` behövde inte röras (typningen kom i
    F2, `_voucher_dict` gav redan `None`). Känt, inte ändrat: `_issue_exists` släpper bara in en
    öppen `voucher_sequence`-fråga åt gången (den har inget `entity_id`), så två serier/år med
    luckor syns en i taget i `run_all_checks` — kontrollen själv hittar båda.
  - Acceptans: `Voucher.number` och `VoucherResponse.number` är `Optional[int]`. Varje ställe i
    backenden som formaterar ett nummer hanterar `None`: `_voucher_dict` i verktygen, `compliance`,
    `sie4_export`, `reports`, `import_sie4` och beskrivningstexten för korrigeringar.
    `_check_voucher_sequence` grupperar på `series, fiscal_year_id`.
  - Verifiera: testfall 12, backenddelen av 13; `mypy` utan nya fel i de rörda filerna.
  - Filer: `domain/models.py`, `api/schemas.py`, `services/compliance.py`,
    `services/agent_tools.py` samt det `grep -rn '\.number\b' services repositories api` visar.
    Blir det fler än fem, dela uppgiften i schema och formatering.

- [x] **F4 — Klienten: ett utkast utan nummer**
  - Gjort 2026-09-23: `formatVerifikationsnummer(nummer, serie?, avgransare = "")` i
    `lib/utils.ts` ger `Utkast` när numret saknas, annars `A12`/`A-12`; alla ställen som visar ett
    verifikationsnummer använder den. 3 nya vitest (formatteraren postad/utkast i
    `lib/__tests__/verifikationsnummer.test.ts`, `verifikationerVy` med två utkast i
    `bocker.test.ts`), sedda röda först (`A-null`); hela sviten 437 gröna, lint, `tsc` och
    `NEXT_PUBLIC_SKAL=1` build gröna. `number: number | null` i `Voucher` (`lib/api.ts`) och
    `Verifikation` (`lib/skal/bocker.ts`). Alla listor hade redan `key={id}`; ingen klientsortering
    på nummer finns (`sort_by` går till servern). Orörda, eftersom de bara ser postade:
    `voucher_number` i huvudboken (`app/reports`), `Postad · A-12` i `chattyta` och
    `PostaUtfall.number`. Avvikelse: tio filer i stället för fyra. De gamla sidorna behövde
    `app/page.tsx`, `app/vouchers/page.tsx`, `app/vouchers/[id]/page.tsx` (rubriken blir
    `Verifikation` bredvid etiketten `Utkast`, kortet `Nummer` visar `Utkast`),
    `app/learning/page.tsx` och `app/audit/page.tsx` (loggens `created`-payload har
    `number: null`, gav `Anull`). Det bryter `skal`s testfall 18 (inga ändringar under `app/`
    utanför `app/v4`), så `grans.test.tsx` fick ett namngivet undantag för exakt de fem filerna;
    `SPEC-skal.md` §12 och specen §4.3 uppdaterade.
  - Acceptans: `number: number | null` i klientens typer. De gamla sidorna och `/v4` visar
    `Utkast` där de i dag visar ett utkasts nummer. Ingen `NaN`, ingen tom rubrik, ingen
    `A-null`.
  - Verifiera: klientdelen av testfall 13; `npm test`, `npx tsc --noEmit`.
  - Filer: `frontend-v3/lib/utils.ts`, `frontend-v3/lib/api.ts`, `frontend-v3/lib/skal/bocker.ts`,
    `frontend-v3/lib/skal/format.ts`

- [ ] **F5 — Migration 028: `thread_drafts` och dess repository**
  - Acceptans: tabellen enligt spec §6.1, med `CHECK`-villkoren. `ThreadDraftRepository` har
    `create`, `get`, `list(view_key, status, limit)`, `mark_posted`, `mark_superseded`,
    `set_error`, `set_receipt` och `pending_for_correction_of(voucher_id)`, med `_commit=False`
    för allt som ska kunna ingå i en annans transaktion. All SQL ligger här.
  - Verifiera: repositoryts egna tester, inklusive att `posted` utan `posted_at` avvisas och att
    `ON DELETE CASCADE` följer tråden.
  - Filer: `db/migrations/028_add_thread_drafts.sql`, `repositories/thread_draft_repo.py`,
    `domain/models.py`, `tests/test_flode_verifikationer.py`

- [ ] **F6 — `foresla_verifikation`: vanligt förslag**
  - Acceptans: `ForeslaVerifikationArgs` enligt spec §5.2, utan korrigeringsgrenen, som ger
    `not_implemented` för `correction_of` tills F11. `DraftService.propose` gör kontrollerna i
    §5.3, och skriver sedan utkast, `thread_drafts`-rad och `draft`-inlägg i **en** transaktion.
    Kroppen följer §5.6 och passerar `chattyta`s fixtur. Idempotensen följer §5.5.
    `replaces_draft_id` ersätter enligt §6.2.
  - Verifiera: testfall 14–21.
  - Filer: `services/draft_service.py`, `services/agent_tools.py` (argument och hanterare, inte
    listan), `tests/test_flode_verifikationer.py`
  - Obs: kroppens form läses ur `frontend-v3/lib/chattyta/__fixtures__/inlagg.ts`, inte skrivs av.
    Testet jämför nycklarna, så att producent och konsument inte kan glida isär.

- [ ] **F7 — Verktygslistan och agentinstruktionen**
  - Acceptans: `foresla_verifikation` sist i `_TOOL_SPECS`. De tio första är byte för byte
    oförändrade. `docs/to_agent/02_bokforingsprocess.md` beskriver när ett förslag används och
    när en direkt postning används (§12.2), och att en rättelse alltid är ett förslag (§12.5).
  - Verifiera: testfall 22; `tests/test_agent_entrypoint.py`, `agentruntime` 17 och `beslut` 26
    gröna.
  - Filer: `services/agent_tools.py`, `docs/to_agent/02_bokforingsprocess.md`,
    `tests/test_agent_entrypoint.py`

- [ ] **F8 — Postningens krokar och kvittot**
  - Acceptans: `POST /vouchers/{id}/post` anropar `DraftService.on_posting` i postningens
    transaktion och `on_posted` efter commit. `on_posting` sätter `posted`. `on_posted` skriver
    `receipt` enligt §8.2 och publicerar `message.completed` och `view.changed`. En uppspelning
    med samma nyckel skriver kvittot om det saknas. Utkast som inte är trådens berörs inte.
  - Verifiera: testfall 23–27.
  - Filer: `api/routes/vouchers.py`, `services/draft_service.py`,
    `repositories/voucher_repo.py` (saldo före/efter per konto),
    `tests/test_flode_verifikationer.py`
  - Obs: saldot räknas i en fråga över postade rader, inte per konto i en loop.

- [ ] **F9 — Felen i tråden**
  - Acceptans: `period_locked` och valideringsfel vid postning av ett trådutkast skriver ett
    `error`-inlägg enligt §9.1 och sätter `last_error_code`. Ett andra fel med samma kod för samma
    utkast skriver inget nytt. Inget nummer förbrukas.
  - Verifiera: testfall 28, 29.
  - Filer: `api/routes/vouchers.py`, `services/draft_service.py`,
    `tests/test_flode_verifikationer.py`

- [ ] **F10 — `GET /drafts`, `count_waiting` och räknaren**
  - Acceptans: `GET /api/v1/drafts` enligt §10. `DecisionService.count_waiting` enligt §11.3.
    `open_decisions` i `GET /overview` läser den. Payloaden är oförändrad.
  - Verifiera: testfall 30, 31; `oversikt`s och `beslut`s tester gröna.
  - Filer: `api/routes/drafts.py`, `main.py` (routern), `services/decision_service.py`,
    `services/overview.py`, `tests/test_flode_verifikationer.py`

- [ ] **F11 — Korrigeringsförslaget**
  - Acceptans: `foresla_verifikation` med `correction_of` bygger ett B-utkast med
    `LedgerService.create_correction`: återföring, sedan agentens rader. Målperiod och datum
    enligt §7.2. `consequence` nämner båda perioderna när originalets är låst. Kontrollerna i
    §7.4 görs.
  - Verifiera: testfall 32–36, 40.
  - Filer: `services/draft_service.py`, `services/ledger.py` (om `_target_correction_period`
    behöver ett datum), `tests/test_flode_verifikationer.py`

- [ ] **F12 — Rättelsens postning och noteringarna**
  - Acceptans: `on_posting` skriver korrigeringshistoriken, och sätter noteringen `applied` om
    `correction_note_id` finns, i postningens transaktion. Kvittot får titeln
    `B-{n} postad · rättar {serie}-{nummer}` och chipet `rättar …`. `las_korrigeringar` tar med
    öppna noteringar i svaret när `voucher_id` ges, med oförändrade argument. `409`-pekaren för
    `correction:`-beslut byts. `posta_verifikation` är oförändrad.
  - Verifiera: testfall 37–39, 41, 43.
  - Filer: `services/draft_service.py`, `services/agent_tools.py` (`_run_las_korrigeringar`),
    `services/decision_service.py` (pekaren), `tests/test_flode_verifikationer.py`

- [ ] **F13 — Förslagskortets lägen**
  - Acceptans: en `useForslag(viewKey)`-fråga mot `GET /drafts`, med ett anrop per vy, samma
    mönster som besluten. `VerifikationsForslag` visar fyra lägen enligt §10. Frågan invalideras
    enligt §10 sista stycket.
  - Verifiera: testfall 44, 47; `chattyta`s tester gröna.
  - Filer: `frontend-v3/hooks/useForslag.ts`, `frontend-v3/lib/chattyta/api.ts`,
    `frontend-v3/components/chattyta/VerifikationsForslag.tsx`, `frontend-v3/hooks/useTrad.ts`

- [ ] **F14 — Vyn Verifikationer**
  - Acceptans: sektionerna enligt §11.1, med trådutkast bara under Väntar. Radlägena finns, inklusive
    `rättelse väntar`. Den optimistiska raden följer §11.2 och har inget nummer medan den väntar.
    `rättad av`/`rättar` kommer ur en join i sidfrågan (backend) och visas i metan.
  - Verifiera: testfall 42, 45, 46; `skal`s tester gröna.
  - Filer: `repositories/voucher_repo.py` (join), `api/schemas.py` (två fält),
    `frontend-v3/lib/skal/bocker.ts`, `frontend-v3/hooks/useBockerVyer.ts` (eller där vyns frågor
    bor), `frontend-v3/components/skal/Skal.tsx`

- [ ] **F15 — Hela flödet, regression, omstart och modulen stängd**
  - Acceptans: testfall 48, med skriptade verktygsanrop: beslut → svar → förslag → post → kvitto,
    och rättelse → post → kvitto. Testfall 49 och 50 gröna. Visuell kontroll i `/v4` mot riktig
    backend med riktig LLM: flödets sex steg, en rättelse av en verifikation i en låst period, och
    två tryck på `Posta`. Därefter en tom databas och SIE4-filerna importerade igen (spec §4.4),
    och luckkontrollen körd. Den ska inte visa luckor som inte finns i filerna.
    `docs/redesign/SPEC-flode-verifikationer.md`, `tasks/README.md` och `ANALYS.md` §8
    markerar modulen och första leveransen som klara.
  - Verifiera: `pytest tests/ -v`, `black --check .`, `isort --check .`, `flake8`, `mypy` (inga nya
    fel), `npm test`, `npm run lint`, `npx tsc --noEmit`, `NEXT_PUBLIC_SKAL=1 npm run build`.
  - Filer: `tests/test_flode_verifikationer.py`, spec, `tasks/README.md`
