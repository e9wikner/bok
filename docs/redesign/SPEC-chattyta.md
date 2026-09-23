# Spec: `chattyta`

Modul-id `chattyta` i kapabilitetskartan (`ANALYS.md` §8). Beror på `skal` (klar, S1–S13),
`tradar` (klar, T1–T14) och `beslut` (klar, B1–B12). `flode-verifikationer` beror på den här.

Status: **Fas 1 — skriven 2026-09-23.** Två beslut tagna i förväg av beställaren (§12.1–§12.2):
`VerifikationsForslag` byggs hela vägen, med postningsknapp, och `age_days` blir röd från sju
dagar. Uppgifterna ligger i `tasks/chattyta/plan.md` och `tasks/chattyta/todo.md` (C1–C14).

---

## Antaganden

1. **Backenden är klar för den här modulen och ändras inte.** Tråden (`GET /threads/{view_key}`,
   `POST …/messages`, `GET …/stream`), besluten (`GET /decisions`, `POST /decisions/{id}/answer`)
   och postningen (`POST /vouchers/{id}/post` med `Idempotency-Key`) finns. `chattyta` är en
   klient. Behövs en Python-ändring har specen fel, och det ska sägas, inte smygas in.
2. **Inlägg ändras aldrig** (`SPEC-tradar.md` §8.4). Ett besvarat beslutskort ser alltså inte
   annorlunda ut för att *inlägget* ändrats, utan för att klienten läser beslutets status ur
   `decisions`. Klienten får aldrig låtsas att ett inlägg sa något annat än det sa.
3. **Agenten formulerar, servern räknar** (`datakontrakt.md`, regel 1–2). Klienten skriver inte om
   `reason`, `rationale`, `consequence`, `cause` eller `footnote`, och räknar inte om ett belopp.
   Den formaterar öre till kronor. Det är allt.
4. **Klienten postar aldrig utan ett utkast-id** (regel 3). Postningsknappen tar `draft_id` ur
   inlägget; den konstruerar ingen verifikation.
5. **Enbolag och en människa.** `answered_by` visas men det finns ingen annan att skilja ut
   (`SPEC-beslut.md` antagande 5).

→ Punkt 1 och 4 är de som kostar om de glöms.

---

## 1. Objektiv

### Problemet, konkret

Skalet ritar tråden som en mockad lista av två typer (`ChattKolumn.tsx`, `lib/skal/mock.ts`
`mockTrad`) och markerar i koden att `chattyta` byter ut renderaren. Mobilens `ChattList`-märke
kommer ur `mockVantandeBeslut`, som svarar `1` för Verifikationer och `0` för allt annat.
`ChattFalt` har en `onSkicka` som ingen kopplar.

Samtidigt skriver backenden i dag sex av de åtta inläggstyperna i riktiga trådar — `agent_text`,
`user_text`, `user_file`, `decision`, `options`, `error` — och ingen klient kan visa fyra av dem.
Ett beslut som agenten lägger fram via `be_om_beslut` finns i tabellen, räknas i headern, och syns
ingenstans.

### Vad vi bygger

- En **renderare per inläggstyp**, alla åtta, med komponenterna ur `komponenter.md`:
  `TradInlagg/agent`, `TradInlagg/du`, `FilInlagg`, `SkriverIndikator`, `SparChip`,
  `RadLista/i-tråd`, `BeslutKort`, `GodkannKort`, `AlternativLista` (`AlternativRad`,
  `RekMarke`), `VerifikationsForslag` (`KonteringsRad`), `FelKort`, `JamforelseRader`.
- **Trådens klientsida**: läs, prenumerera på SSE, återanslut med `since`, skicka meddelande.
- **Svar på beslut**: med knapp (`option_id`) och med fritext — båda vägarna, alltid.
- **Postningsknappen** på `VerifikationsForslag`, med idempotensnyckel härledd ur `draft_id`.
- **`age_days`-regeln**: när `VyRad`-varianten `saknar`/`vantar` går från gul till röd.
- Mocken för tråd och beslutsmärke tas bort.

