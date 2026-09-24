# Spec: `tradar`

Modul-id `tradar` i kapabilitetskartan (`ANALYS.md` §8). Beror på `agentruntime`, som är klar
(A1–A14, `71b512b`). `beslut`, `chattyta` och `flode-verifikationer` beror på den här.

Status: **Fas 1 — skriven 2026-09-21.** Tre beslut tagna i förväg (§12.1–§12.3): full SSE,
`view_key` utan bolag, en tråd per räkenskapsår. Uppgifterna ligger i `tasks/tradar/plan.md` och
`tasks/tradar/todo.md` (T1–T14). Ingen kod skriven ännu.

---

## Antaganden

1. **Sessionsmotorn finns redan.** `SPEC-agentruntime.md` §13 är skriven som en överlämning hit:
   *"`tradar` lägger till lagring per `view_key`, en andra ingång till sessionen (ett meddelande i
   stället för ett underlag), och SSE ovanpå `agent_run_events` — som är därför de raderna har ett
   `seq`."* Den bedömningen håller, med tre reservationer som §2 räknar upp.
2. **Gränsen från `agentruntime` §1 gäller oförändrad:** *runtimen producerar händelser och utfall;
   `tradar` bestämmer hur de visas.* Runtimen får aldrig veta vad en tråd är.
3. **Enbolag.** `view_key` bär vyn och ingenting annat (§12.2).
4. **Append-only är oförhandlingsbart också här.** En agent som postar från ett chattsvar går
   samma väg som en agent som postar från ett underlag: `services/voucher_posting.py`, med
   `Idempotency-Key`. Verktygsytan utökas inte.
5. **Tråden är inte revisionsspåret.** `audit_log` är revisionsspåret. `thread_posts` är vad
   människan såg, i den ordning hon såg det. `ANALYS.md` §7: agentens text lagras som *tråd*,
   aldrig som en verifikations `description` utan mänskligt beslut.

→ Punkt 4 och 5 är de som kostar om de glöms.

---

## 1. Objektiv

### Problemet, konkret

`datakontrakt.md` §1: *"Hela designen står på den. I dag finns ingen konversation någonstans i
API:t."* Och `README.md`: *"**Chatten hör till vyn**, inte till appen. Varje vy har sin egen tråd
med sin egen historik. Byter man vy byter man tråd."*

Det som finns efter `agentruntime`: en worker som tar ett underlag ur kön, kör en LLM-session med
nio verktyg, postar eller avstår, och skriver `agent_run_events`. Det som saknas är att en
människa kan **skriva till den** och **se den tänka**.

### Vad vi bygger

```
GET  /api/v1/threads/{view_key}?since=<cursor>   → inlägg i ordning, äldst först
POST /api/v1/threads/{view_key}/messages         → { text, attachments[] }
GET  /api/v1/threads/{view_key}/stream           → SSE
```

plus lagringen under dem, den andra ingången till sessionen, och strömningshooken som gör
`message.delta` och `SkriverIndikator` möjliga.

### Vad vi inte bygger här

`GET /decisions` och `POST /decisions/{id}/answer` (modulen `beslut`) — tråden *bär* ett
`decision`-inlägg, men listan över öppna beslut och svarsvägen via knapp hör till nästa modul.
Ingen frontend. Ingen tolkning av underlag (`underlagstolkning`). Tröskeln för beslutskort
kontra val (designens öppna fråga 3) hör till `beslut`.

### Framgång

1. En människa skriver i `bocker.verifikationer` och får ett svar som strömmar in tecken för
   tecken.
2. Agentens svar kan innehålla en postning, och den postningen dubbelpostar inte vid omtryck.
3. En postning från tråden får vyns siffror att uppdateras utan att klienten pollar.
4. Ingen väg genom tråden kan ändra eller radera en postad verifikation.
5. Ett byte av modell mitt i en tråd är synligt i efterhand.

---

## 2. Vad `agentruntime` faktiskt lämnade efter sig

