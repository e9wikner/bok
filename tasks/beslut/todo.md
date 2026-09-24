# Uppgifter: modul `beslut`

Spec: `docs/redesign/SPEC-beslut.md` · Plan: `tasks/beslut/plan.md`
Testerna skrivs **före** implementationen (§9). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §9.

---

- [x] **B1 — Migration 026: `decisions` och `decision_options`**
  - Acceptans: båda tabellerna enligt §4. `UNIQUE (post_id)` på `decisions` — ett
    `decision`-inlägg bär exakt ett beslut. `CHECK` på `kind` (`abstention`, `approval`) och på
    `status` (`open`, `answered`, `superseded`), plus de två villkor som säger att ett besvarat
    beslut har både `answered_at` och ett faktiskt svar (`answer_option_id` eller `answer_text`).
    `UNIQUE (decision_id, position)` på alternativen. Belopp i **öre**, som resten av kodbasen.
    Index på `(status, created_at)` — listan är alltid äldst först inom en status.
  - Verifiera: testfall 1, 2, 3, 4. `python main.py --init-db` mot ny DB **och** mot en kopia av
    en befintlig. `sqlite3 bok.db ".schema decisions"`.
  - Filer: `db/migrations/026_add_decisions.sql`
  - Obs: ny fil. Redigera aldrig 001–025.

- [x] **B2 — `DecisionRepository` och domänmodeller**
  - Acceptans: skapa beslut med alternativ, hämta ett, lista på `status` och `view_key` med
    `limit`/`offset`, sätt svar, sätt `reminded_at`, räkna öppna. All SQL här. Samma
    `@staticmethod`-form som `repositories/thread_repo.py`.
  - Verifiera: testfall 5, 10.
  - Filer: `repositories/decision_repo.py`, `domain/models.py`, `tests/test_beslut.py`
  - Obs: `age_days` räknas i domänen eller servicen, inte i SQL — samma hållning som
    `Invoice.counts_as_overdue`, så regeln går att testa utan en databas.

- [x] **B3 — `DecisionService`: livscykeln**
  - Acceptans: `create()`, `answer()`, `count_open()`, `supersede()`. `answer()` skriver
    svarsinlägget och statusändringen i **en** transaktion (§6.2 steg 4–5) — delar de transaktion
    kan två tryck skriva två inlägg innan någon hinner sätta status. Ett andra svar möter en rad
    som inte är `open` och ger den befintliga svarsuppgiften tillbaka, aldrig ett andra inlägg.
    `supersede()` tar beslutet ur kön och lämnar inlägget i tråden.
  - Verifiera: testfall 15, 17, 18, 32.
  - Filer: `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: ingen `Idempotency-Key` här (§11.4) — `decisions.status` **är** den unika resursen.
    Postningen som turen eventuellt gör bär nyckeln som vanligt, ur `thread:{thread_id}:{post_id}`.

- [x] **B4 — Eskaleringsinvarianten och alternativens kontraktsregler (gate)**
  - Acceptans: en `options`-lista vars alternativ ändrar böckerna — `account` satt **och**
    `amount_ore ≠ 0` — och som inte ligger under ett öppet `decision`, avvisas. En lista under ett
    öppet beslut tillåts även när alternativen ändrar resultatet (flöde 1 steg 2). Dessutom de två
    reglerna ur `komponenter.md`: **högst ett** `recommended`, och **sista** alternativet har
    `is_exit`. Alla tre är serverregler, inte klientregler.
  - Verifiera: testfall 19, 20, 21, 22, 23. Tabellen i §11.1 är kontraktet — alla fyra rader ska
    ha ett test.
  - Filer: `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: **landas före B5.** Regeln före verktyget som kan bryta den; annars skrivs den första
    alternativlistan utan validering och invarianten blir en efterhandskonstruktion.

