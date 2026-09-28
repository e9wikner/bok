# Uppgifter: modul `underlagstolkning`

Spec: `docs/redesign/SPEC-underlagstolkning.md` · Plan: `tasks/underlagstolkning/plan.md`
Testerna skrivs **före** implementationen (§14). Ingen uppgift rör mer än 5 filer, testfiler
oräknade. Testfallsnumren syftar på tabellerna i §10. Backendens tester ligger i
`tests/test_underlagstolkning.py`. Ingen frontend i modulen.

---

- [x] **U1 — Predikatet "saknar underlag" (gate)**
  - Gjort 2026-09-28: 6 tester (testfall 1–5, 5b) i `tests/test_underlagstolkning.py`; 2, 4, 5
    och 5b sedda röda först, 1 och 3 var gröna redan och står kvar som vakt (3 prövar att
    SIE4-undantaget inte fångar agentens eller handens verifikationer). `MISSING_ATTACHMENT_SQL`
    enligt §2.1, **inom parentes som helhet**: testfall 2:s andra halva
    (`?missing_attachment=false`) visade att `list_all` negerar predikatet med `NOT {…}`, och
    utan parentesen band `NOT` bara första ledet. `count_missing_attachments(min_row_ore=None)`
    fick tröskeln som parameter; `_check_missing_attachments` anropar den med `50000` och har
    ingen SQL kvar (frågan var den enda i compliance som nämnde `attachments`; aliaset `v`
    försvann med den). Inga befintliga tester förutsatte det gamla felet — hela sviten 1157
    gröna utan ändringar. mypy 61. Utanför fillistan, inte ändrad: kommentaren i
    `services/draft_service.py` vid kvittots "kompletteringsflagga satt" säger fortfarande "no
    row in `attachments`"; beteendet följer det lagade predikatet genom
    `voucher.missing_attachment`.
  - Acceptans: `MISSING_ATTACHMENT_SQL` i `repositories/voucher_repo.py` enligt spec §2.1: ingen
    rad i `attachments`, ingen i `voucher_intake_sources`, och `created_by != 'sie4_import'`.
    `services/compliance.py` har ingen egen SQL för predikatet: frågan med 500 kr-tröskeln flyttas
    till en metod i `VoucherRepository` (t.ex. `count_missing_attachments(min_row_ore=50000)` eller
    en syster till den) som använder det delade predikatet. `GET /vouchers?missing_attachment=…`,
    `GET /overview` och `compliance` ger samma tal på samma data.
  - Verifiera: testfall 1–5, 5b; `oversikt`s, `flode-verifikationer`s och compliance-testerna
    gröna.
  - Filer: `repositories/voucher_repo.py`, `services/compliance.py`,
    `tests/test_underlagstolkning.py`
  - Obs: compliance-frågan aliasar `vouchers v`, predikatet nämner `vouchers.id`. Flytta frågan
    utan alias i stället för att skriva en andra variant av predikatet. Commit-meddelandet ska
    säga att `missing_attachments` sjunker vid driftsättning och att det är rätt siffra.
    Befintliga tester som förutsätter att en agentpostad eller SIE4-importerad verifikation
    "saknar underlag" testar det gamla felet; nämn dem i commiten.

