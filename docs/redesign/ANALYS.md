# Analys: BokAi agent-first redesign

Underlag: `BokAI App Redesign.zip` → `design_handoff_bokai/`
(två `.dc.html`-designfiler, `README.md`, `komponenter.md`, `datakontrakt.md`, 26 skärmbilder).
Analysen är gjord mot `main` @ 9a32d46.

Status: **Fas 0 — scope check. Inga modulspecar skrivna. Väntar på godkännande av kapabilitetskartan (§8).**

Beslutade av beställaren 2026-09-12, efter §9:

1. **Agenten körs som egen worker i backend.** Agenten blir en del av produkten, inte en batchprocess bredvid.
2. **Bara flöde 1 och 4 i den här omgången.** Betalfil, AGI och faktisk fakturaleverans är ur scope → flöde 2 och 3 utgår.
3. **Redesignen ersätter `frontend-v3`.** Rewrite på plats, inte parallell app.

---

## 1. Antaganden jag gör

1. Uppgiften är att **analysera och specificera**, inte att bygga. Ingen kod skrivs förrän kartan och modulspecarna är godkända.
2. Redesignen ska ersätta `frontend-v3`, inte ligga bredvid den. (24 sidor → 3 sidor / 7 vyer är inte en refaktorering.)
3. Backendens append-only-garantier (SQL-triggers, `VoucherValidator`, inga PATCH/PUT på postat) är oförhandlingsbara och gäller även allt nytt.
4. Systemet förblir enanvändar-/enbolagsinstallation tills något annat beslutas. Designens `view_key` "per vy **och bolag**" är noterad men inte budgeterad.
5. "Agenten" i designen är samma sorts LLM-agent som i dag kör via `scripts/bok-curl` — inte en ny, separat produkt.

→ Rätta mig här innan jag går vidare. Punkt 2 och 5 är de dyra.

---

## 2. Vad designen faktiskt föreslår

En **agent-first** omvändning av gränssnittet. I dag är frontend ett CRUD-skal över bokföringen och agenten en batchprocess bredvid. I designen är **konversationen gränssnittet**: agenten bokför det den är säker på, skriver i klartext vad den gjorde, och lägger det den avstod från som beslutskort i samma tråd där siffrorna visas.

| | I dag | Designen |
|---|---|---|
| Navigation | 24 sidor, sidomeny | 3 sidor, 7 vyer, swipe/prickar |
| Primär interaktion | formulär och listor | chatt per vy + läsvy bredvid |
| Agentens output | postade verifikationer | verifikationer **plus** resonemang, förslag, kvitteringar |
| Beslut | människan letar upp dem | agenten lägger fram dem i tråden |
| Notiser | — | inga, medvetet: kön ligger i tråden |

Fyra skrivflöden är ritade hela vägen (väntar → förslag → bekräftelse → pågår → klart/låst), var och en med sitt svåra fall.

---

## 3. Bedömning: designen är stark

Det här är inte ett skin. Det är ett produktbeslut som är genomtänkt in i bokföringsdomänen:

- **Förslag förväljs aldrig.** `AlternativRad` har en tom ring, och sista alternativet är alltid en väg ut (`Annat konto`). Det är rätt hållning när en LLM föreslår kontering.
- **Konsekvensen står i kortet, före trycket** — `låses vid postning`, med datum. Inte i en efterföljande bekräftelsedialog. Det matchar BFL-verkligheten: postning är irreversibel.
- **`JamforelseRader` visar alltid båda talen** (`var` / `blir`). En ensam ny summa vore en lögn om vad som ändras.
- **Rättelse går aldrig genom ändring.** Flöde 2 steg 5 (tidrapport rättas efter godkännande) landar i korrigeringsverifikation, precis som repots regel kräver. Designern har förstått append-only.
- **Fel formuleras i bokföringstermer**, med orsak *och* konsekvens, i tråden där beslutet togs.
- **Två färger bär betydelse och får inte dekorera** — gult = väntar på människan, grönt = postat och låst. Disciplinerat.
- Tillgänglighet är på riktigt genomtänkt: `aria-live` på strömmande svar, tangentbordsekvivalent för swipe, och beslutskortets knapp är aldrig enda vägen — samma beslut ska gå att skriva i fritext.