- [x] **B5 — Verktyget `be_om_beslut`**
  - Acceptans: `be_om_beslut(title, reason, consequence, amount_ore=None, source=None,
    options=[], kind="abstention")` skriver ett `decision`-inlägg, en `decisions`-rad och rader i
    `decision_options` — och ett `options`-inlägg när alternativ finns. Det postar ingenting,
    ändrar ingenting och läser ingenting utanför sin egen tabell. **Sist** i `_TOOL_SPECS`.
    `registrera_avstaende` står orört.
  - Verifiera: testfall 24, 25, **26**, 27.
  - Filer: `services/agent_tools.py`, `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: testfall 26 **är** testfall 17 i `agentruntime`, kört mot den utökade verktygsytan —
    append-only-regelns enda automatiska kontroll genom agentens yta. Ordningen i `_TOOL_SPECS`
    är en del av det cachade prefixet: lägg sist, aldrig i mitten.

- [x] **B6 — Avståendet i tråden blir ett spårat beslut**
  - Acceptans: ett `registrera_avstaende` i en trådtur ger, utöver dagens `decision`-inlägg, en
    rad i `decisions` bunden till inlägget. `_decision_body` flyttas inte och skriver inte om
    agentens text — den får en `decision_id` att bära.
  - Verifiera: testfall 34, och att inget `decision`-inlägg saknar rad i `decisions`.
  - Filer: `services/thread_service.py`, `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: utan den här uppgiften är ett avstående i tråden ett föräldralöst kort — synligt, men
    omöjligt att lista, åldra eller besvara.

- [x] **B7 — `GET /decisions` och `GET /decisions/{id}` (unionen)**
  - Acceptans: unionen av de tre källorna enligt §5 — `decisions`, `intake_sources` med
    `failed`/`needs_attention`, `correction_notes` med `pending`/`suggested`. `kind` skiljer dem
    åt, id:n är prefixade (`intake:`, `correction:`). **Äldst först.** `status` är `open`
    (förvalt), `answered` eller `all`. `view_key` valideras mot `ThreadViewKey`; okänd nyckel ger
    `404`. `age_days` med i svaret. `options` med i listsvaret, så vyn inte blir en
    vattenfallsladdning. `intake`-radens `reason` hämtas ur senaste
    `intake_processing_attempts.summary` / `error_detail` — agentens egen text, inte filnamnet.
  - Verifiera: testfall 6, 7, 8, 9, 10.
  - Filer: `api/routes/decisions.py`, `api/schemas.py`, `api/main.py`,
    `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: HTTP only i rutten, per AGENTS.md. Unionen bor i servicen.

- [x] **B8 — `POST /decisions/{id}/answer`**
  - Acceptans: kroppen är `{option_id}` **eller** `{free_text}` — båda, eller ingen, ger `400`.
    Okänt id `404`; syntetiskt id `409 decision_not_answerable` med pekare till den befintliga
    vägen; redan besvarat `409` med `answered_at`, `answer_post_id` och svaret som gavs.
    `option_id` valideras mot **det här** beslutets alternativ. Svarsinlägget skrivs innan turen
    startar. Turen startas med `ThreadTurnRunner.start(thread, trigger_post=svarsinlägget,
    message=svarstexten)` och väntas **inte** in. Svar `202`.
  - Verifiera: testfall 11, 12, 13, 14, 15, 16, 28, 29, 30.
  - Filer: `api/routes/decisions.py`, `api/schemas.py`, `services/decision_service.py`,
    `tests/test_beslut.py`
  - Obs: fritextvägen är inte en artighet — `README.md`, Tillgänglighet: *"Beslutskortets
    primärknapp är aldrig den enda vägen."* Testfall 12 ska vara lika komplett som 11.

- [x] **B9 — `open_decisions` byter uträkning**
  - Acceptans: `OverviewService._count_open_decisions()` blir `DecisionService().count_open()`.
    Docstringens *"Approximation until the `beslut` module owns this"* tas bort — den är inte
    längre sann. **Fältet ändras inte**, bara uträkningen bakom det.
  - Verifiera: testfall 33 — samma tal före och efter bytet. `tests/test_oversikt.py` ska vara
    grön utan en ändrad assertion.
  - Filer: `services/overview.py`, `tests/test_beslut.py`
  - Obs: behöver ingen assertion skrivas om i `test_oversikt.py` är bytet rätt gjort. Behöver en
    det, är antingen unionen eller uträkningen fel — ändra inte testet först.

- [x] **B10 — Påminnelsen vid sju dagar**
  - Acceptans: ett öppet beslut med `age_days >= 7` och `reminded_at IS NULL` ger ett
    `agent_text`-inlägg i sin tråd och sätter `reminded_at`. Kontrollen ligger i intagspassets
    befintliga cykel — ingen ny schemaläggare, ingen ny tråd.
  - Verifiera: testfall 31 — skrivs vid sju dagar och **inte** en andra gång.
  - Filer: `services/agent_runtime.py`, `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: `reminded_at` är skälet till att det blir en gång. Utan kolumnen påminner varje körning,
    vilket är exakt vad designens mening förbjuder.

