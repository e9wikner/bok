# Uppgifter: modul `flode-underlag`

Spec: `docs/redesign/SPEC-flode-underlag.md` · Plan: `tasks/flode-underlag/plan.md`
Testerna skrivs **före** implementationen (§14, §15). Ingen uppgift rör mer än 5 filer, testfiler
oräknade. Testfallsnumren syftar på tabellerna i §14. Backendens tester ligger i
`tests/test_flode_underlag*.py`, en fil per spår (plan, "Testfilerna"); hjälparna skrivs i FU1
och importeras därifrån. Klientens i `frontend-v3/**/__tests__/`.

Uppgifterna fördelas på flera subagenter. **Beror på** är hårda beroenden; **Filer** är vad
uppgiften äger. En uppgift som behöver röra en fil utanför sin lista stannar och säger till (plan,
"Filägarskap"). Avvikelserna mellan spec och kod står i planen, numrerade; uppgifterna hänvisar
till dem.

---

## Backend

- [x] **FU1 — Migration 032: `intake_link_basis` och `voucher_source_references` (gate 1)**
  - Gjort 2026-09-28: 13 tester i `tests/test_flode_underlag.py` (testfall 17, 42c, CHECK-villkoren
    parametriserade, round trip, repositoryna utan update/delete, domänen fryst, hjälparna);
    domän- och repositorytesterna sedda röda först (modulerna fanns inte). Migrationen skrevs före
    testet som klipper ut §5:s två `sql`-block, så det testet och hjälpartestet var gröna direkt.
    Migrationen är §5 ordagrant plus de två triggrar som blockets kommentar beskriver, och två
    index (`intake_link_basis(decision_id)` för `get_by_decision`, `voucher_source_references
    (via_voucher_id)` för FU16:s join). Hjälparna: `posted_purchase`/`a118`, `make_source(status)`
    (en bild, så tolkningen läser inget textlager), `interpret(source, kind)` genom
    `InterpretationService.interpret`, `make_thread`, `make_run`, `make_decision(thread, source,
    answer=1|2|3|"fritext"|None)` med §9.2:s tre alternativ genom `DecisionService`.
    `test_numrering.py` grön. mypy 61.
  - Beror på: —
  - Acceptans: `db/migrations/032_add_intake_link_basis.sql` med båda tabellerna ordagrant enligt
    §5, fyra triggrar (ingen `UPDATE`, ingen `DELETE` på någondera), huvudkommentar och `INSERT
    OR IGNORE INTO schema_version (version) VALUES (32)` som 031. `domain/intake_link.py`:
    `LinkBasis` (`Literal["exact_match", "decision"]`), `IntakeLinkBasis` och
    `VoucherSourceReference` som frysta dataklasser, `LinkResult` med §6.6:s fält.
    `repositories/intake_link_repo.py`: `IntakeLinkRepository.insert(basis, _commit=True)`,
    `get_for_source(source_id)`, `get_by_decision(decision_id)`, och
    `VoucherSourceReferenceRepository.insert(ref, _commit=True)`, `get_for_voucher(voucher_id)`.
    Inget `update`, inget `delete`. `tests/test_flode_underlag.py` får modulens hjälpare: en
    postad A-verifikation med rader och moms, en källa i given status, en tolkning av given
    `kind` (genom `InterpretationService.interpret`, inte rå SQL), en tråd, och ett beslut
    besvarat med ett givet alternativ eller fritext.
  - Verifiera: testfall 17, 42c; `CHECK ((basis = 'decision') = (decision_id IS NOT NULL))` och
    `CHECK (voucher_id != via_voucher_id)` avvisar; repositoryna har inga skrivande metoder
    utöver `insert` (testat som i U2).
  - Filer: `db/migrations/032_add_intake_link_basis.sql`, `domain/intake_link.py`,
    `repositories/intake_link_repo.py`, `tests/test_flode_underlag.py`
  - Obs: ett test klipper ut §5:s två `sql`-block ur specen och kräver att de står i filen, som
    U2. `test_numrering.py` kontrollerar att version 27 är tillämpad, inte maxversionen — kontrollera
    att den inte bryts. De främmande nycklarna pekar på `intake_interpretations` (030), `decisions`
    (026), `agent_runs` (024) och `threads` (025); hjälparna ska skapa riktiga rader, inte slå av
    `foreign_keys`.

- [x] **FU2 — Predikatet: rättelser (D3) och hänvisningen (gate 2)**
  - Gjort 2026-09-28: 6 tester i `tests/test_flode_underlag_predikat.py` (testfall 44 i två
    delar, predikatdelen av 42, rättelsen ingen kandidat, `match_still_open` följer med, en
    grep-vakt), alla sedda röda först. `MISSING_ATTACHMENT_SQL` fick `vouchers.correction_of IS
    NULL` och `NOT EXISTS (… voucher_source_references …)` inom den yttre parentesen; ingen
    annan variant. Testhjälpens rättelse är en omföring med A-118:s belopp och datum, så att den
    hade varit kandidat utan D3 (första versionen var grön av fel skäl: debetsumman låg utanför
    beloppsfönstret). Inga befintliga tester förutsatte det gamla: `kompletteringsflagga` i
    `tests/` förekommer bara i `test_flode_verifikationer.py` (A-serien, orörd). Hela sviten
    1326 gröna. mypy 61. Spårfilerna binder modulens fixturer med `period_id = fu.period_id`
    i stället för att importera dem, eftersom importen ger F811 i flake8.
  - Beror på: FU1
  - Acceptans: `MISSING_ATTACHMENT_SQL` (`repositories/voucher_repo.py:23`) får två villkor till,
    inom samma yttre parentes: `vouchers.correction_of IS NULL` och `NOT EXISTS (SELECT 1 FROM
    voucher_source_references vsr WHERE vsr.voucher_id = vouchers.id)`. Kommentaren ovanför säger
    varför (§3.1, D2, D3). Inget annat ställe får en egen variant: `GET /vouchers`, `GET
    /overview`, compliance (`count_missing_attachments`), `match_candidates` och
    `match_still_open` följer med.
  - Verifiera: testfall 44 (en postad rättelse saknar inte underlag; samma tal i `/overview`,
    `/vouchers?missing_attachment=true` och compliance); predikatdelen av 42 (en verifikation med
    en rad i `voucher_source_references` saknar inte underlag); en rättelse är ingen kandidat i
    `match_candidates`; `?missing_attachment=false` ger komplementet (parentesen, U1).
    `oversikt`s, `underlagstolkning`s och `flode-verifikationer`s tester gröna.
  - Filer: `repositories/voucher_repo.py`, `tests/test_flode_underlag_predikat.py`
  - Obs: commit-meddelandet ska säga att `missing_attachments` sjunker vid driftsättning och att
    det är rätt siffra (§12 D3). En B-rättelses kvitto slutar få spåret `kompletteringsflagga
    satt` (`services/draft_service.py:296`); grep `kompletteringsflagga` i `tests/` och nämn i
    commiten varje test som förutsatte det gamla.

