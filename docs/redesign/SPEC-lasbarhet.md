# Spec: `lasbarhet`

Modul-id `lasbarhet`. Beror på `chattyta`, `tradar`, `flode-verifikationer` och `flode-underlag`
(alla klara). Uppgifterna ligger i `tasks/lasbarhet/todo.md` (L1–L5).

Status: **skriven 2026-09-29.** Beställarens beslut: punkterna genomförs direkt på `redesign-v4`,
och spår-chippen tas bort helt (inte fälls ihop).

---

## 1. Problemet

Beställaren laddade upp ett lönekvitto (`004 - Lön till tjänsteman januari 52000kr.pdf`) i en tråd.
Agenten tolkade det, fann `amount_diff` mot A-11, lade fram ett beslut och kopplade efter svaret.
Flödet var rätt, men tråden var svår att läsa:

1. **Texten är för lång i förhållande till beslutet.** Beslutskortets `reason`, `consequence`
   och varje alternativs `rationale` är flera meningar. Agentens slutsvar upprepar kortet med
   tabell, bedömning och alla tre alternativen. Markdown (`| … |`, `**…**`) visas rått, eftersom
   `TradInlagg` ritar texten i en `<p>`.
2. **Spår-chippen** (`underlagsfilen hämtad`, `tolka_underlag`, `be_om_beslut` …) ger inget för
   beslutet. Fyra verktyg saknar dessutom etikett och visas med sitt tekniska namn.
3. **Resonemanget syns.** `services/thread_stream.py` samlar *all* text från turen, också den
   agenten skriver mellan verktygsanropen ("Jag läser filen …", "Människan har besvarat …"),
   och sparar den som ett inlägg, ihopklistrad utan mellanslag.
4. **Listan över postade verifikationer tar slut efter 50** (`VERIFIKATIONER_ANTAL`). Resten går
   inte att nå.

## 2. Mål

| # | Mål | Mätbart som |
|---|---|---|
| M1 | Ett agentinlägg innehåller bara turens svar, aldrig mellantexten. | Test: en tur med text → verktyg → text sparar bara det sista stycket. |
| M2 | Under körningen syns mellantexten bara tills nästa verktygsanrop. | Test i reducern: `activity` nollställer den strömmande texten. |
| M3 | Beslut och svar i en tråd är korta. | Instruktionen säger det; `test_agent_entrypoint.py` kräver stycket. |
| M4 | Inga spår-chip i klienten. | Ingen `SparChip`/`sparchip` kvar i `frontend-v3` utanför tester som kräver frånvaro. |
| M5 | Agentens text visas som markdown. | Test: tabell, fetstil och lista blir element, inte tecken. |
| M6 | Alla postade verifikationer går att nå genom att skrolla. | Test: nästa sida hämtas när listans slut syns. |

## 3. Utanför

- Servern slutar **inte** spara `traces[]`. Spåren är bryggan mellan `agent_run_events` och
  inlägget (`SPEC-tradar.md`), och de är revisionsspår. Bara klienten slutar visa dem.
- Beslutskortets layout ändras inte. Kortheten kommer från agentens text.
- Ingen ändring av bokföringsreglerna i instruktionen, bara av hur agenten skriver.

## 4. Lösningen, per punkt

### 4.1 Bara slutsvaret sparas (L1)

**Server** (`services/thread_stream.py`): textdeltan samlas per *stycke*. Ett verktygsanrop
(`_on_tool_call`) avslutar stycket; nästa text börjar ett nytt. `answer_text` till
`ThreadService.record_outcome` är det **sista** stycket, trimmat. Är det tomt (turen slutade med
ett verktygsanrop) skickas `None`, så att `_render` faller tillbaka på `outcome.text` — men bara om
`outcome.text` inte själv är en sammanfogning av mellantext; det ska L1 kontrollera i
`services/thread_session.py` och i så fall ge samma regel där (sista stycket).

Fallbacken för `posted` blir `"Verifikation {series}-{number} är postad."` när numret finns i
`outcome` — chippet `verifikation postad · A-118` var tidigare det enda stället numret syntes utan
att agenten skrev det.

**Klient** (`frontend-v3/lib/chattyta/trad.ts`): `message.delta {activity}` nollställer
`strommande.text` till `""` och sätter `activity`. Då visar `SkriverIndikator` verktygets
presensetikett igen, och mellantexten försvinner. `message.completed` ersätter som förut
platshållaren med det lagrade inlägget.

Deltaströmmens protokoll ändras inte.

### 4.2 Instruktionen (L2)

`docs/to_agent/03_bokforingsinstruktion.md` får ett stycke **"Att skriva i en tråd"**, efter
"Skrivregler för agenten". Innehåll (formuleringen är L2:s, innebörden är fast):

- Skriv till användaren i andra person ("du"). Nämn aldrig "människan" eller dig själv i tredje
  person.
- Beskriv inte vad du ska göra eller har gjort med verktygen. Skriv resultatet.
- Slutsvaret är högst tre meningar, om inte användaren bett om en förklaring eller en lista.
- När du lagt fram ett beslut med `be_om_beslut`: slutsvaret är **en** mening som hänvisar till
  beslutet. Upprepa inte kortets innehåll.