- [x] **U2 — Migration 030: `intake_interpretations`, domän och repository**
  - Gjort 2026-09-28: 9 tester (testfall 30 i fyra delar, CHECK-villkoren parametriserade i tre,
    31:s repositorydel i två) i `tests/test_underlagstolkning.py`, alla sedda röda först
    (modulerna fanns inte). Migrationens DDL är §5 ordagrant — ett test klipper ut §5:s
    `sql`-block ur specen och kräver att det står i filen — plus huvudkommentar och
    `INSERT OR IGNORE INTO schema_version (30)` som 028/029. `domain/interpretation.py`:
    `Confidence` och `MatchKind` som `Literal`, `Candidate` med §7.4:s jämförelsefält, `Match`
    som `Candidate` plus `kind` och `hypothesis`, `Interpretation` med
    `json_columns()`/`from_json_columns()`. `InterpretationRepository`: `insert`,
    `latest_for_source`, `count_for_source`, inget annat (testat); senaste är
    `ORDER BY created_at DESC, rowid DESC` — testfall 31 sätter samma `created_at` på båda, och
    blir rött med `rowid ASC`. `insert` skriver `id` och `created_at` från domänobjektet (som
    `thread_draft_repo`), inte kolumnens förval. `test_numrering.py` grön (19). Hela sviten
    1166 gröna, mypy 61. Öppet till U6/U8: tabellen har `expected_voucher_id` men ingen kolumn
    för det uträknade `expected`; läsvägen (§8, "samma form som §6.5") får räkna om det eller
    lämna det — inget här förutsätter endera.
  - Acceptans: `db/migrations/030_add_intake_interpretations.sql` ordagrant enligt spec §5, med
    index och de två triggrarna. `domain/interpretation.py` har `Interpretation`, `Match`,
    `Candidate` och `Confidence` (dataklasser/Literal, ingen logik utöver (de)serialisering av
    `*_json`). `InterpretationRepository` har `insert(interpretation, _commit=True)`,
    `latest_for_source(source_id)` och `count_for_source(source_id)`, inget `update`, inget
    `delete`. Ordning på `created_at, rowid` så att två tolkningar i samma sekund har en entydig
    senaste.
  - Verifiera: testfall 30; repositorydelen av 31 (två rader, den senare är `latest`);
    `CHECK`-villkoren (`confidence`, negativa belopp) avvisar.
  - Filer: `db/migrations/030_add_intake_interpretations.sql`, `domain/interpretation.py`,
    `repositories/interpretation_repo.py`, `tests/test_underlagstolkning.py`
  - Obs: `test_numrering.py` testfall 1 kontrollerar att en viss version är tillämpad, inte
    maxversionen (ändrat i F5) — kontrollera att den inte bryts.

- [x] **U3 — Kontrollerna och säkerheten (ren logik)**
  - Gjort 2026-09-28: 34 tester (testfall 6–14 med gränsfall, några parametriserade, plus sex
    `test_u3_*`) i `tests/test_underlagstolkning.py`, utan databas, alla sedda röda först.
    `run_checks(read: Read, *, text_layer_text: Optional[str], today: date) -> Checks` och
    `confidence(checks) -> Confidence`. `Read`/`ReadLine` är `Protocol` med skrivskyddade
    properties (bara fälten kontrollerna läser): de är kovarianta, så U6:s Pydantic-modell går
    in rakt av (`list[TolkaUnderlagLine]` mot `Sequence[ReadLine]`, `Literal[25, 12, 6, 0]` mot
    `int`) — prövat med mypy mot en kopia av §6.2 och i ett test. Moms per rad räknas exakt med
    `Fraction` och jämförs med ±1 öre per rad med `vat_rate`; `vat_share` ±0,5 procentenheter
    inklusive gränsen; netto ≤ 0 med moms är `implausible`. `text_layer`: bara ett trippel som
    `reconciliation_result` säger `RECONCILES` räknas — ett som inte går ihop är omkastad text
    och ger `not_available`, inte `disagrees`; totalt **och** moms ska vara lika, så en läsning
    utan `vat_ore` mot en text med moms är `disagrees`. `date = missing` och `currency = not_sek`
    sänker inte. **Utanför fillistan:** `Checks` (fryst dataklass med `to_dict()` i §6.3:s
    ordning) och `Literal`-typerna per kontroll i `domain/interpretation.py`; U6 sparar
    `checks.to_dict()` i `Interpretation.checks`, vars typ är oförändrad. Hela sviten 1213
    gröna, mypy 61.
  - Acceptans: `services/interpretation.py` har `run_checks(read, *, text_layer_text, today) ->
    Checks` och `confidence(checks) -> Confidence` enligt spec §6.3–§6.4. `text_layer` tar den
    redan utlästa texten (eller `None`) och använder `reconciliation_result`; filen läses inte här.
    Toleranser: ±1 öre per rad för `lines_sum` och `vat_rate`, ±0,5 procentenheter för
    `vat_share`. `currency = not_sek` sänker inte säkerheten. Ingen SQL, inga HTTP-begrepp.
  - Verifiera: testfall 6–14, utan databas.
  - Filer: `services/interpretation.py`, `tests/test_underlagstolkning.py`
  - Obs: testfall 11–12 matar in text som `reconciliation_result` känner igen; läs dess
    mönster i `services/agent_documents.py` i stället för att gissa formatet.

