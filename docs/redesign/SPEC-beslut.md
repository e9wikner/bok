# Spec: `beslut`

Modul-id `beslut` i kapabilitetskartan (`ANALYS.md` §8). Beror på `tradar`, som är klar
(T1–T14, `6079ef3`). `chattyta` och `flode-verifikationer` beror på den här.

Status: **Fas 1 — skriven 2026-09-21.** Två beslut tagna i förväg av beställaren (§11.1–§11.2):
eskaleringsregeln `decision` kontra `options`, och att `GET /decisions` unionar dagens två källor.
Uppgifterna ligger i `tasks/beslut/plan.md` och `tasks/beslut/todo.md` (B1–B12). Ingen kod
skriven ännu.

---

## Antaganden

1. **Trådlagret finns och ska inte byggas om.** `thread_posts` bär redan `decision` och `options`
   i sitt `CHECK`-villkor, `ThreadService._render` skriver redan ett `decision`-inlägg när
   `registrera_avstaende` körts, och `ThreadTurnRunner` kör redan en tur i egen arbetstråd med
   SSE. Den här modulen lägger till **livscykeln** ovanpå det, inte en andra trådmodell.
2. **Ett inlägg ändras aldrig** (`SPEC-tradar.md` §8.4). Ett beslut som besvaras får därför inte
   lagra sin status i `thread_posts`. Statusen bor i en egen tabell; inlägget står kvar som det
   människan såg.
3. **Append-only i huvudboken är oförhandlingsbart.** Ett svar på ett beslut postar ingenting av
   sig självt. Det skriver ett inlägg och startar en tur; postningen går som alltid genom
   `services/voucher_posting.py` med `Idempotency-Key`.
4. **Verktygsytan utökas — en gång, med avsikt.** Det här är den enda modulen i redesignen som
   lägger till ett verktyg, och §8 säger varför det inte går att undvika och vad det inte får bli.
5. **Enbolag.** Designens *"Om någon annan i bolaget svarar först byts kortet mot vem som
   beslutade och när"* är noterad och inte budgeterad; `answered_by` finns i schemat, men det
   finns inte två människor att skilja åt. Samma hållning som `SPEC-tradar.md` §12.2.

→ Punkt 2 och 4 är de som kostar om de glöms.

---

## 1. Objektiv

### Problemet, konkret

`datakontrakt.md` §2, under rubriken **Beslut som en förstklassig sak**:

> `GET /agent/intake/pending` är agentens kö och blandar källmaterial med korrigeringsnoteringar.
> Designen behöver de fall **där agenten avstått**, med agentens egen formulering.

Det som finns efter `tradar`: ett `decision`-inlägg hamnar i tråden när agenten avstått, med
agentens egen text i `reason`. Det som saknas är allt som gör det till *en sak*:

- Det går inte att **lista** öppna beslut. `GET /decisions` finns inte.
- Det går inte att **svara** på ett. `POST /decisions/{id}/answer` finns inte.
- Beslutet har ingen **status**. Ett `decision`-inlägg är öppet för evigt, eftersom inlägg inte
  ändras.
- Beslutet har ingen **ålder**, och `VyRad`-varianten `saknar`/`vantar` färgas av `age_days`.
- Agenten kan inte **lägga fram alternativ**. `options` står i `CHECK`-villkoret men ingen kod
  producerar den typen — `grep -rn '"options"' --include='*.py'` ger två träffar, och båda är
  listan över lagliga typer: `repositories/thread_repo.py:30` och `tests/test_tradar.py:251`.
  Samma sak gäller `draft` och `receipt`.
- `services/overview.py:120` räknar öppna beslut med en dokumenterad approximation, och dess
  docstring pekar hit: *"The final home is GET /decisions?status=open."*

### Vad vi bygger

```
GET  /api/v1/decisions?status=open            → besluten, äldst först
GET  /api/v1/decisions/{id}                   → ett beslut
POST /api/v1/decisions/{id}/answer            → { option_id } eller { free_text }
```

plus tabellen under dem, verktyget som låter agenten lägga fram ett beslut eller en
alternativlista (§6.4), eskaleringsinvarianten (§11.1), och utbytet av `open_decisions`
approximation mot den riktiga uträkningen.

### Vad vi inte bygger här

Ingen frontend — `BeslutKort`, `AlternativLista`, `AlternativRad` och `RekMarke` hör till
`chattyta`. Ingen tolkning av underlag (`underlagstolkning`); flöde 4:s matchning är den modulens.
Inget `draft`- eller `receipt`-inlägg: `VerifikationsForslag` är `flode-verifikationer`, och det
är den modulen som stänger kedjan beslut → förslag → postning → låst. Lönens fyra spår är ur
scope (`ANALYS.md` §2).