- [x] **FU3 — `IntakeLinkService`: kontroll 1–8, `exact_match`, transaktionen, uppspelningen**
  - Gjort 2026-09-28: 24 tester i `tests/test_flode_underlag.py` (testfall 1, 2, 3, 8, 9, 12–16,
    18, 19, plus okänd källa/verifikation, kandidat som inte är match, statusarna i kontroll 5
    parametriserade, en källa kopplad av en postning, grep-vakt mot SQL), alla sedda röda först
    utom vakten att `posta_verifikation` fortfarande vägrar en `failed` källa med
    `intake_not_processable` (grön före och efter). Felen är tre underklasser av
    `IntakeLinkError(IntakeError)` efter §7:s statusgrupper: `LinkNotFoundError` (404),
    `LinkConflictError` (409), `LinkRejectedError` (400). Avvikelse 1: skrivningarna i
    `link_existing_voucher` bröts ut till `IntakeService.persist_voucher_link` (inga kontroller,
    `_commit=False`), som `link_existing_voucher` anropar efter sin oförändrade
    `_ensure_can_record_outcome`; postningens två anrop är orörda. **Avvikelse:** en källa som
    kopplats av en *postning* till samma verifikation har inget belägg (§5) och blir
    `intake_already_linked`, inte en uppspelning — det finns inget belägg att spela upp.
    `link_requires_decision` har `match_kind=…` i `details` (`none` utan match). Försökets
    `summary` är `Underlag kopplat till {nummer} ({basis})`. Hela sviten 1350 gröna. mypy 61.
  - Beror på: FU1
  - Acceptans: `services/intake_link.py` med `IntakeLinkService.link(source_id, voucher_id, *,
    decision_id, actor, thread_id, agent_run_id) -> LinkResult`. Kontrollerna i §6.3:s ordning,
    1–8, med felkoderna där (egna `IntakeError`-underklasser eller `IntakeError` med kod; 404-,
    409- och 400-grupperna i §7 ska gå att skilja på typ, så att routen inte mappar på
    strängar). Kontroll 5 släpper igenom `pending`, `processing`, `failed` och `needs_attention`
    (D9). Kontroll 9 i den här uppgiften bara för `exact_match` (§6.4: `kind = "exact"`, samma
    `voucher_id`, `match_still_open` räknat nu); allt annat ger `link_requires_decision` med
    `match.kind` i `details`. En transaktion: länken (med `link_reason` enligt §5), försöket,
    `processed`, belägget. Uppspelning enligt §6.5 (`replayed: true`, ingenting skrivs; samma
    verifikation med annat beslut är också uppspelning). `missing_attachments` i svaret ur
    `VoucherRepository.count_missing_attachments()` efter commit. Ingen SQL i servicen.
  - Verifiera: testfall 1, 2, 3, 8, 9, 12, 13, 14, 15, 16, 18, 19; plus att `posta_verifikation`
    fortfarande vägrar en `failed` källa med `intake_not_processable` (postningens kontroll är
    orörd, §3.3).
  - Filer: `services/intake_link.py`, `services/intake.py`, `domain/intake_link.py`,
    `tests/test_flode_underlag.py`
  - Obs: avvikelse 1 — `link_existing_voucher` kör alltid `_ensure_can_record_outcome`. Lägg till
    en väg förbi den som bara den här servicen använder; ändra inte `_ensure_can_record_outcome`
    och inte postningens två anrop. Testfall 16 får insättningen av belägget att fallera
    (monkeypatch på repositoryt) och kräver att länk, försök och status inte står kvar. Testfall
    18 jämför innehållet i `vouchers` och `voucher_rows`, inte radantalet.

- [x] **FU4 — Beslutsbelägget (kontroll 9, D1)**
  - Gjort 2026-09-28: 11 tester i `tests/test_flode_underlag.py` (testfall 4, 5, 6, 7 med alla
    fyra fel plus `decision_not_found` och `source_kind` fel, 10, 11 över `GET /decisions`, plus
    beslut utan tråd, passet, beslut vid exakt match och uppspelning med annat beslut), alla sedda
    röda först. Med `decision_id` är belägget alltid `decision`, oavsett matchningens slag.
    `decision_not_in_thread` bara när `thread_id` är satt, så routen (§7) kopplar med ett beslut
    ur vilken tråd som helst. **Tillägg:** `link(…, decisions_allowed=True)`; passet (verktyget
    utan tråd, FU5) skickar `False` och får då `link_requires_decision` även med ett
    `decision_id` (§6.7). Felklasser: `decision_not_found` 404, `decision_still_open`/
    `decision_superseded`/`decision_declined` 409, `decision_not_for_source`/
    `decision_not_in_thread` 400 (det senare står inte i §7:s tabell; det kan inte uppstå över
    HTTP). Alternativet läses med `DecisionRepository.get_option`; ingen ny SQL. Hela sviten
    1361 gröna. mypy 61.
  - Beror på: FU3
  - Acceptans: `decision_id` i `IntakeLinkService.link` prövas enligt §6.4:s tabell, i den
    ordningen: `decision_not_found`, `decision_still_open`/`decision_superseded`,
    `decision_not_for_source` (`source_kind = "intake_source"` och `source_id`),
    `decision_not_in_thread` (bara när `thread_id` är satt), `decision_declined` (svaret är ett
    alternativ med `is_exit`). Fritext släpps igenom. Utan tråd (passet) och utan `decision_id`
    gäller bara `exact_match`. Belägget får `basis = "decision"` och `decision_id`; `link_reason`
    `"decision={id} interpretation={id}"`.
  - Verifiera: testfall 4, 5, 6, 7 (alla fyra fel), 10, 11 (inklusive att det syntetiska
    `intake:`-beslutet är borta ur `GET /decisions` efteråt).
  - Filer: `services/intake_link.py`, `tests/test_flode_underlag.py`
  - Obs: beslutets alternativ läses med `DecisionRepository.get_option`/`list_options`; ingen ny
    SQL behövs. Testfall 10 tolkar om med `expected_voucher_id` mot en SIE4-importerad
    verifikation, som aldrig är kandidat (`SPEC-underlagstolkning.md` §12.5).

