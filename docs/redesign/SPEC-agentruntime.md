# Spec: `agentruntime`

Modul-id `agentruntime` i kapabilitetskartan (`ANALYS.md` §8). Beror på `idempotens`, som är
klar. Allt ovanför i byggordningen — `tradar`, `beslut`, `chattyta`, `flode-verifikationer` —
beror på den här.

Status: **Fas 1 — alla sex frågor besvarade 2026-09-14 (se §12).** Runtimen är
leverantörsoberoende: den går mot en OpenAI-/Anthropic-kompatibel gateway med beställarens egen
nyckel, och modellen väljs per konversation. §2, §4, §5 och §6 är omskrivna efter det. Ingen kod,
`tasks/plan.md` och `tasks/todo.md` skrivs härnäst.

---

## Antaganden

1. **Agenten går mot en modellgateway, inte mot en enskild leverantör.** Repot har ingen LLM i
   dag (`grep -riE "openai|anthropic"` över `*.py` → 0 träffar, `requirements.txt` har ingen
   klient), så det här är ett första val och inte en migrering. Beslutet (§12.5) är att bok
   använder beställarens nyckel hos **OpenCode Zen** — en gateway som serverar 60+ modeller från
   flera leverantörer på en nyckel — och att **modellen väljs per konversation**, inte en gång i
   konfigurationen.
2. **Enbolag, en installation.** Runtimen behöver inte bära bolag i sin session.
3. **Agenten postar med `Idempotency-Key`.** Modulen `idempotens` är förutsättningen, inte en
   trevlighet: en worker som kraschar mitt i ett pass ska kunna köra om utan att förorena
   huvudboken. Se §6.4.
4. **Runtimen ersätter det manuella passet först, chatten sedan.** Det som finns i dag är en
   människa som startar en LLM som kör `scripts/bok-curl` en gång. Den här modulen tar bort
   människan ur den slingan. Tråd, SSE och beslutskort byggs i `tradar`/`beslut` ovanpå samma
   sessionsmotor.
5. **Bokföringsdata lämnar maskinen.** Underlag, kontoplan och verifikationstexter skickas till
   gatewayen och vidare till den leverantör modellen tillhör. Det är ett verkligt beslut, inte en
   teknikalitet, och det är bekräftat i §12.4. Med en gateway är det dessutom **två** parter per
   anrop: gatewayen och modelleverantören bakom den.

→ Punkt 1 och 5 är de dyra, och punkt 5 blev dyrare av punkt 1. De är bekräftade 2026-09-14.

---

## 1. Objektiv

### Problemet, konkret

`ANALYS.md` §4: designen står och faller med en agent som **finns kontinuerligt, har ett läge och
en röst**. Repot har ingen sådan sak. Vad som finns:

- `services/dropzone.py` lägger filer i intagskön automatiskt, dygnet runt.
- `GET /api/v1/agent/intake/pending` visar kön.
- `POST /api/v1/agent/vouchers` postar en verifikation och kräver spårbarhet till kön.
- `GET /api/v1/agent/operations/log` returnerar `{"operations": [], "total": 0}` — en stubb
  (`api/routes/agent.py`).

Kedjan är komplett utom i mitten. Dropzonen fyller kön automatiskt; ingenting tömmer den
automatiskt. Underlag hopar sig tills en människa startar en LLM-session för hand. Ett system
som tar emot underlag dygnet runt och bokför dem när någon kommer ihåg det är inte ett
bokföringssystem — det är en inkorg.

### Vad vi bygger

En **worker i backend** som startas per pass, tar ett underlag i taget ur kön, kör en
LLM-session med bolagets bokföringskontext och ett litet, typat verktygsset, och antingen
postar en verifikation eller registrerar ett dokumenterat avstående. Plus det läge om sig själv
som `GET /api/v1/agent/status` behöver för att designens header ska kunna säga något sant.

### Vad vi inte bygger här

Tråd, meddelanden, SSE, beslutskort, underlagstolkning som egen endpoint. Alla fyra beror på
den här modulen och specificeras var för sig. Gränsen går vid: **runtimen producerar händelser
och utfall; `tradar` bestämmer hur de visas.**

### Användare

1. **Bolaget.** Underlag som kommer in på måndag är bokfört på måndag.
2. **`tradar` och `beslut`.** De behöver en sessionsmotor att ringa in i, inte en egen.
3. **Revisorn.** Varje postning ska gå att spåra bakåt till underlaget, prompten och beslutet.

### Framgång

Ett underlag som landar i dropzonen blir en postad verifikation — eller ett avstående med
skriven motivering — utan att en människa startar något. Och `GET /agent/status` säger sanningen
om vad agenten gjorde, hur länge, och vad det kostade.

---

## 2. Tech stack

Oförändrat i övrigt. Nytt:

```
anthropic>=1.0          # Messages-protokollet
openai>=2.0             # Chat Completions-protokollet
```

Två klientbibliotek, en nyckel, en gateway. Det ser ut som dubbelarbete och är det inte:
**OpenCode Zen serverar olika modellfamiljer över olika protokoll på samma bas-URL**
(`https://opencode.ai/zen/v1`), och båda SDK:erna tar en `base_url`, så ingen av dem används mot
sin egen leverantör:

| Protokoll | Väg | Modeller | SDK |
|---|---|---|---|
| Anthropic Messages | `/zen/v1/messages` | Claude (Opus, Sonnet, Haiku, Fable) | `anthropic` |
| OpenAI Chat Completions | `/zen/v1/chat/completions` | GPT, Grok, Qwen, DeepSeek, Kimi, GLM, MiniMax | `openai` |
| Google | `/zen/v1/models/<id>` | Gemini | **byggs inte i den här modulen** |

Gemini-vägen är utelämnad med avsikt: den är ett tredje protokoll för en familj ingen bett om, och
den kan läggas till som en tredje adapter utan att röra något annat.

### Vad som skiljer sig mellan protokollen

Det här är den verkliga kostnaden för leverantörsoberoendet, och den ska stå skriven innan någon
bygger:

| Förmåga | Messages-vägen | Chat Completions-vägen |
|---|---|---|
| Cache-brytpunkt (§6.6) | Explicit, och hela kostnadskalkylen bygger på den | Ingen explicit brytpunkt. Prefixcache kan finnas, men styrs inte av oss och kan inte verifieras med `cache_read_input_tokens` |
| PDF som `document`-block (§6.3) | Ja | Nej. En PDF måste renderas till bild eller extraheras till text **innan** anropet |
| Tänkande / `effort` | `thinking`, `output_config.effort` | Leverantörsspecifikt eller obefintligt |
| Verktygsloopen | `stop_reason == "tool_use"`, `tool_use`-block | `finish_reason == "tool_calls"`, JSON-strängargument som måste parsas |
| Vägran som eget utfall (§6.7) | `stop_reason == "refusal"` | Ingen egen kod — en vägran kommer som text |

Konsekvens: **Messages-vägen byggs först och är standard.** Chat Completions-vägen byggs efter,
med sina egna tester, och `LLMClient.capabilities` säger vad den saknar så att §6.6:s cachekrav
och §6.3:s dokumentblock inte tyst antas finnas.

### Modellen är per konversation

Ingen `MODEL = ...` i koden. Modellen kommer in i sessionen som ett argument:

- `LLM_DEFAULT_MODEL` i `config.py` är vad ett pass använder när ingen sagt något annat.
- Ett manuellt startat pass (§12.3) tar modellen som parameter.
- `tradar` lägger senare modellen på tråden — en konversation, en kontext, en modell — och skickar
  in den samma väg. Runtimen behöver ingen ändring för det; `agent_runs.model` bär redan svaret.

### Prislista, inte gissning

`cost_ore` (§5) räknas ur `usage` och en prislista per **modell** i `config.py`, inte per
leverantör. En modell utan prisrad får inte köra: passet vägrar starta med ett tydligt fel. Det är
avsiktligt strängt — dygnstaket i §6.5 är en säkring, och en säkring som inte kan räkna är ingen
säkring. Att lägga till en modell är att lägga till en rad med in-, ut- och cachepris.

---

## 3. Kommandon

Inga nya. Runtimen startar med API:t:

```bash
AGENT_RUNTIME_ENABLED=true \
LLM_API_KEY=... \
LLM_BASE_URL=https://opencode.ai/zen/v1 \
LLM_DEFAULT_MODEL=opencode/claude-opus-5 \
python main.py

pytest tests/test_agent_runtime.py -v
```

Avstängd som standard, som dropzonen. En utvecklare som kör `python main.py` ska inte råka
starta en betald LLM-loop mot sin testdatabas. `LLM_BASE_URL` har gatewayen som standardvärde men
är konfigurerbar — pekar den på `api.anthropic.com` fungerar Messages-vägen lika bra med en
Anthropic-nyckel, och det är den enklaste vägen ut om gatewayen ligger nere.

---

## 4. Projektstruktur

```
services/agent_runtime.py      # AgentWorker + AgentRunner (tråd, flock, start, status)
services/agent_tools.py        # verktygsdefinitioner + utförare, ett verktyg per tillåten handling
services/agent_session.py      # passet: systemprompt, verktygsloop, budget, felhantering
services/llm/__init__.py       # LLMClient-protokollet + modellregistret (modell → protokoll, pris)
services/llm/messages.py       # Anthropic Messages-adapter (standard)
services/llm/chat.py           # OpenAI Chat Completions-adapter
services/voucher_posting.py    # utbruten ur api/routes/agent.py — se §7
repositories/agent_run_repo.py # all SQL för agent_runs / agent_run_events
db/migrations/024_*.sql        # agent_runs, agent_run_events
api/routes/agent.py            # GET /agent/status ersätter operations/log-stubben
tests/test_agent_runtime.py
```

Lagren är de vanliga: ingen SQL utanför `repositories/`, inga HTTP-begrepp i `services/`.

**`services/llm/` är det enda stället som importerar `anthropic` eller `openai`.** Allt ovanför —
sessionen, verktygen, workern, statusen — ser bara `LLMClient`. Det är den gränsen som gör
leverantörsoberoendet till något annat än en `if`-sats: går den sönder, sprider sig ett
protokollval upp i bokföringslogiken och en tredje leverantör blir en omskrivning i stället för en
fil till.

`LLMClient` är smalt med flit:

```python
class LLMClient(Protocol):
    capabilities: LLMCapabilities   # cache_breakpoint, pdf_document_blocks, refusal_stop_reason
    def run_turn(self, system, messages, tools, model, max_tokens) -> LLMTurn: ...

# LLMTurn: text, tool_calls, stop ('tool_calls'|'end'|'refusal'|'max_tokens'), usage
```