### Vad vi inte bygger här

- **Producenten av `draft` och `receipt`.** Ingen backendkod skriver dem i dag, och ingen gör det
  efter den här modulen heller. Kedjan beslut → förslag → postning → kvitto → låst, `view.changed`
  som uppdaterar vyns rader och de optimistiska `pagaende`-raderna hör till
  `flode-verifikationer`. `chattyta` spikar kroppens form (§4.3) så att producenten har ett
  kontrakt att skriva mot.
- **Vyernas riktiga rader.** Vyerna fortsätter visa `MOCK_VYER`. `age_days`-regeln byggs som en
  ren funktion och kopplas till de rader som finns.
- **`ChattFalt`s `drop`-variant** (fil, kamera, urklipp) — `flode-underlag`.
- **Äldre räkenskapsårs trådar.** `archive_fiscal_year_ids` finns i svaret; ingen ritning visar
  hur man bläddrar dit.
- **Modellväljaren** (`PUT /threads/{view_key}/model`). Inte ritad.
- Förslagschips. Beslutat nej (`SPEC-skal.md` §2.1).

### Framgång

En människa öppnar `/v4`, ser agentens riktiga tråd i varje vy, skriver en fråga och ser svaret
strömma in; ser ett beslutskort, väljer ett alternativ **eller** skriver sitt svar, och ser kortet
bli besvarat; och — mot en fixtur, tills `flode-verifikationer` skriver riktiga utkast — trycker
`Posta` två gånger och får **en** verifikation.

---

## 2. Vad de tre modulerna faktiskt lämnade efter sig

Verifierat i koden 2026-09-23, inte i specarna.

| Sak | Läge | Var |
|---|---|---|
| Inlägg med `id`, `seq`, `type`, `actor`, `created_at`, `body`, `traces`, `run_id` | Finns | `api/schemas.py::ThreadPostResponse` |
| Tom tråd | `thread_id: null`, `posts: []`, `cursor: 0` — inte `404` | `ThreadResponse` |
| Ström mot en tråd som inte finns | **`404 thread_not_found`** | `api/routes/threads.py::stream_thread` |
| `message.created` | `{id: "streaming-{run_id}", type: "agent_text", actor, run_id}` | `services/thread_stream.py` |
| `message.delta` | **två former**: `{id, text}` för text, `{id, activity}` för verktygsanrop | samma |
| `message.completed` | hela inlägget; ersätter `streaming-{run_id}` | samma |
| `view.changed` | `{view_key, changed: {voucher_id, kind: "voucher_posted"}}` | samma |
| Hjärtslag | kommentarsram var 15 s | samma |
| `traces[]` | `{tool, label, detail?, voucher_id?}`, `label` på svenska | `services/thread_service.py::build_trace` |
| `decision`-kropp | `{decision_id, title, amount, reason, source, consequence}` — `amount` i öre eller `null` | `_decision_body`, `_decision_post_body` |
| `options`-kropp | `{decision_id, options: [{option_id, title, account, amount_ore, rationale, recommended, is_exit}], footnote}` | `_options_post_body` |
| `error`-kropp | `{cause, consequence, retry_draft_id}` — `retry_draft_id` är **alltid `null`** i dag | `_error_body` |
| Påminnelse | `agent_text` med `{text, decision_id}` | `_reminder_post_body` |
| `draft`, `receipt` | **Ingen producent** | — |
| Beslutets status | Bara i `GET /decisions`, filter `view_key` och `status=open\|answered\|all` | `api/routes/decisions.py` |
| Svar två gånger | `409` med `answered_at`, `answer_post_id`, `answer_option_id`/`answer_text` | samma |
| Syntetiska beslut (`intake:`, `correction:`) | Listas, **ej besvarbara**: `409 decision_not_answerable` med pekare | samma |
| Postning två gånger | `409` med befintligt id, eller uppspelning med `Idempotent-Replay: true` | `SPEC-idempotens.md` §6 |
| Låst period | `409 period_locked` med `locked_at`, `locked_by` (kan vara `null`), `period_id` | samma, testfall 8–9 |
| Autentisering | Bearer-header ur `localStorage` via axios-interceptorn | `frontend-v3/lib/api.ts` |