- [x] **U4 — Kandidatfrågan**
  - Gjort 2026-09-28: 13 tester (testfall 5b, 20–24, 29 och fyra `test_u4_*` för fälten, flera
    bankhändelser, utkast och fönstrens placering) i `tests/test_underlagstolkning.py`, alla sedda
    röda först (metoden fanns inte). `match_candidates` är en CTE-fråga: `totals` grupperar
    verifikationsraderna (debetsumma, `vat_in`-summa som `debit − credit`, `HAVING
    ABS(SUM(debit) − total) <= fönster`), `bank` väljer med `ROW_NUMBER()` den tidigaste
    bankhändelsen (`transaction_date`, sedan `id`) per verifikation. Returtyp: egen frusen
    `MatchCandidateRow` (`voucher_id`, `voucher_number` som `"A-118"`, `voucher_date: date`,
    `voucher_description`, `voucher_ore`, `vat_ore` — `None` utan `vat_in`-rad, inte 0 — och
    `bank_transaction: CandidateBankTransaction | None` med `id`, `date`, `amount_ore`,
    `counterpart_name`, `description`) i `voucher_repo.py`, inte domänens `Candidate`: raden är
    råa fakta, `Candidate` bär jämförelsen (`diff_ore`, `date_diff_days`, `vat.equal`) som U5
    räknar. `date_window` är `(före, efter)` i dagar, `amount_window_ore` ett färdigt öretal;
    båda keyword-only utan förval (testat). **Utanför fillistan:** `services/interpretation.py`
    skapad med bara konstanterna (`DATE_WINDOW_DAYS_BEFORE/AFTER = 3/7`,
    `AMOUNT_WINDOW_MIN_ORE = 5000`, `AMOUNT_WINDOW_PERCENT = 10`) och en docstring; U3/U5/U6 bygger
    vidare i den. `max(5 000, 10 %)` räknas av anroparen (U6), i testerna av en hjälpfunktion
    på konstanterna. Hela sviten 1179 gröna, mypy 61.
  - Acceptans: `VoucherRepository.match_candidates(document_date, total_ore, *, date_window,
    amount_window_ore)` i **en** fråga: postade, lagat predikat (U1), inte serie `IB`, datum- och
    beloppsfönster enligt §7.2 (utan `document_date`: bara exakt belopp). Varje rad bär
    `voucher_ore` (summan av debet), `vat_ore` (rader på konton av typ `VAT_IN`) och den kopplade
    bankhändelsen ur `voucher_bank_transactions` (id, datum, belopp, `counterpart_name`,
    `description`), eller `None`. Fönstrens konstanter står i `services/interpretation.py` och
    skickas in; repositoryt har inga egna förval för dem.
  - Verifiera: testfall 20–24, 29; 5b:s undantag gäller även här.
  - Filer: `repositories/voucher_repo.py`, `tests/test_underlagstolkning.py`
  - Obs: en verifikation med flera bankhändelser ska inte ge flera kandidatrader. Välj en
    (tidigaste) i frågan och skriv valet i docstringen.