### Framgång

1. Agenten avstår, och avståendet går att lista, läsa och svara på — med agentens egen text.
2. Ett svar på ett beslut startar en tur i tråden där beslutet togs, och svaret syns i tråden
   innan agenten har sagt något.
3. Ett beslut kan besvaras en gång. Ett andra svar ger `409` med det befintliga svaret.
4. En `options`-lista som skulle ändra böckerna utan ett öppet beslut bakom sig avvisas.
5. `GET /overview` räknar öppna beslut ur `GET /decisions` och tappar inte sina siffror den dag
   modulen driftsätts.

---

## 2. Vad `tradar` faktiskt lämnade efter sig

Fyra saker står redo och ska användas som de är:

- **`decision`-inlägget skrivs redan.** `services/thread_service.py:197` `_decision_body()` bygger
  `BeslutKort`s kropp ur `registrera_avstaende`-utfallet, med kommentaren *"The agent's own
  wording is the point … It is never rewritten here."* Den funktionen flyttas inte; den får en
  `decision_id` att bära.
- **Tråden vet vilken vy den hör till.** `threads.view_key` är exakt det `datakontrakt.md` §2 ber
  om som `view_key` på beslutet, och det behöver därför inte lagras en andra gång.
- **Turen går att starta från vad som helst.** `ThreadTurnRunner.start(thread, trigger_post,
  message, …)` tar ett utlösande inlägg och en text. Ett besvarat beslut är precis det: ett
  inlägg och en text. Svarsvägen är alltså inte en andra sessionsmotor, bara en andra anropare.
- **Idempotensnamnrymden finns.** `SPEC-tradar.md` §6.4 hänger postningsnyckeln på det utlösande
  användarinlägget: `uuid5(BOK_NAMESPACE, f"thread:{thread_id}:{post_id}")`. Ett svarsinlägg är ett
  användarinlägg och ärver den regeln oförändrad — ingen tredje namnrymd.

Tre saker saknas, och de är det modulen faktiskt är:

**1. Ingen status någonstans.** `thread_posts` ändras inte, så `open` → `answered` kan inte bo
där. Det är skälet till att §4 lägger till en tabell och inte en kolumn.

**2. Agenten kan inte lägga fram ett beslut avsiktligt.** `registrera_avstaende` tar
`source_id`, `summary`, `error_detail`, `warnings` — den är byggd för **ett underlag i kön** och
skriver ett `failed`-försök på `intake_sources` via `IntakeService.record_failed`
(`services/agent_tools.py:546`). Ett beslut som uppstår mitt i ett samtal har inget `source_id`.
Och alternativ — `account`, `amount`, `rationale`, `recommended` — finns det ingen väg att
uttrycka alls. Det är §6.4.

**3. `open_decisions` är en approximation som pekar hit.** Två källor summeras
(`services/overview.py:120`): `intake_sources` med `failed`/`needs_attention`, och
`correction_notes` med `pending`/`suggested`. `SPEC-oversikt.md` säger vad som ska hända:
*"När `beslut` kommer byter den ut uträkningen bakom fältet — inte fältet."*

---

## 3. Tech stack

Inget nytt beroende. FastAPI-rutt, Pydantic-scheman, en migration, en repository-klass, en
service. Samma form som `tradar`.

`db/database.py` delar ut **trådlokala** SQLite-anslutningar med WAL. Svarsvägen startar en tur i
en arbetstråd precis som `POST /threads/{view_key}/messages` gör, via samma `ThreadTurnRunner`,
och rutten returnerar innan turen är klar.

---

## 4. Datamodell

Migration `026_add_decisions.sql`. Ny fil; `001`–`025` redigeras aldrig.

```sql
CREATE TABLE IF NOT EXISTS decisions (
    id              TEXT PRIMARY KEY,
    thread_id       TEXT NOT NULL,
    post_id         TEXT NOT NULL,
    view_key        TEXT NOT NULL,
    kind            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    title           TEXT NOT NULL,
    amount_ore      INTEGER,
    reason          TEXT NOT NULL,
    consequence     TEXT NOT NULL,
    source_kind     TEXT,
    source_id       TEXT,
    source_date     DATE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    answered_at     TIMESTAMP,
    answered_by     TEXT,
    answer_option_id TEXT,
    answer_text     TEXT,
    answer_post_id  TEXT,
    reminded_at     TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES thread_posts(id),
    FOREIGN KEY (answer_post_id) REFERENCES thread_posts(id),
    UNIQUE (post_id),
    CHECK (kind IN ('abstention', 'approval')),
    CHECK (status IN ('open', 'answered', 'superseded')),
    CHECK (status != 'answered' OR answered_at IS NOT NULL),
    CHECK (status != 'answered' OR answer_option_id IS NOT NULL OR answer_text IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS decision_options (
    id           TEXT PRIMARY KEY,
    decision_id  TEXT NOT NULL,
    position     INTEGER NOT NULL,
    title        TEXT NOT NULL,
    account      TEXT,
    amount_ore   INTEGER,
    rationale    TEXT NOT NULL,
    recommended  INTEGER NOT NULL DEFAULT 0,
    is_exit      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE,
    UNIQUE (decision_id, position),
    CHECK (recommended IN (0, 1)),
    CHECK (is_exit IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_thread ON decisions(thread_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (26);
```