Tre av raderna styr designen av klienten mer än resten:

1. **Strömmen ger `404` innan tråden finns.** En vy där ingen sagt något i år har ingen ström att
   öppna. Klienten öppnar den först när `GET` svarat med ett `thread_id`, eller när det första
   `POST …/messages` har svarat.
2. **`message.delta` har två former.** `{text}` byggs på det strömmande inlägget; `{activity}` är
   vad `SkriverIndikator` ska säga just nu. En klient som bara läser `text` visar en anonym
   väntan, och *"aldrig en anonym spinner"* är designens ord.
3. **`EventSource` kan inte skicka en `Authorization`-header.** Se §6.

---

## 3. Tech stack

Oförändrad från `skal`: Next 16, React 18, Tailwind 3 med `bok-*`-tokens, TanStack Query, axios,
`vitest` + Testing Library. **Inga nya beroenden.** SSE läses med `fetch` och en
`ReadableStream`-läsare (§6); UUIDv5 för idempotensnyckeln räknas med `crypto.subtle` (§8).

Nya filer ligger under `frontend-v3/components/chattyta/`, `frontend-v3/lib/chattyta/` och
`frontend-v3/hooks/`. Skalets filer rörs bara där renderaren byts (`ChattKolumn.tsx`,
`ChattList.tsx`, `Skal.tsx`, `lib/skal/mock.ts`) och där `VyRad` får sin tröskel.

---

## 4. Kontraktet i klienten

### 4.1 En typ per inläggstyp

`lib/chattyta/typer.ts` bär en diskriminerad union över `type`, med kroppen typad per typ. Formen
är exakt §2:s tabell. **`parseInlagg()` är den enda platsen** där ett råinlägg från servern blir
en typad sak, och den vägrar det som bryter kontraktet i stället för att rendera det halvt:

| Brott | Utfall |
|---|---|
| Okänd `type` | Renderas inte. Loggas en gång per typ i konsolen. |
| `options` med mer än ett `recommended` | Renderas som `okant_kontrakt` (§4.4) |
| `options` där sista alternativet saknar `is_exit` | `okant_kontrakt` |
| `receipt` där en rad saknar något av sina två tal | `okant_kontrakt` |
| `draft` utan `draft_id` | `okant_kontrakt` |
| `draft`-rad med både debet och kredit, eller ingetdera | `okant_kontrakt` |
| `receipt` utan exakt två `labels` | `okant_kontrakt` |
| `decision` eller `options` utan `decision_id` | `okant_kontrakt` — kortet går inte att svara på |
| Ett obligatoriskt fält saknas eller har fel typ, i vilken typ som helst | `okant_kontrakt` |

Ett trasigt `traces[]`-chip faller bort utan att inlägget gör det: spåren är agentens redovisning,
inte kortets kontrakt.

Servern garanterar redan de två första (`SPEC-beslut.md` §6.3, B4). Klienten kontrollerar ändå,
av samma skäl som append-only vaktas på tre ställen: ett kort som ser rätt ut men bryter
kontraktet är värre än inget kort.

### 4.2 Ingenting förväljs

`AlternativRad` har en tom ring. `recommended: true` ger `RekMarke`, inte ett förvalt val, inte
fokus, inte en annan knappfärg. Det finns ingen state som börjar på ett alternativ. Testfall 14.

### 4.3 `draft` och `receipt` — formen spikas här

Ingen producent finns. Kropparna nedan är **kontraktet `flode-verifikationer` skriver mot**. De
utvidgar `SPEC-tradar.md` §6.2:s rader utan att motsäga dem.