§13 sa att `tradar` skulle bli "ett mycket mindre problem än det ser ut". Det stämmer för
sessionsmotorn, verktygsloopen, felhanteringen och kostnadskontrollen. Tre saker är däremot inte
på plats, och de är de som gör modulen till mer än lagring:

**1. Inget streamar någonstans.** `grep -rn "StreamingResponse|text/event-stream|EventSource|
asyncio.Queue"` över `*.py`, `*.ts`, `*.tsx` (utan `venv/` och `node_modules/`) ger **noll
träffar**. `requirements.txt` har ingen `sse-starlette`. Den enda "stream" som finns i förstaparts
kod är `services/llm/messages.py`:

```python
with self._client.messages.stream(**kwargs) as stream:
    final_message = stream.get_final_message()
```

Adaptern *strömmar redan* — och kastar varje inkrement. `LLMClient.run_turn` är synkron och
returnerar en färdig `LLMTurn`. Det finns ingen `Callable`-parameter någonstans i
`services/llm/*.py` eller `services/agent_session.py`. `message.delta` kräver alltså en ny hook,
inte en ny endpoint ovanpå något som redan finns.

**2. `run_session` är dokumentformad.** `services/agent_session.py:383` kräver
`source: IntakeSource` och `file_bytes`, bygger användarturen ur underlagets metadata, och:

```python
if turn.stop == "end":
    return SessionOutcome(kind="abstained", reason="agent_no_outcome", ...)
```

Ett blankt `end` — vilket är precis vad ett vanligt samtalssvar *är* — behandlas som ett
misslyckande att bestämma sig. Det är rätt för ett underlag och fel för ett meddelande. Den andra
ingången är en refaktorering av loopen, inte en parameter.

**3. Händelserna skrivs i en klump.** `AgentWorker._write_events` körs en gång per avslutad
session och skriver alla rader då. En SSE byggd på att polla `agent_run_events` skulle leverera
hela svaret i en enda skur när det redan är klart. Dessutom saknar
`AgentRunRepository.list_events` en markör — det finns inget `since_seq`.

Det som däremot står redo, och ska användas som det är:

- `agent_runs.trigger` listar redan `'thread'` som lagligt värde och har **inget CHECK-villkor**
  på kolumnen. Ingen migration behövs för att köra en trådkörning.
- `agent_runs.model` och `.protocol` per kör ger "modell per konversation" och ett synligt
  modellbyte mitt i tråden utan en ny tabell (§13).
- `agent_run_events` med `seq` och `UNIQUE (run_id, seq)` är den markörform SSE ska följa.
  `domain/models.py:365` säger det rakt ut: raderna finns *"so `tradar` can later render the same
  events as thread posts"*.
- `build_system_prompt()` är deterministisk, tidsstämpelfri och cachebar — återanvänds ordagrant.
- `AGENT_TOOL_DEFINITIONS` + `execute_tool` ger samma typade verktygsyta till en chattur.
- `compute_cost_ore` och `ensure_daily_budget_available` är rena och globala, så trådturer räknas
  automatiskt mot samma dygnstak på 50 kr.
- `services/voucher_posting.py` är fortfarande enda skrivvägen till huvudboken.

---

## 3. Tech stack

Inget nytt beroende. SSE görs med FastAPI:s egen `StreamingResponse` och `text/event-stream`, inte
med `sse-starlette` — modulen behöver en generator och en kö, inte ett bibliotek.

Trådning: `db/database.py` delar ut **trådlokala** SQLite-anslutningar med WAL. Det betyder att en
session måste köra i sin egen arbetstråd med sin egen anslutning, och att kön mellan arbetstråden
och SSE-generatorn bara får bära serialiserade händelser — aldrig en rad, en anslutning eller ett
öppet resultat. Bryggan är `loop.call_soon_threadsafe` in i en `asyncio.Queue` per prenumerant.

---

## 4. Datamodell

Migration `025_add_threads.sql`. Ny fil; `001`–`024` redigeras aldrig.