`stop` är normaliserad. Att `refusal` bara finns på den ena vägen (§2) är adapterns problem, inte
sessionens — men `capabilities` säger vilket som gäller, så §6.7 kan behandla en vägran som
verklig vägran på Messages-vägen och som ett avstående utan kategori på den andra.

---

## 5. Datamodell

```sql
CREATE TABLE agent_runs (
    id            TEXT PRIMARY KEY,
    trigger       TEXT NOT NULL,         -- 'schedule' | 'manual' | 'thread'
    status        TEXT NOT NULL,         -- 'running' | 'completed' | 'failed' | 'abandoned'
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    model         TEXT NOT NULL,         -- t.ex. 'opencode/claude-opus-5'
    protocol      TEXT NOT NULL,         -- 'messages' | 'chat'
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_ore      INTEGER NOT NULL DEFAULT 0,
    items_seen    INTEGER NOT NULL DEFAULT 0,
    items_posted  INTEGER NOT NULL DEFAULT 0,
    items_abstained INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    CHECK (status IN ('running','completed','failed','abandoned'))
);

CREATE TABLE agent_run_events (
    id            TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES agent_runs(id),
    seq           INTEGER NOT NULL,
    kind          TEXT NOT NULL,   -- 'item_started'|'tool_call'|'tool_result'|'posted'
                                   -- |'abstained'|'error'|'text'
    source_id     TEXT,
    voucher_id    TEXT,
    payload_json  TEXT NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    UNIQUE (run_id, seq)
);
```

Två saker att säga om det här:

**`agent_run_events` är inte revisionsspåret.** `audit_log` är revisionsspåret, och det ändras
inte. Händelseraderna finns för att `GET /agent/status` ska kunna visa vad agenten gör just nu
och för att `tradar` senare ska kunna rendera samma händelser som inlägg utan att runtimen får
veta vad en tråd är.

**Beloppen i ören, som allt annat i systemet.** `cost_ore` beräknas ur `usage` och prislistan i
`config.py`, inte ur en gissning. Prislistan slås upp på **modellen**, och en modell utan prisrad
får inte köra (§2) — därför kan kolumnen vara `NOT NULL` utan att ljuga.

**`model` och `protocol` står på körningen, inte i konfigurationen.** En kör som gick på
`opencode/claude-opus-5` och en som gick på `opencode/gpt-5.5` ska gå att skilja åt i efterhand,
och `cache_read_tokens = 0` betyder olika saker på de två vägarna (§2). Utan `protocol` på raden
är den siffran oläsbar ett halvår senare. När `tradar` lägger modellen på tråden är det de här två
kolumnerna som visar vad som faktiskt användes.

---

## 6. Beteende

### 6.1 Livscykeln

Exakt samma form som `DropzoneRunner` (`services/dropzone.py`), och det är avsiktligt — mönstret
är redan i drift på hubbabubba och dess fallgropar är redan lösta där:

- Bakgrundstråd, startad i `lifespan` i `api/main.py`, avstängd som standard.
- **`flock` på en låsfil**, inte en PID-fil. Kommentaren i `_acquire_lock` förklarar varför: under
  rootless Podman får uvicorn ~samma PID vid varje omstart, så en PID-baserad staleness-check
  pekar ut den nya processen som den gamla låshållaren. Två workers som bokför samma kö parallellt
  är värre än ingen worker alls.
- `stop()` sätter en `Event` och joinar med timeout. En pågående LLM-tur avbryts inte mitt i en
  postning; den får gå klart eller falla på sin egen timeout.
- `status()` returnerar en ögonblicksbild utan att röra API:t.

### 6.2 Ett pass

```
passet startas (manuellt — §12.3)
  → finns en pågående kör med status='running' och en död tråd? markera 'abandoned', logga
  → slå upp modellen: parametern, annars LLM_DEFAULT_MODEL
       → ingen prisrad för modellen? vägra starta, tydligt fel (§2)
  → hämta kön: IntakeService, samma vy som GET /agent/intake/pending
  → kön tom → avsluta, skriv ingen agent_runs-rad
  → skapa agent_runs-rad (status='running', model, protocol)
  → för varje post, en i taget:
       → markera posten 'processing'
       → kör en session (§6.3) mot vald modell med posten som uppgift
       → utfallet är postning, avstående eller fel
       → budgettak nått (§6.5)? avsluta passet snyggt, resten ligger kvar i kön
  → status='completed', summera tokens och kostnad
```

Intervallslingan finns i `AgentRunner` men startas inte av en timer i den här modulen (§12.3).
Den som lägger på schemaläggningen senare ändrar `trigger` från `'manual'` till `'schedule'`,
ingenting annat.

En post i taget. Det är inte en optimering som väntar — det är hur `02_bokforingsprocess.md`
redan instruerar agenten ("one item at a time" står också i entrypointens guardrails), och det är
vad som gör ett avbrott billigt: allt utom den pågående posten är redan klart och committat.

### 6.3 Sessionen

Ett anrop per underlag, inte en session som lever över hela passet. Sessionen vet inte vilket
protokoll den kör på — den ser `LLMClient` (§4) och frågar `capabilities` när svaret skiljer sig. Motivet är återställbarhet:
en session som dör tar med sig allt den höll på med, och ett underlag som redan är bokfört ska
inte bokföras om för att underlag sju kraschade.

**Systemprompt** (stabil, cachad — se §6.6):

1. `repositories/system_instructions.get_system_instructions()` — samma fyra filer som serveras
   till dagens externa agent. Runtimen läser sina instruktioner från exakt samma källa som en
   människa skulle ge en LLM. Divergerar de, är en av dem fel.