```jsonc
// draft — VerifikationsForslag
{
  "draft_id": "<vouchers.id, status=draft>",
  "kind": "voucher",                    // "invoice" | "payroll" — ur scope, renderas inte
  "title": "Kontorsmaterial, Clas Ohlson",
  "meta": "A · 2026-09-18",             // serverns sträng, ordagrant
  "rows": [
    { "account": "6110", "name": "Kontorsmateriel", "debit_ore": 71680, "credit_ore": null },
    { "account": "2640", "name": "Ingående moms",   "debit_ore": 17920, "credit_ore": null },
    { "account": "1930", "name": "Företagskonto",   "debit_ore": null,  "credit_ore": 89600 }
  ],
  "footnote": "Underlag: kvitto 2026-09-18 · kompletteringsflagga sätts inte",
  "consequence": "Låses vid postning · period september öppen till 2026-10-12",
  "decision_id": "<om förslaget kommer ur ett besvarat beslut, annars null>"
}

// receipt — JamforelseRader
{
  "title": "A-118 postad",
  "labels": ["var", "blir"],            // eller ["kvitto", "A-118"]
  "rows": [
    { "key": "1510", "text": "Kundfordringar", "left_ore": 14850000, "right_ore": 14400000 }
  ],
  "voucher_id": "<id, när kvittot gäller en postning>"
}
```

`consequence` bär varningen och renderas i mono 12 `#52525b`, **inte** i metatextgrå
(`komponenter.md`: *"Notisen är inte metatext"*). `kind` ≠ `voucher` renderas som `okant_kontrakt`
— faktura- och löneförslag är ur scope (`ANALYS.md` §2).

### 4.4 `okant_kontrakt`

Ett kort som inte kan visas ärligt blir en neutral rad i mono 12: `kortet kunde inte visas ·
{type} · {id}`. Den säger att något finns utan att låtsas veta vad. Ingen knapp.

---

## 5. Komponenterna

Mått, färger och copy ur `komponenter.md` gäller ordagrant och upprepas inte här. Det som
specen lägger till är beteende.

| Komponent | Inlägg | Beteende utöver `komponenter.md` |
|---|---|---|
| `TradInlagg/agent` | `agent_text` | Metarad `agenten · HH:MM` ur `created_at`, lokal tid. `traces[]` → `SparChip`. |
| `TradInlagg/du` | `user_text` | Optimistisk tills servern svarat; ersätts på `id`. |
| `FilInlagg` | `user_file` | Läsbar; filmeta ur `size_bytes`, `pages`. Ingen förhandsvisning. |
| `SkriverIndikator` | strömmande | Text ur senaste `activity` — verktygsnamnet via samma svenska etiketter som `build_trace`. Utan `activity` än: `Läser…`. Aldrig tom. |
| `SparChip` | `traces[]` | `label` + ` · detail` när den finns. |
| `BeslutKort` | `decision` | Tre lägen ur beslutets status (§7): **öppen**, **besvarad** (`Besvarat · HH:MM` + svaret, inga knappar), **ersatt** (`superseded`: `Inte längre aktuellt`, inga knappar). |
| `GodkannKort` | `decision` där beslutet har `kind="approval"` | Som `BeslutKort`, rubrik `Väntar på ditt godkännande`. |
| `AlternativLista` | `options` | Tryck på en rad = svar. Ingen bekräftelsedialog — konsekvensen står i kortet (`README.md` regel 4). En rad åt gången i flykt; övriga låsta tills svaret kommit. |
| `VerifikationsForslag` | `draft` | §8. |
| `FelKort` | `error` | `Försök igen` bara när `retry_draft_id` finns (§9). `Visa vad som hände` fäller ut `traces[]` på plats. |
| `JamforelseRader` | `receipt` | Båda talen, alltid. |
| `RadLista/i-tråd` | inuti `agent_text` när kroppen bär `rows[]` | Samma radkomponent som `JamforelseRader`, en kolumn tal. |