```sql
CREATE TABLE IF NOT EXISTS threads (
    id              TEXT PRIMARY KEY,
    view_key        TEXT NOT NULL,
    fiscal_year_id  TEXT NOT NULL,
    model           TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id),
    UNIQUE (view_key, fiscal_year_id)
);

CREATE TABLE IF NOT EXISTS thread_posts (
    id           TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    type         TEXT NOT NULL,
    actor        TEXT NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    body_json    TEXT NOT NULL,
    traces_json  TEXT,
    run_id       TEXT,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES agent_runs(id),
    UNIQUE (thread_id, seq),
    CHECK (type IN ('agent_text','user_text','user_file','decision',
                    'options','draft','error','receipt'))
);

CREATE INDEX IF NOT EXISTS idx_thread_posts_thread_seq ON thread_posts(thread_id, seq);
```

**`UNIQUE (view_key, fiscal_year_id)`** är beslutet i §12.3 skrivet i schemat: en tråd per vy och
räkenskapsår, inte en evig tråd per vy.

**`CHECK` på `type`** finns därför att inläggstyperna är ett kontrakt mot klienten
(`datakontrakt.md` §1 räknar upp de åtta), och en nionde typ som smyger in är en renderare som
tyst faller igenom.

`body_json` bär typens nyttolast — texten för `agent_text`, filkortet för `user_file`, utkastets
rader och `draft_id` för `draft`, orsak och konsekvens för `error`. Formen per typ står i §6.2.
`traces_json` är `SparChip`-raden. `run_id` binder ett agentinlägg till körningen som skapade det,
så att modellbytet i §12.4 går att se i efterhand.

### Inget `thread_posts`-inlägg ändras

Samma hållning som huvudboken, av en annan anledning: tråden är vad människan såg. Ett strömmande
`agent_text` skrivs **en gång, när turen är klar**; deltana under vägen går bara över SSE och
lagras inte per tecken. Klienten ritar dem och ersätter dem med det slutgiltiga inlägget vid
`message.completed`, precis som designens regel om optimistiska rader (regel 4 i datakontraktet).

---

## 5. `view_key`

Sju stabila nycklar, en per vy:

| `view_key` | Sida · vy |
|---|---|
| `bocker.balans` | Böcker · Balansräkning |
| `bocker.resultat` | Böcker · Resultaträkning |
| `bocker.verifikationer` | Böcker · Verifikationer |
| `betala.fakturering` | Fakturering och löner · Fakturering |
| `betala.loner` | Fakturering och löner · Löner |
| `bokslut.rapporter` | Bokslut · Rapporter |
| `bokslut.atgarder` | Bokslut · Åtgärder och nyckeltal |

Listan är sluten och validerad. En okänd `view_key` ger `404`, inte en tom tråd — annars skapar ett
stavfel i klienten en tråd som ingen hittar tillbaka till.

Ingen bolagsdel. Se §12.2.

---

## 6. Beteende

### 6.1 Ett meddelande, hela vägen

1. `POST /threads/{view_key}/messages` tar emot `{ text, attachments[] }`.
2. Rutten slår upp aktuellt räkenskapsår, hämtar eller skapar tråden för
   `(view_key, fiscal_year_id)`, och skriver `user_text` (och ett `user_file` per bilaga) som
   inlägg. Det svaret går tillbaka direkt — människans egen replik ska stå i tråden innan agenten
   har sagt något.
3. En `agent_runs`-rad skapas med `trigger='thread'`, `model` från tråden, `protocol` från
   modellregistret.
4. Sessionen körs i en **arbetstråd**. Systemprompten är `build_system_prompt()` oförändrad;
   användarturen är trådfönstret (§6.3) plus dagens datum och öppna perioder.
5. Under vägen skjuts `message.delta` ut per textinkrement och `SkriverIndikator`-texten byts per
   verktygsanrop.
6. När turen är klar skrivs `agent_text` som ett inlägg, `message.completed` sänds, och om
   turen postade något sänds även `view.changed`.

Budgettaken kontrolleras **mellan** verktygsvarv, aldrig inuti `with db.transaction():` — samma
regel som `agentruntime` §6.5, och den ärvs oförändrad.

### 6.2 Inläggstyperna