Varför varje ovanlig sak står där:

**`UNIQUE (post_id)`** — ett `decision`-inlägg bär exakt ett beslut. Utan villkoret kan samma kort
i tråden svara mot två rader med olika status, och gränssnittet visar då ett kort vars knappar
gör olika saker beroende på vilken rad som lästes.

**De två `CHECK`-villkoren på `answered`** är svarets integritet i schemat i stället för i en
service som kan ha en bugg — samma hållning som append-only-reglerna i AGENTS.md. Ett besvarat
beslut utan tidpunkt, eller utan vare sig `option_id` eller fritext, är inte ett svar.

**`amount_ore`, inte `amount`.** Kronor i heltal öre, som resten av kodbasen. `BeslutKort` visar
beloppet med tabulära siffror och `−` (U+2212); formateringen är klientens, talet är serverns.

**`status = 'superseded'`** finns för ett fall som uppstår på riktigt: beslutet blir irrelevant
utan att någon svarade — underlaget raderas, verifikationen korrigeras på annat håll, perioden
låses. Alternativet vore att radera raden, och ett beslut som försvinner ur listan utan spår är
precis vad tråden finns för att förhindra. `superseded` lämnar kortet i tråden och tar bort det
ur kön.

**`reminded_at`** bär designens påminnelseregel, flöde 1 steg 1: *"Ett beslut som legat mer än sju
dagar påminner agenten om en gång, inte varje körning."* En kolumn, inte en jobbtabell: det är
en gång per beslut, och `NULL` betyder att det inte har hänt.

**`decision_options` som egen tabell, inte JSON i `decisions`.** `option_id` i svaret ska gå att
kontrollera mot det som faktiskt lades fram, och `position` bär ordningen alternativen visades i —
vilket är en del av kontraktet, eftersom sista alternativet alltid är en väg ut (§6.3).
`is_exit` är den flaggan.

### `options`-inlägget

En alternativlista skriven av agenten blir ett `options`-inlägg i tråden **och** rader i
`decision_options` under samma `decision`. Inlägget är vad människan såg; tabellen är vad hon kan
svara på. Formen i `body_json` följer `SPEC-tradar.md` §6.2 oförändrad:

```json
{"decision_id": "…",
 "options": [{"option_id": "…", "title": "Förbrukningsinventarier", "account": "5410",
              "amount_ore": 358400, "rationale": "Kostnadsförs direkt i juni…",
              "recommended": true, "is_exit": false}],
 "footnote": "Moms 25 % · 896 kr dras av i båda alternativen"}
```

`footnote` är `AlternativLista`s fot i `komponenter.md`: *"ett villkor som gäller alla
alternativ"*. Den är agentens text och räknas inte om av klienten.

---

## 5. De tre källorna

Beslutet i §11.2 är att `GET /decisions` unionar. Tre `kind`-värden i svaret, en id-rymd per
källa, och `kind` är det som skiljer dem åt:

| `kind` | Källa | `id` | Agentens egen text finns? |
|---|---|---|---|
| `abstention` | `decisions` (ny tabell) | `decisions.id` | ja, `reason` |
| `intake` | `intake_sources` med `failed`/`needs_attention` | `intake:{source_id}` | ja, ur senaste `intake_processing_attempts.summary` / `error_detail` |
| `correction` | `correction_notes` med `pending`/`suggested` | `correction:{note_id}` | nej — `note_text` är **människans** text |

De två syntetiska källorna är **läsbara men inte besvarbara via den här modulen**:
`POST /decisions/{id}/answer` på ett `intake:`- eller `correction:`-id svarar `409` med
`code: "decision_not_answerable"` och pekar på den befintliga vägen
(`PUT /intake/{id}/agent-guidance`, `POST /vouchers/{id}/correction-notes/{note_id}/suggest`).

Det är medvetet och det är hela priset för §11.2. Skälet att ändå unionera är att `open_decisions`
i headern ska vara sann: en backlog som inte syns är en backlog som inte arbetas av. Skälet att
inte göra dem besvarbara är att en svarsväg som ser likadan ut men går till ett annat flöde är
värre än ingen svarsväg alls — och `correction_notes.note_text` är dessutom inte agentens
formulering, vilket kortet bygger hela sin trovärdighet på.