Tokens, mått och tillstånd är specificerade på en nivå som går att bygga mot utan gissningar. Geist/Geist Mono finns redan i `frontend-v3/app/fonts/`.

---

## 4. Den centrala luckan: det finns ingen agentruntime

Designen står och faller med en agent som **finns kontinuerligt, skriver in i en tråd, strömmar text och har ett läge**. Repot har ingen sådan sak.

Vad som faktiskt finns i dag (verifierat):

- Ingen LLM någonstans i backend. `grep -riE "anthropic|openai"` över `*.py` → 0 träffar.
- Ingen konversationslagring. Inga `threads`, `messages`, `conversations` i schema eller kod.
- Ingen streaming. `StreamingResponse` / `text/event-stream` → 0 träffar.
- `GET /agent/operations/log` finns som route men returnerar `{"operations": [], "total": 0}` — en stubb (`api/routes/agent.py:347`). `datakontrakt.md` listar den under "Finns i repot", vilket överdriver.

Agenten i dag är **en människa som startar en LLM som kör `bok-curl` i ett pass**: läser `docs/to_agent/*.md`, pollar `GET /agent/intake/pending`, postar via `POST /agent/vouchers`, slutar. Den har inget minne mellan pass, ingen närvaro, och ingen röst i produkten.

Att bygga designen betyder alltså att bygga **en agentruntime som produkt** — inte bara en frontend. Det är den största enskilda posten i hela arbetet och den syns inte i `datakontrakt.md`, som beskriver endpoints som om agenten redan fanns på andra sidan.

Konsekvens för planeringen: `POST /threads/{view_key}/messages` är inte ett CRUD-anrop. Det är "kör en LLM med bolagets bokföringskontext, låt den svara, och låt den ha verktyg som kan posta i huvudboken". Sessionshantering, kontextbudget, kostnad, tool-use-loop, felhantering när modellen är nere — inget av det är ritat.

---

## 5. Gapanalys mot repot

`datakontrakt.md` är i huvudsak korrekt. Rättelser och tillägg:

| # | Designen kräver | Läge i repot | Kommentar |
|---|---|---|---|
| 1 | Tråd per vy + SSE | **Saknas helt** | Störst. Se §4. Kräver agentruntime, inte bara tabell. |
| 2 | `GET /decisions?status=open` | **Saknas** | `GET /agent/intake/pending` är agentens kö och blandar källmaterial med korrigeringsnoteringar. Designen behöver *fallen där agenten avstod*, med agentens egen motivering — ett annat begrepp. |
| 3 | Idempotensnyckel på utkast | **Saknas helt** | Inga `Idempotency-Key` någonstans. Kritiskt: utan den ger dubbeltryck två verifikationer i en append-only-bok som inte kan städas. |
| 4 | `period_locked` som eget fel | Delvis | Låsning finns (`POST /periods/{id}/lock`), men felet kommer inte typat med vem/när. Flöde 1:s svåra fall kräver det. |
| 5 | `POST /payroll/runs/{id}/approve` med fyra spår | **2 av 4 spår existerar inte** | `payslips` och `voucher` finns. `payment_file` (betalfil, `cancellable_until`) och `agi` — 0 träffar på `betalfil\|payment_file\|agi\|bankgiro\|pain.001` i `services/payroll.py`. Flöde 2 är ritat mot funktioner som inte finns. |
| 6 | `GET /vouchers?missing_attachment=true` | Billigare än det låter | Logiken finns redan i `services/compliance.py:359` (`_check_missing_attachments`). Saknas som queryparam + persistent flagga på verifikationen. |
| 7 | `POST /intake/{id}/interpret` | **Saknas** | Utläsning av leverantör/datum/belopp/moms + matchning mot bankhändelse med `hypothesis`. Det är en LLM-uppgift → hör ihop med §4. |
| 8 | `GET /agent/status` | **Saknas** | Kan inte finnas förrän agenten har ett liv att rapportera om. |
| 9 | `GET /overview` | **Saknas** | Enkel aggregering. Låg risk, hög effekt (headern blinkar annars). |
| 10 | `exclude_series=IB` | **Finns** ✓ | `api/routes/vouchers.py:535`, `repositories/voucher_repo.py:172`. |
| 11 | Faktura faktiskt skickad | **Skickar ingenting** | `POST /invoices/{id}/send` sätter bara `status` + `sent_at` (`api/routes/invoices.py:264`). Ingen SMTP, ingen leverans. Flöde 3:s svåra fall — "bokföring lyckas men **sändning** fallerar" — kan inte inträffa i dagens system eftersom sändning inte gör något som kan fallera. |
| 12 | `view_key` per vy **och bolag** | Enbolag i praktiken | `user_tenants` finns (migration 008) men `vouchers` bär ingen `tenant_id`; `company_id` förekommer 2 gånger i hela kodbasen. Multitenans är inte byggd och ska inte smygas in via `view_key`. |