`BeslutKort` och `AlternativLista` hör ihop via `decision_id`, men **renderas där de ligger i
tråden** — klienten slår inte ihop två inlägg till ett kort. Ordningen i tråden är serverns.

---

## 6. Strömmen

### 6.1 Transport: `fetch`, inte `EventSource`

`EventSource` tar ingen header, och API:t autentiserar med bearer. Alternativen var:

| Väg | Kostnad |
|---|---|
| Token i query-strängen | Backendändring (bryter antagande 1), och token hamnar i loggar och historik. |
| Cookie-autentisering | Backendändring och en andra autentiseringsväg. |
| **`fetch` + `ReadableStream`** | ~80 rader klientkod: ramparser, återanslutning. |

Vi tar den tredje. `lib/chattyta/strom.ts` läser `event:`/`data:`-ramar, ignorerar
kommentarsramar (hjärtslaget), och är en ren funktion av en `ReadableStream` så att den går att
testa utan nätverk.

### 6.2 Livscykel

1. Vyn monteras → `GET /threads/{view_key}`. `thread_id: null` → tom tråd, **ingen ström**.
2. `thread_id` finns → öppna strömmen med `since=cursor`.
3. Första `POST …/messages` i en tom tråd → svaret bär `thread_id` och `cursor` → öppna strömmen
   därifrån.
4. Bortkopplad → återanslut med `since` = högsta `seq` klienten har sett, med backoff
   1 s → 2 s → 4 s → … tak 30 s. `message.completed` från återuppspelningen dedupliceras på `id`.
5. Vybyte → strömmen för den gamla vyn stängs (`AbortController`). En ström åt gången per flik,
   den aktiva vyns.
6. `401` → ingen återanslutning; samma utloggningsväg som axios-interceptorn.

### 6.3 Tillståndet

`lib/chattyta/trad.ts` är en ren reducer över `{ inlagg: Map<id, Inlagg>, strommande, maxSeq }`:

| Händelse | Effekt |
|---|---|
| `GET`-svar | Ersätter listan; `maxSeq = cursor` |
| optimistiskt `user_text` | Läggs sist med tillfälligt id |
| `POST`-svar | Ersätter det optimistiska med serverns inlägg |
| `message.created` | Startar ett strömmande inlägg med `id = streaming-…` |
| `message.delta {text}` | Läggs till det strömmande inläggets text |
| `message.delta {activity}` | Sätter `SkriverIndikator`s text |
| `message.completed` | Tar bort `streaming-{run_id}`, lägger in det lagrade inlägget på sin `seq`; idempotent på `id` |
| `view.changed` | Invaliderar `overview`- och beslutsfrågorna. Vyns rader är `flode-verifikationer`s. |

Sortering alltid på `seq`; optimistiska inlägg sist.

---

## 7. Beslutets status

Inlägget säger inte om beslutet är besvarat (antagande 2). Klienten läser
`GET /decisions?view_key={vk}&status=all&limit=200` en gång per vy och slår upp `decision_id`
lokalt — ett anrop per vy, inte ett per kort. Frågan invalideras när:

- ett svar skickats (`POST /decisions/{id}/answer` gav `202` eller `409`),
- `message.completed` kommer med typen `decision`, `options` eller `user_text`,
- `view.changed` kommer.

Ett `409 decision_already_answered` är **inte ett fel** för människan: kortet går till besvarat
läge med svaret ur `409`-kroppen. Ett `409 decision_not_answerable` kan bara uppstå för
syntetiska beslut, som inte har något inlägg i tråden — klienten har ingen knapp som kan utlösa
det. Syntetiska beslut räknas i märket (§10) och syns i vyns väntar-sektion, inte i tråden.

**Fritextvägen.** `README.md`: *"Beslutskortets primärknapp är aldrig den enda vägen."* Ett
meddelande i `ChattFalt` är det, oförändrat: `POST …/messages`. Agenten tolkar det; klienten
gissar inte att en viss text är ett svar på ett visst beslut.