2. Bolagets egen bokföringsinstruktion (`GET /agent-instructions/accounting`, den redigerbara).
3. Kontoplanen.
4. De senaste korrigeringarna — vad människan rättade sist är den starkaste signalen som finns.

**Användarturen** (volatil, efter cachebrytpunkten): dagens datum, öppna perioder, och det
aktuella underlaget — metadata plus filen. Hur filen bifogas beror på adaptern:

- `capabilities.pdf_document_blocks` → PDF som `document`-block, foto som `image`-block.
- Annars → PDF:en renderas till bild innan anropet. Går inte det, är underlaget ett **avstående**
  med motiveringen att modellen inte kan läsa underlaget — aldrig en postning på gissad metadata.

Det är skillnaden mellan vägarna som faktiskt biter i bokföringen, och därför är den ett testfall
(§9) och inte en kommentar i koden.

**Verktygsloopen**: manuell loop på `LLMTurn.stop == "tool_calls"`, inte SDK:ns tool runner.
Skälet är att varje verktygsanrop ska passera en punkt där vi kan neka, logga och skriva en
`agent_run_events`-rad innan det utförs. Det är samma argument som §6.4 gör för verktygsytan.

### 6.4 Verktygsytan: inga generella verktyg

**Ingen bash. Ingen SQL. Inget generellt HTTP-verktyg. Ingen filsystemsåtkomst.**

Standardrådet är att börja brett med bash och smalna av. Det gäller inte här. Ett bash-verktyg
ger harnesset en ogenomskinlig kommandosträng — samma form för "läs kontoplanen" som för "skriv i
huvudboken". I ett system vars hela poäng är att append-only-garantin ska hålla även när ett lager
har en bugg är det fel riktning. Varje handling agenten får göra ska vara ett eget verktyg med
typade argument, så att den kan nekas, granskas, loggas och renderas var för sig.

| Verktyg | Läs/skriv | Går till |
|---|---|---|
| `las_kontoplan` | läs | `AccountRepository` |
| `las_perioder` | läs | `PeriodRepository` — öppna perioder, låsta med `locked_by`/`locked_at` |
| `las_verifikationer` | läs | `VoucherRepository`, filtrerbar |
| `las_korrigeringar` | läs | `AccountingCorrectionRepository` |
| `las_underlag` | läs | `IntakeService` — kön och en posts metadata |
| `hamta_underlagsfil` | läs | `IntakeService.resolve_source_file`, returneras som dokumentblock |
| `las_bankhandelser` | läs | `BankInputService` |
| `posta_verifikation` | **skriv** | `services/voucher_posting.py` — enda skrivvägen till boken |
| `registrera_avstaende` | skriv | intagspostens `failed`/`warning`-utfall med motivering |

`posta_verifikation` är det enda verktyget som rör huvudboken, och det går genom **samma** kod som
`POST /api/v1/agent/vouchers`: samma spårbarhetskrav, samma `VoucherValidator`, samma transaktion,
samma idempotensnyckel. Det kräver att postningen bryts ut ur ruttfunktionen, se §7.

**Nyckeln är härledd, inte slumpad.** Runtimen genererar
`uuid5(BOK_NAMESPACE, f"intake:{source_id}")`. Avsikten är "bokför underlag X", och den avsikten
är densamma vid varje omförsök — så en worker som kraschar efter postningen men före
kö-uppdateringen får en uppspelning med `Idempotent-Replay: true` i stället för en andra
verifikation. Det är exakt det fall `idempotens` byggdes för, och det första som faktiskt använder
det. Att ett intagsunderlag bara får länkas en gång gör kopplingen en-till-en korrekt: ett
underlag, en avsikt, en nyckel.

### 6.5 Budget och tak

Fyra tak, alla i `config.py`:

| Tak | Standard | Vid träff |
|---|---|---|
| Verktygsvarv per underlag | 25 | Avbryt underlaget, registrera avstående `agent_turn_limit` |
| Ut-token per underlag | 32 000 | Samma |
| Kostnad per dygn | 50 kr | Avsluta passet, `status='completed'`, logga `budget_exhausted` |
| Underlag per pass | 20 | Avsluta passet snyggt, resten ligger kvar |

Taken avbryter aldrig mitt i en postning: de kontrolleras mellan underlag och mellan
verktygsvarv, aldrig inuti `with db.transaction():`.

Dygnstaket är en säkring, inte en budget. En loop som av något skäl börjar bränna token ska stanna
av sig själv innan någon hinner läsa en faktura. Vid taket **stannar** runtimen (§12.5) — den går
aldrig ned till en billigare modell på egen hand. Ett tak som sänker kvaliteten i stället för att
stoppa börjar bokföra sämre precis när det är som mest att göra, och med modellval per konversation
är nedgraderingen dessutom beställarens beslut att ta, inte workerns.

Taket räknas i kronor över alla modeller i ett dygn, inte per modell. Det är samma nyckel som
betalar.

### 6.6 Cache — bara på Messages-vägen

Gäller när `capabilities.cache_breakpoint` är sann. På Chat Completions-vägen finns ingen
brytpunkt vi styr och ingen `cache_read_input_tokens` att mäta på: då är cachen inte en besparing
vi räknar med, och kostnadsuppskattningen för ett pass blir därefter. Det ska synas i kalkylen
innan någon väljer modell, inte upptäckas på fakturan.