- [x] **FU5 — `koppla_underlag` sist i verktygslistan**
  - Gjort 2026-09-28: 8 tester i `tests/test_flode_underlag_verktyg.py` (testfall 36 i två delar:
    sha256 av de tolv tagen på `a326fdf` och beskrivningen läst ur §6.2; argumenten; docstrings;
    testfall 1 och 4 genom `execute_tool` med en riktig tråd; beslut ur en annan tråd; passet),
    alla sedda röda först. `KopplaUnderlagArgs` utan `extra="forbid"`, så
    `test_u6_only_tolka_underlag_forbids_extra_fields` står orörd. Handläggaren skickar
    `decisions_allowed = thread is not None` (§6.7). Uppdaterade: `agentruntime` 17
    (`_EXPECTED_TOOL_NAMES`, och `koppla_underlag` bland de skrivande verktygen i
    `test_only_the_writing_tools_are_undocumented_as_read_only`), `beslut` 25 (13 namn),
    `underlagstolkning` 34 (`[-1]` → `[11]`, "last" → "twelfth", U7:s docstringtest kräver
    "thirteen" i `execute_tool`), U15:s schemahash (`[-1]` → `[11]`) och `flode-verifikationer`
    22. Hela sviten 1369 gröna. mypy 61. **Öppen punkt till FU18:** verktyget är inte terminalt,
    så i passet blir en koppling följd av ett bart `end` utfallet `abstained: agent_no_outcome`
    (räknas i `items_abstained`); källan är `processed` och får inget avstående.
  - Beror på: FU4
  - Acceptans: `KopplaUnderlagArgs` enligt §6.2 och `_run_koppla_underlag`, som läser `thread`
    (→ `thread_id`), `agent_run_id` och aktören ur `tool_context` och anropar
    `IntakeLinkService.link`. Sist i `_TOOL_SPECS`, med beskrivningen i §6.2 ordagrant; det
    trettonde verktyget. Modulens och `execute_tool`s docstrings säger tretton. Inte terminalt.
  - Verifiera: testfall 36 (sha256 av `json.dumps(AGENT_TOOL_DEFINITIONS[:12])` tagen på
    commiten före och hårdkodad; beskrivningen jämförd med blockcitatet i §6.2 läst ur spec-filen);
    testfall 1 och 4 genom `execute_tool` med en falsk tråd. Uppdatera och håll gröna:
    `agentruntime` 17 (`tests/test_agent_runtime.py`, `_EXPECTED_TOOL_NAMES`), `beslut` 25/26
    (`tests/test_beslut.py`, `len(names) == 12`), `underlagstolkning` 34
    (`tests/test_underlagstolkning.py`: `[-1]` blir `[11]`, "sist" blir "tolfte") och
    `flode-verifikationer` 22.
  - Filer: `services/agent_tools.py`, `tests/test_flode_underlag_verktyg.py`,
    `tests/test_agent_runtime.py`, `tests/test_beslut.py`, `tests/test_underlagstolkning.py`,
    `tests/test_flode_verifikationer.py`
  - Obs: inga andra verktygs argumentmodeller ändras (prefixet). Beskrivningen nämner inte
    "huvudboken" (§6.2); `tradar` 14 och `agentruntime` 17 förbjuder ordet. `KopplaUnderlagArgs`
    får `extra="forbid"` bara om testet för det i `underlagstolkning`
    (`test_u6_only_tolka_underlag_forbids_extra_fields`) uppdateras i samma commit.

- [x] **FU6 — `POST /api/v1/intake/{id}/link`**
  - Gjort 2026-09-28: 27 tester i `tests/test_flode_underlag_http.py` (testfall 1, 4, 13 över
    HTTP; tre riktiga avvisningar, en per statusgrupp; §7:s femton koder parametriserade genom
    en monkeypatchad service, så att routen visas mappa på typ; tjänstens egen typ för ett urval
    av koderna; `405` för PUT/PATCH/DELETE; `401`; `422` för okänt fält, `source_id` i kroppen
    och tom kropp), alla sedda röda först utom ett (typurvalet mot servicen). `LinkRequest` med
    `extra="forbid"`. `_http_error` fick kopplingens tre typer först; mappningen för befintliga
    fel är orörd. `201` vid koppling, `200` med `replayed: true` vid uppspelning (satt på
    `Response`). Routen ligger före `GET /{source_id}`. Hela sviten 1396 gröna. mypy 61.
  - Beror på: FU4
  - Acceptans: bearer-autentiserad route i `api/routes/intake.py`, före `GET /{source_id}`.
    Kroppen `{voucher_id, decision_id?}` med `extra="forbid"`. Anropar `IntakeLinkService.link`
    med `thread_id = None`, `agent_run_id = None` och aktören ur `get_current_actor`. `201` vid
    koppling, `200` med `replayed: true` vid uppspelning, felen enligt §7:s tabell. PUT, PATCH och
    DELETE på sökvägen ger `405`.
  - Verifiera: testfall 1, 4 och 13 över HTTP; varje felkod i §7:s tabell ger sin status (ett
    parametriserat test); `405`; `401` utan bearer; `422` för okänt fält i kroppen.
  - Filer: `api/routes/intake.py`, `tests/test_flode_underlag_http.py`
  - Obs: `_http_error` (`api/routes/intake.py:480`) mappar på undantagstyp. Mappa kopplingens
    fel på typ, inte på kodsträngar, och ändra inte mappningen för befintliga fel.

- [x] **FU7 — Stoppet i postningen (§8, D5)**
  - Gjort 2026-09-28: 10 tester i `tests/test_flode_underlag_stopp.py` (testfall 20–24, 23
    parametriserat över `amount_diff`/`exact_no_date`/ingen tolkning, trådförslagets postning
    kör inte stoppet, grep-vakt för var funktionen anropas, flera källor), 5 sedda röda först;
    testfall 23, 24 och trådförslagets postning var gröna redan och står kvar som vakter.
    `IntakeLinkService.ensure_not_matching_posted(source_ids)` (statisk) höjer
    `SourceMatchesPostedVoucherError(LinkConflictError)` med `details` enligt §8 ordagrant
    (`voucher=` är tolkningens `match.voucher_number`, `diff_ore=` dess `diff_ore`). Avvikelse 2:
    anropet ligger i `post_agent_voucher` direkt efter `ensure_source_ready_for_voucher_link`,
    och reservationen i anroparna släpps av deras `release`; testfall 20 och 21 visar att
    nyckeln (den härledda i verktyget, `Idempotency-Key` över HTTP) inte finns i
    `idempotency_keys` efteråt. I `DraftService._check_traceability` efter källkontrollen; inget
    utkast, inget inlägg. `_intake_http_error` fick koden i 409-mängden (den mappar på kod, som
    tidigare). `services/agent_tools.py` är orörd. Hela sviten 1406 gröna. mypy 61.
  - Beror på: FU4
  - Acceptans: `IntakeLinkService.ensure_not_matching_posted(source_ids)` (namnet valfritt): för
    varje källa, den senaste tolkningen; `match.kind = "exact"` och `match_still_open` nu ger
    `source_matches_posted_voucher` med `details` enligt §8. Anropas i `post_agent_voucher`
    (`services/voucher_posting.py`, bredvid `ensure_source_ready_for_voucher_link`) och i
    `DraftService._check_traceability` (`services/draft_service.py:1188`). `POST /agent/vouchers`
    svarar `409`. `POST /vouchers/{id}/post` kör inte kontrollen.
  - Verifiera: testfall 20 (ingen verifikation; idempotensnyckeln finns inte efteråt), 21, 22
    (inget utkast), 23, 24.
  - Filer: `services/intake_link.py`, `services/voucher_posting.py`, `services/draft_service.py`,
    `api/routes/agent.py`, `tests/test_flode_underlag_stopp.py`
  - Obs: avvikelse 2 — reservationen ligger i anroparna (`api/routes/agent.py:86`,
    `services/agent_tools.py` `_post_voucher`), inte i `voucher_posting`. Båda släpper nyckeln när
    anropet kastar; kontrollera det i testet i stället för att flytta reservationen.
    `_intake_http_error` (`api/routes/agent.py:293`) behöver koden i 409-mängden. Rör inte
    `services/agent_tools.py` här (FU5 äger den); går felet genom verktyget som `IntakeError`
    räcker det.