---

## 8. Postningsknappen

`VerifikationsForslag` har primär `Posta`, sekundär `Ändra` och konsekvensnotisen.

1. `Posta` → `POST /vouchers/{draft_id}/post` med
   `Idempotency-Key: uuid5(BOK_KLIENT_NS, "draft:" + draft_id)`.
   Nyckeln är **härledd, inte slumpad**: ett andra tryck, en omladdning, en annan flik och
   `FelKort`s `Försök igen` ger alla samma nyckel och därmed samma verifikation.
   `BOK_KLIENT_NS` är en fast UUID i `lib/chattyta/idempotens.ts`, skild från serverns
   `BOK_NAMESPACE` så att klient- och servernycklar aldrig kan kollidera.
2. Knappen är låst medan anropet är i flykt. Det är bekvämlighet, inte skyddet — skyddet är
   nyckeln (testfall 25 trycker två gånger *utan* att låsningen hinner verka).
3. Utfall:

| Svar | Kortet |
|---|---|
| `200` | Klart: `Postad · {serie}-{nummer}` i klartoner. Knapparna borta. |
| `200` + `Idempotent-Replay: true` | Samma som `200`. |
| `409 already_posted` (bär hela `voucher`) | Samma som `200`, med det befintliga numret. Inte ett fel. |
| `409 request_in_flight` | Vänta `retry_after_ms`, fråga igen med samma nyckel. Knappen står kvar i `Postar…`. |
| `422 idempotency_key_reuse` | Kan bara hända om `draft_id`s rader ändrats mellan två tryck. Inline fel: `Förslaget har ändrats sedan du tryckte. Ingenting är bokfört.` Ingen `Försök igen`. |
| `409 period_locked` | Inline `FelKort`-ton i kortet: `Perioden {period} är låst sedan {locked_at} av {locked_by ?? "okänd"}. Ingenting är bokfört.` Ingen `Försök igen` — det kan inte lyckas. |
| Nätverksfel, `5xx` | Inline fel med `Försök igen` (samma nyckel). |

4. `Ändra` lägger fokus i `ChattFalt`, med tomt fält. Den skickar ingenting själv — en knapp som
   skickar en färdig mening är ett förvalt yttrande, samma sak som förslagschipsen som togs bort
   (`SPEC-skal.md` §2.1). Förslag ändras i samtalet, aldrig i ett formulär i kortet
   (`PUT /vouchers/{id}` anropas inte härifrån).

Vad tråden säger efter en postning — kvitto, `view.changed`, nästa väntande sak — är
producentens, alltså `flode-verifikationer`s (§12.1).

---

## 9. `FelKort`

`retry_draft_id` är `null` i varje `error` backenden skriver i dag. Då har kortet **ingen
primärknapp** — bara `Visa vad som hände`. En `Försök igen` som skickar om människans senaste
meddelande vore en ny tur, inte ett omförsök av samma avsikt, och kan ge ett annat utfall. Finns
`retry_draft_id` går `Försök igen` samma väg som §8 steg 1, med samma nyckel.

---

## 10. Märket och åldern

**Mobilens `ChattList`-märke** = `total` ur `GET /decisions?view_key={vk}&status=open&limit=1`.
Unionen, alltså även syntetiska beslut — samma tal som `open_decisions` i headern räknar med
(`SPEC-beslut.md` §6.6). `mockVantandeBeslut` tas bort.

**`age_days`-tröskeln** (§12.2): `lib/chattyta/alder.ts`

```ts
export const ROD_FRAN_DAGAR = 7; // samma dag som påminnelsen (SPEC-beslut.md §6.5)
export function aldersTon(ageDays: number): "vantar" | "forfallen"
```

`vantar` → meta `#b45309`, `forfallen` → `#dc2626`. Talet står på ett ställe. Regeln gäller
`VyRad`-varianterna `saknar` och `vantar` och `BeslutKort`s källrad.