Systemprompten (instruktioner + kontoplan + korrigeringar) är samma bytes för varje underlag i ett
pass och nästan samma mellan pass. Med en explicit brytpunkt sist i systemprompten läses den från
cache till ~0,1× priset i stället för att betalas fullt tjugo gånger per pass.

Tre fällor som tystar cachen och som ska testas, inte antas:

- **Ingen tidsstämpel i systemprompten.** `datetime.now()` någonstans i prefixet gör varje anrop
  till en missar. Dagens datum hör hemma i användarturen.
- **Deterministisk ordning.** Kontoplan och korrigeringar sorteras; verktygslistan byggs i fast
  ordning. Ett `dict` som råkar itereras i annan ordning är samma sak som en ändrad prompt.
- **Verifiera, gissa inte.** `usage.cache_read_input_tokens` ska vara > 0 från och med underlag
  två i ett pass. Är den noll finns en tyst invaliderare, och det är ett testfall — på den väg där
  siffran finns.

### 6.7 Felhantering

| Fel | Svar |
|---|---|
| Gateway nere, timeout, 5xx | SDK:n gör sina omförsök. Håller det i sig: underlaget tillbaka till `pending`, passet `failed`, exponentiell backoff |
| 429 | Respektera `retry-after`, avsluta passet, ta om vid nästa start |
| `stop == "refusal"` | Registrera avstående med kategorin. Aldrig posta något efter en vägran. Saknar adaptern egen vägrankod (§2) blir det ett avstående utan kategori — aldrig en postning |
| `stop == "max_tokens"` | Avstående `agent_output_truncated`. En avhuggen tur får aldrig tolkas som ett beslut |
| Modellen finns inte hos gatewayen (404 / `model_not_found`) | Passet startar inte. Ingen tyst nedgradering till en annan modell |
| Verktyget kastar (`ValidationError`, `IntakeError`) | `tool_result` med `is_error: true` tillbaka till modellen. Den får rätta sig själv inom varvtaket |
| `409 request_in_flight` från postningen | Någon annan håller nyckeln. Lämna underlaget, gå vidare |
| `201` med `Idempotent-Replay: true` | Redan bokfört. **Kvitto, inte fel.** Uppdatera kön, gå vidare |
| Processen dör mitt i | Nästa start ser `status='running'` utan levande tråd → `abandoned`. Nyckeln räddar postningen |

Den generella regeln: **ett osäkert utfall är ett avstående, aldrig en postning.** Det är samma
regel som redan står under "När agenten ska avstå" i `02_bokforingsprocess.md`, och runtimen ärver
den i stället för att få en egen.

---

## 7. Utbrytning ur ruttlagret

`api/routes/agent.py::_create_and_post_voucher` innehåller i dag hela postningsorkestreringen:
spårbarhetskontroll, `VoucherValidator`, transaktionen och idempotensskrivningen. Den kom dit i
`idempotens`/T5 och hörde hemma där så länge HTTP var enda vägen in.

Runtimen är en andra väg in. Två alternativ, båda dåliga om de väljs slarvigt:

- **Workern anropar sitt eget HTTP-API.** Ingen utbrytning behövs, men vi får en process som
  pratar med sig själv över loopback med sin egen bearer-token, och all bokföring passerar en
  serialiserande ASGI-hop. Det är dagens externa agent, inflyttad.
- **Workern anropar servicelagret direkt**, och postningen flyttar till
  `services/voucher_posting.py` som både rutten och verktyget anropar.

Jag förordar det andra. Det betyder ett eget, ensamt steg — flytta funktionen, ändra ingenting i
den, hela sviten grön — innan något av runtimen byggs. Samma form som T8 i `idempotens`: en
gate-uppgift som inte lägger till funktionalitet. Se §12.1.

---

## 8. `GET /api/v1/agent/status`

Ersätter `GET /api/v1/agent/operations/log`, som är en stubb som returnerar tom lista och som
`datakontrakt.md` felaktigt listar som befintlig (`ANALYS.md` §4).

```json
{
  "enabled": true,
  "running": true,
  "current_run": {
    "id": "...", "started_at": "...", "trigger": "manual",
    "model": "opencode/claude-opus-5", "protocol": "messages",
    "items_seen": 7, "items_posted": 5, "items_abstained": 1,
    "current_source_id": "...", "current_activity": "las_kontoplan"
  },
  "last_run": { "...": "...", "status": "completed", "cost_ore": 1240 },
  "queue_depth": 3,
  "cost_today_ore": 4310,
  "budget_today_ore": 5000,
  "last_error": null
}
```

Auth som övriga agent-endpoints. `current_activity` är verktygsnamnet — designens header ska kunna
skriva "läser kontoplanen" utan att uppfinna en egen vokabulär.

`model` står i svaret därför att modellen är ett val per konversation (§2) och en människa som
läser statusen ska se vilken som faktiskt körde. **Nyckeln står aldrig i svaret** — varken hel
eller maskerad, och inte heller i `agent_run_events` (§12.6).

---

## 9. Teststrategi

`tests/test_agent_runtime.py`. Testerna skrivs före implementationen, som i `idempotens`.

**Ingen LLM anropas i tester.** En falsk `LLMClient` returnerar förinspelade `LLMTurn`-objekt.
Det som testas är loopen, verktygen, budgetarna och felvägarna — inte att modellen är klok. Ett
test som kostar pengar körs inte i CI och är därför inte ett test.