**Unionen är övergående.** Den dag agenten kör allt intag genom `be_om_beslut` (§6.4) blir
`intake`-raderna tomma av sig själva, utan en migrering och utan en dag då siffran hoppar.
`correction`-raderna lever tills `flode-verifikationer` äger korrigeringsvägen.

---

## 6. Beteende

### 6.1 `GET /decisions`

```
GET /api/v1/decisions?status=open&view_key=bocker.verifikationer&limit=50&offset=0
```

`status` är `open` (förvalt), `answered` eller `all`. `view_key` filtrerar och valideras mot de
sju (`ThreadViewKey`); en okänd nyckel ger `404`, samma regel som `SPEC-tradar.md` §5.

Svaret, per `datakontrakt.md` §2:

```json
{"decisions": [
  {"id": "…", "view_key": "bocker.verifikationer", "kind": "abstention",
   "status": "open", "title": "Kortköp Elektronikhuset", "amount_ore": 448000,
   "reason": "Kvittot saknas och beloppet ligger nära gränsen för förbrukningsinventarier…",
   "consequence": "Ingenting är bokfört. Beslutet ligger kvar tills du svarar på det.",
   "source": {"kind": "bank_input", "id": "…", "date": "2026-06-03"},
   "age_days": 3, "thread_id": "…", "post_id": "…",
   "options": [ … ]}],
 "total": 2}
```

**Äldst först.** Flöde 1 steg 1: *"Flera obesluta händelser: en i taget i tråden, äldst först,
resten som rader i vyn."*

`age_days` räknas från `created_at` till i dag. **Vilka trösklar som gör raden gul eller röd är
inte den här modulens beslut** — det är samma öppna fråga som `oversikt` lämnade och som
`tasks/skal/todo.md` noterar att `VyRad`-varianten `saknar` fortfarande väntar på. Servern ger
talet; färgen är `chattyta`s, den dag talet finns.

`options` är med i listsvaret därför att `BeslutKort` och `AlternativLista` renderas i samma tråd
och ett andra anrop per kort skulle göra vyn till en vattenfallsladdning. Är listan tom har
agenten ännu inte lagt fram några alternativ — vilket flöde 1 steg 1 är: kortet kommer först,
alternativen när människan ber om dem.

### 6.2 `POST /decisions/{id}/answer`

Kroppen är `{ "option_id": "…" }` **eller** `{ "free_text": "…" }` — exakt en av dem. Båda, eller
ingen, ger `400`.

Fritextvägen är inte en artighet. `README.md`, Tillgänglighet: *"Beslutskortets primärknapp är
aldrig den enda vägen: samma beslut ska gå att uttrycka i text i chattfältet."* Ett svar som bara
går att ge med ett musklick är ett gränssnitt som utesluter folk, och `ANALYS.md` §3 räknar det
till designens styrkor.

Steg för steg:

1. Slå upp beslutet. Okänt id → `404`. Syntetiskt id (`intake:`/`correction:`) → `409`
   `decision_not_answerable` (§5).
2. Redan besvarat → `409` med `answered_at`, `answer_post_id` och svaret som gavs. Inte `400`:
   klienten ska kunna visa klart-läget i stället för ett fel, vilket är samma regel som
   `datakontrakt.md` §3 ställer på postningen.
3. `option_id` valideras mot `decision_options` för **det här** beslutet. Ett id från ett annat
   beslut är `400`, inte en tyst uppslagning som råkar träffa.
4. Skriv ett `user_text`-inlägg i beslutets tråd med svaret som text — alternativets titel och
   konto, eller fritexten ordagrant. Det är människans replik, och den ska stå i tråden innan
   agenten har sagt något (samma regel som `SPEC-tradar.md` §6.1 steg 2).
5. Sätt `status='answered'`, `answered_at`, `answered_by`, `answer_option_id` / `answer_text`,
   `answer_post_id` — i **en** transaktion med steg 4.
6. Starta turen: `ThreadTurnRunner.start(thread, trigger_post=svarsinlägget, message=svarstexten)`.
7. Returnera `202` med beslutet i sitt nya läge och svarsinläggets `id` och `seq`.

Turen är inte inväntad. Svaret på ett beslut går samma väg som ett meddelande, och agentens svar
kommer över SSE — det är hela poängen med `tradar`s ström.

**Steg 4 och 5 i samma transaktion** är det som gör dubbelsvar omöjligt. Delade de transaktion
skulle två tryck kunna skriva två inlägg innan någon av dem hann sätta status, och tråden fick
två repliker på ett kort som bara har ett svar.

### 6.3 Eskaleringsinvarianten