- [x] **FU8 — Jämförelseinlägget (§9.1, D6)**
  - Gjort 2026-09-28: 8 tester i `tests/test_flode_underlag_trad.py` (testfall 25 med
    `message.completed`, 26, 27 både utan tråd och över `POST …/interpretation`, 28, `expected`
    som är matchen ger ett inlägg, utan moms på ena sidan/utan hypotes, gemensam transaktion,
    radbyggaren ren), 6 sedda röda först; 26 och 27 var gröna redan och står kvar som vakter.
    Rent i `services/interpretation.py`: `comparison_rows(part)` (återanvänds av FU9),
    `comparison_body(part, *, vendor, document_date)` och `comparison_parts(match, expected)`
    (`expected` först, `exact` hoppas över, samma verifikation en gång). `title` är `Kvitto
    {leverantör} {datum} mot {nummer}` med de delar som finns. `InterpretationService.interpret`
    skriver raden och inläggen i en `db.transaction()` och publicerar `message.completed` efter
    commit (inlägget saknar `run_id`, så turens pågående meddelande lämnas orört; `DraftService.
    propose` publicerar inte sitt `draft`-inlägg, så formen är `on_posted`s). Inläggets `actor`
    är tolkningens. `repositories/interpretation_repo.py` behövde ingen ändring: `insert` hade
    redan `_commit`. `underlagstolkning` 33 grön oförändrad. Hela sviten 1414 gröna. mypy 61.
  - Beror på: FU1 (hjälparna)
  - Acceptans: en ren radbyggare (`comparison_body(interpretation_part, voucher_number) -> dict`,
    namnet valfritt) i `services/interpretation.py`: `title`, `labels ["kvitto", "{nummer}"]`,
    `rows` (belopp; moms bara när båda sidor har moms), `note` = hypotesen ordagrant eller
    utelämnad, `voucher_id`. `InterpretationService.interpret` skriver, när `thread_id` är satt och
    svaret har `match` eller `expected` med `kind != "exact"`, ett `receipt`-inlägg per
    verifikation (`expected` först) i samma transaktion som tolkningen, och publicerar
    `message.completed` för det.
  - Verifiera: testfall 25, 26, 27 (både utan tråd och över `POST …/interpretation`), 28;
    `underlagstolkning` 33 oförändrat grönt.
  - Filer: `services/interpretation.py`, `services/interpretation_service.py`,
    `repositories/interpretation_repo.py`, `tests/test_flode_underlag_trad.py`
  - Obs: `InterpretationRepository.insert` committar i dag själv; ge den `_commit=False` och lägg
    båda skrivningarna i en `db.transaction()`. Hur andra inlägg som skrivs mitt i en tur når
    strömmen: läs hur `DraftService.propose`s `draft`-inlägg gör (grep `EVENT_MESSAGE_COMPLETED`)
    och gör likadant. Verktygets beskrivning ändras inte (§9.1).

- [x] **FU9 — Kvittot och `view.changed` efter kopplingen (§9.3)**
  - Gjort 2026-09-28: 8 tester i `tests/test_flode_underlag_trad.py` (testfall 29 i två delar,
    30, 31 i två delar, 32, flaggspåret bara när verifikationen saknade underlag,
    `receipt_for_source` är en fråga med `json_extract`), 7 sedda röda först; 31:s "ingen
    `bocker.verifikationer`-tråd, inget skickas" var grönt redan och står kvar som vakt.
    Kvittot skrivs efter commit i `IntakeLinkService._after_commit`, som fångar och loggar
    varje fel. `rows` ur FU8:s `comparison_rows` för den del av tolkningen som gäller
    verifikationen (match, expected eller kandidat). Spåren: `{"tool": "koppla_underlag",
    "label": "underlag kopplat", "detail": nummer, "voucher_id"}`, `{"tool":
    "kompletteringsflagga", "label": "kompletteringsflagga borttagen"}` (samma verktygsnamn som
    postningskvittots flagga) och `{"tool": "saknar_underlag", "label": "{n} saknar underlag"}`.
    Inlägget har `run_id = null`. `view.changed` har `voucher_posted`s form: `{view_key,
    changed: {voucher_id, source_id, kind: "source_linked"}}`. Avvikelse 5: publiceras på den
    kopplande tråden och, när dess vy inte är `bocker.verifikationer`, på den vyns tråd för
    **verifikationens** räkenskapsår om den finns; utan tråd bara där, och bara för en ny
    koppling. En uppspelning i en tråd skriver kvittot om `receipt_for_source` inte hittar det,
    och publicerar då; annars ingenting. **Avvikelser:** vid uppspelning läses raderna ur den
    *senaste* tolkningen (repositoryt har ingen `get` per id, och U2:s test låser dess publika
    metoder) — samma tolkning om inte källan tolkats om efter kopplingen; flaggspåret vid
    uppspelning sätts när belägget är `exact_match` (som krävde att verifikationen saknade
    underlag). Hela sviten 1422 gröna. mypy 61.
  - Beror på: FU7, FU8
  - Acceptans: efter kopplingens commit, i en trådtur: ett `receipt`-inlägg med FU8:s rader ur
    samma tolkning, `title` `Underlag kopplat till {nummer}`, `source_id`; `traces` enligt §9.3
    (`underlag kopplat`, `kompletteringsflagga borttagen` när verifikationen saknade underlag före,
    `{n} saknar underlag`); `actor` `agent` vid `exact_match` och beslutets `answered_by` vid
    `decision`. `message.completed` och `view.changed` `{voucher_id, source_id, kind:
    "source_linked"}`. `ThreadRepository.receipt_for_source(thread_id, source_id)` med
    `json_extract`; en uppspelning skriver kvittot bara om det saknas. Fel i kvittot loggas och
    ändrar inte svaret. Utan tråd: inget kvitto, men `view.changed` enligt avvikelse 5.
  - Verifiera: testfall 29, 30, 31, 32.
  - Filer: `services/intake_link.py`, `repositories/thread_repo.py`,
    `tests/test_flode_underlag_trad.py`
  - Obs: avvikelse 5 — brokern är per `thread_id`. Publicera på den kopplande tråden och, när dess
    vy inte är `bocker.verifikationer`, på den vyns tråd för det aktuella räkenskapsåret om den
    finns (`ThreadRepository.find`). Testfall 31 kräver händelsen bara när en sådan tråd finns.