Att `LLMClient` är smalt (§4) är det som gör den falska klienten trivial. De två adaptrarna testas
var för sig mot inspelade råsvar, så att protokollskillnaderna i §2 fångas i adapterlagret i
stället för att läcka upp i sessionstesterna.

| # | Fall | Förväntat |
|---|---|---|
| 1 | Kö med ett underlag, modellen svarar med `posta_verifikation` | En postad verifikation, posten ur kön, `items_posted=1` |
| 2 | Samma underlag två gånger (worker startas om) | **En** verifikation. Andra gången uppspelning |
| 3 | Modellen svarar med `registrera_avstaende` | Ingen verifikation, posten `failed` med motiveringen |
| 4 | `stop_reason="refusal"` | Avstående, ingen postning, kategorin loggad |
| 5 | `stop_reason="max_tokens"` | Avstående, ingen postning |
| 6 | Verktyget kastar `ValidationError` | `is_error`-resultat, modellen får försöka igen inom varvtaket |
| 7 | Modellen loopar utan att avsluta | Varvtaket slår, avstående `agent_turn_limit` |
| 8 | Dygnstaket redan nått | Passet startar inte, ingen `agent_runs`-rad, loggat |
| 9 | Kön tom | Ingen `agent_runs`-rad, inget API-anrop |
| 10 | API kastar `APIConnectionError` | Underlaget tillbaka till `pending`, passet `failed`, backoff |
| 11 | 429 med `retry-after` | Passet avslutas, nästa start försöker igen |
| 12 | Tråden dödas mitt i ett pass, ny start | Föregående kör `abandoned`, ingen dubbelpostning |
| 13 | Två workers, samma kö | `flock` släpper bara igenom en |
| 14 | Systemprompten byggd två gånger med samma data | Byte för byte identisk (cachetest) |
| 15 | Fem underlag i ett pass | `cache_read_input_tokens > 0` från och med nummer två |
| 16 | `AGENT_RUNTIME_ENABLED=false` | Ingen tråd, `status.enabled=false`, inget API-anrop |
| 17 | Verktygslistan | Innehåller inget verktyg som kan ändra eller radera en postad verifikation |
| 18 | Samma pass, en gång per adapter | Samma verktygsanrop ger samma postning. Protokollet syns inte i utfallet |
| 19 | Modell utan prisrad i `config.py` | Passet startar inte, ingen `agent_runs`-rad, tydligt fel |
| 20 | Adapter utan `pdf_document_blocks`, PDF som inte kan renderas | Avstående med läsbar motivering, **ingen** postning på metadata |
| 21 | Modellen valdes per kör | `agent_runs.model` och `.protocol` bär den valda modellen, inte standardvärdet |

Testfall 17 är ingen formalitet. Det är den enda automatiska kontrollen av att append-only-regeln
inte kan gå förlorad genom att någon lägger till ett bekvämt verktyg.

---

## 10. Gränser

**Alltid**

- Ny migrationsfil. Aldrig redigera en applicerad.
- All SQL i `repositories/`. Inga HTTP-begrepp i `services/`.
- Postning genom `services/voucher_posting.py` — samma väg som rutten, samma validering.
- Idempotensnyckel på varje postning, härledd ur underlagets id.
- Ett underlag i taget.
- `black . && isort . && flake8 && mypy .` och hela `tests/` före commit. Jobboutputen läses,
  inte bocken. `black`/`isort`/`flake8` ska vara rena; `mypy` har 61 pre-existerande fel i repot
  (eget spår, se `tasks/todo.md`) — modulens egna filer lägger inte till ett enda.

**Fråga först**

- Att låta runtimen skriva något annat än verifikationer och intagsutfall.
- Att höja dygnstaket, eller ändra vad som händer vid det.
- Att lägga till en tredje adapter (t.ex. Gemini-vägen) eller ett protokoll till.
- Att ändra vad som händer vid dygnstaket.
- Varje ändring i `docs/to_agent/*.md`. Katalogen är runtime-innehåll och blir nu bokstavligen
  agentens systemprompt — en redigering där ändrar vad agenten gör, inte vad den läser om sig
  själv.

**Aldrig**

- Ett bash-, SQL-, filsystems- eller generellt HTTP-verktyg.
- Ett verktyg som ändrar eller raderar en postad verifikation. Korrigering går genom B-serien.
- Posta efter en vägran, en avhuggen tur, eller ett verktygsfel som modellen inte rättat.
- Låta en LLM-genererad sträng bli en verifikations `description` utan att den passerat
  `VoucherValidator` och spårbarhetskravet.
- Anropa en riktig LLM i ett test.
- Importera `anthropic` eller `openai` utanför `services/llm/`.
- Nedgradera modellen automatiskt — vid taket, vid fel, eller för att spara pengar.
- Två workers mot samma databas.

---

## 11. Framgångskriterier

Modulen är klar när allt nedan är sant:

1. En fil i dropzonen blir en postad verifikation utan mänskligt ingripande.
2. En worker som dödas mitt i ett pass och startas om producerar **noll** dubbletter.
3. Ett underlag som agenten inte kan avgöra blir ett avstående med läsbar motivering på posten —
   aldrig en gissad postning.
4. `GET /api/v1/agent/status` svarar sant om pågående kör, ködjup, kostnad i dag och senaste fel.
   `operations/log`-stubben är borta.