Frontend: 24 sidor, ~12 700 rader TSX/TS, Next 16 + React 18, Tailwind 3, Radix, TanStack Query, recharts. **Noll frontendtester.** Redesignen är en omskrivning av frontend, inte en omstyling — och det finns inget testnät under den som fångar regressioner.

---

## 6. Fel och motsägelser i handoffen

Små, men de ska redas ut innan de blir kod:

1. **Förslagschips.** `README.md` och `komponenter.md` säger båda uttryckligen om `ChattFalt`: *"Ren text, inga förslagschips."* Skärmbilden `v10-desktop-01-bocker-balansrakning.png` visar två chips under fältet ("Visa de 2 obokade händelserna", "Vad ligger i kundfordringar?"). Vilket gäller?
2. **`operations/log` som befintlig.** Se §4 — den är en tom stubb, inte en källa.
3. **Flöde 3:s svåra fall är inte byggbart som ritat** (§5 rad 11) förrän sändning gör något.
4. **Flöde 2 är ritat mot betalfil och AGI som inte finns** (§5 rad 5). Flödet är rätt tänkt; det bara förutsätter två moduler till.
5. `v10-desktop-01` och `-02` heter balansräkning respektive verifikationer men `-02` visar balansräkningsvyn. Bara märkning.

Designens tre egna öppna frågor (trådens längd över årsskiften, agentläge globalt eller per sida, tröskeln 120 kr för beslutskort) står kvar och är alla tre riktiga produktfrågor, inte detaljer.

---

## 7. Risker

| Risk | Varför den biter | Motdrag |
|---|---|---|
| Dubbelpostning | Append-only betyder att ett dubbeltryck inte kan städas bort — det kräver korrigeringsverifikation. Ingen idempotens finns. | Idempotens byggs **före** något skrivflöde kopplas till en knapp. Icke förhandlingsbart. |
| Agentruntime underskattad | Hela designen antar den; `datakontrakt.md` beskriver bara dess endpoints. | Egen modul, egen spec, byggs först. |
| Big-bang-rewrite av frontend | 24 sidor ersätts av 7 vyer, utan frontendtester. | Ny frontend bredvid den gamla bakom flagga; gamla sidor tas bort vy för vy när motsvarigheten är klar. |
| LLM formulerar text som blir bokföringsunderlag | Designens regel "agenten formulerar, klienten skriver inte om" betyder att modellens ord hamnar i något som liknar en revisionshistorik. | Agentens text lagras som *tråd*, aldrig som verifikationens `description` utan mänskligt beslut. Gränsen ska stå i specen. |
| Kostnad och latens | Sju vyer × egen tråd × strömmande svar. | Trådlängd och kontextbudget beslutas i modulspecen, inte i koden. |
| Scope creep via `view_key` | "per bolag" drar in multitenans genom bakdörren. | Enbolag tills någon beslutar annat. |

---

## 8. Kapabilitetskarta

Efter besluten ovan: `lonespar`, `flode-lon`, `fakturautskick` och `flode-faktura` utgår. Tio moduler kvar.

