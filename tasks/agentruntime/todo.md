# Uppgifter: modul `agentruntime`

Spec: `docs/redesign/SPEC-agentruntime.md` · Plan: `tasks/agentruntime/plan.md`
Testerna skrivs **före** implementationen (§9). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §9.

---

- [ ] **A1 — `services/voucher_posting.py` (gate: ren flytt, ingen ny funktionalitet)**
  - Acceptans: `_create_and_post_voucher` flyttad ur `api/routes/agent.py` med spårbarhetskontroll,
    `VoucherValidator`, transaktionen och idempotensskrivningen intakta. Rutten anropar servicen.
    Inga HTTP-begrepp följer med ned i `services/` — felen är domänutfall, mappningen stannar i rutten.
  - Verifiera: **hela** `pytest tests/ -v` grön utan ny funktionalitet. Särskilt
    `test_idempotency.py`, `test_agent_accounting_workflow.py`, `test_agent_entrypoint.py`.
  - Filer: `services/voucher_posting.py`, `api/routes/agent.py`
  - Obs: landas ensam, som T8. Ändra ingenting i logiken — flytta den.

- [ ] **A2 — Migration 024: `agent_runs` och `agent_run_events`**
  - Acceptans: båda tabellerna enligt §5, inklusive `protocol` på `agent_runs` och
    `UNIQUE (run_id, seq)` på händelserna. `cost_ore` är `NOT NULL DEFAULT 0` — det är sant eftersom
    en modell utan prisrad inte får köra (A4).
  - Verifiera: `python main.py --init-db` mot ny DB **och** mot en kopia av en befintlig.
    `sqlite3 bok.db ".schema agent_runs"`.
  - Filer: `db/migrations/024_add_agent_runs.sql`
  - Obs: ny fil. Redigera aldrig 001–023.

- [ ] **A3 — `AgentRunRepository`**
  - Acceptans: skapa kör, uppdatera status, summera tokens och kostnad, lägga händelse med
    nästa `seq`, hitta körningar med `status='running'` utan levande tråd. All SQL här.
  - Verifiera: `pytest tests/test_agent_runtime.py -v` — skapa, händelsesekvens, övergiven kör.
  - Filer: `repositories/agent_run_repo.py`, `tests/test_agent_runtime.py`

- [ ] **A4 — `services/llm/`: protokollet, modellregistret, prislistan, konfigurationen**
  - Acceptans: `LLMClient`, `LLMTurn`, `LLMCapabilities` enligt §4. Modellregistret svarar på
    modell → protokoll + pris. `config.py` får `AGENT_RUNTIME_ENABLED`, `LLM_API_KEY`,
    `LLM_BASE_URL` (standard `https://opencode.ai/zen/v1`), `LLM_DEFAULT_MODEL`, prislistan och
    de fyra taken i §6.5. **En modell utan prisrad är ett fel, inte ett standardvärde.**
  - Verifiera: testfall 19. Inget nätverksanrop i något test.
  - Filer: `services/llm/__init__.py`, `config.py`, `tests/test_agent_runtime.py`
  - Obs: nyckeln får aldrig loggas, aldrig hamna i status, aldrig i `agent_run_events` (§12.6).

- [ ] **A5 — Messages-adaptern**
  - Acceptans: `services/llm/messages.py` bygger Anthropic-anropet mot `LLM_BASE_URL`, normaliserar
    svaret till `LLMTurn` (`stop`: `tool_calls` | `end` | `refusal` | `max_tokens`), och rapporterar
    `capabilities` med cache, dokumentblock och egen vägrankod.
  - Verifiera: adaptertester mot **inspelade råsvar**, inte mot API:t. `usage` mappas rätt,
    inklusive `cache_read_input_tokens`.
  - Filer: `services/llm/messages.py`, `tests/test_agent_runtime.py`
  - Obs: `thinking={"type": "adaptive"}`, `output_config={"effort": "high"}`, **ingen**
    `budget_tokens` (den ger 400 på Opus 5). `.stream()` + `get_final_message()`.

- [ ] **A6 — Underlagsläsning: textlagret först**
  - Acceptans: ordningen i §6.3 — textlager via `pypdf` → annars `document`-block om adaptern kan →
    annars avstående. Bilder går som `image`-block på båda vägarna. Avstämningsregeln finns som
    egen, testbar funktion: beloppen ordagrant i texten, netto + moms = totalen.
  - Verifiera: testfall 20, 21, 22, 23.
  - Filer: `services/agent_documents.py`, `requirements.txt`, `tests/test_agent_runtime.py`
  - Obs: `pdf2image` (poppler i containern) och PyMuPDF (AGPL) tas **inte** in.

- [ ] **A7 — Verktygsytan**
  - Acceptans: de nio verktygen i §6.4 med typade argument. `posta_verifikation` går genom A1:s
    service med nyckeln `uuid5(BOK_NAMESPACE, f"intake:{source_id}")`. Inget bash-, SQL-,
    filsystems- eller generellt HTTP-verktyg.
  - Verifiera: testfall 1, 3, 6 och **17** — verktygslistan innehåller ingen väg att ändra eller
    radera en postad verifikation.
  - Filer: `services/agent_tools.py`, `tests/test_agent_runtime.py`
  - Obs: testfall 17 är append-only-regelns enda automatiska kontroll genom agentens yta. Det ska
    gå sönder om någon lägger till ett bekvämt verktyg.

