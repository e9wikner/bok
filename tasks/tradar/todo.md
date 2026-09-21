# Uppgifter: modul `tradar`

Spec: `docs/redesign/SPEC-tradar.md` · Plan: `tasks/tradar/plan.md`
Testerna skrivs **före** implementationen (§9). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §9.

---

- [ ] **T1 — Migration 025: `threads` och `thread_posts`**
  - Acceptans: båda tabellerna enligt §4, inklusive **`UNIQUE (view_key, fiscal_year_id)`** på
    `threads` (beslutet i §12.3, skrivet i schemat), `UNIQUE (thread_id, seq)` på inläggen, och
    `CHECK` på `type` med de åtta inläggstyperna. `run_id` är nullbar FK till `agent_runs`.
  - Verifiera: testfall 5. `python main.py --init-db` mot ny DB **och** mot en kopia av en
    befintlig. `sqlite3 bok.db ".schema threads"`.
  - Filer: `db/migrations/025_add_threads.sql`
  - Obs: ny fil. Redigera aldrig 001–024.

- [ ] **T2 — `ThreadRepository`**
  - Acceptans: hämta eller skapa tråd för `(view_key, fiscal_year_id)`, lägg inlägg med nästa
    `seq`, läs sida med `since`-markör, lista arkivets räkenskapsår för en `view_key`. All SQL
    här. Samma `@staticmethod`-form som `repositories/agent_run_repo.py`.
  - Verifiera: testfall 1, 2, 3.
  - Filer: `repositories/thread_repo.py`, `domain/models.py`, `tests/test_tradar.py`

- [ ] **T3 — `since_seq` på `list_events`**
  - Acceptans: `AgentRunRepository.list_events(run_id, since_seq=None)` ger bara händelser efter
    markören. Befintliga anropare är oförändrade.
  - Verifiera: testfall 6.
  - Filer: `repositories/agent_run_repo.py`, `tests/test_tradar.py`
  - Obs: liten och oberoende. Kan landa när som helst före T9.

- [ ] **T4 — Bryt ut verktygsloopen ur `run_session` (gate: ren refaktorering)**
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

- [ ] **T5 — Strömningshook på `LLMClient`**
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

- [ ] **T6 — Trådsessionen**
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

- [ ] **T7 — Runtimens händelser → inlägg**
  - Acceptans: `agent_run_events` renderas som `thread_posts` enligt typtabellen i §6.2. Ett
    `tool_call` blir ett `traces[]`-chip (`SparChip`), inte ett eget inlägg. Base64 når aldrig
    `body_json` eller `traces_json` — samma precedens som `_compact_tool_result`. Runtimen får
    fortfarande inte veta vad en tråd är: ingen `thread_id` ned i `services/agent_runtime.py`
    eller `services/agent_session.py`.
  - Verifiera: testfall 16, 17.
  - Filer: `services/thread_service.py`, `tests/test_tradar.py`

- [ ] **T8 — `GET /threads/{view_key}` och `POST /threads/{view_key}/messages`**
  - Acceptans: HTTP-lagret bara — parse, autentisera, mappa domänutfall till statuskoder.
    De sju `view_key` i §5 är en **sluten, validerad lista**; en okänd ger `404`, inte en tom
    tråd. `POST` skriver människans `user_text` (och ett `user_file` per bilaga) och svarar
    **innan** agenten har sagt något. Valfri `fiscal_year_id` på `GET` ger arkivet.
  - Verifiera: testfall 4, 18.
  - Filer: `api/routes/threads.py`, `api/schemas.py`, `api/main.py`, `tests/test_tradar.py`
  - Obs: `POST` är också **beslutskanalen**. README: *"Beslutskortets primärknapp är aldrig den
    enda vägen: samma beslut ska gå att uttrycka i text i chattfältet."*

- [ ] **T9 — `GET /threads/{view_key}/stream` (SSE)**
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

- [ ] **T10 — `view.changed`**
  - Acceptans: sänds när en postning faktiskt ändrade vyns rader, härlett ur
    `posta_verifikation`-utfallet. Aldrig ur ett intervall, aldrig som en periodisk "kanske har
    något hänt".
  - Verifiera: testfall 23 — och särskilt att den **inte** sänds efter ett svar utan postning.
  - Filer: `services/thread_stream.py`, `tests/test_tradar.py`

- [ ] **T11 — Modell per tråd**
  - Acceptans: `threads.model` skickas in i runtimen som argument; `agent_runs.model`/`.protocol`
    per kör gör ett byte mitt i tråden synligt i efterhand utan ny tabell. Protokollskillnaderna
    följer med upp och **visas**: en tråd på en Chat Completions-modell kan inte läsa PDF-underlag
    direkt och har ingen cache-ekonomi.
  - Verifiera: testfall 24, 25.
  - Filer: `services/thread_session.py`, `api/routes/threads.py`, `api/schemas.py`,
    `tests/test_tradar.py`

- [ ] **T12 — `GET /agent/status` får `state`, `since`, `current_task`, `paused_reason`**
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

- [ ] **T13 — Agentinstruktionerna**
  - Acceptans: `docs/to_agent/*.md` och `/agent-instructions/entrypoint` ändras **bara om**
    trådvägen faktiskt ändrar vad agenten gör. Gör den det, beskriver texten det som det blev.
  - Verifiera: `pytest tests/test_agent_entrypoint.py -v`. Assertionerna **skärps**, aldrig
    lättas.
  - Filer: `docs/to_agent/02_bokforingsprocess.md`, `api/routes/agent_instructions.py`,
    `tests/test_agent_entrypoint.py`
  - Obs: runtime-innehåll, inte dokumentation. Katalogen är bokstavligen agentens systemprompt —
    en redigering där ändrar vad agenten *gör*. **Fråga först.**

- [ ] **T14 — Regression och lint**
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