- [x] **FU10 — Hänvisningen i postningens transaktion (§5, D2, §9.2)**
  - Gjort 2026-09-28: 5 tester i `tests/test_flode_underlag_hanvisning.py` (backenddelen av 42,
    42b, förslag utan beslut, insättningen fallerar och postningen rullas tillbaka, vakt att
    `foresla_verifikation`s argument inte fått något fält), 2 sedda röda först; 42b och
    vakterna var gröna redan. `DraftService._record_source_reference` anropas i `on_posting`
    direkt efter `_link_traceability`, med `_commit=False`, och slår upp belägget med
    `IntakeLinkRepository.get_by_decision`. Vid fel svarar routen `500` (`_post_and_record`
    gör oväntade fel till 500) och ingenting står kvar: inget nummer, utkastet kvar, raden
    `pending`. `CHECK (voucher_id != via_voucher_id)` prövas i FU1. **Fynd, inte ändrat:**
    `POST /vouchers/{id}/post` bygger svaret av verifikationen som `post_voucher` returnerade,
    före `on_posting`, så `missing_attachment` i svaret är `true` fast A-121 har underlag
    genom hänvisningen (samma sak gäller redan ett förslag med `intake_source_ids`); en ny
    läsning ger `false`. `repositories/intake_link_repo.py` behövde ingen ändring. Hela sviten
    1427 gröna. mypy 61.
  - Beror på: FU2, FU7
  - Acceptans: `DraftService.on_posting` skriver, när det postade trådförslagets `decision_id` är
    ett `intake_link_basis.decision_id`, en rad i `voucher_source_references` (`voucher_id` =
    det postade, `intake_source_id` och `via_voucher_id` ur belägget, `decision_id`), med
    `_commit=False`, efter `_link_traceability`. `foresla_verifikation`s argument ändras inte.
  - Verifiera: backenddelen av testfall 42 (förslag med beslutets `decision_id` efter en koppling
    → postningen ger en rad, och verifikationen saknar inte underlag); 42b (beslut utan koppling
    bakom → ingen rad, postas som vanligt); insättningen får fallera och hela postningen rullas
    tillbaka (inget nummer förbrukat, utkastet kvar, raden `pending`).
  - Filer: `services/draft_service.py`, `repositories/intake_link_repo.py`,
    `tests/test_flode_underlag_hanvisning.py`
  - Obs: hänvisningen är serverns uppslag, inte agentens påstående (§9.2). Ett förslag vars
    beslut kopplade ett underlag till *samma* verifikation som postas kan inte uppstå
    (`CHECK (voucher_id != via_voucher_id)`), men testa att `CHECK`en avvisar det om det gör det.

- [x] **FU11 — Passet hoppar över trådens filer (D4, §11.3)**
  - Gjort 2026-09-28: 4 tester i `tests/test_flode_underlag_pass.py` (testfall 38 med två
    SQL-anrop räknade, `GET /intake/workspace` visar båda, `las_underlag` och `GET
    /agent/intake/pending` följer med, ett `user_text`-inlägg tar inte källan), 2 sedda röda
    först; de två vakterna var gröna redan. Villkoret är en modulkonstant
    `_NOT_IN_A_THREAD_SQL` i `repositories/intake_repo.py` (korrelerad `NOT EXISTS` med
    `json_extract`), i `list_pending` och `count_pending`; `list_by_status`/`count_by_status`
    orörda. `tests/test_intake_api.py` och `tests/test_bank_input_agent.py` gröna. Hela sviten
    1431 gröna. mypy 61.
  - Beror på: FU1 (hjälparna)
  - Acceptans: `IntakeRepository.list_pending` och `count_pending` får villkoret i §11.3, i en
    fråga. `list_by_status`/`count_by_status` (intagssidan) oförändrade.
  - Verifiera: testfall 38 (en källa med `user_file`-inlägg är inte med, en utan är det; SQL-anropen
    räknade); `GET /intake/workspace` visar fortfarande båda; `tests/test_intake_api.py` och
    `tests/test_bank_input_agent.py` gröna.
  - Filer: `repositories/intake_repo.py`, `tests/test_flode_underlag_pass.py`
  - Obs: avvikelse 3 — filtret når också `las_underlag`, `GET /agent/intake/pending` och
    `queue_depth`. Det är avsett (tråden äger filen); säg det i commit-meddelandet och pröva
    `las_underlag` i ett test.

- [x] **FU12 — `missing_attachment` och `age_days` i `las_verifikationer` (§11.1)**
  - Gjort 2026-09-28: 2 tester i `tests/test_flode_underlag_verktyg.py` (testfall 37: svaret
    har fälten med `Voucher`s värden, och sha256 av hela `las_verifikationer`-definitionen,
    tagen på `a326fdf`, är oförändrad), svarstestet sett rött först; hashvakten var grön före
    och efter. `_voucher_dict` fick de två fälten sist. Hela sviten 1433 gröna. mypy 61.
  - Beror på: FU5
  - Acceptans: `_voucher_dict` (`services/agent_tools.py:458`) får `missing_attachment` och
    `age_days` ur `Voucher`. Argumenten och beskrivningen av `las_verifikationer` orörda.
  - Verifiera: testfall 37 (schemat och beskrivningen byte för byte som på commiten före).
  - Filer: `services/agent_tools.py`, `tests/test_flode_underlag_verktyg.py`