Beslutet i §11.1, som en regel koden kan kontrollera:

> En `options`-lista vars alternativ ändrar resultat, moms eller en period, och som inte ligger
> under ett öppet `decision`, avvisas. Agenten får lägga fram beslutet först.

Två följdregler ur `komponenter.md`, som hör till kontraktet och inte till klienten
(`SPEC-tradar.md` §6.2 räknar upp dem; här är de villkor som valideras när listan skrivs):

- **Ingen rekommendation är förvald.** `recommended: true` är ett märke. `AlternativRad` har en
  tom ring. Fler än ett `recommended` bland alternativen är ett fel.
- **Sista alternativet är alltid en väg ut** (`Annat konto`, `Det är ett annat köp`). En lista
  vars sista rad inte har `is_exit` avvisas — annars är alternativen en meny utan dörr, och
  designen är uttrycklig om att det sista alternativet är en väg ut.

Hur "ändrar böckerna" avgörs: ett alternativ som bär `account` **och** `amount_ore ≠ 0` skriver en
rad i huvudboken om det väljs. Ett alternativ utan konto, eller med noll, gör det inte. Det är
härlett ur alternativen själva och kräver ingen ny uppgift från agenten — vilket är vad som gör
regeln testbar i stället för promptberoende.

### 6.4 Verktyget

Redesignens enda nya verktyg, och `SPEC-tradar.md` §8.2 säger uttryckligen att ett tionde verktyg
är ett "fråga först". Frågan är ställd och besvarad här, med motiveringen i §11.3.

```
be_om_beslut(title, reason, consequence, amount_ore=None,
             source=None, options=[], kind="abstention")
```

Det skriver ett `decision`-inlägg (och ett `options`-inlägg om `options` är ifyllt), en rad i
`decisions`, och rader i `decision_options`. Det postar ingenting, det ändrar ingenting, det läser
ingenting utanför sin egen tabell.

`registrera_avstaende` **står kvar orört.** Det är dokumentvägens verktyg, det skriver ett
`failed`-försök på ett underlag i kön, och `tests/test_agent_runtime.py` står på det. De två
överlappar i vad de uttrycker men inte i vad de rör: det ena hör till en post i intagskön, det
andra till ett samtal i en vy. Att slå ihop dem vore en refaktorering av en klar modul mitt i en
ny, och `ANALYS.md` §7 är emot precis det.

`AGENT_TOOL_DEFINITIONS`-ordningen är en del av det cachade systempromptprefixet
(`SPEC-agentruntime.md` §6.6). Det nya verktyget läggs **sist** i `_TOOL_SPECS`, aldrig i mitten.

### 6.5 Påminnelsen

Flöde 1 steg 1: *"Ett beslut som legat mer än sju dagar påminner agenten om en gång, inte varje
körning."*

Ett öppet beslut med `age_days >= 7` och `reminded_at IS NULL` ger ett `agent_text`-inlägg i sin
tråd och sätter `reminded_at`. Kontrollen sker i intagspassets befintliga cykel — ingen ny
schemaläggare, ingen ny tråd. Tonen är designens: flöde 4 steg 1 säger *"Mycket gamla
kompletteringar hör hemma i en påminnelse, inte i samma neutrala ton som färska."*

`reminded_at` är skälet till att det blir en gång. Utan kolumnen påminner varje körning, vilket är
exakt vad meningen förbjuder.

### 6.6 `open_decisions` byter uträkning

`services/overview.py:120` `_count_open_decisions()` blir
`DecisionService().count_open()`. Docstringens *"Approximation until the `beslut` module owns
this"* tas bort — den är inte längre sann.

Fältet ändras inte. `SPEC-oversikt.md`: *"När `beslut` kommer byter den ut uträkningen bakom
fältet — inte fältet."* Med unionen i §11.2 ger den nya uträkningen samma tal som den gamla dag
ett, plus de nya besluten. Det finns alltså ingen dag då siffran hoppar, och inget test i
`tests/test_oversikt.py` som behöver skrivas om för att sluta vara sant.

### 6.7 Felhantering

Ärvs från `SPEC-tradar.md` §6.7. En tur som startats av ett besvarat beslut och havererar blir ett
`error`-inlägg med orsak *och* konsekvens i bokföringstermer — i tråden där beslutet togs.

**Beslutet går inte tillbaka till `open` när turen misslyckas.** Svaret gavs; det var turen som
inte gick fram. `FelKort`s `Försök igen` bär samma utkast-id (`komponenter.md`), och att öppna
beslutet igen skulle betyda att människan ombeds fatta ett beslut hon redan fattat. Flöde 1 steg 6
säger det rakt ut: *"förslaget ligger kvar så att försöket kan göras om"*.

