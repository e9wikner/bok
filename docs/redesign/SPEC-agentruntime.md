# Spec: `agentruntime`

Modul-id `agentruntime` i kapabilitetskartan (`ANALYS.md` §8). Beror på `idempotens`, som är
klar. Allt ovanför i byggordningen — `tradar`, `beslut`, `chattyta`, `flode-verifikationer` —
beror på den här.

Status: **Fas 1 — fem av sex frågor besvarade 2026-09-14 (se §12). §12.5 är omkullkastad:
runtimen ska vara leverantörsoberoende, inte Anthropic-bunden.** Det ändrar §2, §4 och §6 och
måste landa innan uppgifterna skrivs. Ingen kod, ingen `tasks/`-fil ännu.

---

## Antaganden

1. **Agenten är Claude via Anthropics API.** Repot har ingen LLM i dag
   (`grep -riE "openai|anthropic"` över `*.py` → 0 träffar, `requirements.txt` har ingen
   klient). Valet är alltså inte en migrering utan ett första val. Ingen annan leverantör
   förekommer i repot.
2. **Enbolag, en installation.** Runtimen behöver inte bära bolag i sin session.
3. **Agenten postar med `Idempotency-Key`.** Modulen `idempotens` är förutsättningen, inte en
   trevlighet: en worker som kraschar mitt i ett pass ska kunna köra om utan att förorena
   huvudboken. Se §6.4.
4. **Runtimen ersätter det manuella passet först, chatten sedan.** Det som finns i dag är en
   människa som startar en LLM som kör `scripts/bok-curl` en gång. Den här modulen tar bort
   människan ur den slingan. Tråd, SSE och beslutskort byggs i `tradar`/`beslut` ovanpå samma
   sessionsmotor.
5. **Bokföringsdata lämnar maskinen.** Underlag, kontoplan och verifikationstexter skickas till
   Anthropics API. Det är ett verkligt beslut, inte en teknikalitet. Se §12.4.

→ Punkt 1 och 5 är de dyra. Rätta mig där innan resten byggs.

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