- [x] **U5 — Rankning, entydighet, `match`, `expected` och hypotesen (ren logik)**
  - Gjort 2026-09-28: 41 tester (testfall 16:s logikdel, 17–19, 25–28 med gränsfall, några
    parametriserade, plus `test_u5_*`) i `tests/test_underlagstolkning.py`, utan databas, alla
    sedda röda först. Publikt i `services/interpretation.py`: `amount_window_ore(total_ore)`
    (U4:s testhjälp använder den nu), `match_document(read, rows) -> Matching` (`match` +
    högst fem `candidates` i rankordning, matchen först; `currency != SEK` ger `None`/`[]`),
    `rank(read, rows) -> list[Candidate]` (stabil sortering, ingen trunkering),
    `build_match(read, candidate) -> Match`, `expected(read, row, matching) -> Expected | None`
    och `hypothesis(lines, diff_ore)`. `rows` är U4:s `MatchCandidateRow`. `MatchRead`/
    `MatchReadLine` utökar U3:s protokoll med `vendor` och `text`; §6.2:s Pydantic-modell går in
    rakt av (testat). Val: `date_diff_days` = verifikation − underlag (positivt = bokfört efter,
    som fönstret [−3, +7]), `None` utan `document_date`, och då är `kind` aldrig `exact`;
    `vat.equal` är `None` om någon sida saknar moms; `bank_transaction` bär även
    `description`; `is_best_match` bara när verifikationen är den entydiga `match`; `expected`
    är `None` i annan valuta. Hypotesen: rader på 0 öre räknas inte, sökningen per storlek
    avbryts vid andra träffen (tvetydigt), 100 rader utan träff < 2 s (ca 0,1 s). Beloppet i
    texten har tecken (`-120,00` för en rabatt). **Utanför fillistan:** `Expected(Match)` med
    `is_best_match` i `domain/interpretation.py`. `services.pdf_export.format_sek` återanvänds
    inte (modulen drar in weasyprint, ca 1 s kallt); en egen `_format_kr` hålls lika med den av
    ett test. Hela sviten 1254 gröna, mypy 61.
  - Acceptans: i `services/interpretation.py`: `rank(read, candidates)` sorterar på `|diff_ore|`,
    `|date_diff_days|`, leverantörsträff (skiftlägesokänslig, i `description` eller bankhändelsens
    `counterpart_name`/`description`); `match` sätts bara om första kandidaten är entydig på alla
    tre nycklarna; `candidates` högst fem. `build_match` ger formen i §7.4 med `kind` (`exact`
    när `diff_ore = 0` och `date_diff_days ≤ 3`), `vat.equal`, `bank_transaction`.
    `hypothesis(lines, diff_ore)` enligt §7.5: en rad, annars minsta mängd av högst tre rader,
    tvetydighet ger `None`; texten formuleras av servern (`Skillnaden på 120,00 kr motsvarar
    raden ”Pant” på underlaget.`). `expected` räknas mot en given verifikation med
    `is_best_match`. `currency != SEK` ger `match = None`, `candidates = []`.
  - Verifiera: testfall 16 (logikdelen), 17–19, 25–28, plus ett hypotestest med 100 rader och en
    tidsgräns.
  - Filer: `services/interpretation.py`, `tests/test_underlagstolkning.py`
  - Obs: `date_diff_days` i `kind` är absolutvärdet. Beloppsformateringen i hypotestexten ska
    vara svensk (mellanslag som tusentalsavgränsare, komma som decimaltecken) — återanvänd en
    befintlig formaterare om en finns i `services/`.

- [ ] **U6 — `tolka_underlag`: argument, hanterare och orkestrering**
  - Acceptans: `TolkaUnderlagArgs`/`TolkaUnderlagLine` enligt §6.2 med `extra="forbid"`, så att
    `confidence` eller `hypothesis` i argumenten ger `invalid_tool_arguments`.
    `InterpretationService.interpret(args, *, actor, thread_id, agent_run_id)`: hämtar källan
    (`source_not_found`/`source_deleted` som `las_underlag`), läser filen och textlagret med
    `extract_pdf_text` när den är en PDF, kör U3, hämtar kandidater (U4) och rankar (U5), räknar
    `expected` (hämtar den verifikationen även utanför fönstren), sparar raden (U2) och svarar
    enligt §6.5 med `read` oförändrat. `_run_tolka_underlag` i `agent_tools.py` läser `thread_id`
    och `agent_run_id` ur `tool_context` om de finns. Hanteraren läggs **inte** i `_TOOL_SPECS`.
  - Verifiera: testfall 15, 16 (hela vägen mot testdatabasen: 4 600/4 480, `diff_ore = 12000`,
    hypotes på pantraden, `vat.equal`), 25, 33, 35, 36.
  - Filer: `services/interpretation.py`, `services/agent_tools.py` (argument och hanterare, inte
    listan), `tests/test_underlagstolkning.py`
  - Obs: inga andra verktygs argumentmodeller får `extra="forbid"` här — det ändrar deras schema
    och därmed det cachade prefixet. Om `tool_context` inte bär `agent_run_id` i dag, skriv var
    det kommer ifrån i stället för att lägga till det i förbifarten. Testfall 33 jämför de fyra
    tabellerna/kolumnerna före och efter, inte bara radantalet.

