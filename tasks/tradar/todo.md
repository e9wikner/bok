# Uppgifter: modul `tradar`

Spec: `docs/redesign/SPEC-tradar.md` · Plan: `tasks/tradar/plan.md`
Testerna skrivs **före** implementationen (§9). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §9.

---

- [x] **T1 — Migration 025: `threads` och `thread_posts`**
  - Acceptans: båda tabellerna enligt §4, inklusive **`UNIQUE (view_key, fiscal_year_id)`** på
    `threads` (beslutet i §12.3, skrivet i schemat), `UNIQUE (thread_id, seq)` på inläggen, och
    `CHECK` på `type` med de åtta inläggstyperna. `run_id` är nullbar FK till `agent_runs`.
  - Verifiera: testfall 5. `python main.py --init-db` mot ny DB **och** mot en kopia av en
    befintlig. `sqlite3 bok.db ".schema threads"`.
  - Filer: `db/migrations/025_add_threads.sql`
  - Obs: ny fil. Redigera aldrig 001–024.

- [x] **T2 — `ThreadRepository`**
  - Acceptans: hämta eller skapa tråd för `(view_key, fiscal_year_id)`, lägg inlägg med nästa
    `seq`, läs sida med `since`-markör, lista arkivets räkenskapsår för en `view_key`. All SQL
    här. Samma `@staticmethod`-form som `repositories/agent_run_repo.py`.
  - Verifiera: testfall 1, 2, 3.
  - Filer: `repositories/thread_repo.py`, `domain/models.py`, `tests/test_tradar.py`

- [x] **T3 — `since_seq` på `list_events`**
  - Acceptans: `AgentRunRepository.list_events(run_id, since_seq=None)` ger bara händelser efter
    markören. Befintliga anropare är oförändrade.
  - Verifiera: testfall 6.
  - Filer: `repositories/agent_run_repo.py`, `tests/test_tradar.py`
  - Obs: liten och oberoende. Kan landa när som helst före T9.

- [x] **T4 — Bryt ut verktygsloopen ur `run_session` (gate: ren refaktorering)**
  - Acceptans: `services/agent_session.py:383` blir en tunn omslagsfunktion kring en generisk
    loop som tar systemprompt, meddelanden, verktyg, tak och en **terminalpolicy**.
    Dokumentvägens policy är oförändrad byte för byte — särskilt `agent_no_outcome` på blankt
    `end`. Återanvänds som de är: `build_system_prompt`, `_tool_result_block`,
    `_tool_result_content_blocks`, `_assistant_message`, `_format_tool_error`, `_add_usage`,
    `SessionTurnRecord`, `SessionOutcome`. Tabellen i §11 är kontraktet.
  - Verifiera: testfall 7 och 8. Sedan **hela** `pytest tests/ -v` grön utan ny funktionalitet.
    Särskilt `test_agent_runtime.py`, `test_agent_accounting_workflow.py`.
  - Filer: `services/agent_session.py`, `tests/test_tradar.py`
  - Obs: landas ensam, som A1. Ändra ingenting i logiken — flytta den.

- [x] **T5 — Strömningshook på `LLMClient`**
  - Acceptans: valfria `on_text: Callable[[str], None]` och `on_tool_call: Callable[[str], None]`
    på `run_turn`. `services/llm/messages.py` plockar upp inkrementen den i dag kastar i
    `get_final_message()`. `services/llm/chat.py` får dem via `stream=True`; det adaptern inte
    kan säger `LLMCapabilities` nej till, som cache och dokumentblock redan gör. Samma hook ger
    `AgentWorker.current_activity` ett verktygsnamn i stället för dagens `"processing"`.
  - Verifiera: testfall 9, 10, 11. Adaptertester mot **inspelade råsvar**, inget nätverksanrop.
  - Filer: `services/llm/__init__.py`, `services/llm/messages.py`, `services/llm/chat.py`,
    `services/agent_runtime.py`, `tests/test_tradar.py`
  - Obs: `FakeLLMClient` i `tests/test_agent_runtime.py:1420` behöver anropa hookarna innan den
    returnerar sin turnyckel. Det är dubbelns enda nya ansvar.