| Modul-id | Ansvar | Beror på |
|---|---|---|
| `idempotens` | `Idempotency-Key` på postning, `409` med befintligt id, typat `period_locked`-fel med vem/när | — |
| `oversikt` | `GET /overview`, kompletteringsflagga på verifikation + `missing_attachment`-filter | — |
| `agentruntime` | Egen worker: LLM-session med bokföringskontext, verktygsloop, agentläge (`GET /agent/status`), felhantering, livscykel | `idempotens` |
| `tradar` | Trådlagring per `view_key`, inläggstyper, `POST /messages`, SSE med `message.*` + `view.changed` | `agentruntime` |
| `beslut` | `GET /decisions`, `POST /decisions/{id}/answer`, agentens motivering och alternativ | `tradar` |
| `skal` | Nytt frontendskal på plats i `frontend-v3`: 3 sidor / 7 vyer, header, `PrickNav`, `SidVaeljare`, mobil `ChattList`, tokens | `oversikt` |
| `chattyta` | `TradInlagg`, `SparChip`, `BeslutKort`, `AlternativLista`, `VerifikationsForslag`, `FelKort`, `JamforelseRader` | `skal`, `tradar`, `beslut` |
| `flode-verifikationer` | Flöde 1 helt: beslutskort → förslag → postning → låst, inkl. låst period mitt i | `chattyta` |
| `underlagstolkning` | `POST /intake/{id}/interpret`, matchning mot bankhändelse, `hypothesis` | `agentruntime` |
| `flode-underlag` | Flöde 4 helt: agenten ber → filen läses → matchning → kopplat | `flode-verifikationer`, `underlagstolkning` |

**Byggordning**

```
idempotens, oversikt
  → agentruntime
    → tradar → beslut
       skal → chattyta
         → flode-verifikationer
            → underlagstolkning → flode-underlag
```

`skal` byggs parallellt med `agentruntime`/`tradar` mot mockad tråd. Det är den enda meningsfulla parallelliseringen.

**Första leverans:** `idempotens` + `oversikt` + `agentruntime` + `tradar` + `beslut` + `skal` + `chattyta` + `flode-verifikationer` → Böcker · Verifikationer fungerar agent-first hela vägen.

### Konsekvens av att flöde 2 och 3 utgår

Vyerna **Fakturering** och **Löner** finns kvar i informationsarkitekturen — v10 ritar dem som vyer, och de ska byggas som **läsvyer med tråd men utan skrivflöde**. Agenten kan svara på frågor om dem; den kan inte godkänna en lönekörning eller skicka en faktura. Skrivning sker tills vidare via befintliga endpoints, utanför redesignen.

Det ska stå i `skal`-specen, annars byggs två tomma vyer eller två vyer som lovar mer än de gör.

## 8b. Olöst: sidorna som designen inte ritar

Beslutet att **ersätta** `frontend-v3` betyder att 24 sidor ska rymmas i 3. Designen ritar sju vyer och tar inte ställning till resten. Följande finns i dag och har ingen plats i den nya IA:n:

| Sida i dag | Trolig hemvist | Behöver beslut |
|---|---|---|
| `bokslut/ink2`, `bokslut/moms`, `settings/sru-mappings` | Bokslut · Åtgärder | Ryms de som vyer, eller blir Bokslut fler än två vyer? |
| `accounts` (kontoplan) | — | Ingen. Agentens verktyg, eller egen yta? |
| `audit` | Böcker · Verifikationer? | Revisionsspåret är ett BFL-krav, inte en bekvämlighet. Det får inte försvinna i en rewrite. |
| `settings`, `learning` | — | Ingen. |
| `invoices/customers`, `invoices/articles`, `invoices/drafts`, `invoices/new` | Fakturering | Men flöde 3 är ur scope — behålls de som formulär? |
| `vouchers/new`, `vouchers/intake` | Böcker · Verifikationer | Ersätts de av chatten, eller finns de kvar som manuell väg? |

Tre vägar: (a) en fjärde sida "Inställningar" utanför designen, (b) sidorna behålls som egna rutter utanför skalet, (c) de utgår och funktionen flyttas till agenten. Det här är ett designbeslut som inte är taget, och det blockerar `skal`-specen — inte de andra nio.

## 9. Frågor som kvarstår

Besvarade: agentens hemvist, scope, frontendstrategi (se toppen av dokumentet).

Kvar innan modulspecarna skrivs:

1. **Sidorna utan hemvist** (§8b). Blockerar `skal`, ingen annan modul.
2. **Enbolag bekräftat?** `view_key` bär bolaget från dag ett eller inte alls.
3. **Förslagschips: ja eller nej?** (§6.1)
4. **Var går gränsen för agentens text?** Den får aldrig bli en verifikations `description` utan mänskligt beslut — men var exakt går linjen?
5. Designens tre egna: trådlängd över årsskiften, agentläge globalt eller per sida, tröskeln för beslutskort kontra val.