---

## 11. Tillgänglighet

- **`aria-live="polite"`** finns redan på tråden. Deltan annonseras **inte** en och en — det
  blir ett ord i taget i skärmläsaren. En dold live-region annonserar `SkriverIndikator`s text vid
  byte och hela inlägget vid `message.completed`.
- Kortens knappar är `<button>`, träffyta ≥ 46 på mobil, ≥ 44 på desktop.
- `AlternativLista` är en grupp knappar med `aria-describedby` till fotnoten, inte en radiogrupp
  — en radiogrupp har ett valt värde, och här finns inget valt värde förrän svaret är skickat.
- Efter ett svar flyttas fokus till kortets besvarade rad, inte till `body`.
- Konsekvensnotiser och felorsaker har kontrast ≥ 4.5:1; `#9ca3af` används bara för metarader.

---

## 12. Beslut

### 12.1 `VerifikationsForslag` byggs hela vägen — **BESLUTAT 2026-09-23**

Knappen, nyckeln och alla fem utfall i §8 byggs här och testas mot fixturer. Producenten, kvittot
och `view.changed`-kedjan är `flode-verifikationer`s. Priset: knappen går inte att se mot
riktiga data förrän den modulen skriver ett `draft`-inlägg. Motmedel: `draft`-kroppen spikas i
§4.3, och en fixtur i `lib/chattyta/__fixtures__/` är samma JSON som specen visar.

### 12.2 `age_days` röd från sju dagar — **BESLUTAT 2026-09-23**

Samma dag som påminnelsen går (`SPEC-beslut.md` §6.5). Stänger `SPEC-beslut.md` öppen fråga 1
och den ärvda frågan i `tasks/skal/todo.md`.

### 12.3 SSE över `fetch` — **tekniskt val, §6.1**

Inget beroende, ingen backendändring.

---

## 13. Teststrategi

`vitest` + Testing Library, som `skal`. Testerna skrivs **före** implementationen. Ingen
Playwright (`SPEC-skal.md` §15.5).