- [x] **B11 — Agentinstruktionerna (runtime-innehåll — fråga först)**
  - Acceptans: `docs/to_agent/` beskriver att agenten kan lägga fram ett beslut med alternativ,
    och när den ska göra det i stället för att avstå tyst eller gissa. Befintliga assertioner i
    `tests/test_agent_entrypoint.py` **skärps, aldrig lättas** — texten radbryts om så att de
    fortsätter gälla.
  - Verifiera: `pytest tests/test_agent_entrypoint.py -v`.
  - Filer: `docs/to_agent/02_bokforingsprocess.md`, `tests/test_agent_entrypoint.py`
  - Obs: **fråga beställaren först.** Katalogen är runtime-innehåll, inte dokumentation:
    `repositories/system_instructions.py` läser och serverar den, och att ändra den ändrar vad
    systemet gör. Samma regel som T13 och A13.

- [x] **B12 — Regression och lint**
  - Acceptans: `pytest tests/ -v` grön. `black . && isort . && flake8` rena. Inga nya `mypy`-fel
    i modulens filer. Migrationen körd mot en kopia av en befintlig DB. De 13
    framgångskriterierna i §10 verifierade och avbockade här.
  - Verifiera: hela sviten, inte bara `tests/test_beslut.py`.
  - Filer: —
  - Obs: CI:s steg är alla `continue-on-error: true` (AGENTS.md) — en grön bock betyder inte att
    kontrollerna gick igenom. Läs jobbutskriften.

---

## Vad som faktiskt gjordes, och vad som avvek

Modulen är **klar 2026-09-22**. 967 tester gröna (794 före modulen, 173 nya).
`black`, `isort` och `flake8` rena över hela repot. `mypy .` ger **61 fel i 23 filer** — exakt
det pre-existerande antalet; noll i modulens egna filer. Migrationen körd både mot en ny databas
och mot en kopia som stannat på version 25, där enbart `026` tillämpades.

### Avvikelser från specen och planen

- **Beslutets id myntas i servicen, inte i repositoryt** (B3). `decisions.post_id` är en vanlig
  främmande nyckel, så inlägget måste finnas före raden, och ett inlägg skrivs aldrig om
  (`SPEC-tradar.md` §8.4) — id:t kan alltså inte fyllas i efteråt. Låter man raden mynta sitt
  eget id blir kortet i tråden oadresserbart utan ett andra anrop och en join på `post_id`,
  vilket är precis den vattenfallsladdning §6.1 avvisar när den lägger alternativen i listsvaret.
  `DecisionRepository.create` tar därför ett `decision_id`, och både `decision`- och
  `options`-inlägget bär det. B6 lämnar in samma id för det inlägg den redan skrivit.

- **Trådkontexten till verktyget reser i en ogenomskinlig mapping, inte som ett `thread`-argument**
  (B5). Första försöket namngav parametern `thread` hela vägen ner genom `run_tool_loop`, vilket
  fällde `tests/test_tradar.py::TestRuntimeKnowsNothingOfThreads` — ett AST-test som kräver att
  inget argument i runtimemodulerna ens *heter* något med "thread" i sig. Det testet har rätt:
  `SPEC-beslut.md` §7.6 säger "samma gräns som §8.1 drar för tråden", alltså att §8.1 står kvar.
  `run_tool_loop` tar nu ett `tool_context` som den vidarebefordrar oöppnat, precis som den redan
  bär ett `posting_idempotency_key` utan att veta vad en verifikations idempotensgaranti betyder.
  `services/agent_session.py` nämner inte längre en tråd över huvud taget, och §8.1-testet är
  grönt **utan en enda ändring**.

- **Fyra ärvda assertioner räknade nio verktyg** (B5) och säger nu tio, vilket §11.3 uttryckligen
  beslutar. Två av dem jämförde mot ett literal-tal och jämför nu mot den förväntade listan
  respektive mot `AGENT_TOOL_DEFINITIONS` själv — en hårdkodad siffra fångar inte det de finns
  för att fånga. En tredje kallade allt utom två verktyg skrivskyddat; `be_om_beslut` skriver
  (till `decisions`, `decision_options`, `thread_posts` — aldrig `vouchers`), och att påstå annat
  vore precis den lögn testet finns för att avslöja.