- [ ] **U7 — Verktygslistan**
  - Acceptans: `tolka_underlag` sist i `_TOOL_SPECS`, med beskrivningen i §6.2 ordagrant. De elva
    första oförändrade byte för byte. Modulens och `execute_tool`s docstrings säger tolv verktyg.
  - Verifiera: testfall 34 (sha256 av `json.dumps(AGENT_TOOL_DEFINITIONS[:11])` tagen på commiten
    före); `agentruntime` 17 och `flode-verifikationer` 22 uppdaterade och gröna.
  - Filer: `services/agent_tools.py`, `tests/test_underlagstolkning.py`,
    `tests/test_agent_runtime.py`, `tests/test_flode_verifikationer.py`

- [ ] **U8 — `GET /api/v1/intake/{id}/interpretation`**
  - Acceptans: bearer-autentiserad route i `api/routes/intake.py`, före eventuella fångande
    routes. Svaret har §6.5:s form plus `created_at`, `actor`, `thread_id`, `superseded_count`
    och `match.still_open` (verifikationen saknar fortfarande underlag enligt predikatet **och**
    källan har ingen rad i `voucher_intake_sources`), härlett vid läsning i servicen genom en
    repository-fråga. `404 source_not_found` / `404 interpretation_not_found`. Ingen skrivande
    route.
  - Verifiera: testfall 31, 32, 37.
  - Filer: `api/routes/intake.py`, `services/interpretation.py`,
    `repositories/interpretation_repo.py` (eller `voucher_repo` för `still_open`),
    `tests/test_underlagstolkning.py`
  - Obs: testfall 32 kopplar källan genom en befintlig väg (`IntakeService.link_existing_voucher`
    i testet), inte genom ny kod — kopplingen hör till `flode-underlag`.

- [ ] **U9 — Agentinstruktionen**
  - Acceptans: `docs/to_agent/03_bokforingsinstruktion.md` får tillägget i §9, punkt 1–5: tolka
    före postning eller förslag; `exact` eller `amount_diff` med hypotes → avstå i passet med
    verifikationsnummer och differens i motiveringen, säg det i tråden; `match = null` med
    kandidater → fråga; `low` → gissa inte; hypotesen återges som hypotes.
  - Verifiera: testfall 38 i `tests/test_agent_entrypoint.py`; hela den filen grön.
  - Filer: `docs/to_agent/03_bokforingsinstruktion.md`, `tests/test_agent_entrypoint.py`
  - Obs: körtidsinnehåll (`AGENTS.md`). Om `02_bokforingsprocess.md` beskriver postningens steg
    och motsäger det nya, rätta den i samma commit och nämn det.

- [ ] **U10 — Skriptat pass, regression och modulen stängd**
  - Acceptans: testfall 39 med `agentruntime`s skriptade klient: ett intagspass med ett kvitto
    som matchar en postad A-verifikation exakt → `hamta_underlagsfil` → `tolka_underlag` →
    `registrera_avstaende` med verifikationsnumret i motiveringen; ingen ny verifikation, inget i
    `voucher_intake_sources`. Specens status, `tasks/README.md` och `ANALYS.md` §8 markerar
    modulen klar. Framgångskriterierna i §11 gås igenom ett och ett under "Modulen är klar"
    nedan.
  - Verifiera: `pytest tests/ -v`, `black --check .`, `isort --check .`, `flake8`, `mypy .` (≤ 61
    fel).
  - Filer: `tests/test_underlagstolkning.py`, spec, `tasks/README.md`, `docs/redesign/ANALYS.md`
  - Obs: kriterium 6 med riktig LLM kontrolleras av beställaren (§11); skriv det under "Kvar för
    beställaren" om det inte gjorts.

---

## Kvar för beställaren

- Kriterium 6 med riktig LLM: ett kvitto för en bankbokförd verifikation ger ett avstående, inte
  en ny verifikation.