`datakontrakt.md` §1: *"Inläggstyper som klienten måste kunna rendera, i samma ordning som de kom:
`agent_text`, `user_text`, `user_file`, `decision`, `options`, `draft` (verifikation, faktura,
lönekörning), `error`, `receipt`. Varje inlägg bär `id`, `created_at`, `actor` (`agent` eller
användarens namn) och valfria `traces[]` (spårchipsen)."*

Mappningen mot `komponenter.md`:

| Typ | Komponent | `body_json` bär |
|---|---|---|
| `agent_text` | `TradInlagg/agent` | `text` |
| `user_text` | `TradInlagg/du` | `text` |
| `user_file` | `FilInlagg` | `filename`, `size_bytes`, `pages`, `intake_source_id` |
| `decision` | `BeslutKort` / `GodkannKort` | `title`, `amount`, `reason`, `source`, `consequence` |
| `options` | `AlternativLista` | `options[]` med `account`, `amount`, `rationale`, `recommended` |
| `draft` | `VerifikationsForslag` m.fl. | `draft_id`, `rows[]`, `consequence` |
| `error` | `FelKort` | `cause`, `consequence`, `retry_draft_id` |
| `receipt` | `JamforelseRader` | `rows[]` med **båda** talen |

Tre regler som hör till kontraktet och inte till klienten, och som därför ska hedras när
`body_json` byggs:

- **Ingen rekommendation är förvald.** `recommended: true` är ett märke, inte ett val.
  `AlternativRad` har en tom ring.
- **Sista alternativet är alltid en väg ut** (`Annat konto`, `Det är ett annat köp`).
- **`receipt` visar alltid båda talen** (`var`/`blir`, `kvitto`/`A-118`). En ensam ny summa är en
  lögn om vad som ändras.

**Base64 kommer aldrig in i ett inlägg.** `AgentWorker._compact_tool_result` stryper redan
dokument- och bildnyttolaster ur händelserader (`{"type": …, "note": "<binary content omitted>"}`).
Samma precedens gäller `user_file`: inlägget bär filkortets metadata och en referens, aldrig
innehållet.

### 6.3 Trådfönstret

Beslutet i §12.3 är en tråd per räkenskapsår. Inom det året går **inte** hela tråden in i
kontexten — det skulle låta kostnaden växa obegränsat tills dygnstaket slår i av sig självt.

Kontexten är: systemprompten (cachebar, oförändrad), följt av de senaste inläggen inom
räkenskapsårets tråd upp till en token-budget, följt av dagens datum, öppna perioder och det nya
meddelandet. Budgetens storlek är öppen fråga 1 i §13.

Ett inlägg som inte ryms utelämnas — det sammanfattas inte. En LLM-sammanfattning av tidigare
bokföringssamtal som sedan ligger till grund för en postning är precis den sortens andrahandstext
`ANALYS.md` §7 varnar för.

### 6.4 Verktygsytan är oförändrad

De nio verktygen i `services/agent_tools.py` gäller ordagrant. **Testfall 17 från
`agentruntime` §9 — att verktygslistan inte innehåller någon väg att ändra eller radera en postad
verifikation — gäller lika hårt för trådvägen, och ska köras mot den.** Ordningen i `_TOOL_SPECS`
är dessutom en del av det cachade prefixet; den får inte röras för trådens skull.

En postning från ett trådsvar behöver en egen idempotens-namnrymd vid sidan av
`intake:{source_id}`:

```python
uuid5(BOK_NAMESPACE, f"thread:{thread_id}:{post_id}")
```

Nyckeln hänger på det **utlösande användarinlägget**, inte på tidpunkten. Två tryck på samma
meddelande ger samma nyckel och därmed `409` med den befintliga verifikationen, inte två poster i
en bok som inte kan städas.

### 6.5 Strömmen

Fyra händelsetyper, som i `datakontrakt.md`:

| Händelse | När | Nyttolast |
|---|---|---|
| `message.created` | Ett inlägg börjar | `id`, `type`, `actor`, `created_at` |
| `message.delta` | Ett textinkrement | `id`, `text` |
| `message.completed` | Inlägget är skrivet och lagrat | hela inlägget |
| `view.changed` | En postning ändrade vyns rader | `view_key`, och vad som ändrades |