- [x] **T6 — Trådsessionen**
  - Acceptans: andra ingången — ett meddelande i stället för ett underlag. Systemprompten är
    `build_system_prompt()` oförändrad (cachebrytpunkten får inte flyttas); användarturen är
    trådfönstret plus dagens datum, öppna perioder och meddelandet. Terminalpolicyn enligt §11:
    blankt `end` är ett **svar**. Fönstret är token-budgeterat och det som inte ryms
    **utelämnas — det sammanfattas aldrig** (§6.3). Verktygsytan är `AGENT_TOOL_DEFINITIONS`
    oförändrad. Idempotensnyckeln är `uuid5(BOK_NAMESPACE, f"thread:{thread_id}:{post_id}")`,
    hängd på användarinlägget och inte på tiden. Taken kontrolleras **mellan** verktygsvarv,
    aldrig inuti `with db.transaction():`.
  - Verifiera: testfall 12, 13, **14**, 15, 29, 30.
  - Filer: `services/thread_session.py`, `services/agent_tools.py`, `tests/test_tradar.py`
  - Obs: testfall 14 **är** testfall 17 i `agentruntime`, kört mot trådvägen — append-only-regelns
    enda automatiska kontroll genom agentens yta. Det ska gå sönder om någon lägger till ett
    bekvämt verktyg. `_TOOL_SPECS`-ordningen är en del av det cachade prefixet och rörs inte.

- [x] **T7 — Runtimens händelser → inlägg**
  - Acceptans: `agent_run_events` renderas som `thread_posts` enligt typtabellen i §6.2. Ett
    `tool_call` blir ett `traces[]`-chip (`SparChip`), inte ett eget inlägg. Base64 når aldrig
    `body_json` eller `traces_json` — samma precedens som `_compact_tool_result`. Runtimen får
    fortfarande inte veta vad en tråd är: ingen `thread_id` ned i `services/agent_runtime.py`
    eller `services/agent_session.py`.
  - Verifiera: testfall 16, 17.
  - Filer: `services/thread_service.py`, `tests/test_tradar.py`

- [x] **T8 — `GET /threads/{view_key}` och `POST /threads/{view_key}/messages`**
  - Acceptans: HTTP-lagret bara — parse, autentisera, mappa domänutfall till statuskoder.
    De sju `view_key` i §5 är en **sluten, validerad lista**; en okänd ger `404`, inte en tom
    tråd. `POST` skriver människans `user_text` (och ett `user_file` per bilaga) och svarar
    **innan** agenten har sagt något. Valfri `fiscal_year_id` på `GET` ger arkivet.
  - Verifiera: testfall 4, 18.
  - Filer: `api/routes/threads.py`, `api/schemas.py`, `api/main.py`, `tests/test_tradar.py`
  - Obs: `POST` är också **beslutskanalen**. README: *"Beslutskortets primärknapp är aldrig den
    enda vägen: samma beslut ska gå att uttrycka i text i chattfältet."*

- [x] **T9 — `GET /threads/{view_key}/stream` (SSE)**
  - Acceptans: `StreamingResponse` med `text/event-stream`, en `asyncio.Queue` per prenumerant,
    sessionen körd i en **arbetstråd** som skjuter in händelser med `loop.call_soon_threadsafe`.
    `message.created` → `message.delta`* → `message.completed`. `?since=<cursor>` ger en
    återansluten klient det den missade och sedan levande händelser. Inget nytt beroende — ingen
    `sse-starlette`.
    Två invarianter, i koden **och** i test: **en skrivare per `run_id`**, och **flocken vaktar
    intag-passet, inte varje LLM-anrop**.
  - Verifiera: testfall 19, 20, 21, 22.
  - Filer: `api/routes/threads.py`, `services/thread_stream.py`, `tests/test_tradar.py`
  - Obs: `db/database.py` är trådlokal med WAL. Kön får bara bära serialiserade händelser —
    aldrig en rad, en anslutning eller ett öppet resultat. `agent_runs.trigger` accepterar redan
    `'thread'` utan CHECK-villkor; ingen migration behövs där.

- [x] **T10 — `view.changed`**
  - Acceptans: sänds när en postning faktiskt ändrade vyns rader, härlett ur
    `posta_verifikation`-utfallet. Aldrig ur ett intervall, aldrig som en periodisk "kanske har
    något hänt".
  - Verifiera: testfall 23 — och särskilt att den **inte** sänds efter ett svar utan postning.
  - Filer: `services/thread_stream.py`, `tests/test_tradar.py`

- [x] **T11 — Modell per tråd**
  - Acceptans: `threads.model` skickas in i runtimen som argument; `agent_runs.model`/`.protocol`
    per kör gör ett byte mitt i tråden synligt i efterhand utan ny tabell. Protokollskillnaderna
    följer med upp och **visas**: en tråd på en Chat Completions-modell kan inte läsa PDF-underlag
    direkt och har ingen cache-ekonomi.
  - Verifiera: testfall 24, 25.
  - Filer: `services/thread_session.py`, `api/routes/threads.py`, `api/schemas.py`,
    `tests/test_tradar.py`