- [x] **FU13 — Agentinstruktionen (§11.2)**
  - Gjort 2026-09-28: `tests/test_agent_entrypoint.py` fick `_assert_linking_rules` (testfall
    43: §11.2:s nio punkter och stopplistans rad), körd både mot `GET
    /agent-instructions/accounting` och mot `build_system_prompt()`; den är röd mot
    instruktionen på `fef32d8` (kontrollerat med HEAD-versionen av filen, eftersom texten
    skrevs före testet). "Tolka underlaget innan du bokför" är omskrivet i nio punkter, med
    hypotesregeln som ett stycke efter listan. **Omskrivna påståenden** i
    `_assert_interpretation_rules` (testfall 38, U9/U13/U15): avståendet vid `exact` är borta
    och ersatt av kopplingen; `amount_diff` kräver inte längre "med en `hypothesis`" (punkt 4
    gäller varje differens); "med båda beloppen" → "båda beloppen"; "Posta inte." → "Posta
    inte"; ordningsvakten mäter mot `**`match.kind = "exact"`` i stället för "2. **`match.kind".
    Avståendet i passet vid `amount_diff`, `exact_no_date` och `match = null` står kvar, med
    samma motiveringskrav. `02_bokforingsprocess.md`: en rad i "När agenten ska avstå" säger att
    ett sådant underlag kopplas i stället för att postas. Hela sviten 1433 gröna. mypy 61.
  - Beror på: FU5, FU7
  - Acceptans: `docs/to_agent/03_bokforingsinstruktion.md`: avsnittet "Tolka underlaget innan du
    bokför" skrivs om enligt §11.2 punkt 1–9; `SPEC-underlagstolkning.md` §9 punkt 2:s
    avstående vid exakt match ersätts av `koppla_underlag`. Stopplistan får en rad om att inte
    posta ett underlag som matchar exakt.
  - Verifiera: testfall 43 i `tests/test_agent_entrypoint.py` (instruktionen som `GET
    /agent-instructions/accounting` serverar den och som `build_system_prompt()` skickar den),
    utökat med §11.2:s nio punkter; hela filen grön.
  - Filer: `docs/to_agent/03_bokforingsinstruktion.md`, `docs/to_agent/02_bokforingsprocess.md`
    (bara om den motsäger), `tests/test_agent_entrypoint.py`
  - Obs: körtidsinnehåll (`AGENTS.md`). Befintliga påståenden i testfall 38 (U9, U13, U15) om
    avstående vid `exact` skrivs om, inte tas bort; nämn dem i commiten.

- [x] **FU14 — Meddelande utan text med bilagor (D8)**
  - Gjort 2026-09-28: 8 tester i `tests/test_flode_underlag_meddelande.py` (testfall 33 med tom
    text och med bara blanktecken, två bilagor, text och bilaga som förut, testfall 34 i fyra
    varianter), 4 sedda röda först; resten var gröna redan och står kvar som vakter.
    `ThreadMessageRequest.text` har standardvärdet `""` och en `model_validator` som ger `422`
    när text (efter `strip`) och `attachments` båda saknas; egenskapen `has_text`. `post_message`
    skriver `user_text` bara med text och startar annars turen på det första `user_file` med
    `(bifogade {n} filer)` (ordagrant, även för n = 1). Klientens `text: ""` med bilagor tas
    emot. **Beteendeändring:** text med bara blanktecken utan bilagor gav `201` förut och ger nu
    `422` (§14:s "text med bara blanktecken är tom"). `run_thread_session` klarar ett
    `user_file` som trigger: det används bara för idempotens- och förslagsnyckeln. `tradar`s
    tester gröna. Hela sviten 1441 gröna. mypy 61.
  - Beror på: FU1 (hjälparna)
  - Acceptans: `ThreadMessageRequest.text` (`api/schemas.py:531`) får vara tom när `attachments`
    inte är tom, annars `422` som i dag (en modellvalidator). `post_message`
    (`api/routes/threads.py:159`) skriver inget `user_text` utan text, bara `user_file`-inläggen,
    och startar turen på det första av dem med `(bifogade {n} filer)` som meddelande.
  - Verifiera: testfall 33, 34; `tradar`s tester för meddelanden gröna.
  - Filer: `api/schemas.py`, `api/routes/threads.py`, `tests/test_flode_underlag_meddelande.py`
  - Obs: text med bara blanktecken är tom. `ThreadTurnRunner.start(thread, posts[0], text)` tar
    inlägget turen hänger på; kontrollera att `run_thread_session` klarar ett `user_file` som
    trigger.

- [x] **FU15 — `existing_id` i `409 duplicate_intake_source` (§7)**
  - Gjort 2026-09-28: 2 tester i `tests/test_flode_underlag_http.py` (testfall 35: två
    uppladdningar av samma bytes, `detail.existing_id` är den förstas id, `details` oförändrad,
    nycklarna exakt `error`/`code`/`details`/`existing_id`; ett annat fel har inget
    `existing_id`), det första sett rött först. `_http_error` lägger `existing_id` i `detail`
    för `DuplicateIntakeSourceError`; servicen är orörd. Kontraktet är det frontendagenten
    byggde mot (`detail.existing_id`). `tests/test_intake_api.py` grön. Hela sviten 1443 gröna.
    mypy 61.
  - Beror på: FU6
  - Acceptans: `POST /intake` svarar vid dubblett med `existing_id` i felkroppen (`detail`),
    bredvid `error`, `code`, `details`. `details`-strängen oförändrad.
  - Verifiera: testfall 35; `tests/test_intake_api.py` grön.
  - Filer: `api/routes/intake.py`, `tests/test_flode_underlag_http.py`
  - Obs: `DuplicateIntakeSourceError` har redan attributet `existing_id`
    (`services/intake.py:29`); ingen ändring i servicen.

- [ ] **FU16 — `referenced_by` i `VoucherResponse`, och hänvisningen i `source-context`**
  - Beror på: FU2, FU14
  - Acceptans: `VOUCHER_SELECT_SQL` joinar `voucher_source_references` på `via_voucher_id =
    vouchers.id` och ger `referenced_by: {id, series, number} | null` (senast postade om flera),
    utan N+1, som `corrected_by`. `Voucher.referenced_by`, `VoucherResponse.referenced_by`,
    `_voucher_to_response`. `GET /vouchers/{id}/source-context` listar för en verifikation med
    hänvisning källan via `via_voucher_id` (med det numret), så att klienten kan öppna kvittot.
  - Verifiera: testfall 49e (ifyllt för A-118 efter A-121; SQL-anropen räknade per sida);
    backenddelen av 49d.
  - Filer: `repositories/voucher_repo.py`, `domain/models.py`, `api/schemas.py`,
    `api/routes/vouchers.py`, `tests/test_flode_underlag_predikat.py`
  - Obs: avvikelse 6 — `GET /vouchers/{id}` returnerar inga källor; det gör `source-context`
    (`api/routes/vouchers.py:316`). Ingen ny route.

- [ ] **FU17 — Sidantalet i `user_file` för pdf (§10.4)**
  - Beror på: FU14
  - Acceptans: `_attachment_posts` (`api/routes/threads.py:230`) fyller i `pages` för en pdf med
    sidantalet ur `pypdf`; `null` för bilder och för en pdf som inte går att läsa.
  - Verifiera: nytt test (inget nummer i §14): pdf med två sidor ger `2`, bild ger `null`, trasig
    pdf ger `null` och inget fel.
  - Filer: `api/routes/threads.py`, `services/agent_documents.py`,
    `tests/test_flode_underlag_meddelande.py`
  - Obs: avvikelse 4 — fältet heter `pages` och finns redan i kroppen och i klienten; inget
    `page_count`. Sidräkningen är en funktion i `services/agent_documents.py` (som redan importerar
    `PdfReader`); routen läser filen genom `IntakeService.resolve_source_file`.

- [ ] **FU18 — Skriptade flöden och backendens regression**
  - Beror på: FU5, FU9, FU10, FU11, FU13, FU14
  - Acceptans: testfall 39 och 40 med `agentruntime`s skriptade klient (`FakeLLMClient` ur
    `tests/test_agent_runtime.py`) genom `AgentWorker.run_pass_once`; 41 och 42 som skriptade
    trådturer genom `ThreadTurnRunner.run`, med svaret på beslutet genom `POST
    /decisions/{id}/answer`, och i 42 `Posta` genom `POST /vouchers/{id}/post`.
  - Verifiera: testfall 39–42; `pytest tests/ -v`, `black --check .`, `isort --check .`,
    `flake8`, `mypy .` (≤ 61 fel).
  - Filer: `tests/test_flode_underlag_pass.py`
  - Obs: testerna prövar FU1–FU17 och bör vara gröna direkt. Ett rött test här är ett fel i en
    tidigare uppgift; rätta det där, i en egen commit, och skriv det under den uppgiften.

## Klienten

- [x] **FU19 — Uppladdningen: `lib/chattyta/uppladdning.ts`**
  - Beror på: kontraktet i FU15 (`existing_id`). Kan byggas mot specens form efter FU1;
    verifieras mot backend när FU15 landat.
  - Acceptans: ren logik för ett filchip: `klar`/`laddar upp…`/`fel` och orsak; kontroll av typ
    och storlek före uppladdning mot en spegling av `IntakeService.ALLOWED_MIME_TYPES` och
    `MAX_FILE_SIZE` (`services/intake.py:64`, `:71`); `409 duplicate_intake_source` ger `klar`
    med `existing_id`. `laddaUppUnderlag(fil)` (`POST /api/v1/intake`, multipart) och
    `skickaMeddelande(viewKey, text, attachments)` i `lib/chattyta/api.ts`; befintliga anrop
    utan bilagor oförändrade.
  - Verifiera: testfall 46, 47 (logiken); `uppladdning.test.ts`.
  - Filer: `frontend-v3/lib/chattyta/uppladdning.ts`, `frontend-v3/lib/chattyta/api.ts`,
    `frontend-v3/lib/chattyta/__tests__/uppladdning.test.ts`
  - Obs: klienten läser inga filer och räknar inget (§10.3). Speglingen av typerna ska ha en
    kommentar som pekar på servern, som avgör ändå.
  - Gjort 2026-09-28: `uppladdning.test.ts` (46, 47, speglingen, `skickaMeddelande` med och utan
    bilagor). `409 duplicate_intake_source` utan `existing_id` blir ett felchip — id:t läses inte ur
    `details`. Inte verifierat mot backend: FU15 hade inte landat.

- [x] **FU20 — `ChattFalt`: `drop`-varianten (§10.1–§10.2)**
  - Beror på: FU19, FU14
  - Acceptans: knapp i fältet som öppnar filväljaren (på mobil `accept="image/*"
    capture="environment"`), dra och släpp på hela tråden, `paste` med fil. Ett chip per fil;
    fel står kvar tills det tas bort och följer inte med; `↵` avstängt medan ett chip laddar upp;
    `↵` skickar `text` och chipens id:n, även utan text. `onSkicka(text, attachments)` genom
    `useTrad().skicka`. Kommentaren i `ChattFalt.tsx` om att `drop` "hör till `flode-underlag`"
    tas bort.
  - Verifiera: testfall 45, 48, 49; ett meddelande utan text med ett chip skickas (D8);
    `ChattKolumn.test.tsx`, `mobil.test.tsx` och `useTrad.test.tsx` gröna.
  - Filer: `frontend-v3/components/skal/ChattFalt.tsx`,
    `frontend-v3/components/skal/ChattKolumn.tsx`, `frontend-v3/components/skal/ChattList.tsx`,
    `frontend-v3/hooks/useTrad.ts`
  - Obs: avvikelse 8 — `komponenter.md`s mått och copy för `drop` ligger i designpaketet, inte i
    repot. Finns det inte till hands: stanna och fråga. Inga förslagschips (`SPEC-skal.md` §2.1).
  - Gjort 2026-09-28: `components/skal/__tests__/drop.test.tsx` (45, 46, 48, 49, D8) och ett test
    i `useTrad.test.tsx`. Släppytan är kolumnen/chattlisten (`slappYta`); en inaktiv vy tar inte emot
    filer. Filväljarens `input` ligger utanför formuläret så att Enter sänder implicit. Chipens mått
    är `SparChip`s (komponenter.md ger inga för `drop` utöver fältet). `ChattKolumn.test.tsx`s "ingen
    knapp" blir "ingen knapp utom filväljarens". Inte verifierat mot backend: FU14 hade inte landat.

- [x] **FU21 — Sektionen `Saknar underlag`, `Nyss kopplad` och foten (§10.4)**
  - Beror på: FU20, FU9 (`source_linked`), FU16 (`referenced_by`)
  - Acceptans: `verifikationerVy` (`lib/skal/bocker.ts:376`) får sektionerna i ordningen Väntar på
    beslut, Saknar underlag, Postade, Utkast. `Saknar underlag` ur `GET
    /vouchers?missing_attachment=true&sort_by=age`, meta `{serie}-{nummer} · kvitto saknas sedan
    {n} dgr`, `saknar` med `ageDays`; borta när tom. `Postade` hämtas med
    `missing_attachment=false`; en verifikation på ett ställe. `Nyss kopplad` ur `view.changed`
    med `kind: "source_linked"`, `ny` i 6 s, meta `kvitto kopplat HH:MM` och `· {A-n} korrigering`
    ur `referenced_by`. Kopplad rad: `{datum} · kvitto kopplat`. Foten enligt §10.4.
    `Verifikation` får `referenced_by`.
  - Verifiera: testfall 49b, 49c, 51; `bocker.test.ts`, `optimistisk.test.tsx`, `vyskal.test.tsx`
    gröna.
  - Filer: `frontend-v3/lib/skal/bocker.ts`, `frontend-v3/hooks/useVyer.ts`,
    `frontend-v3/hooks/useTrad.ts`, `frontend-v3/lib/chattyta/kopplingar.ts` (ny, som
    `postningar.ts`)
  - Obs: avvikelse 7 — `useTrad` invaliderar redan `vouchers` och `overview` vid varje
    `view.changed`; testfall 51 blir en vakt. `Nyss kopplad` hålls utanför `VOUCHERS_NYCKEL`, som
    `postningar.ts`, så att invalideringen inte tar den. `{n}` är serverns `age_days`.
  - Gjort 2026-09-28: `lib/skal/__tests__/underlag.test.ts` (49b, 49c),
    `lib/chattyta/__tests__/kopplingar.test.ts`, `components/skal/__tests__/saknar.test.tsx` (genom
    `useVyer`) och testfall 51 i `useTrad.test.tsx`. `view.changed` bär det ändrade under `changed`
    (som `voucher_posted`); `lasKoppling` läser båda formerna. `VoucherResponse` säger inte att en
    verifikation har ett kopplat kvitto, så `Kopplad` (`{datum} · kvitto kopplat`) gäller bara
    kopplingar klienten sett i sessionen; posten står kvar med `ny: false` efter 6 s. Statusen säger
    `{n} saknar underlag` (serverns `total`) när inget väntar på beslut; perioden säger
    `kompletteringar först · postade nedan` när sektionen finns. Foten byts helt; `bocker.test.ts`s
    fottest och `optimistisk.test.tsx`s mock (svarar tomt på `missing_attachment=true`) uppdaterade.

- [x] **FU22 — `note` i `receipt` (D7) och `FilInlagg`s länk**
  - Beror på: kontraktet i FU8. Kan byggas efter FU1; verifieras mot backend när FU8 landat.
  - Acceptans: `receipt` får valfritt `note: string` i `typer.ts` och `parse.ts` (fel typ ger
    samma fallback som andra fel); `JamforelseRader` ritar den i mono 12 `#52525b` som
    `consequence`, och utan `note` som förut. `FilInlagg` får en länk som öppnar filen ur `GET
    /intake/{id}/file`.
  - Verifiera: testfall 50; `jamforelse.test.tsx`, `parse.test.ts`, `renderare.test.tsx` gröna.
  - Filer: `frontend-v3/lib/chattyta/typer.ts`, `frontend-v3/lib/chattyta/parse.ts`,
    `frontend-v3/components/chattyta/JamforelseRader.tsx`,
    `frontend-v3/components/chattyta/FilInlagg.tsx`
  - Obs: `GET /intake/{id}/file` kräver bearer; hämta som blob genom `apiClient` (som
    `api.getIntakeFile`, `frontend-v3/lib/api.ts:1016`), inte med en vanlig `href`. `note` är den
    enda ändringen i `chattyta`s kontrakt (§15).
  - Gjort 2026-09-28: `components/chattyta/__tests__/underlag.test.tsx` (testfall 50, parse av
    `note` inklusive fel typ och `null` → `okant_kontrakt`, länken). `oppnaUnderlag(sourceId)` bor i
    `FilInlagg.tsx` och återanvänds av FU23: fönstret öppnas i trycket, filen hämtas som blob genom
    `apiClient` och fönstret får blob-adressen; ett fel stänger fönstret och kortet säger
    `filen kunde inte öppnas`. `receipt.source_id` (§9.3) tas inte in i typen — kroppen släpps igenom.