---

## 7. Gränser

1. **Ett `decision`- eller `options`-inlägg ändras aldrig.** Status bor i `decisions`. Ett kort i
   tråden är vad människan såg, i det skick hon såg det.
2. **Ett svar postar ingenting direkt.** Det skriver ett inlägg och startar en tur. Vägen till
   huvudboken är `services/voucher_posting.py` och ingen annan.
3. **Klienten hittar inte på alternativ och räknar inte om belopp.** `datakontrakt.md` §2, ordagrant.
   Servern äger `rationale`, `recommended`, `footnote` och varje tal.
4. **Agentens text skrivs aldrig om.** `reason`, `consequence` och `rationale` lagras som agenten
   formulerade dem. `ANALYS.md` §7, och `_decision_body`s egen kommentar.
5. **Ett beslut besvaras en gång.** Andra svaret är `409` med det befintliga, aldrig ett andra
   inlägg.
6. **Runtimen får inte veta vad ett beslut är.** Samma gräns som `SPEC-tradar.md` §8.1 drar för
   tråden: `services/agent_runtime.py` och `services/agent_session.py` ser ett verktygsanrop, inte
   en livscykel.
7. **`anthropic` och `openai` importeras bara i `services/llm/`.**

**Fråga först:** ett elfte verktyg, en fjärde `kind`, en svarsväg för de syntetiska källorna, en
`decisions`-rad utan `thread_id`, eller en ändring i `docs/to_agent/`.

---

## 8. Det nya verktyget — varför det inte går att undvika

`SPEC-tradar.md` §8.2: *"Verktygsytan utökas inte. Ett bekvämt trådverktyg är den enda vägen förbi
append-only som inte går genom en migration, och testfall 17 finns för att gå sönder då."*

Regeln gäller fortfarande. Det här verktyget bryter inte mot den, och skälet är vad verktyget
*får göra*: `be_om_beslut` skriver till `decisions`, `decision_options` och `thread_posts`. Det rör
inte `vouchers`, `voucher_lines`, `periods` eller `fiscal_years`. Testfall 17 —
att ingen väg genom verktygsytan ändrar eller raderar en postad verifikation — körs mot den
utökade listan och ska passera oförändrat.

Alternativen som övervägdes och varför de faller:

- **Låt `registrera_avstaende` ta alternativ.** Det ändrar dokumentvägens verktyg mitt i en ny
  modul, och `source_id` är obligatoriskt där — ett beslut i ett samtal har inget underlag.
- **Härled beslut ur agentens fritext.** En LLM-text som tolkas till strukturerade alternativ med
  konto och belopp är precis den andrahandstext `ANALYS.md` §7 varnar för, och den skulle ligga
  till grund för en postning.
- **Låt människan skapa beslut.** Då är det inte agenten som avstod, och kortets rubrikrad
  (*"Agenten avstod · behöver ditt beslut"*) blir en lögn.

---

## 9. Teststrategi

Ny fil `tests/test_beslut.py`. Testerna skrivs **före** implementationen.

LLM:en fejkas med `FakeLLMClient`-mönstret från `tests/test_agent_runtime.py`, injicerad via
`client_factory`, aldrig monkeypatch. **Inget nätverksanrop i något test.** Turen körs synkront
via `ThreadTurnRunner.run` (inte `.start`), som `tests/test_tradar.py` redan gör.