| # | Fall | Förväntat |
|---|---|---|
| 1 | `parseInlagg` med var och en av de åtta typerna ur fixturerna | Rätt variant, rätt fält |
| 2 | Okänd `type` | Renderas inte; en konsolrad |
| 3 | `options` med två `recommended` / utan `is_exit` sist | `okant_kontrakt` |
| 4 | `receipt` med en rad som saknar ett tal | `okant_kontrakt` |
| 5 | Ramparsern: ramar delade över chunk-gränser, kommentarsram, flerradig `data:` | Rätt händelser, hjärtslag ignorerat |
| 6 | Återanslutning | Ny begäran med `since` = högsta sedda `seq`; backoff växer; taket håller |
| 7 | Återuppspelning av ett redan sett inlägg | Ingen dubblett |
| 8 | Tom tråd | Ingen ström öppnas; första `POST` öppnar den |
| 9 | `401` på strömmen | Ingen återanslutning |
| 10 | `delta {text}` × n + `completed` | Strömmande inlägg ersätts av det lagrade; texten är den lagrade, inte den ihopsamlade |
| 11 | `delta {activity}` | `SkriverIndikator` byter text; aldrig tom |
| 12 | Optimistiskt `user_text` | Syns direkt; ersätts av serverns på `id` |
| 13 | `SparChip` ur `traces[]` | `label · detail` |
| 14 | `AlternativLista` renderas | **Ingen** rad vald, fokuserad eller annorlunda stylad för att den är `recommended`; `RekMarke` finns |
| 15 | Tryck på alternativ | `POST /decisions/{id}/answer {option_id}`; övriga låsta i flykt |
| 16 | `409 decision_already_answered` | Besvarat läge med svaret ur kroppen; inget felkort |
| 17 | `BeslutKort` öppen / besvarad / ersatt | Tre lägen; knappar bara i öppen |
| 18 | `kind="approval"` | `GodkannKort`-rubriken |
| 19 | Fritext via `ChattFalt` | `POST …/messages`; ingen tolkning i klienten |
| 20 | Beslutsstatus | Ett `GET /decisions` per vy, inte per kort |
| 21 | Märket | `total` ur `status=open`; syntetiska räknas |
| 22 | `aldersTon(6)`, `(7)`, `(30)` | `vantar`, `forfallen`, `forfallen` |
| 23 | `JamforelseRader` | Båda talen i varje rad; etiketterna ur kroppen |
| 24 | `VerifikationsForslag` | Konto, namn, debet, kredit; konsekvensnotisen i `#52525b`, inte `#9ca3af` |
| 25 | `Posta` två gånger utan väntan | Två anrop, **samma** `Idempotency-Key`; en verifikation i klart läge |
| 26 | Nyckelns härledning | Samma `draft_id` → samma UUID över omladdning; annan `draft_id` → annan UUID; giltig UUIDv5 |
| 27 | `409 period_locked` | Inline med vem/när; `locked_by: null` → `okänd`; ingen `Försök igen` |
| 28 | `409 already_posted` | Klart läge med befintligt nummer |
| 29 | `FelKort` utan `retry_draft_id` | Ingen primärknapp |
| 30 | `FelKort` med `retry_draft_id` | `Försök igen` med samma nyckel som §8 |
| 31 | Live-regionen | Annonserar indikatorbyte och färdigt inlägg; inte varje delta |
| 32 | Mocken borta | `mockTrad` och `mockVantandeBeslut` finns inte; `grans.test.tsx` uppdaterad |
| 33 | Regression | Skalets 89 tester gröna; `pytest tests/` grön utan att någon Python ändrats |
| 34 | `409 request_in_flight` | Nytt anrop efter `retry_after_ms`, samma nyckel; slutar i klart läge |
| 35 | `422 idempotency_key_reuse` | Inline fel, ingen `Försök igen` |
| 36 | `Ändra` | Fokus i `ChattFalt`, fältet tomt, inget anrop |

---

## 14. Framgångskriterier

1. Alla åtta inläggstyper renderas med `komponenter.md`s mått; kontraktsbrott blir
   `okant_kontrakt`, aldrig ett halvt kort (testfall 1–4).
2. Tråden är riktig i alla sju vyer, strömmar, och överlever en bortkoppling utan dubbletter
   eller hål (5–12).
3. Ett beslut kan besvaras med knapp och med text, och ett andra svar är ett besvarat kort, inte
   ett fel (14–20).
4. Ingenting förväljs (14).
5. Två tryck på `Posta` ger en verifikation; låst period säger vem och när (25–28, 34, 35).
6. Märket och åldersfärgen kommer ur servern och en regel på ett ställe (21, 22).
7. Mocken för tråd och beslut är borta (32).
8. `npm test`, `npm run lint`, `npx tsc --noEmit` och `NEXT_PUBLIC_SKAL=1 npm run build` gröna;
   `git diff main -- '*.py'` tom.
9. Visuellt kontrollerat i `next dev` mot riktig backend: fråga, svar som strömmar, ett beslut
   lagt via `be_om_beslut` och besvarat.

---

## 15. Öppna frågor

Ingen av dem blockerar starten.

1. **Postar människan direkt, eller via tråden?** §8 anropar `POST /vouchers/{id}/post` direkt.
   Då skriver ingen något i tråden om att människan postade — om inte `flode-verifikationer`
   lägger en trådväg (t.ex. ett `receipt`-inlägg som följd). Knappens anrop ligger i en funktion
   (`lib/chattyta/api.ts::postaUtkast`) så att vägen kan bytas utan att kortet ändras. Frågan är
   `flode-verifikationer`s.
2. **`ny`-markeringens varaktighet** (6 s, `SPEC-skal.md` öppen fråga 3) — gäller nu även ett
   besvarat kort som blir grönt. Samma konstant används.