- [x] **T12 — `GET /agent/status` får `state`, `since`, `current_task`, `paused_reason`**
  - Acceptans: de fyra fälten enligt `datakontrakt.md` §7, med tre namngivna lägen (`arbetar`,
    `postar`, `pausad`). `paused_reason` ligger kvar så länge agenten är pausad, inte bara i
    felinlägget. Befintliga fält tas **inte** bort — endpointen har redan en konsument.
    Agentläget är **globalt**, inte per sida (§7). Nyckeln finns inte i svaret, varken hel eller
    maskerad.
  - Verifiera: testfall 26, 27, 28.
  - Filer: `api/routes/agent.py`, `api/schemas.py`, `services/agent_runtime.py`,
    `tests/test_tradar.py`
  - Obs: `current_task` blir möjlig först nu, tack vare T5:s hook. A10 lämnade
    `current_activity` grov av exakt det skälet.

- [x] **T13 — Agentinstruktionerna**
  - Acceptans: `docs/to_agent/*.md` och `/agent-instructions/entrypoint` ändras **bara om**
    trådvägen faktiskt ändrar vad agenten gör. Gör den det, beskriver texten det som det blev.
  - Verifiera: `pytest tests/test_agent_entrypoint.py -v`. Assertionerna **skärps**, aldrig
    lättas.
  - Filer: `docs/to_agent/02_bokforingsprocess.md`, `api/routes/agent_instructions.py`,
    `tests/test_agent_entrypoint.py`
  - Obs: runtime-innehåll, inte dokumentation. Katalogen är bokstavligen agentens systemprompt —
    en redigering där ändrar vad agenten *gör*. **Fråga först.**

- [x] **T14 — Regression och lint**
  - Acceptans: alla tretton framgångskriterier i §10 uppfyllda.
  - Verifiera: `pytest tests/ -v` och `black . && isort . && flake8 && mypy .`.
    `black`/`isort`/`flake8` ska vara **rena**; `mypy` har 61 pre-existerande fel i repot
    (`tasks/idempotens/todo.md`) — modulens egna filer lägger inte till ett enda. Läs
    jobboutputen i CI, bocken betyder inget (`continue-on-error: true`).
  - Filer: inga nya.

---

**Utanför scope:** `GET /decisions` och `POST /decisions/{id}/answer` (`beslut`), tröskeln för
beslutskort kontra val, all frontend, `underlagstolkning`, och de 61 mypy-felen.

**Fråga först** (§8): en nionde inläggstyp, ett tionde verktyg, en `thread_id` ned i runtimen,
varje ändring i `docs/to_agent/`, och en `view_key` utanför de sju.

**Öppna frågor** (§13), som inte blockerar T1–T5: trådfönstrets storlek, vad som händer med en
öppen tråd när räkenskapsåret stängs, och om `LLMTurn` ska bära `thinking`-block.

---

## Vad som faktiskt gjordes

Klart 2026-09-21, T1–T14. `pytest tests/ -v`: **794 gröna** (588 före modulen, 191 nya i
`tests/test_tradar.py`, 15 nya i adaptertesterna). `black`, `isort`, `flake8` rena. `mypy`
står kvar på exakt **61** pre-existerande fel — modulens filer lägger inte till ett enda.

### Avvikelser från specen och varför

- **T5 rörde sex filer, inte fem.** `tests/test_agent_runtime.py` fanns inte i fillistan, men
  T5:s egen Obs förutsåg det: dubbeln där måste ta emot hookarna för att fortfarande uppfylla
  `LLMClient` strukturellt (annars blir det ett `mypy`-fel), och den anropar `on_tool_call`
  eftersom `AgentWorker.current_activity` nu rapporterar verktygsnamnet genom den.

- **Adaptertesterna för strömning ligger i adapterfilerna, inte i `tests/test_tradar.py`.**
  Testfall 9 och 10 skrevs först i `test_tradar.py` och bröt då
  `TestOpenaiImportBoundary` — framgångskriterium 10 tillåter `openai` bara i
  `services/llm/chat.py` och dess egen testfil. Gränsen fick gälla; testerna flyttade till
  `test_llm_messages_adapter.py` respektive `test_llm_chat_adapter.py`, där de dessutom hör
  hemma. Kriteriet är alltså bevisat av att det *slog till*, inte bara av att det står kvar.

- **`LLMCapabilities` fick ett fält, `streaming`.** Testfall 10 kräver en adapter som inte
  strömmar; utan ett fält vore "kan inte strömma" omöjligt att uttrycka. Defaultar till
  `False`, så en adapter som inte lärt sig strömma säger nej genom utelämnande. Båda de två
  befintliga adaptrarna sätter `True` — de två testerna som pinnar hela
  capability-tupeln skärptes med det fältet.