| # | Testfall |
|---|---|
| 1 | `UNIQUE (post_id)`: två beslut på samma inlägg avvisas av schemat |
| 2 | `status='answered'` utan `answered_at` avvisas av `CHECK` |
| 3 | `status='answered'` utan vare sig `option_id` eller fritext avvisas av `CHECK` |
| 4 | En fjärde `kind` och en fjärde `status` avvisas av `CHECK` |
| 5 | `GET /decisions?status=open` ger äldst först |
| 6 | `GET /decisions` unionar `decisions`, `intake_sources` och `correction_notes` |
| 7 | Unionens id:n är prefixade och kolliderar inte mellan källorna |
| 8 | `intake`-radens `reason` är agentens text ur senaste försöket, inte filnamnet |
| 9 | `view_key`-filtret validerar mot de sju; okänd nyckel ger `404` |
| 10 | `age_days` räknas från `created_at` och är `0` för ett beslut skapat i dag |
| 11 | Ett svar med `option_id` skriver `user_text` **före** att turen startar |
| 12 | Ett svar med `free_text` gör samma sak, ordagrant |
| 13 | Både `option_id` och `free_text` ger `400`; ingetdera ger `400` |
| 14 | `option_id` från ett annat beslut ger `400` |
| 15 | Andra svaret ger `409` med `answered_at` och `answer_post_id` — inte ett andra inlägg |
| 16 | Svar på `intake:`/`correction:` ger `409 decision_not_answerable` |
| 17 | Svarsinlägg och statusändring sker i **en** transaktion: en rullad transaktion lämnar varken inlägg eller status |
| 18 | Ett besvarat beslut faller ur `status=open` och ur `open_decisions` |
| 19 | **Eskaleringsinvarianten:** en `options`-lista som ändrar böckerna utan öppet beslut avvisas |
| 20 | En `options`-lista under ett öppet beslut tillåts, även när alternativen ändrar resultatet (flöde 1 steg 2) |
| 21 | En `options`-lista som inte ändrar böckerna tillåts utan öppet beslut (flöde 4, `koppla utan att ändra`) |
| 22 | Fler än ett `recommended` avvisas |
| 23 | Sista alternativet utan `is_exit` avvisas |
| 24 | `be_om_beslut` skriver `decision`-inlägg, `decisions`-rad och `decision_options` i rätt ordning |
| 25 | `be_om_beslut` ligger **sist** i `AGENT_TOOL_DEFINITIONS` |
| 26 | **Testfall 17 från `agentruntime`:** ingen väg genom den utökade verktygsytan ändrar eller raderar en postad verifikation |
| 27 | `registrera_avstaende` beter sig exakt som före modulen — hela sviten grön |
| 28 | En postning i en tur startad av ett svar bär `thread:{thread_id}:{post_id}`-nyckeln |
| 29 | Två svar på samma beslut ger aldrig två verifikationer |
| 30 | En havererad tur ger ett `error`-inlägg och lämnar beslutet `answered` |
| 31 | Påminnelsen skrivs vid sju dagar och **inte** en andra gång |
| 32 | `superseded` tar beslutet ur kön men lämnar inlägget i tråden |
| 33 | `open_decisions` i `GET /overview` ger samma tal före och efter bytet av uträkning |
| 34 | Agentens text i `reason`, `consequence` och `rationale` lagras oförändrad |

---

## 10. Framgångskriterier

1. De tre endpointsen svarar enligt `datakontrakt.md` §2.
2. Ett avstående går att lista, läsa och svara på, med agentens egen formulering intakt.
3. Ett beslut besvaras en gång; andra svaret är `409` med det befintliga.
4. Svarsinlägg och statusändring är atomära.
5. Fritextsvar fungerar överallt där knappsvar fungerar.
6. Eskaleringsinvarianten är pinnad av testfall 19–21 och stämmer mot alla fyra fall designen ritar.
7. `AlternativLista`s två kontraktsregler — ingen förvald rekommendation, sista raden är en väg ut
   — valideras på servern.
8. Testfall 17 från `agentruntime` passerar mot den utökade verktygsytan.
9. `registrera_avstaende` och dokumentvägen är oförändrade; hela sviten grön.
10. `open_decisions` ger samma tal dag ett som approximationen gav dag noll.
11. En postning i en tur startad av ett svar dubbelpostar inte.
12. Påminnelsen kommer en gång, inte varje körning.
13. `pytest tests/ -v` grön; `black`, `isort`, `flake8` rena; inga nya `mypy`-fel i modulens filer.

---

## 11. Beslut

### 11.1 Tröskeln `decision` kontra `options` — **BESLUTAT: täckt av ett öppet beslut**

Besvarar designens öppna fråga 3 (`README.md`) och `ANALYS.md` §9.5: *"Vilken tröskel gör en
avvikelse till ett beslutskort i stället för ett val — underlagsflödets 120 kr är satt på känsla."*

De två korten har olika livscykel, och det är skillnaden som bär: ett `decision` är ett spårat,
räknat, åldrande objekt som någon måste komma tillbaka till; ett `options` är en fråga till någon
som står här nu. I flöde 1 är de inte ett vägval utan två steg — kortet finns för att ingen var
närvarande 06:41, listan för att någon är närvarande 09:12.

Regeln:

> Varje ändring i böckerna som en människa valde är antingen **(a)** tagen inuti ett redan öppet,
> spårat beslut, eller **(b)** själv ett spårat beslut. En `options`-lista som ändrar resultat,
> moms eller en period utan att ligga under ett öppet `decision` är det förbjudna fallet.

Den stämmer mot alla fyra ställen designen ritar:

| Fall | Öppet beslut? | Ändrar böckerna? | Blir | Designen |
|---|---|---|---|---|
| Flöde 1 steg 2 — 5410 mot 1250 | ja | ja | `options` | alternativlista ✓ |
| Flöde 4 — exakt match | nej | nej | hoppas över | *"Exakt match ska hoppa över det här steget"* ✓ |
| Flöde 4 — `koppla utan att ändra` | nej | nej | `options` | alternativlista ✓ |
| Flöde 4 — `bokför skillnaden 120 kr` | nej | **ja** | `decision` | *"bör bli ett beslutskort"* ✓ |