`?since=<cursor>` på både `GET /threads/{view_key}` och strömmen. Markören är `thread_posts.seq`
för lagrade inlägg; en återansluten klient får det den missade och sedan levande händelser.

Två invarianter som ska stå i koden **och** i ett test:

- **En skrivare per `run_id`.** `AgentRunRepository.add_event` allokerar `seq` läs-sedan-skriv och
  motiverar det i sin docstring med att repositoryt bara drivs av en enda trådlokal anslutning.
  En trådkörning är sin **egen** `agent_runs`-rad, så premissen håller — men bara så länge inget
  delar `run_id` mellan två trådar. `UNIQUE (run_id, seq)` fångar brottet som ett fel, inte som
  tyst korruption, men ett fel mitt i ett svar är inte en acceptabel upptäcktsmekanism.
- **Flocken vaktar intag-passet, inte varje LLM-anrop.** `AgentRunner.start()` håller
  `.agent_runtime.lock` för processens livstid; en trådkörning går förbi det **med avsikt**,
  eftersom den inte rör intagskön. Två personer ska kunna skriva i två vyer samtidigt.

### 6.6 `view.changed`

Sänds när en postning faktiskt ändrade vyns rader, härlett ur `posta_verifikation`-utfallet —
aldrig ur ett gissat intervall, aldrig som en periodisk "kanske har något hänt". Utan den måste
klienten polla för att hålla siffrorna i takt med tråden, vilket är precis vad datakontraktet
säger att strömmen finns för att slippa.

### 6.7 Felhantering

Ärvs från `agentruntime` §6.7 och gäller oförändrad: en vägran, en avhuggen tur och ett orättat
verktygsfel blir aldrig en postning. Skillnaden i tråden är att utfallet ska **synas**: det blir
ett `error`-inlägg med orsak *och* konsekvens i bokföringstermer, i tråden där beslutet togs, med
`Försök igen` som bär **samma utkast-id**.

Går LLM-anropet inte fram alls (`LLMConnectionError`, `LLMRateLimitError`) blir det också ett
`error`-inlägg. Tråden tappar aldrig en tur i tysthet.

---

## 7. Agentläget

`GET /api/v1/agent/status` finns sedan A11 men saknar det designen behöver. `AgentStatus` i
`komponenter.md` har tre namngivna lägen — `Agenten arbetar`, `Agenten postar`, `Agenten pausad` —
och *"Pausad ska visas så länge den är pausad, inte bara i felinlägget."* `datakontrakt.md` §7 ber
om `{ state, since, current_task, paused_reason }`.

Dagens payload (`api/schemas.py:281`) har varken `state`-enum eller `paused_reason`, och
`current_activity` är grov med avsikt: A10 kunde inte rapportera verktygsnamn eftersom loopen inte
hade någon hook. **T5:s strömningshook är den hooken**, så `current_task` blir möjlig för första
gången.

Fälten läggs till; de befintliga tas inte bort, eftersom `GET /agent/status` redan har en
konsument.

**Agentläget är globalt, inte per sida.** Det finns en worker, en flock och en budget. Ett läge
per sida vore en uppfinning i gränssnittet utan motsvarighet i systemet. Det besvarar designens
egen öppna fråga 2 (`README.md`, "Öppna frågor att svara på innan bygget").

Nyckeln når aldrig svaret, varken hel eller maskerad — `agentruntime` §12.6, redan pinnat i test.

---

## 8. Gränser

1. **Runtimen får inte veta vad en tråd är.** Ingen `thread_id` in i `services/agent_runtime.py`
   eller `services/agent_session.py` som något annat än ogenomskinlig kontext. Mappningen
   händelse → inlägg bor i `tradar`.
2. **Verktygsytan utökas inte.** Ett bekvämt trådverktyg är den enda vägen förbi append-only som
   inte går genom en migration, och testfall 17 finns för att gå sönder då.