En **worker i backend** som vaknar på intervall, tar ett underlag i taget ur kön, kör en
Claude-session med bolagets bokföringskontext och ett litet, typat verktygsset, och antingen
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
anthropic>=1.0          # officiell Python-SDK, inget annat sätt att nå API:t
```

Modell: **`claude-opus-5`** ($5 / $25 per miljon in/ut-token). Motiv: verktygsloopen fattar
bokföringsbeslut med rättslig verkan, och de fallen är precis de där en billigare modell kostar
mer — ett felaktigt konto rättas med B-serieverifikation, inte med en omkörning. `claude-sonnet-5`
($2 / $10) är rätt val först om mätning visar att kvaliteten håller. Det är inte mitt beslut att
ta i förväg, se §12.5.

Parametrar:

- `thinking={"type": "adaptive"}` — modellen väljer själv djup per underlag. Ett kvitto på 250 kr
  och en periodiserad leasingfaktura ska inte kosta lika mycket att tänka på.
- `output_config={"effort": "high"}` — `xhigh`/`max` sparas till fall som mätning visar behöver
  det. `low`/`medium` är rimliga för enkla kvitton om §12.5 landar i att differentiera.
- `.stream()` med `get_final_message()` — inte för att någon läser strömmen i den här modulen
  (det gör `tradar`), utan för att undvika HTTP-timeout på långa turer.
- **Ingen** `budget_tokens`. Den är borttagen på Opus 5 och ger 400.

---

## 3. Kommandon

Inga nya. Runtimen startar med API:t:

```bash
AGENT_RUNTIME_ENABLED=true ANTHROPIC_API_KEY=... python main.py
pytest tests/test_agent_runtime.py -v
```

Avstängd som standard, som dropzonen. En utvecklare som kör `python main.py` ska inte råka
starta en betald LLM-loop mot sin testdatabas.

---

## 4. Projektstruktur

```
services/agent_runtime.py      # AgentWorker + AgentRunner (tråd, flock, intervall, status)
services/agent_tools.py        # verktygsdefinitioner + utförare, ett verktyg per tillåten handling
services/agent_session.py      # Claude-anropet: systemprompt, cache, verktygsloop, felhantering
services/voucher_posting.py    # utbruten ur api/routes/agent.py — se §7
repositories/agent_run_repo.py # all SQL för agent_runs / agent_run_events
db/migrations/024_*.sql        # agent_runs, agent_run_events
api/routes/agent.py            # GET /agent/status ersätter operations/log-stubben
tests/test_agent_runtime.py
```

Lagren är de vanliga: ingen SQL utanför `repositories/`, inga HTTP-begrepp i `services/`.
`services/agent_session.py` är det enda stället som importerar `anthropic`.

---

## 5. Datamodell

```sql
CREATE TABLE agent_runs (
    id            TEXT PRIMARY KEY,
    trigger       TEXT NOT NULL,         -- 'schedule' | 'manual' | 'thread'
    status        TEXT NOT NULL,         -- 'running' | 'completed' | 'failed' | 'abandoned'
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    model         TEXT NOT NULL,
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

**Beloppen i ören, som allt annat i systemet.** `cost_ore` beräknas ur `response.usage` och
prislistan i `config.py`, inte ur en gissning.

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
vakna på intervall
  → finns en pågående kör med status='running' och en död tråd? markera 'abandoned', logga
  → hämta kön: IntakeService, samma vy som GET /agent/intake/pending
  → kön tom → sov vidare, skriv ingen agent_runs-rad
  → skapa agent_runs-rad (status='running')
  → för varje post, en i taget:
       → markera posten 'processing'
       → kör en Claude-session (§6.3) med posten som uppgift
       → utfallet är postning, avstående eller fel
       → budgettak nått (§6.5)? avsluta passet snyggt, resten ligger kvar i kön
  → status='completed', summera tokens och kostnad
```

En post i taget. Det är inte en optimering som väntar — det är hur `02_bokforingsprocess.md`
redan instruerar agenten ("one item at a time" står också i entrypointens guardrails), och det är
vad som gör ett avbrott billigt: allt utom den pågående posten är redan klart och committat.

### 6.3 Sessionen

Ett anrop per underlag, inte en session som lever över hela passet. Motivet är återställbarhet:
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
aktuella underlaget — metadata plus filen som `document`-block för PDF, `image`-block för foto.

**Verktygsloopen**: manuell `while stop_reason == "tool_use"`-loop, inte SDK:ns tool runner.
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
av sig själv innan någon hinner läsa en faktura. Vad som händer **vid** taket — stanna helt, eller
gå ned till en billigare modell — är §12.5.

### 6.6 Cache

Systemprompten (instruktioner + kontoplan + korrigeringar) är samma bytes för varje underlag i ett
pass och nästan samma mellan pass. Med en explicit brytpunkt sist i systemprompten läses den från
cache till ~0,1× priset i stället för att betalas fullt tjugo gånger per pass.

Tre fällor som tystar cachen och som ska testas, inte antas:

- **Ingen tidsstämpel i systemprompten.** `datetime.now()` någonstans i prefixet gör varje anrop
  till en missar. Dagens datum hör hemma i användarturen.
- **Deterministisk ordning.** Kontoplan och korrigeringar sorteras; verktygslistan byggs i fast
  ordning. Ett `dict` som råkar itereras i annan ordning är samma sak som en ändrad prompt.
- **Verifiera, gissa inte.** `usage.cache_read_input_tokens` ska vara > 0 från och med underlag
  två i ett pass. Är den noll finns en tyst invaliderare, och det är ett testfall.

### 6.7 Felhantering

| Fel | Svar |
|---|---|
| API nere, timeout, 5xx | SDK:n gör sina omförsök. Håller det i sig: underlaget tillbaka till `pending`, passet `failed`, exponentiell backoff |
| 429 | Respektera `retry-after`, avsluta passet, ta om vid nästa intervall |
| `stop_reason == "refusal"` | Registrera avstående med `stop_details.category`. Aldrig posta något efter en vägran |
| `stop_reason == "max_tokens"` | Avstående `agent_output_truncated`. En avhuggen tur får aldrig tolkas som ett beslut |
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
    "id": "...", "started_at": "...", "trigger": "schedule",
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

---

## 9. Teststrategi

`tests/test_agent_runtime.py`. Testerna skrivs före implementationen, som i `idempotens`.

**Anthropic-API:t anropas aldrig i tester.** En falsk klient returnerar förinspelade
`Message`-objekt. Det som testas är loopen, verktygen, budgetarna och felvägarna — inte att
modellen är klok. Ett test som kostar pengar körs inte i CI och är därför inte ett test.

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
| 11 | 429 med `retry-after` | Passet avslutas, nästa intervall försöker igen |
| 12 | Tråden dödas mitt i ett pass, ny start | Föregående kör `abandoned`, ingen dubbelpostning |
| 13 | Två workers, samma kö | `flock` släpper bara igenom en |
| 14 | Systemprompten byggd två gånger med samma data | Byte för byte identisk (cachetest) |
| 15 | Fem underlag i ett pass | `cache_read_input_tokens > 0` från och med nummer två |
| 16 | `AGENT_RUNTIME_ENABLED=false` | Ingen tråd, `status.enabled=false`, inget API-anrop |
| 17 | Verktygslistan | Innehåller inget verktyg som kan ändra eller radera en postad verifikation |

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
  inte bocken.

**Fråga först**

- Att låta runtimen skriva något annat än verifikationer och intagsutfall.
- Att höja dygnstaket, eller ändra vad som händer vid det.
- Att byta modell eller lägga till en andra modell.
- Varje ändring i `docs/to_agent/*.md`. Katalogen är runtime-innehåll och blir nu bokstavligen
  agentens systemprompt — en redigering där ändrar vad agenten gör, inte vad den läser om sig
  själv.

**Aldrig**

- Ett bash-, SQL-, filsystems- eller generellt HTTP-verktyg.
- Ett verktyg som ändrar eller raderar en postad verifikation. Korrigering går genom B-serien.
- Posta efter en vägran, en avhuggen tur, eller ett verktygsfel som modellen inte rättat.
- Låta en LLM-genererad sträng bli en verifikations `description` utan att den passerat
  `VoucherValidator` och spårbarhetskravet.
- Anropa Anthropics API i ett test.
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
9. Ingen testkörning träffar Anthropics API.
10. `tests/` grön, `black`/`isort`/`flake8`/`mypy` rena — läst i jobboutput.

---

## 12. Beslut och öppna frågor

Besvarade av beställaren 2026-09-14. Fem av sex är stängda; §12.5 är öppen igen i en annan form
och blockerar uppgiftslistan.

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

### 12.5 Modellval — **OMKULLKASTAD: runtimen ska vara leverantörsoberoende**

Svar 2026-09-14: *"Jag vill kunna koppla vilken LLM-provider och modell jag vill. Exempelvis
Opencode skall kunna köra detta."*

Det är inte ett val mellan Opus och Sonnet utan ett krav som ändrar §2, §4 och §6: specen är
skriven mot Anthropics SDK och mot parametrar bara den har (`thinking`, `output_config.effort`,
cache-prefixets ekonomi, `usage`-fälten som `cost_ore` räknas ur). Vad kravet kostar och exakt
vilken form det tar är **den fråga som nu blockerar uppgiftslistan** — se §12.5b.

Den ursprungliga frågan, som underlag:

`claude-opus-5` för allt var rekommendationen och specens utgångspunkt. Alternativ: `claude-sonnet-5`
($2/$10) för enkla kvitton och Opus för resten. Två invändningar mot att differentiera nu: cachen
är modellbunden, så två modeller i samma pass betalar prefixet två gånger, och vi har ingen mätning
som säger att Sonnet räcker. Rätt ordning är att bygga på Opus, mäta, och sedan sänka — inte tvärtom.

Relaterat: vad händer vid dygnstaket? Stanna, eller gå ned till en billigare modell och fortsätta?
Jag föreslår **stanna** — ett tak som sänker kvaliteten i stället för att stoppa är ett tak som
tyst börjar bokföra sämre när det är som mest att göra.

### 12.5b Vad leverantörsoberoende betyder konkret — **ÖPPEN, blockerar uppgifterna**

Tre former, med olika pris:

1. **Intern adapter.** `services/agent_session.py` blir ett tunt gränssnitt med en adapter per
   leverantör, valda via `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY`. Störst
   arbete i den här modulen, och den minsta gemensamma nämnaren blir OpenAI-kompatibel
   verktygsanropsform — vilket betyder att `thinking`, `effort` och cache-ekonomin i §2 blir
   valfria finesser i Anthropic-adaptern i stället för specens grundantagande. `cost_ore` behöver
   en prislista per leverantör och modell i `config.py`, annars blir kostnadstaket en gissning.
2. **Extern harness.** Bok bygger ingen egen LLM-klient alls. Runtimen blir en kö och ett
   verktygs-API, och en harness utanför — Opencode, Claude Code, vad som helst — kör modellen och
   anropar bok. Billigast för bok, men då finns ingen `AgentWorker` som kör av sig själv, och
   `GET /agent/status` kan bara rapportera vad harnessen hunnit berätta.
3. **Båda.** Intern adapter för det schemalagda passet, och verktygs-API:t hålls skarpt nog att en
   extern harness kan köra samma sak. Dyrast, men det är den enda varianten där både "agenten
   sköter sig själv" och "jag kör den med mitt eget verktyg" är sanna.

Relaterat, och fortfarande obesvarat oavsett form: vad händer vid dygnstaket? Förslaget står kvar
— **stanna**, inte gå ned till en billigare modell, eftersom ett tak som sänker kvaliteten börjar
bokföra sämre precis när det är som mest att göra.

### 12.6 Var bor nyckeln på hubbabubba? — **BESLUTAT: `bok.env`**

Beslut 2026-09-14: API-nyckeln bor i `/srv/appdata/bok/bok.env` bredvid `BOKFOERING_API_KEY`, med
filrättigheterna som skydd. **Gräns som ska stå i implementationen:** nyckeln når aldrig
`GET /agent/status` och aldrig `agent_run_events` — varken hel eller maskerad.

Underlaget:

`ANTHROPIC_API_KEY` i `/srv/appdata/bok/bok.env`, som `BOKFOERING_API_KEY`? Det är det enkla svaret
och det som passar quadlet-uppsättningen. Bekräfta bara att den filens rättigheter är det skydd vi
tänker oss, och att nyckeln aldrig ska hamna i `GET /agent/status` eller i `agent_run_events`.

---

---

## 13. Vad som händer sedan

När `agentruntime` är klar är `tradar` ett mycket mindre problem än det ser ut i `ANALYS.md` §4:
sessionsmotorn, verktygsloopen, felhanteringen och kostnadskontrollen finns redan. `tradar` lägger
till lagring per `view_key`, en andra ingång till sessionen (ett meddelande i stället för ett
underlag), och SSE ovanpå `agent_run_events` — som är därför de raderna har ett `seq`.