5. Dygnstaket stoppar passet, och det är verifierat i test — inte i produktion.
6. `cache_read_input_tokens > 0` från andra underlaget i ett pass, mätt.
7. Verktygslistan innehåller ingen väg att ändra eller radera postad bokföring, verifierat i test.
8. Postningen går genom samma kod som `POST /api/v1/agent/vouchers`, och båda vägarna delar
   idempotens, validering och transaktion.
9. Ingen testkörning träffar en riktig LLM, och `anthropic`/`openai` importeras ingenstans utanför
   `services/llm/`.
10. Samma pass går att köra på en Claude-modell och på en GPT-modell med samma nyckel, och
    `agent_runs` visar vilken som användes.
11. En modell utan prisrad stoppas innan passet börjar, inte efter.
12. `tests/` grön och `black`/`isort`/`flake8` rena — läst i jobboutput. `mypy` lägger inte till
    ett fel i modulens filer.

---

## 12. Beslut och öppna frågor

Besvarade av beställaren 2026-09-14. Alla sex är stängda. §12.5 blev inte ett modellval utan ett
arkitekturkrav och skrev om §2, §4, §5 och §6.

### 12.1 In-process eller över eget HTTP? (§7) — **BESLUTAT: in-process**

Beslut 2026-09-14: workern anropar servicelagret direkt. Postningen bryts ut till
`services/voucher_posting.py` som en ensam gate-uppgift — flytta funktionen, ändra ingenting i
den, hela sviten grön — innan något av runtimen byggs.

Underlaget: rekommendationen var **in-process**, med postningen utbruten till `services/voucher_posting.py` som en
ensam gate-uppgift först. Alternativet är att workern anropar sitt eget API över loopback — mindre
kod nu, men då är runtimen dagens externa agent med en tråd runt, och varje postning tar en
ASGI-hop genom en trådlokal SQLite-connection. Säg till om du hellre tar det.

### 12.2 Får agenten posta själv? — **BESLUTAT: ja, som i dag**

Beslut 2026-09-14: dagens beteende behålls. Agenten postar när underlaget och konteringen är
tillräckligt klara och avstår annars; modulen `beslut` inför det mänskliga steget för just de fall
agenten avstår från. Underlaget:

I dag postar den direkt: `02_bokforingsprocess.md` säger "Agenten får bokföra direkt via API:t när
underlaget och konteringen är tillräckligt klara", och `POST /agent/vouchers` postar i samma
anrop. Redesignen ritar samtidigt beslutskort där människan väljer.

Jag föreslår att **behålla dagens beteende** i den här modulen — posta när det är klart, avstå
annars — och låta `beslut` införa det mänskliga steget för de fall agenten avstår från. Motsatsen
(allt blir förslag) betyder att kön aldrig töms utan en människa, vilket är precis det problem
§1 beskriver.

### 12.3 Hur ofta, och när? — **BESLUTAT: bara manuellt till att börja med**

Beslut 2026-09-14: ingen schemaläggning i den här modulen. Passet startas manuellt — via
kommando och en endpoint — tills vi har mätt vad ett pass kostar och hur bra det bokför.
Intervallkörning läggs på när de siffrorna finns, och `agent_runs.trigger` bär redan `'manual'`
respektive `'schedule'`, så tillägget kräver ingen schemaändring.

Konsekvens för §6: nedräkningen och `flock`-slingan finns kvar som mekanism, men startas inte av
en timer. `AGENT_RUNTIME_ENABLED` styr fortfarande om passet över huvud taget får köra.

Underlaget:

Dropzonen skannar på intervall. Ska bokföringspasset göra samma sak (säg var femtonde minut,
dygnet runt), eller ska det vara sällan och schemalagt (en gång per natt)? Det första ger snabb
bokföring och en jämn kostnad; det andra ger billigare drift och en människa som hinner emellan.
Jag lutar åt **var femtonde minut med tomkö-kontroll först** — ett pass utan underlag kostar
ingenting eftersom inget API-anrop görs.

### 12.4 Bokföringsdata till LLM-leverantören — **BEKRÄFTAT**

Beslut 2026-09-14: ja, bokföringsdata får lämna maskinen till den LLM-leverantör som är
konfigurerad. Retentionsfrågan (vad leverantören sparar och hur länge, och om något
datahanteringsavtal behövs) följer med leverantörsvalet i §12.5 och ska besvaras per leverantör,
inte en gång för alla.

Underlaget, skrivet när Anthropic var enda alternativet:

Underlag (kvitton, fakturor, kontoutdrag), kontoplan, verifikationstexter och bolagets egna
bokföringsinstruktioner skickas till Anthropics API. Det är leverantörsnamn, belopp,
kundrelationer och i praktiken en läsbar bild av bolagets affärer.

BFL hindrar det inte — bevarandekravet gäller att räkenskapsinformationen finns kvar hos bolaget,
inte att den aldrig får läsas av någon annan. Men det är ett beslut du ska ta uttryckligen, inte
ärva från en spec. Det finns också en retentionsdimension (vad som sparas hos leverantören och hur
länge) som påverkar om något datahanteringsavtal behövs. **Detta är den fråga jag helst vill ha
svar på innan något byggs.**

### 12.5 Modellval — **BESLUTAT: gateway med modell per konversation**

Svar 2026-09-14: *"Jag vill kunna koppla vilken LLM-provider och modell jag vill. Exempelvis
Opencode skall kunna köra detta."* Förtydligat: beställarens nyckel hos OpenCode konfigureras i
runtimen, och modellen väljs sedan **per konversation** — en konversation har en kontext och en
modell.