3. **Agentens text blir aldrig en verifikations `description` utan mänskligt beslut.**
   `ANALYS.md` §7.
4. **Inget inlägg ändras eller raderas.** Rättelse är ett nytt inlägg.
5. **Deltan lagras inte.** Ett strömmat tecken är en leverans, inte en händelse värd en rad.
6. **`anthropic` och `openai` importeras bara i `services/llm/`** — kriterium 10 i
   `agentruntime` §11, och det gäller fortfarande.

**Fråga först:** en nionde inläggstyp, ett tionde verktyg, en `thread_id` ned i runtimen, en ändring
i `docs/to_agent/`, eller en `view_key` utanför de sju.

---

## 9. Teststrategi

Ny fil `tests/test_tradar.py`. Testerna skrivs **före** implementationen.

LLM:en fejkas med `FakeLLMClient`-mönstret från `tests/test_agent_runtime.py:1420`: en kö av
färdiga `LLMTurn`, `self.calls` för att inspektera vad som faktiskt *skickades*, injicerad via
`client_factory`, aldrig monkeypatch. **Inget nätverksanrop i något test.** För strömning behöver
dubbeln utökas så att den anropar `on_text`/`on_tool_call` innan den returnerar sin turnyckel —
det är dubbelns enda nya ansvar.

| # | Testfall | Uppgift |
|---|---|---|
| 1 | Tråd skapas en gång per `(view_key, fiscal_year_id)`; andra anropet hittar samma | T2 |
| 2 | `seq` är tät och stigande per tråd | T2 |
| 3 | `since`-markören ger exakt det som kom efter | T2 |
| 4 | Okänd `view_key` ger `404`, inte en ny tråd | T8 |
| 5 | En nionde inläggstyp avvisas av `CHECK`-villkoret | T1 |
| 6 | `list_events(run_id, since_seq=n)` ger bara händelser efter `n` | T3 |
| 7 | Dokumentvägen beter sig exakt som före refaktoreringen — hela sviten grön | T4 |
| 8 | Ett blankt `stop == "end"` är ett **svar** i trådvägen och `agent_no_outcome` i dokumentvägen | T4 |
| 9 | `on_text` anropas per inkrement på Messages-vägen | T5 |
| 10 | En adapter utan strömning ger fortfarande ett komplett svar, bara utan deltan | T5 |
| 11 | `current_activity` bär verktygsnamnet under ett verktygsanrop | T5 |
| 12 | Systemprompten i en trådtur är byte för byte samma som i en dokumenttur | T6 |
| 13 | Trådfönstret klipps vid token-budgeten och sammanfattar inte det som föll bort | T6 |
| 14 | **Testfall 17 från `agentruntime`: ingen väg genom trådens verktygsyta ändrar eller raderar en postad verifikation** | T6 |
| 15 | Två postningar från samma användarinlägg ger samma idempotensnyckel och en verifikation | T6 |
| 16 | Ett `tool_call`-event blir ett `traces[]`-chip, inte ett eget inlägg | T7 |
| 17 | Base64 från ett dokumentblock når aldrig `body_json` eller `traces_json` | T7 |
| 18 | `POST /messages` skriver människans replik innan agenten svarar | T8 |
| 19 | Strömmen ger `message.created` → `message.delta`* → `message.completed` i den ordningen | T9 |
| 20 | En återansluten klient med `since` får det den missade och inget dubbelt | T9 |
| 21 | Två samtidiga trådkörningar delar aldrig `run_id` | T9 |
| 22 | En trådkörning startar även när `AgentRunner` håller flocken | T9 |
| 23 | `view.changed` sänds efter en postning och **inte** efter ett svar utan postning | T10 |
| 24 | Ett modellbyte mitt i en tråd syns via `agent_runs.model` per kör | T11 |
| 25 | En tråd på en Chat Completions-modell avstår från PDF-underlag i stället för att gissa | T11 |
| 26 | `GET /agent/status` bär `state`, `since`, `current_task`, `paused_reason` | T12 |
| 27 | `paused_reason` ligger kvar så länge agenten är pausad | T12 |
| 28 | `LLM_API_KEY` finns inte i något SSE-utskick, inget inlägg och ingen statusrad | T12 |
| 29 | En vägran, en avhuggen tur och ett orättat verktygsfel blir `error`-inlägg, aldrig postningar | T6 |
| 30 | Dygnstaket stoppar en trådtur mellan varv, aldrig inuti en transaktion | T6 |