- **`SessionOutcome.kind` fick ett fjärde värde, `"answered"`, och ett `text`-fält.** §11:s
  tabell kräver att ett blankt `end` betyder olika saker på de två vägarna. Dokumentvägen
  producerar aldrig `"answered"`.

- **`execute_tool` fick `idempotency_key`, men ingen tionde verktyg.** Nyckeln är hur
  *anroparen* namnger sin postningsavsikt; den finns inte i någon `input_schema` och kan inte
  begäras av en modell. `AGENT_TOOL_DEFINITIONS` är oförändrad byte för byte, inklusive
  `_TOOL_SPECS`-ordningen. Alla nio handlers tar emot den likformigt — bara
  `posta_verifikation` läser den — så dispatchern förblir en tabelluppslagning utan specialfall.

- **Den explicita nyckeln vinner över den härledda `intake:{source_id}`.** Risken det skapar
  (samma underlag postat en gång per väg under två olika nycklar) fångas inte av
  idempotensen utan av `intake_already_linked`, som körs före transaktionen. Det är pinnat av
  ett eget test, `TestThreadKeyDoesNotDefeatTheIntakeGuard`.

- **`POST /messages` startar bara en tur när `AGENT_RUNTIME_ENABLED=true`.** Agentläget är
  globalt (§7) och visas i headern; ett `error`-inlägg per meddelande skulle fylla tråden med
  rader om en inställning. Människans eget inlägg skrivs och står kvar oavsett.

- **Två strukturkontroller skrevs om från textsökning till AST.** Både
  "runtimen vet inte vad en tråd är" och "trådvägen tar inte flocken" slog först till på
  *prosa* — modulerna förklarar båda sakerna utförligt, och ska fortsätta göra det. Regeln
  gäller kod, så kontrollen läser nu parsad kod. Verifierat att den fortfarande smäller: en
  `thread_id`-parameter inlagd på försök i `agent_session.py` fällde testet.

- **`?since=0` var en bugg, hittad av ett test.** Rutten gjorde ett sanningstest på markören,
  så `since=0` — "från allra första början" — tolkades som "ingen markör". Rättad till
  `since is not None`.

- **SSE-testerna driver generatorn direkt.** Varken `TestClient` eller `httpx.ASGITransport`
  kan läsa ett oändligt svar: den förra levererar aldrig frånkopplingen som avslutar
  generatorn, den senare buffrar hela kroppen innan den returnerar. Ett försök med `TestClient`
  hängde tills det timade ut. Testerna itererar `StreamingResponse.body_iterator` — samma
  produktionsgenerator, utan en transport som inte kan representera den.

- **T13 ändrade `docs/to_agent/02_bokforingsprocess.md`, efter fråga.** Trådvägen ändrar en sak
  i vad agenten *gör*: ett rent svar är ett tredje giltigt utfall, och texten formulerade
  regeln binärt. Eftersom systemprompten delas byte för byte av båda vägarna (testfall 12)
  måste texten beskriva båda. Två nya assertioner i `tests/test_agent_entrypoint.py`; den
  befintliga assertionen om "posta när underlaget ... avstå annars" står kvar orörd (texten
  radbröts om så att den fortsatte gälla — assertionerna skärptes, aldrig lättades).

### Öppna frågor (§13) — läge

1. **Trådfönstrets storlek: besvarad.** 12 000 tokens, konfigurerbart via
   `AGENT_THREAD_WINDOW_TOKENS`. Formen var redan bestämd (token-budget, inte antal inlägg).
   Tokenuppskattningen är teckenbaserad och avsiktligt pessimistisk (3 tecken/token) — inget
   nytt beroende (§3), och en tokenizer för den ena leverantören vore ändå fel för den andra.
   Används bara för att klippa fönstret, aldrig för kostnad: `compute_cost_ore` prissätter
   leverantörens egen rapporterade `Usage`.
2. **Årsskiftet mitt i ett samtal: fortfarande öppen.** Inte blockerande. Tråden hittas per
   `(view_key, innevarande räkenskapsår)`, så nästa meddelande efter ett årsskifte börjar i en
   ny tråd — men det avslutande inlägget i den gamla, som specen föreslår, är inte byggt.
3. **`thinking`-block över flera turer: fortfarande öppen.** Ärvd begränsning från
   `agentruntime`; ändrar `LLMTurn`s form och är därför en fråga, inte ett beslut här.

### Kvar utanför modulen, som planerat

`GET /decisions` och `POST /decisions/{id}/answer` (`beslut`), tröskeln för beslutskort
kontra val, all frontend, `underlagstolkning`, och de 61 mypy-felen.
