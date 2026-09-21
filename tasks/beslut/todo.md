# Uppgifter: modul `beslut`

Spec: `docs/redesign/SPEC-beslut.md` · Plan: `tasks/beslut/plan.md`
Testerna skrivs **före** implementationen (§9). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §9.

---

- [ ] **B1 — Migration 026: `decisions` och `decision_options`**
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

- [ ] **B2 — `DecisionRepository` och domänmodeller**
  - Acceptans: skapa beslut med alternativ, hämta ett, lista på `status` och `view_key` med
    `limit`/`offset`, sätt svar, sätt `reminded_at`, räkna öppna. All SQL här. Samma
    `@staticmethod`-form som `repositories/thread_repo.py`.
  - Verifiera: testfall 5, 10.
  - Filer: `repositories/decision_repo.py`, `domain/models.py`, `tests/test_beslut.py`
  - Obs: `age_days` räknas i domänen eller servicen, inte i SQL — samma hållning som
    `Invoice.counts_as_overdue`, så regeln går att testa utan en databas.

- [ ] **B3 — `DecisionService`: livscykeln**
  - Acceptans: `create()`, `answer()`, `count_open()`, `supersede()`. `answer()` skriver
    svarsinlägget och statusändringen i **en** transaktion (§6.2 steg 4–5) — delar de transaktion
    kan två tryck skriva två inlägg innan någon hinner sätta status. Ett andra svar möter en rad
    som inte är `open` och ger den befintliga svarsuppgiften tillbaka, aldrig ett andra inlägg.
    `supersede()` tar beslutet ur kön och lämnar inlägget i tråden.
  - Verifiera: testfall 15, 17, 18, 32.
  - Filer: `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: ingen `Idempotency-Key` här (§11.4) — `decisions.status` **är** den unika resursen.
    Postningen som turen eventuellt gör bär nyckeln som vanligt, ur `thread:{thread_id}:{post_id}`.

- [ ] **B4 — Eskaleringsinvarianten och alternativens kontraktsregler (gate)**
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

- [ ] **B5 — Verktyget `be_om_beslut`**
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

- [ ] **B6 — Avståendet i tråden blir ett spårat beslut**
  - Acceptans: ett `registrera_avstaende` i en trådtur ger, utöver dagens `decision`-inlägg, en
    rad i `decisions` bunden till inlägget. `_decision_body` flyttas inte och skriver inte om
    agentens text — den får en `decision_id` att bära.
  - Verifiera: testfall 34, och att inget `decision`-inlägg saknar rad i `decisions`.
  - Filer: `services/thread_service.py`, `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: utan den här uppgiften är ett avstående i tråden ett föräldralöst kort — synligt, men
    omöjligt att lista, åldra eller besvara.

- [ ] **B7 — `GET /decisions` och `GET /decisions/{id}` (unionen)**
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

- [ ] **B8 — `POST /decisions/{id}/answer`**
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

- [ ] **B9 — `open_decisions` byter uträkning**
  - Acceptans: `OverviewService._count_open_decisions()` blir `DecisionService().count_open()`.
    Docstringens *"Approximation until the `beslut` module owns this"* tas bort — den är inte
    längre sann. **Fältet ändras inte**, bara uträkningen bakom det.
  - Verifiera: testfall 33 — samma tal före och efter bytet. `tests/test_oversikt.py` ska vara
    grön utan en ändrad assertion.
  - Filer: `services/overview.py`, `tests/test_beslut.py`
  - Obs: behöver ingen assertion skrivas om i `test_oversikt.py` är bytet rätt gjort. Behöver en
    det, är antingen unionen eller uträkningen fel — ändra inte testet först.

- [ ] **B10 — Påminnelsen vid sju dagar**
  - Acceptans: ett öppet beslut med `age_days >= 7` och `reminded_at IS NULL` ger ett
    `agent_text`-inlägg i sin tråd och sätter `reminded_at`. Kontrollen ligger i intagspassets
    befintliga cykel — ingen ny schemaläggare, ingen ny tråd.
  - Verifiera: testfall 31 — skrivs vid sju dagar och **inte** en andra gång.
  - Filer: `services/agent_runtime.py`, `services/decision_service.py`, `tests/test_beslut.py`
  - Obs: `reminded_at` är skälet till att det blir en gång. Utan kolumnen påminner varje körning,
    vilket är exakt vad designens mening förbjuder.

- [ ] **B11 — Agentinstruktionerna (runtime-innehåll — fråga först)**
  - Acceptans: `docs/to_agent/` beskriver att agenten kan lägga fram ett beslut med alternativ,
    och när den ska göra det i stället för att avstå tyst eller gissa. Befintliga assertioner i
    `tests/test_agent_entrypoint.py` **skärps, aldrig lättas** — texten radbryts om så att de
    fortsätter gälla.
  - Verifiera: `pytest tests/test_agent_entrypoint.py -v`.
  - Filer: `docs/to_agent/02_bokforingsprocess.md`, `tests/test_agent_entrypoint.py`
  - Obs: **fråga beställaren först.** Katalogen är runtime-innehåll, inte dokumentation:
    `repositories/system_instructions.py` läser och serverar den, och att ändra den ändrar vad
    systemet gör. Samma regel som T13 och A13.

- [ ] **B12 — Regression och lint**
  - Acceptans: `pytest tests/ -v` grön. `black . && isort . && flake8` rena. Inga nya `mypy`-fel
    i modulens filer. Migrationen körd mot en kopia av en befintlig DB. De 13
    framgångskriterierna i §10 verifierade och avbockade här.
  - Verifiera: hela sviten, inte bara `tests/test_beslut.py`.
  - Filer: —
  - Obs: CI:s steg är alla `continue-on-error: true` (AGENTS.md) — en grön bock betyder inte att
    kontrollerna gick igenom. Läs jobbutskriften.