---

## 10. Framgångskriterier

1. De tre endpointsen svarar enligt `datakontrakt.md` §1.
2. Alla åtta inläggstyper går att lagra och läsa tillbaka i den ordning de kom.
3. Strömmen ger `message.created`, `message.delta`, `message.completed` och `view.changed`.
4. `message.delta` kommer under turen, inte i en skur efteråt.
5. En tråd per `(view_key, fiscal_year_id)`, pinnat av ett unikhetsvillkor i schemat.
6. Dokumentvägen är oförändrad: hela sviten grön efter T4, utan en rad ändrad logik.
7. Testfall 17 passerar mot trådens verktygsyta.
8. En postning från tråden bär `Idempotency-Key` ur `thread:{thread_id}:{post_id}` och
   dubbelpostar inte.
9. Två samtidiga trådkörningar delar aldrig `run_id`, och en trådkörning blockeras inte av
   intagspassets flock.
10. `anthropic`/`openai` importeras fortfarande bara i `services/llm/`.
11. `GET /agent/status` bär `state`, `since`, `current_task`, `paused_reason`, och nyckeln finns
    inte i svaret.
12. Base64 når aldrig ett inlägg.
13. `pytest tests/ -v` grön; `black`, `isort`, `flake8` rena; inga nya `mypy`-fel i modulens filer.

---

## 11. Utbrytning: hur `run_session` delas

T4 är en **gate-uppgift** i A1:s mening — ren refaktorering, noll ny funktionalitet, hela sviten
grön innan nästa uppgift påbörjas.

Formen: `services/agent_session.py:383` blir en tunn omslagsfunktion kring en generisk loop som
tar systemprompt, meddelanden, verktyg, tak och en **terminalpolicy**. Policyn är det enda som
skiljer vägarna åt:

| Utfall | Dokumentvägen | Trådvägen |
|---|---|---|
| `posta_verifikation` | `posted`, avsluta | `posted`, fortsätt eller avsluta |
| `registrera_avstaende` | `abstained` | `abstained`, blir ett `decision`-inlägg |
| `stop == "refusal"` | `abstained: agent_refusal` | oförändrad, blir ett `error`-inlägg |
| `stop == "max_tokens"` | `abstained: agent_output_truncated` | oförändrad |
| `stop == "end"`, inga verktyg | `abstained: agent_no_outcome` | **svar** — turen är klar |
| varvtaket nås | `abstained` | `abstained` |

Återanvänds oförändrat: `build_system_prompt()`, `_tool_result_block`,
`_tool_result_content_blocks`, `_assistant_message`, `_format_tool_error`, `_add_usage`,
`SessionTurnRecord`, `SessionOutcome`.

En känd begränsning ärvs och blir mer synlig här: modulens docstring noterar att `LLMTurn` inte
bär `thinking`/`redacted_thinking`-block, så flerturskonversationer mot Anthropic inte
nödvändigtvis round-trippar perfekt. Det spelade liten roll för ett engångspass per underlag. I en
lång tråd spelar det större roll, och det är öppen fråga 3 i §13.

---

## 12. Beslut

### 12.1 SSE-djup — **BESLUTAT: full ström**

`message.created` + `message.delta` + `message.completed` + `view.changed`.

Alternativen var att bygga strömmen utan deltan, eller att polla. Båda faller på designen:
*"Chatten visar tråden så fort den finns; agentens svar strömmar in som text"*, och
`SkriverIndikator` ska säga vad som görs — `Postar verifikation A-118…` — **"Aldrig en anonym
spinner."** Utan deltan och utan verktygsnamn blir indikatorn precis det.