Alternativet var en krongräns i `config.py`. Den faller på att 120 kr då blir ett val i strid med
designens egen kant, medan flöde 1:s 4 480 kr förblir en lista — talet skulle alltså behöva ligga
mellan 120 och 4 480 utan något som säger var, vilket är definitionen av "satt på känsla". Att
låta agenten avgöra faller på att gränsen mot böckerna då blir icke-deterministisk och omöjlig att
pinna i test.

Priset: eskaleringen är ett extra steg i flöde 4 som designen inte har ritat — beslutskortet
mellan matchningen och alternativen. Det är rätt enligt kanten, men det är en skärm som saknas,
och `chattyta` får rita den.

### 11.2 `GET /decisions` omfattning — **BESLUTAT: union**

Ny tabell för nya avståenden, plus `intake_sources` med `failed`/`needs_attention` och
`correction_notes` med `pending`/`suggested` som syntetiska, läsbara beslut (§5).

Alternativen var en ren tabell, eller en engångsmigrering av backloggen. Den rena tabellen faller
på att `open_decisions` skulle gå från sitt nuvarande tal till noll vid driftsättning och
backloggen bli osynlig tills varje underlag körts om — en räknare som ljuger den dag modulen som
ska göra den sann driftsätts. Engångsmigreringen faller på att `correction_notes` inte har någon
agentmotivering att flytta över: `note_text` är människans text, och migrationen skulle behöva
hitta på `reason` för ett kort vars hela poäng är agentens ord.

Priset är tre id-rymder och två källor som listas men inte kan besvaras här. Unionen är övergående
för `intake`-delen (§5) och avvecklas utan en dag då siffran hoppar.

### 11.3 Ett tionde verktyg — **BESLUTAT: ja, `be_om_beslut`, sist i listan**

`SPEC-tradar.md` §8 gjorde det till ett "fråga först". Motiveringen står i §8: `options` finns i
schemat men har ingen producent, `registrera_avstaende` är bunden till ett underlag i kön, och de
två alternativen — att bygga om dokumentvägens verktyg, eller att tolka agentens fritext till
strukturerade alternativ — bryter mot en modulgräns respektive mot `ANALYS.md` §7.

Verktyget rör aldrig `vouchers`. Testfall 26 är `agentruntime`s testfall 17, körd mot den utökade
listan.

### 11.4 Svar på ett beslut är inte idempotent via header — **BESLUTAT: `409` ur schemat**

`SPEC-idempotens.md` gäller postningar. Ett beslutssvar behöver ingen `Idempotency-Key`, eftersom
`decisions.status` redan är den unika resursen som bara kan gå `open → answered` en gång: andra
svaret möter en rad som inte längre är öppen och får `409` med det befintliga svaret.

Postningen som turen eventuellt gör bär däremot nyckeln som vanligt, ur
`thread:{thread_id}:{post_id}` med svarsinläggets id (`SPEC-tradar.md` §6.4) — vilket är varför
testfall 29 kan kräva att två svar aldrig ger två verifikationer.

---

## 12. Öppna frågor

Ingen av dem blockerar starten.

1. **`age_days`-trösklarna.** Ärvd från `oversikt` och noterad i `tasks/skal/todo.md`: vad gör
   `VyRad`-varianten `saknar` gul respektive röd? Servern ger talet oavsett; frågan är
   `chattyta`s och behöver ett svar innan den modulen stänger.
2. **Vem sätter `superseded`, och när?** Kolumnen finns och regeln är beskriven (§4), men vilka
   händelser som faktiskt utlöser den — raderat underlag, låst period, korrigerad verifikation —
   hör ihop med `flode-verifikationer`, som äger korrigeringsvägen. Tills dess sätts den bara
   manuellt, och inget beslut blir `superseded` av sig självt.
3. **Var går linjen vid ett mänskligt godkänt förslag?** `ANALYS.md` §9.4, delvis besvarad i
   `tradar` (agentens text blir aldrig en verifikations `description`). Ett besvarat beslut är den
   mänskliga godkännandepunkten — men vad som får bli `description` när förslaget postas avgörs
   när `VerifikationsForslag` byggs, alltså i `flode-verifikationer`.
4. **Årsskiftet.** Ett öppet beslut i förra årets tråd: följer det med till den nya tråden eller
   ligger det kvar i arkivet? Ärvd från `SPEC-tradar.md` §13.2, som fortfarande är öppen. Tills
   den besvaras ligger beslutet kvar i sin tråd och syns ändå i `GET /decisions`, eftersom listan
   inte filtrerar på räkenskapsår.