- I `be_om_beslut`: `reason` högst två meningar med de belopp som skiljer; `consequence` en
  mening; varje alternativs `rationale` en mening. Ett alternativ som inte rekommenderas förklaras
  inte utförligt.
- Efter en postning: nämn verifikationsnumret.
- Efter en koppling (regel 9 i underlagsavsnittet): en mening om kopplingen, en om nästa
  verifikation som saknar underlag med nummer, belopp och ålder, och frågan om underlaget.

Regel 9 och eventuella andra ställen som motsäger stycket justeras så att de inte krockar.
`docs/to_agent/*.md` är körtidsinnehåll: `tests/test_agent_entrypoint.py` ska kräva att stycket
finns (rubriken och regeln om `be_om_beslut`-svaret).

**L6** (tillagd efter L2): verktygsbeskrivningarna i `services/agent_tools.py` och
`docs/to_agent/02_bokforingsprocess.md` säger "människan"; det är det agenten läser och
upprepar. De säger "användaren". `BeOmBeslutArgs.reason`, `consequence` och
`BeOmBeslutOption.rationale` får `Field(description=…)` med längden ur stycket ovan.

### 4.3 Spår-chippen bort (L3)

Klienten ritar inga spår. Bort: `SparChip`, `SparChipRad`, deras användning i `TradInlagg`,
`TradRenderare` och `FelKort` (knappen "Visa vad som hände" försvinner med dem, eftersom den bara
fällde ut chippen), och `SPAR_ETIKETTER` i `lib/chattyta/etiketter.ts`. `Spar`/`traces` får ligga
kvar i typerna — servern skickar dem fortfarande.

`SKRIVER_ETIKETTER` behålls (indikatorn) och får de verktyg som saknas: `tolka_underlag`
("Tolkar underlaget…"), `be_om_beslut` ("Lägger fram ett beslut…"), `koppla_underlag`
("Kopplar underlaget…"), `foresla_verifikation` ("Föreslår en verifikation…"). L3 kontrollerar
mot `services/agent_tools.py` att listan är komplett. Testet som krävde att klientens tabell var
lika med serverns `_TRACE_LABELS` skrivs om: det kräver i stället att varje verktyg i
`agent_tools.py` har en presensetikett. `_TRACE_LABELS` på servern får samma fyra verktyg, så att
lagrade spår är läsbara i revisionen.

### 4.4 Markdown (L4)

Agentens text i `TradInlagg` ritas med `react-markdown` + `remark-gfm` (tabeller). Ingen rå HTML
(ingen `rehype-raw`). Länkar öppnas i ny flik med `rel="noopener noreferrer"`. Stilen följer
inläggets: 15/1.6, max 54ch för stycken; tabeller får full kolumnbredd, tunna linjer
(`border-bok-linje`), siffror högerställda när cellen är ett belopp är inte ett krav. Användarens
egna inlägg ritas som förut, som ren text.

Gäller bara `agent_text`. Beslutskortets fält är ren text.

### 4.5 Hela listan (L5)

"Postade" i Böcker → Verifikationer hämtas sida för sida med `useInfiniteQuery` (`offset`,
`limit = VERIFIKATIONER_ANTAL`), under samma nyckelprefix `VOUCHERS_NYCKEL`, så att
`view.changed` och postningar fortfarande invaliderar den. Nästa sida hämtas när ett vaktelement
i slutet av vyns skrollyta blir synligt (`IntersectionObserver`). Så länge fler finns står en rad
"Laddar fler…" sist; när `total` är nådd står ingenting. Rubriken ("N postade") använder
serverns `total` som förut.

`VyData` får det som behövs för att vyn ska kunna be om mer (t.ex. `harFler` och `hamtaFler`),
utan att andra vyer påverkas.

## 5. Uppgifter och filägarskap

| Uppgift | Filer (testfiler oräknade) | Beror på |
|---|---|---|
| L1 | `services/thread_stream.py`, `services/thread_service.py`, `services/thread_session.py`, `frontend-v3/lib/chattyta/trad.ts` | — |
| L2 | `docs/to_agent/03_bokforingsinstruktion.md`, `tests/test_agent_entrypoint.py` | — |
| L3 | `frontend-v3/components/chattyta/{TradInlagg,TradRenderare,FelKort}.tsx`, `frontend-v3/lib/chattyta/etiketter.ts`, `services/thread_service.py` (`_TRACE_LABELS`) | — |
| L4 | `frontend-v3/components/chattyta/TradInlagg.tsx`, `frontend-v3/package.json`, `package-lock.json` | L3 |
| L6 | `services/agent_tools.py`, `docs/to_agent/02_bokforingsprocess.md` | L2 |
| L5 | `frontend-v3/hooks/useVyer.ts`, `frontend-v3/lib/skal/bocker.ts`, `frontend-v3/lib/skal/vydata.ts`, `frontend-v3/components/skal/VyInnehall.tsx` | — |

L1 och L3 rör båda `services/thread_service.py` men olika ställen (`_render` resp.
`_TRACE_LABELS`). L4 väntar på L3 eftersom båda rör `TradInlagg.tsx`.

## 6. Klart när

- `pytest tests/ -q` grönt; `cd frontend-v3 && npm test && npm run lint && npx tsc --noEmit`
  grönt.
- M1–M6 har var sitt test.
- `black`, `isort`, `flake8` rena för ändrade Python-filer.