Kostnaden är en valfri `on_text`/`on_tool_call` på `LLMClient.run_turn`. Messages-adaptern
strömmar redan internt, så där är det att plocka upp något som kastas bort i dag. Chat-adaptern
får det via `stream=True`, och det den inte kan säger `LLMCapabilities` nej till — samma hållning
som redan gäller cache och dokumentblock: **en protokollskillnad som visas, inte en brist som
döljs.**

### 12.2 `view_key` — **BESLUTAT: bara vyn**

`bocker.verifikationer`, inte `{bolag}.bocker.verifikationer`.

`datakontrakt.md` säger "stabil per vy **och bolag**". `ANALYS.md` §7 säger tvärtom att
multitenans inte ska smygas in via `view_key`, och §9.2 stod obesvarad. Nu besvarad: **enbolag.**

Skälet är att ett bolagsprefix vore en garanti som inte gäller. `vouchers` bär ingen `tenant_id`,
`company_id` förekommer två gånger i hela kodbasen, och `user_tenants` från migration 008 är
oanvänd. En `view_key` som bär bolaget skulle skilja trådarna åt medan bokföringen de handlar om
inte är åtskild — separationen skulle se ut som en säkerhetsgräns utan att vara det. Bolaget
läggs till den dag multitenans byggs på riktigt, i hela stacken.

### 12.3 Trådlängd — **BESLUTAT: en tråd per räkenskapsår**

Besvarar `README.md`:s öppna fråga 1 och `ANALYS.md` §9.5: *"Hur långt tillbaka ska en vys tråd
läsas in, och vad händer med historik över årsskiften?"*

Tråden nollställs vid årsskiftet. Äldre år nås som arkiv — `GET /threads/{view_key}` tar en
valfri `fiscal_year_id` och ger utan den innevarande år.

Det matchar hur bokföring faktiskt tänker: räkenskapsåret är den enhet allt annat i systemet
redan är organiserat kring, perioder hör till ett år, och ett samtal om mars 2026 hjälper sällan
någon i februari 2027. Det ger också ett naturligt tak på hur lång en tråd kan bli, utan en
godtycklig gräns i antal inlägg. Priset är att vyn tappar sitt minne en gång om året — vilket
är synligt, förutsägbart och står i gränssnittet.

Inom året gäller ändå ett token-budgeterat fönster (§6.3); ett räkenskapsår av dagligt
bokföringssamtal är inte en kontext någon vill betala för.

### 12.4 Modell per tråd — ärvt från `agentruntime` §12.5

`threads.model` är platsen människan klickar i sitt val. Runtimen tar modellen som argument, och
`agent_runs.model`/`.protocol` per kör gör ett byte mitt i tråden synligt i efterhand utan en ny
tabell. Protokollskillnaderna följer med upp och ska visas: en tråd på en Chat Completions-modell
kan inte läsa PDF-underlag direkt och har ingen cache-ekonomi. Det är en produktsanning, inte en
detalj att dölja.

### 12.5 Agentläget — **BESLUTAT: globalt**

Se §7. Besvarar designens öppna fråga 2.

---

## 13. Öppna frågor

Ingen av dem blockerar starten. T1–T5 kan byggas medan de besvaras.

1. **Trådfönstrets storlek** (§6.3). Antal inlägg eller token-budget? Ett tal behövs innan T6
   landar. Förslag att bestämma mot: en budget i tokens, inte ett antal inlägg, eftersom ett
   `draft`-inlägg och ett `agent_text` skiljer sig med en storleksordning.
2. **Årsskiftet mitt i ett samtal.** Räkenskapsåret stängs medan en tråd är öppen — börjar nästa
   meddelande i en ny tråd omedelbart, eller får det pågående samtalet gå klart? Förslag: ny tråd
   omedelbart, med ett avslutande inlägg i den gamla som säger vart samtalet tog vägen.
3. **`thinking`-block över flera turer** (§11). Ska `LLMTurn` bära dem, så att en lång tråd
   round-trippar korrekt mot Anthropic? Det är en ändring i `agentruntime`s gränsyta och därför
   en fråga som ska ställas, inte avgöras här.