- [x] **FU23 — Kvittot från verifikationen (§10.4, 49d)**
  - Beror på: FU21, FU16
  - Acceptans: en rad i `Postade` med kopplade källor eller en hänvisning får en länk som öppnar
    kvittot (för A-121 via A-118), ur `GET /vouchers/{id}/source-context`. Hämtas när länken
    används, inte per rad.
  - Verifiera: klientdelen av testfall 49d.
  - Filer: `frontend-v3/lib/skal/bocker.ts`, `frontend-v3/lib/skal/vydata.ts`,
    `frontend-v3/components/skal/VyRad.tsx`
  - Obs: avvikelse 6 — `/v4` har ingen raddetalj. Bygg det minsta som bär länken; en detaljpanel
    är ett "fråga först".
  - Gjort 2026-09-28: `components/skal/__tests__/kvitto.test.tsx` (klientdelen av 49d). `VyRadData`
    får `kvitto: {voucherId, nummer}` och `VyRad` en länk `kvitto` i metaraden; `VyInnehall.tsx` för
    vidare fältet (en rad, utanför listan). Klienten vet inte per rad om underlaget är ett kvitto, så
    länken står på postade rader som inte saknar underlag och inte är rättelser; vid tryck hämtas
    `source-context` och `kvittoKalla` väljer en direkt kopplad `voucher_source`, annars en med
    `via_voucher_id` (FU16:s form antagen), och bankfiler aldrig. Utan källa säger länken `inget
    kvitto`. `oppnaUnderlag` flyttade från `FilInlagg.tsx` till `lib/chattyta/api.ts` och tar också en
    uppslagsfunktion, så att fönstret öppnas i trycket före båda hämtningarna. Ingen detaljpanel.