- [ ] **A8 — Sessionen**
  - Acceptans: systemprompten enligt §6.3 (instruktionerna från
    `repositories/system_instructions.py`, bolagets egen instruktion, kontoplanen, senaste
    korrigeringarna — deterministiskt sorterade, **ingen tidsstämpel i prefixet**), användarturen
    efter cachebrytpunkten, manuell verktygsloop på `LLMTurn.stop == "tool_calls"`.
    Avståenden enligt §6.7: vägran, avhuggen tur och orättat verktygsfel blir aldrig postningar.
  - Verifiera: testfall 4, 5, 7, 14, 15.
  - Filer: `services/agent_session.py`, `tests/test_agent_runtime.py`
  - Obs: ett anrop per underlag, inte en session över hela passet.

- [ ] **A9 — Budget, kostnad och tak**
  - Acceptans: de fyra taken i §6.5 kontrollerade **mellan** underlag och verktygsvarv, aldrig
    inuti `with db.transaction():`. `cost_ore` ur `usage` och prislistan. Vid dygnstaket: stanna,
    aldrig nedgradera modell.
  - Verifiera: testfall 8.
  - Filer: `services/agent_session.py`, `services/agent_runtime.py`, `tests/test_agent_runtime.py`

- [ ] **A10 — Workern**
  - Acceptans: `AgentWorker`/`AgentRunner` enligt §6.1 — bakgrundstråd startad i `lifespan`,
    avstängd som standard, **`flock` på låsfil** (inte PID-fil, av skälet i `services/dropzone.py`),
    `stop()` med `Event` och join. Passet startas manuellt (§12.3); `trigger='manual'`.
    Övergivna körningar markeras `abandoned` vid nästa start.
  - Verifiera: testfall 9, 10, 11, 12, 13, 16, 24.
  - Filer: `services/agent_runtime.py`, `api/main.py`, `tests/test_agent_runtime.py`
  - Obs: en tom kö ska inte skriva en `agent_runs`-rad och inte göra ett API-anrop.

- [ ] **A11 — `GET /api/v1/agent/status`**
  - Acceptans: svaret i §8, med `model` och `protocol` på pågående kör.
    `GET /agent/operations/log`-stubben tas bort. Nyckeln finns inte i svaret, varken hel eller
    maskerad.
  - Verifiera: `pytest tests/test_agent_runtime.py -v` plus att ingen befintlig konsument läser
    `operations/log` (samma kontroll som §12.3 i `idempotens`).
  - Filer: `api/routes/agent.py`, `api/schemas.py`, `tests/test_agent_runtime.py`

- [ ] **A12 — Chat Completions-adaptern**
  - Acceptans: `services/llm/chat.py` mot samma `LLMClient`. `finish_reason == "tool_calls"`,
    JSON-strängargument parsas med `json.loads` — aldrig strängmatchning. `capabilities` säger
    nej till cache, dokumentblock och egen vägrankod.
  - Verifiera: testfall 18, 22, 23 — samma pass ger samma postning, och det adaptern saknar blir
    ett avstående, aldrig en gissning.
  - Filer: `services/llm/chat.py`, `tests/test_agent_runtime.py`

- [ ] **A13 — Agentinstruktionerna**
  - Acceptans: `docs/to_agent/*.md` och `/agent-instructions/entrypoint` beskriver runtimen som den
    faktiskt blev — att bok kör passet själv, att `operations/log` är ersatt av `status`, och att
    avstående är utfallet när underlaget inte går att belägga.
  - Verifiera: `pytest tests/test_agent_entrypoint.py -v`. Assertionerna **skärps**, aldrig lättas.
  - Filer: `docs/to_agent/02_bokforingsprocess.md`, `api/routes/agent_instructions.py`,
    `tests/test_agent_entrypoint.py`
  - Obs: runtime-innehåll, inte dokumentation. Katalogen blir nu bokstavligen agentens systemprompt
    (§6.3) — en redigering där ändrar vad agenten *gör*.

- [ ] **A14 — Regression och lint**
  - Acceptans: alla tretton framgångskriterier i §11 uppfyllda.
  - Verifiera: `pytest tests/ -v` och `black . && isort . && flake8 && mypy .`.
    `black`/`isort`/`flake8` ska vara **rena**; `mypy` har 61 pre-existerande fel i repot
    (`tasks/idempotens/todo.md`) — modulens egna filer lägger inte till ett enda. Läs jobboutputen
    i CI, bocken betyder inget (`continue-on-error: true`).
  - Filer: inga nya.

---

**Utanför scope:** schemaläggning (§12.3), Gemini-protokollet, trådar och SSE (`tradar`),
modellväljaren i gränssnittet (`tradar`), och de 61 mypy-felen (eget spår).

**Fråga först** (§10): en tredje adapter, ett protokoll till, ändrat beteende vid dygnstaket, och
varje ändring i `docs/to_agent/`.