- **Två repositoryn fick varsin obegränsad flerstatusfråga** (B7): `IntakeRepository.
  list_by_statuses` / `list_latest_attempts` och `CorrectionNoteRepository.list_by_statuses`.
  Unionen behöver alla matchande rader ur varje källa innan den kan sorteras och skivas, och
  ingen av dem hade en sådan fråga. All SQL ligger kvar i repositoryn.

- **Testmodulens räknare för räkenskapsår var ett ändligt `range`** (B8) och tog slut när filen
  växte, med `StopIteration` inne i en orelaterad hjälpfunktion. Den är nu obegränsad.

- **B8:s tester skrevs av föräldern**, inte av deluppgiftens agent, som slog i sessionens
  hastighetsgräns efter implementationen men före testerna.

### De 13 framgångskriterierna i §10

1. De tre endpointsen svarar enligt `datakontrakt.md` §2 — ✅ (testfall 6–16).
2. Ett avstående går att lista, läsa och svara på med agentens formulering intakt — ✅ (B6,
   testfall 34).
3. Ett beslut besvaras en gång; andra svaret är `409` med det befintliga — ✅ (testfall 15).
4. Svarsinlägg och statusändring är atomära — ✅ (testfall 17, som rullar transaktionen mitt i).
5. Fritextsvar fungerar överallt där knappsvar fungerar — ✅ (testfall 12, lika många tester som
   testfall 11, inklusive ett beslut helt utan alternativ).
6. Eskaleringsinvarianten stämmer mot alla fyra fall designen ritar — ✅ (testfall 19–21, ett
   test per rad i §11.1-tabellen).
7. `AlternativLista`s två kontraktsregler valideras på servern — ✅ (testfall 22, 23).
8. `agentruntime`s testfall 17 passerar mot den utökade verktygsytan — ✅ (testfall 26, med
   radräkning i `vouchers` runt ett verktygsanrop).
9. `registrera_avstaende` och dokumentvägen oförändrade; hela sviten grön — ✅ (testfall 27).
10. `open_decisions` ger samma tal dag ett som approximationen gav dag noll — ✅ (testfall 33,
    mätt mot en kopia av den gamla uträkningen). `tests/test_oversikt.py` grön utan en ändrad
    assertion.
11. En postning i en tur startad av ett svar dubbelpostar inte — ✅ (testfall 28, 29).
12. Påminnelsen kommer en gång, inte varje körning — ✅ (testfall 31).
13. `pytest tests/ -v` grön; `black`, `isort`, `flake8` rena; inga nya `mypy`-fel — ✅.

Alla 34 testfall i §9 har minst ett test som namnger dem.

## Kvar att nämna för beställaren

- **Systemprompten växte med ~1 900 tecken** (B11), från 24 932 till 26 858. Den ligger före
  cache-brytpunkten, så den betalas en gång per cachefönster och inte per tur — men den är
  mätbart dyrare än före modulen.

- **Eskaleringsinvariantens avvisande gren nås inte genom `create()`**, eftersom `create()` alltid
  öppnar ett färskt beslut först. Regeln är alltså i dag en spärr för en anropare som ännu inte
  finns — flöde 4:s "koppla utan att ändra", som `chattyta` respektive `flode-verifikationer`
  bygger. Det är avsiktligt (planen lägger regeln före verktyget som kan bryta den), men det
  betyder att den inte är bevisad i drift, bara i test.

- **`superseded` sätts aldrig automatiskt.** Kolumnen, regeln och `supersede()` finns, men vilka
  händelser som utlöser den hör till `flode-verifikationer` (öppen fråga 2). Tills dess blir
  inget beslut `superseded` av sig självt.

- **`age_days`-trösklarna är fortfarande inte satta** (öppen fråga 1, ärvd från `oversikt`).
  Servern ger talet; vad som gör en rad gul eller röd är `chattyta`s beslut.

- **De två syntetiska källorna är läsbara men inte besvarbara**, och svarar `409` med en pekare
  till den befintliga vägen. Det är hela priset för §11.2 och kommer att synas i gränssnittet
  som ett kort utan primärknapp — `chattyta` behöver rita det läget.

Nästa modul i byggordningen är `chattyta`, som ritar `BeslutKort`, `AlternativLista`,
`AlternativRad` och `RekMarke` ovanpå den här modulens endpoints.