## Stängning

- [ ] **FU24 — Regression och modulen stängd**
  - Beror på: alla
  - Acceptans: testfall 52. Specens status, `tasks/README.md` och `ANALYS.md` §8 markerar modulen
    klar. Framgångskriterierna i §16 gås igenom ett och ett under "Modulen är klar" nedan, med
    commit per kriterium. `D10`, ersättningen, står i kvarlistan (§12 D10).
  - Verifiera: `pytest tests/ -v`, `black --check .`, `isort --check .`, `flake8`, `mypy .` (≤ 61
    fel); `cd frontend-v3 && npm test && npm run lint && npx tsc --noEmit &&
    NEXT_PUBLIC_SKAL=1 npm run build`.
  - Filer: spec, `tasks/README.md`, `docs/redesign/ANALYS.md`, `tasks/flode-underlag/todo.md`
  - Obs: kriterium 7 med riktig LLM kontrolleras av beställaren tillsammans med
    `underlagstolkning`s kriterium 6; skriv det under "Kvar för beställaren" om det inte gjorts.

---

## Kvar för beställaren

- Kriterium 7 med riktig LLM: ett kvitto för en bankbokförd verifikation ger en koppling, inte en
  ny verifikation, i `/v4`. Kontrolleras tillsammans med `underlagstolkning`s kriterium 6.
- Modulen `underlag-ersatt` (D10). Till dess avviker `/v4` från panelens *"vägen tillbaka måste
  vara lika lätt som vägen fram"*.