Det var inte ett val mellan Opus och Sonnet utan ett arkitekturkrav. Två saker gör att det kostar
mindre än det såg ut att göra:

1. **OpenCode Zen talar båda protokollen på samma nyckel** — `/zen/v1/messages` för Claude-familjen
   och `/zen/v1/chat/completions` för GPT, Grok, Qwen, DeepSeek m.fl. Anthropic-SDK:n tar en
   `base_url`, så Messages-vägen — med cache, `thinking` och dokumentblock — överlever intakt. Det
   är inte en minsta gemensamma nämnare, det är två vägar där den ena är den ursprungliga specens.
2. **`agent_runs.model` fanns redan.** Modell per konversation kräver ingen ny tabell, bara att
   modellen är ett argument hela vägen ned i stället för en konstant.

Vad det ändå kostar, och som står skrivet i §2: Chat Completions-vägen har ingen cache-brytpunkt
vi styr, ingen egen vägrankod, och inga PDF-dokumentblock. Ett pass på en GPT-modell är alltså
dyrare per underlag än kalkylen i §6.6 antyder, och PDF-underlag måste renderas till bild först.
Därför byggs Messages-vägen först och är standard.

**Vid dygnstaket: stanna.** Runtimen nedgraderar aldrig modellen automatiskt — vid taket, vid fel
eller för att spara pengar. Med modellval per konversation är det beställarens beslut.

Den ursprungliga frågan, som underlag:

`claude-opus-5` för allt var rekommendationen och specens utgångspunkt. Alternativ: `claude-sonnet-5`
($2/$10) för enkla kvitton och Opus för resten. Två invändningar mot att differentiera nu: cachen
är modellbunden, så två modeller i samma pass betalar prefixet två gånger, och vi har ingen mätning
som säger att Sonnet räcker. Rätt ordning är att bygga på Opus, mäta, och sedan sänka — inte tvärtom.

Relaterat: vad händer vid dygnstaket? Stanna, eller gå ned till en billigare modell och fortsätta?
Jag föreslår **stanna** — ett tak som sänker kvaliteten i stället för att stoppa är ett tak som
tyst börjar bokföra sämre när det är som mest att göra.

### 12.5b Formen: intern adapter, inte extern harness — **BESLUTAT**

Tre former stod öppna: intern adapter, extern harness (bok bygger ingen LLM-klient och Opencode
kör modellen utifrån), eller båda. Beställarens förtydligande avgjorde: **bok kör anropen själv**
med beställarens nyckel. Alltså intern adapter, `services/llm/` som enda import av ett SDK, och
`LLMClient` som gräns.

Den externa vägen finns kvar oavsett — `/api/v1/agent/*` är kvar som det är, och en människa som
vill köra ett pass med sitt eget verktyg kan fortfarande göra det, precis som i dag. Skillnaden är
att bok inte behöver den vägen för att fungera.

### 12.6 Var bor nyckeln på hubbabubba? — **BESLUTAT: `bok.env`**

Beslut 2026-09-14: API-nyckeln bor i `/srv/appdata/bok/bok.env` bredvid `BOKFOERING_API_KEY`, med
filrättigheterna som skydd. **Gräns som ska stå i implementationen:** nyckeln når aldrig
`GET /agent/status` och aldrig `agent_run_events` — varken hel eller maskerad.

Underlaget:

`ANTHROPIC_API_KEY` i `/srv/appdata/bok/bok.env`, som `BOKFOERING_API_KEY`? (Variabeln heter efter
§12.5 `LLM_API_KEY` och bär OpenCode-nyckeln, men platsen är densamma.) Det är det enkla svaret
och det som passar quadlet-uppsättningen. Bekräfta bara att den filens rättigheter är det skydd vi
tänker oss, och att nyckeln aldrig ska hamna i `GET /agent/status` eller i `agent_run_events`.

---

## 13. Vad som händer sedan

När `agentruntime` är klar är `tradar` ett mycket mindre problem än det ser ut i `ANALYS.md` §4:
sessionsmotorn, verktygsloopen, felhanteringen och kostnadskontrollen finns redan. `tradar` lägger
till lagring per `view_key`, en andra ingång till sessionen (ett meddelande i stället för ett
underlag), och SSE ovanpå `agent_run_events` — som är därför de raderna har ett `seq`.

**Modellen per konversation landar i `tradar`, inte här.** Beslutet i §12.5 säger att en
konversation har en kontext och en modell. Trådar finns inte i den här modulen, så runtimen tar
modellen som ett argument och `agent_runs.model` bär svaret; `tradar` lägger kolumnen på tråden och
skickar in den samma väg. Det som byggs nu är alltså hela mekaniken — bara inte platsen där
människan klickar i sitt val.

Två saker `tradar` ärver och som är värda att veta redan nu:

- **Ett byte av modell mitt i en tråd ska vara synligt.** `agent_runs.model` och `.protocol` per
  kör gör det möjligt utan en ny tabell.
- **Protokollskillnaderna i §2 följer med upp.** En tråd på en Chat Completions-modell kan inte
  läsa PDF-underlag direkt och har ingen cache-ekonomi. Det är en produktsanning som hör hemma i
  gränssnittet, inte en detalj att dölja.

Schemaläggningen (§12.3) är den andra kvarvarande biten: den läggs på när ett pass är mätt, och
kräver inget mer än att `trigger` blir `'schedule'`.
