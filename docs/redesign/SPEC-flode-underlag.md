# Spec: `flode-underlag`

Modul-id `flode-underlag` i kapabilitetskartan (`ANALYS.md` §8). Beror på `flode-verifikationer`
(klar, F1–F16) och `underlagstolkning` (klar, U1–U15), och genom dem på alla moduler i första
leveransen. Det är den sista modulen i kartan: när den är klar fungerar flöde 4 agent-first hela
vägen, från att en verifikation saknar underlag till att underlaget är kopplat.

Status: **Fas 1 — skriven och godkänd 2026-09-28.** Tio beslut tagna av beställaren (§12,
D1–D10), alla enligt förslaget: agenten kopplar själv bara vid exakt match; differensen bokförs som
en egen verifikation med hänvisning till kvittot; rättelser räknas inte som "saknar underlag";
ersättning av ett felkopplat underlag blir en egen modul direkt efter den här. Uppgifterna skrivs
i `tasks/flode-underlag/`.

---

## Antaganden

1. **Flödet är designens flöde 4, fyra steg.** Källan är annoteringspanelen i
   `BokAi flöden v1.dc.html` (`flode4` i `BokAI App Redesign.zip`): *Agenten ber om underlaget*,
   *Filen läses*, *Agentens matchning*, *Kopplat*. Citat i kursiv nedan är panelens. Där specen
   avviker från panelen står det, och varför (§2).
2. **Tolkningen är klar och ändras inte i sak.** Matchningen, säkerheten och hypotesen räknas som
   i `SPEC-underlagstolkning.md` §6–§7. Den här modulen läser den senaste tolkningen och handlar
   på den. Den enda ändringen i tolkningsvägen är att verktyget skriver ett jämförelseinlägg när
   det körs i en tråd (D6).
3. **Att koppla är att skriva i bokföringens spår, men inte i huvudboken.** En koppling är en rad
   i `voucher_intake_sources`, ett försök i `intake_processing_attempts` och ett statusbyte på
   källan. Ingen verifikation ändras och ingen skapas. Men kopplingen är en del av det BFL kräver
   (verifikationen ska ha sitt underlag), och det finns ingen väg att ta bort den. Den behandlas
   därför som en postning: den kräver belägg för att den är rätt (§6.3), och den är idempotent.
4. **Append-only är oförhandlingsbart.** En differens bokförs genom en ny verifikation, aldrig
   genom att den matchade ändras (D2). Panelen kräver att ett felkopplat underlag ska kunna
   ersättas *"och lämna spår"*; det byggs i en egen modul direkt
   efter den här (D10).
5. **Enbolag, en människa, SEK**, som i alla tidigare moduler.

→ Punkt 1 och 3 är de dyra. Punkt 1 för att specen annars bygger ett flöde som inte är ritat, punkt
3 för att en koppling som inte kan tas bort är lika svår att städa som en postning.

---

## 1. Objektiv

### Problemet, konkret

Varje del av flöde 4 finns utom den sista, och den sista är den som ger flödet ett slut:

- **Det finns ingen väg att koppla ett underlag till en postad verifikation.**
  `IntakeService.link_existing_voucher` (`services/intake.py:254`) gör precis det, men den anropas
  bara inifrån en postning: `services/voucher_posting.py:103` och `services/draft_service.py:789`.
  Ingen route och inget verktyg kan koppla ett kvitto till A-118 i efterhand. `POST
  /vouchers/{id}/attachments` (`api/routes/attachments.py:35`) skriver en ny fil i `attachments`
  utan koppling till intagskön, tolkningen eller tråden, och har SQL i routen.
- **Tolkningen hittar matchningen men kan inte göra något med den.** `SPEC-underlagstolkning.md`
  §9 punkt 2 säger åt agenten att avstå och skriva *"Kopplingen görs i `flode-underlag`"*. I dag
  slutar alltså flöde 4 i ett avstående, och det avstående underlaget ligger kvar som ett
  syntetiskt beslut (`intake:…`) som inte går att besvara (`SPEC-beslut.md` §5).
- **Dubbelposten stoppas bara av en instruktion.** Det hårda stoppet i postningen sköts hit
  (`SPEC-underlagstolkning.md` §12.4), eftersom ett stopp utan kopplingsväg bara blir ett nytt
  avstående.
- **Människan kan inte släppa en fil i tråden.** Backenden tar redan emot bilagor
  (`POST /threads/{vk}/messages` med `attachments`, `api/routes/threads.py:230`), men `ChattFalt`
  är ren text. `drop`-varianten är ritad och uttryckligen lämnad hit (`SPEC-skal.md` §9,
  `SPEC-chattyta.md` §1).
- **Jämförelsen syns inte.** Tolkningen har båda beloppen, men ingenting skriver designens
  `JamforelseRader` med `labels: ["kvitto", "A-118"]` (`SPEC-chattyta.md` §4.3).
- **Vyn har ingen kompletteringslista.** Panelen: *"Kompletteringar är en egen sektion i vyn"*,
  först, med ålder (*"Kompletteringar först · postade nedan"*). I `/v4` står de i dag inne i
  `Postade` med varianten `saknar` (`lib/skal/bocker.ts:288`).
- **Agenten kan inte se vad som saknar underlag.** `las_verifikationer` returnerar inte
  `missing_attachment` (`services/agent_tools.py:458`), så agenten kan inte be om kvittot till
  A-118 utan att människan först säger att det saknas.

Två fynd till, i §3, formar modulen.

### Vad vi bygger

1. **`koppla_underlag`**, agentens trettonde verktyg: kopplar ett underlag till en postad
   verifikation, med belägg (§6).
2. **`POST /api/v1/intake/{id}/link`**, samma regler och samma service för en session utan
   verktyget (§7).
3. **Tabellerna `intake_link_basis` och `voucher_source_references`**, append-only: varför
   varje koppling gjordes, och differensverifikationens hänvisning till kvittot (§5, D2).
4. **Det hårda stoppet** `source_matches_posted_voucher` i postningen och förslaget (§8).
5. **Jämförelseinlägget**: tolkning i en tråd ger `JamforelseRader` med båda beloppen (§9).
6. **Kvittot**: en koppling i en tråd ger ett `receipt`-inlägg och `view.changed` (§9.3).
7. **`ChattFalt`s `drop`-variant**: fil, kamera, urklipp (§10).
8. **Sektionen `Saknar underlag`** i Verifikationer, och kvittot åtkomligt från verifikationen
   (§10.4).
9. **Agentinstruktionen**: be med motivering, koppla vid exakt match, lägg fram beslut vid
   differens (§11).

### Vad vi inte bygger här

- **Att ersätta ett felkopplat underlag** (D10: egen modul, `underlag-ersatt`, direkt efter). Panelen kräver det
  (*"Ersätta ett felaktigt kopplat underlag ska vara möjligt och lämna spår"*, *"Fel verifikation
  vald: vägen tillbaka måste vara lika lätt som vägen fram"*). Det kräver en ombyggnad av
  `voucher_intake_sources` (§3.2), och den förtjänar en egen spec.
- **Att dela upp ett underlag med flera köp** (*"Ett kvitto kan innehålla flera köp och då behöver
  det delas upp"*). Ett underlag kopplas till en verifikation; `UNIQUE(intake_source_id)` i
  `voucher_intake_sources` står kvar (§3.2).
- **Valutaomräkning.** Ett underlag i annan valuta matchas inte (`SPEC-underlagstolkning.md`
  §7.1) och kan bara kopplas via ett beslut (§6.3).
- **En påminnelse om gamla kompletteringar** (*"Mycket gamla kompletteringar hör hemma i en
  påminnelse"*). Ingen schemaläggare i den här modulen (§13.2).
- **`POST /vouchers/{id}/attachments`** rörs inte. Den gamla vägen står kvar orörd, som de gamla
  sidorna (`SPEC-skal.md` §3), med sin SQL i routen.

### Användare

- **Människan**, i Verifikationers tråd: släpper ett kvitto, ser det mot verifikationen, väljer
  vid en differens.
- **Agenten**, i trådturen och i intagspasset: kopplar vid exakt match, lägger fram ett beslut
  annars.
- **En extern session** (`scripts/bok-curl`): samma koppling över HTTP.

### Framgång

A-118 på 4 480 kr är bankbokförd och står överst i `Saknar underlag`, *"kvitto saknas sedan 3
dgr"*. Agenten ber om kvittot och säger varför: avdraget ska hålla vid en granskning. Människan
släpper det i tråden. Agenten läser det och tolkar det: 4 600 kr mot 4 480 kr, samma moms, och en
hypotes om raden *Pant 120,00*. Tråden visar båda beloppen. Agenten lägger fram ett beslut med tre
alternativ: koppla och bokför skillnaden, koppla utan att ändra, eller det är ett annat köp.
Människan väljer att koppla och bokföra. Tråden kvitterar kopplingen, agenten lägger fram
differensen som ett förslag, och människan postar det som A-121. A-118 flyttar till `Postade`
med *"kvitto kopplat · A-121 korrigering"*, räknaren i headern går ner med ett utan omladdning,
och agenten nämner nästa saknade kvitto.

Med ett kvitto på exakt 4 480 kr samma dag hoppas beslutet över: agenten kopplar direkt och
kvittot står i tråden.

I intagspasset kopplas ett kvitto som matchar exakt, i stället för att passet avstår. Ett försök
att posta en ny verifikation för samma kvitto avvisas med `source_matches_posted_voucher`.

---

## 2. Flödet, steg för steg, mot vad som bär det

| Steg | Panelen | Bärs av | Ny här? |
|---|---|---|---|
| 1 Agenten ber om underlaget | Sektionen `Saknar underlag` med ålder; agenten säger *varför* underlaget behövs; `ChattFalt/drop` | Sektionen (§10.4); `missing_attachment` i `las_verifikationer`s svar; instruktionen | **Ja** (§10, §11) |
| 2 Filen läses | Filen i tråden, *"Läser kvittot…"*, status `läser underlag` | `drop` → `POST /intake` → `POST /threads/{vk}/messages`; `hamta_underlagsfil` → `tolka_underlag` | Uppladdningen (§10) |
| 3 Agentens matchning | Kvitto mot A-118, båda talen; momsen som fot; tre alternativ | **Jämförelseinlägget** (§9.1); `be_om_beslut` med alternativ (§9.2) | Inlägget |
| 4 Kopplat | Kopplingen och korrigeringen som två rader; raden till `Postade`; nästa saknade nämns | **`koppla_underlag`** + kvitto (§6, §9.3); differensen via `foresla_verifikation` → flöde 1 steg 3–6 | **Ja** |
| — Exakt match | *"ska hoppa över det här steget och gå direkt till kopplat"* | `koppla_underlag` med `exact_match`, utan beslut (D1) | **Ja** |
| — Utan sammanhang | *"agenten fråga vilken verifikation det gäller"* | `match = null`: agenten frågar; svaret binder `voucher_id` (§6.3) | Nej |
| — Oläsbar bild | *"agenten ber om en ny i stället för att gissa fram belopp"* | `confidence = low`: instruktionen | Nej |
| — Ett annat köp | Alternativ 3, tillbaka till steg 1 | Exit-alternativet; ingen koppling | Nej |
| — Fel verifikation vald | *"vägen tillbaka måste vara lika lätt som vägen fram"* | **Byggs inte här** (D10) | — |

Fem avvikelser från panelen, alla medvetna:

- **Steg 3 är ett beslutskort med alternativlistan, inte bara en lista.** Panelens egen kant säger
  det: *"Skillnader över en tröskel bör bli ett beslutskort i stället för ett val"*, och
  `SPEC-beslut.md` §11.1 gör regeln skarp: `Koppla och bokför skillnaden` ändrar böckerna.
  `be_om_beslut` skriver kortet och listan i samma anrop, så människan ser dem tillsammans.
- **Jämförelsen och kvittot är serverns inlägg, inte agentens rader.** Panelen ritar raderna
  (`kvitto 4 600` / `A-118 4 480`) inne i agentens text. Här skriver servern dem som
  `JamforelseRader` (§9.1, D6), av samma skäl som `SPEC-flode-verifikationer.md` §12.3: talen är
  fakta om underlaget och bokföringen. Agentens text står bredvid, med hypotesen som hypotes.
- **Steg 4 är två kvitton och ett tryck, inte ett inlägg.** Panelen visar kopplingen och den
  postade korrigeringen i samma agentinlägg. Här kvitteras kopplingen av servern direkt, och
  korrigeringen blir ett förslag som människan postar med `Posta`, med eget kvitto. Panelen säger
  själv *"Kopplingen och korrigeringen kvitteras som två rader, eftersom den ena rör underlag och
  den andra bokföringen"*; här blir det två inlägg av samma skäl. Att agenten postar differensen
  direkt vore att posta på ett val, och ett förslag är vägen när människan har valt
  (`SPEC-flode-verifikationer.md` §12.2).
- **Jämförelsen räknas mot verifikationen, inte mot bankhändelsen.** Panelens rad heter
  *"A-118 · Bankhändelse"*. Bankhändelsen visas som sammanhang när verifikationen har en, men det
  är verifikationen som får underlaget (`SPEC-underlagstolkning.md` §7.1).
- **Ingenting kopplas utan att människan sagt ja — utom vid exakt match.** Panelens steg 2 säger
  *"Ingenting kopplas förrän du sagt att det stämmer"* och *"aldrig en automatisk koppling"*,
  medan steg 3:s kant säger att exakt match går *"direkt till kopplat"*. Specen läser kanten som
  undantaget från regeln (D1).

---

## 3. Fynden som formar modulen

### 3.1 Rättelser räknas som "saknar underlag"

`MISSING_ATTACHMENT_SQL` (`repositories/voucher_repo.py:23`) undantar IB och SIE4-importen men
inte B-serien. En rättelse som postats via Verifikationers chatt (`SPEC-flode-verifikationer.md`
§7) har varken `attachments` eller `voucher_intake_sources`: dess underlag är originalet och
rättelsehistoriken i `accounting_corrections`. Varje sådan rättelse står alltså som "saknar
underlag" i vyn, räknas i `GET /overview` och blir en kandidat i matchningen.

Det slår mot modulen eftersom sektionen `Saknar underlag` (§10.4) blir den lista flöde 4 börjar
i: varje rättelse skulle stå där och be om ett kvitto som inte finns. D3 föreslår att predikatet
undantar `vouchers.correction_of IS NOT NULL`. Det ändrar vad "saknar underlag" betyder, vilket
är ett "fråga först" (`SPEC-underlagstolkning.md` §14).

### 3.2 Ett underlag bär en verifikation

`voucher_intake_sources` har `UNIQUE(intake_source_id)` (`db/migrations/018_add_intake_sources.sql:49`).
Det är skyddet mot att samma kvitto bokförs två gånger, och `intake_already_linked` bygger på det.
Det står kvar.

Två följder:

- **Panelens A-121 har inget underlag.** Differensen bokförs som en egen verifikation på 120 kr,
  men kvittot är redan kopplat till A-118 och kan inte kopplas en gång till. A-121 skulle stå i
  `Saknar underlag` för alltid. D2 löser det med en **hänvisning**: A-121 hänvisar till kvittot
  via A-118, i en egen tabell (§5), utan att kvittot kopplas två gånger. Hänvisningen skrivs av
  servern ur beslutet, inte av agenten (§9.2).
- **Ett felkopplat underlag kan inte flyttas.** Att ersätta kopplingen, som panelen kräver,
  betyder att källan måste kunna bära en ny länk medan den gamla står kvar som spår. Det går inte
  med `UNIQUE(intake_source_id)`, och SQLite kan inte ta bort ett `UNIQUE` utan att bygga om
  tabellen. Det är D10.

### 3.3 Kopplingen kräver en källa i kön

`IntakeService._ensure_can_record_outcome` (`services/intake.py:320`) släpper bara igenom
`pending` och `processing`. Men flöde 4:s underlag hamnar ofta i `failed`: intagspasset avstår
från ett kvitto som matchar en postad verifikation, precis som `SPEC-underlagstolkning.md` §9
punkt 2 föreskriver, och `registrera_avstaende` sätter källan `failed`. Just det underlag som
kopplingen finns för skulle då inte gå att koppla.

Kontrollen i `_ensure_can_record_outcome` ändras inte: den skyddar postningen, där ett `failed`
underlag ska förbli avstått. Kopplingen får en egen kontroll som också släpper igenom `failed` och
`needs_attention` (D9, §6.3).

### 3.4 Tråd och intagspass tävlar om samma fil

En fil som släpps i tråden blir en källa med `status='pending'`. Trådturen startar direkt och
tolkar den. Nästa intagspass läser `list_pending` (`services/agent_runtime.py:396`) och får samma
källa. Passet körs bara manuellt i dag, men om det körs medan tråden väntar på människans val
avstår det, och källan blir `failed` mitt i ett samtal där beslutet redan ligger framme.

D4 föreslår att passet hoppar över källor som har ett `user_file`-inlägg i en tråd. Tråden äger
dem.

---

## 4. Tech stack och kommandon

Inga nya beroenden. FastAPI, SQLite med trådlokala anslutningar och WAL, pydantic. Frontend som
`chattyta`: Next 16, React 18, TanStack Query, vitest.

```bash
pytest tests/test_flode_underlag.py -v
pytest tests/ -v
black . && isort . && flake8
mypy .                               # 61 fel är baslinjen; inga nya
python main.py --init-db             # tillämpar migration 032
cd frontend-v3 && npm test && npm run lint && npx tsc --noEmit
cd frontend-v3 && NEXT_PUBLIC_SKAL=1 npm run build
```

Nya och ändrade filer, i huvudsak:

```
db/migrations/032_add_intake_link_basis.sql     # §5
domain/intake_link.py                           # LinkBasis, LinkResult
repositories/intake_link_repo.py                # insert, get_for_source; ingen update/delete
repositories/intake_repo.py                     # list_pending utan trådens källor (D4)
repositories/voucher_repo.py                    # predikatet (D3); missing_attachment i agentens läsning
repositories/thread_repo.py                     # receipt_for_source (§9.3)
services/intake_link.py                         # kontrollerna, beläggen, kopplingen, kvittot
services/voucher_posting.py                     # stoppet (§8)
services/draft_service.py                       # stoppet i foresla_verifikation (§8)
services/interpretation_service.py              # jämförelseinlägget i en tråd (§9.1)
services/agent_tools.py                         # koppla_underlag sist; missing_attachment i _voucher_dict
api/routes/intake.py                            # POST /intake/{id}/link; existing_id i 409
api/routes/threads.py                           # tom text med bilagor (D8)
docs/to_agent/03_bokforingsinstruktion.md       # §11 -- körtidsinnehåll
frontend-v3/components/skal/ChattFalt.tsx       # drop-varianten
frontend-v3/lib/chattyta/uppladdning.ts         # uppladdning, dubbletter, fel
frontend-v3/lib/chattyta/parse.ts               # receipt.note (D7)
tests/test_flode_underlag.py
frontend-v3/lib/chattyta/__tests__/uppladdning.test.ts
```

`services/intake_link.py` innehåller ingen SQL. Service-till-service-importer skjuts in i
metoderna (`AGENTS.md`).

---

## 5. Datamodell — migration 032

```sql
CREATE TABLE intake_link_basis (
    intake_source_id   TEXT PRIMARY KEY REFERENCES intake_sources(id),
    voucher_id         TEXT NOT NULL REFERENCES vouchers(id),
    basis              TEXT NOT NULL,
    interpretation_id  TEXT NOT NULL REFERENCES intake_interpretations(id),
    decision_id        TEXT REFERENCES decisions(id),
    actor              TEXT NOT NULL,
    agent_run_id       TEXT REFERENCES agent_runs(id),
    thread_id          TEXT REFERENCES threads(id),
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (basis IN ('exact_match', 'decision')),
    CHECK ((basis = 'decision') = (decision_id IS NOT NULL))
);

CREATE TRIGGER prevent_update_intake_link_basis
BEFORE UPDATE ON intake_link_basis
BEGIN SELECT RAISE(ABORT, 'intake link basis is append-only'); END;

CREATE TRIGGER prevent_delete_intake_link_basis
BEFORE DELETE ON intake_link_basis
BEGIN SELECT RAISE(ABORT, 'intake link basis is append-only'); END;
```

**Varför en egen tabell.** `voucher_intake_sources.link_reason` är fri text. Beläggen för en
koppling (vilken tolkning servern jämförde, vilket beslut människan besvarade) ska gå att läsa och
testa som data, inte tolkas ur en sträng. Samma skäl som tolkningens ögonblicksbild
(`SPEC-underlagstolkning.md` §5): det agenten handlade på ska gå att läsa i efterhand.

**Varför `intake_source_id` är nyckeln.** En källa kopplas en gång (§3.2), så den har ett
belägg. Kopplingar som gjorts av en postning har inget belägg här: de bär sitt underlag genom
postningen, och `basis` gäller bara kopplingar i efterhand.

**Varför ingen `receipt_post_id`.** Den skulle kräva en `UPDATE` efter commit, som
`thread_drafts` gör. Tabellen är append-only i tre lager, och kvittots idempotens löses i stället
genom att fråga tråden (§9.3).

**Hänvisningen (D2)**, i samma migration:

```sql
CREATE TABLE voucher_source_references (
    voucher_id        TEXT PRIMARY KEY REFERENCES vouchers(id),   -- A-121
    intake_source_id  TEXT NOT NULL REFERENCES intake_sources(id), -- kvittot
    via_voucher_id    TEXT NOT NULL REFERENCES vouchers(id),       -- A-118, som bär kopplingen
    decision_id       TEXT NOT NULL REFERENCES decisions(id),
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (voucher_id != via_voucher_id)
);
-- samma två triggrar: ingen UPDATE, ingen DELETE
```

Raden skrivs i postningens transaktion (`DraftService.on_posting`), när ett trådförslag postas
vars `decision_id` är ett `intake_link_basis.decision_id`. Förslaget bär alltså ingenting nytt:
beslutet binder differensen till kvittot, och servern slår upp det. `foresla_verifikation`s
argument ändras inte.

`MISSING_ATTACHMENT_SQL` får ett villkor till: `AND NOT EXISTS (SELECT 1 FROM
voucher_source_references vsr WHERE vsr.voucher_id = vouchers.id)`. A-121 har ett underlag, genom
hänvisningen, och står inte i `Saknar underlag`.

`link_reason` i `voucher_intake_sources` fylls ändå, för den som läser den tabellen direkt:
`"exact_match interpretation={id}"` eller `"decision={id} interpretation={id}"`.

**Ingen kolumn på `vouchers`**, ingen ändring i `voucher_intake_sources`.

---

## 6. `koppla_underlag`

### 6.1 Vad det gör

Kopplar ett underlag i intagskön till en postad verifikation, efter att servern kontrollerat att
kopplingen har belägg. Skriver i en transaktion: länken (`IntakeService.link_existing_voucher`
utan källkontrollen i §3.3), försöket, källans status `processed`, och raden i
`intake_link_basis`. Efter commit, i en tråd: kvittot (§9.3).

Verktyget skapar aldrig en verifikation och ändrar aldrig en. Det är inte terminalt: turen
fortsätter efter svaret.

### 6.2 Argumenten

```python
class KopplaUnderlagArgs(BaseModel):
    source_id: str
    voucher_id: str
    decision_id: Optional[str] = None
```

Inget fält för belopp, differens eller motivering. Differensen finns i tolkningen, och
motiveringen är beslutet eller den exakta matchningen.

Beskrivning i verktygslistan:

> Koppla ett underlag till en redan postad verifikation som det hör till. Kräver en tolkning av
> underlaget (tolka_underlag). Utan beslut: bara när tolkningens match är exakt och verifikationen
> fortfarande saknar underlag. Annars: ange decision_id för ett besvarat beslut om just det
> underlaget. Skapar ingen verifikation och ändrar ingen.

Den nämner inte huvudboken (`SPEC-underlagstolkning.md` §12.6 c).

### 6.3 Kontrollerna

I den här ordningen. Ingenting skrivs om någon av dem slår.

| # | Kontroll | Fel |
|---|---|---|
| 1 | Källan finns | `source_not_found` |
| 2 | Källan är inte raderad | `source_deleted` |
| 3 | Källan är redan kopplad **till samma verifikation** | Ingen felkod: uppspelning (§6.5) |
| 4 | Källan är kopplad till en annan verifikation | `intake_already_linked`, med den verifikationens nummer i `details` |
| 5 | Källans status är `pending`, `processing`, `failed` eller `needs_attention` (D9) | `intake_not_linkable` med status |
| 6 | Verifikationen finns, är postad och inte i serie `IB` | `voucher_not_found` / `voucher_not_posted` / `voucher_is_opening_balance` |
| 7 | Källan har en tolkning | `interpretation_required`: *"tolka underlaget med tolka_underlag först"* |
| 8 | Verifikationen står i den senaste tolkningen: som `match`, som `expected` eller bland `candidates` | `voucher_not_in_interpretation`, med tolkningens verifikationsnummer |
| 9 | Beläggen, §6.4 | `link_requires_decision` / `decision_*` |

Kontroll 8 binder kopplingen till det servern jämförde. Agenten kan inte koppla kvittot till en
verifikation som aldrig ställts mot det. Vill människan koppla till en verifikation utanför
fönstren, till exempel en SIE4-importerad som aldrig är kandidat (`SPEC-underlagstolkning.md`
§12.5), tolkar agenten om med `expected_voucher_id` först. Då står den i tolkningen som `expected`.

### 6.4 Beläggen (D1)

En koppling har exakt ett av två belägg:

**`exact_match`**, utan människa. Alla tre:

- den senaste tolkningens `match.kind = "exact"`;
- `match.voucher_id = voucher_id`;
- `match.still_open` räknat nu (`VoucherRepository.match_still_open`): verifikationen saknar
  fortfarande underlag.

Det är designens *"Exakt match ska hoppa över det här steget"*. `exact_no_date` räcker inte
(`SPEC-underlagstolkning.md` §12.6 d): utan datum skiljer ingenting ett återkommande belopp från
samma köp.

**`decision`**, med `decision_id`. Alla fem:

| Villkor | Fel |
|---|---|
| Beslutet finns | `decision_not_found` |
| Det har status `answered` | `decision_still_open` / `decision_superseded` |
| Dess `source` är `{kind: "intake_source", id: source_id}` | `decision_not_for_source` |
| I en trådtur: beslutet hör till samma tråd | `decision_not_in_thread` |
| Svaret är fritext eller ett alternativ utan `is_exit` | `decision_declined` |

Det sista villkoret är det enda sättet servern kan läsa ett *nej* ur svaret. Sista alternativet i
en lista är alltid en väg ut (`SPEC-beslut.md` §6.3), och i flöde 4 är vägen ut *"Det är ett
annat köp"*. Ett fritextsvar kan servern inte läsa. Det släpps igenom, eftersom varje beslut ska
gå att ge i fritext (`README.md`), och agenten bär ansvaret för att läsa det rätt. Priset står i
§13.4.

Saknas båda: `link_requires_decision`, med tolkningens `match.kind` i `details`, så att agenten
vet att den ska lägga fram ett beslut.

### 6.5 Idempotens

Kopplingen är idempotent genom schemat, inte genom en nyckel: `UNIQUE(intake_source_id)` gör att
en källa bara kan kopplas en gång. Ett andra anrop med samma källa och samma verifikation är en
uppspelning. Det ger samma svar med `replayed: true`, skriver ingenting och kör om kvittot bara om
det saknas (§9.3). Samma verifikation, annat beslut, är också en uppspelning: kopplingen finns
redan och beläggen skrivs inte om.

Samma mönster som `SPEC-beslut.md` §11.4: resursen är unik, så ingen `Idempotency-Key` behövs.

### 6.6 Svaret

```json
{
  "source_id": "…",
  "voucher_id": "…", "voucher_number": "A-118",
  "basis": "decision",
  "interpretation_id": "…",
  "decision_id": "…",
  "replayed": false,
  "missing_attachments": 3
}
```

`missing_attachments` är räknaren efter kopplingen (`VoucherRepository.count_missing_attachments`),
så att agenten kan säga hur många som är kvar utan att läsa om listan.

### 6.7 Placering i verktygslistan

Sist i `_TOOL_SPECS`, efter `tolka_underlag`. Det blir det trettonde verktyget. Ett tillägg sist
kostar en cache-miss en gång och flyttar inget annat (`SPEC-agentruntime.md` §6.6).
`agentruntime`s testfall 17, `beslut`s 26 och `underlagstolkning`s 34 körs mot den utökade
listan; det senares *"`tolka_underlag` sist"* blir *"`tolka_underlag` tolfte"*.

`tool_context` ger `thread` → `thread_id`, turens `agent_run_id` och aktören. Utan `thread` är
det ett anrop från intagspasset: då gäller bara `exact_match`, eftersom ett beslut hör till en
tråd och passet inte har någon (kontroll 9 ger `link_requires_decision`).

---

## 7. `POST /api/v1/intake/{id}/link`

För en session utan verktyget, som `POST /intake/{id}/interpretation`
(`SPEC-underlagstolkning.md` §8). Bearer-autentiserad. Kroppen är `{ voucher_id, decision_id? }`
med `extra="forbid"`. Routen anropar samma `IntakeLinkService.link` som verktyget, med
`thread_id` och `agent_run_id` `null` och aktören från autentiseringen. Samma regler gäller, också
kontroll 9: en extern session får koppla vid exakt match, eller med ett besvarat beslut ur en
tråd. Det finns ingen tredje väg för den som anropar routen direkt.

| Utfall | Svar |
|---|---|
| Kopplad | `201` med §6.6:s kropp |
| Uppspelning | `200`, `replayed: true` |
| `source_not_found`, `voucher_not_found`, `decision_not_found` | `404` |
| `source_deleted`, `intake_already_linked`, `intake_not_linkable`, `voucher_not_posted`, `decision_still_open`, `decision_superseded`, `decision_declined` | `409` |
| `interpretation_required`, `voucher_not_in_interpretation`, `voucher_is_opening_balance`, `link_requires_decision`, `decision_not_for_source` | `400` |

Ingen `PUT`, `PATCH` eller `DELETE` på sökvägen (`405`). En koppling tas inte bort (§1).

**Följdändring i samma fil:** `409 duplicate_intake_source` från `POST /intake` får fältet
`existing_id` i kroppen. I dag står id:t bara inuti `details`-strängen
(`services/intake.py:29`), och klienten behöver det för att släppa samma kvitto en gång till
(§10.2).

---

## 8. Stoppet i postningen

Stänger `SPEC-underlagstolkning.md` §12.4.

`posta_verifikation`, `POST /agent/vouchers` och `foresla_verifikation` vägrar när ett underlag i
`intake_source_ids` har en senaste tolkning med `match.kind = "exact"` och `still_open` räknat
nu:

```
source_matches_posted_voucher
  details: "source_id=…, voucher=A-118, diff_ore=0 -- underlaget hör till en redan
            postad verifikation. Koppla det med koppla_underlag i stället."
```

- Kontrollen ligger i servicen, inte i verktyget: `services/voucher_posting.py` för de två
  första, `DraftService` för förslaget. Samma kontroll, en funktion i `IntakeLinkService`.
- `POST /agent/vouchers` svarar `409`.
- Den körs **före** idempotensreservationen i `voucher_posting`, så att ett stoppat anrop inte
  håller en nyckel.
- `exact_no_date` och `amount_diff` stoppas inte här. De stoppas av instruktionen och ett beslut
  (`SPEC-underlagstolkning.md` §12.4).
- Utan tolkning, eller med en tolkning vars matchning inte längre är öppen, stoppas ingenting.
  Stoppet slår på det servern vet, inte på vad agenten borde ha gjort.

Postningen av ett **trådförslag** (`POST /vouchers/{id}/post`) kör inte kontrollen igen. Om
underlaget hunnit kopplas medan förslaget låg vägrar länkningen redan med `source_already_booked`
(`SPEC-flode-verifikationer.md` §8.1).

---

## 9. Tråden

### 9.1 Jämförelseinlägget (D6)

När `tolka_underlag` körs i en trådtur, och svaret har en `match` eller en `expected`, skriver
servern ett `receipt`-inlägg med tolkningens tal, i samma transaktion som tolkningen:

```jsonc
{
  "title": "Kvitto Elektronikhuset 2026-06-03 mot A-118",
  "labels": ["kvitto", "A-118"],
  "rows": [
    { "key": "Belopp", "text": "inklusive moms", "left_ore": 460000, "right_ore": 448000 },
    { "key": "Moms",   "text": "ingående moms",  "left_ore":  89600, "right_ore":  89600 }
  ],
  "note": "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.",
  "voucher_id": "<A-118>"
}
```

- `labels` är designens (`SPEC-chattyta.md` §4.3). `rows` är `match.amounts` och `match.vat`,
  eller `expected`s. Momsraden utelämnas när någon sida saknar moms.
- `note` är serverns hypotes, ordagrant (`SPEC-underlagstolkning.md` §7.5), och bara den. Utan
  hypotes finns inget `note`. Agentens egen förklaring står i agentens text, som agentens ord.
  Fältet är nytt i `chattyta`s kontrakt (D7).
- Med både `match` och `expected` mot olika verifikationer skrivs två inlägg, `expected` först:
  det var den agenten bad om.
- **Vid `kind = "exact"` skrivs inget jämförelseinlägg.** Steget hoppas över, och kvittot efter
  kopplingen (§9.3) bär samma rader.
- Utan tråd, i passet eller över `POST /intake/{id}/interpretation`, skrivs inget inlägg.

Verktygets beskrivning ändras inte. Den säger redan att det inte kopplar något och inte ändrar
bokföringen, och ett inlägg är ingetdera. Testfall 33 i `underlagstolkning` gäller oförändrat.

### 9.2 Beslutet vid differens

Inget nytt verktyg. Agenten anropar `be_om_beslut` med `source: {kind: "intake_source", id}` och
panelens tre alternativ, i panelens ordning:

1. **Koppla och bokför skillnaden** — `account` (t.ex. `5410`) och `amount_ore` (`12000`),
   ändrar böckerna. Tillåtet eftersom listan ligger under ett öppet beslut (`SPEC-beslut.md`
   §11.1).
2. **Koppla utan att ändra** — utan `account`/`amount_ore`. Panelen: *"Skillnaden lämnas som en
   anteckning."* Anteckningen är beslutet självt: frågan, alternativet och svaret, bundna till
   kopplingen genom `intake_link_basis.decision_id`. Ingen fritext från agenten lagras på
   verifikationen.
3. **Det är ett annat köp** — `is_exit`. Tillbaka till steg 1.

`recommended` väljs av agenten, som alltid (`SPEC-beslut.md` §6.3). Panelen rekommenderar
alternativ 1. Instruktionen (§11.2) säger: rekommendera 1 när differensen har en hypotes som
pekar på en rad som ska bokföras, annars ingen rekommendation.

Svaret går som alla svar genom `POST /decisions/{id}/answer` och startar en tur. I turen:

- **Alternativ 1:** `koppla_underlag` med `decision_id`, sedan `foresla_verifikation` med
  differensens rader och samma `decision_id`. Flöde 1 steg 3–6 tar över: förslag, `Posta`,
  kvitto, numret (A-121) vid postningen. I postningens transaktion skrivs hänvisningen till
  kvittot (§5). Kopplingen görs först, eftersom hänvisningen går via den.
- **Alternativ 2:** `koppla_underlag` med `decision_id`.
- **Alternativ 3:** ingen koppling. Agenten frågar vad kvittot gäller, eller tolkar om med ett
  annat `expected_voucher_id`.

Efter en koppling nämner agenten nästa verifikation som saknar underlag, med ålder (panelen:
*"Nästa saknade underlag nämns direkt, så kön kan arbetas av utan att byta vy"*). Det står i
instruktionen; kvittots chip `{n} saknar underlag` ger talet.

### 9.3 Kvittot

Efter kopplingens commit, i en trådtur:

```jsonc
{
  "title": "Underlag kopplat till A-118",
  "labels": ["kvitto", "A-118"],
  "rows": [ /* samma som jämförelseinlägget, ur samma tolkning */ ],
  "voucher_id": "<A-118>",
  "source_id": "<källan>"
}
```

- `traces[]`: `underlag kopplat` · `A-118` (`tool: "koppla_underlag"`), `kompletteringsflagga
  borttagen` när verifikationen saknade underlag före kopplingen, och `{n} saknar underlag` ur
  räknaren efter commit.
- `actor` är den som kopplade: `agent` vid `exact_match`, människan vid `decision` (den som
  besvarade beslutet). Det är hennes val som kopplade.
- `message.completed` för inlägget, och `view.changed` med `{voucher_id, source_id, kind:
  "source_linked"}` på trådens `view_key`. Är trådens vy inte `bocker.verifikationer` skickas
  samma händelse där också, eftersom raden `saknar` bor där.

**Efter commit, och idempotent.** Samma skäl som `SPEC-flode-verifikationer.md` §8.1: kopplingen
är bokföringens och kvittot trådens, och ett fel i trådlagret får inte rulla tillbaka en koppling.
En uppspelning (§6.5) letar efter ett `receipt`-inlägg med samma `source_id` i tråden
(`ThreadRepository.receipt_for_source`, en fråga med `json_extract`) och skriver det bara om det
saknas.

Utan tråd, i passet eller över HTTP, skrivs inget kvitto. `view.changed` skickas ändå på
`bocker.verifikationer`, så att en öppen vy tappar raden.

---

## 10. `ChattFalt`: `drop`-varianten

### 10.1 Vad den tar emot

Tre ingångar, en väg:

| Ingång | Hur |
|---|---|
| Fil | Knapp i fältet som öppnar filväljaren; dra och släpp på hela tråden |
| Kamera | Samma knapp på mobil: `<input type="file" accept="image/*" capture="environment">` |
| Urklipp | `paste` med en fil i fältet |

Typerna och storleken är `IntakeService`s (`ALLOWED_MIME_TYPES`, `MAX_FILE_SIZE`), speglade i
klienten för att kunna säga nej innan uppladdningen. Servern avgör ändå.

`komponenter.md`s mått och copy för `drop`-varianten gäller ordagrant och upprepas inte här.

### 10.2 Vägen

1. Varje fil laddas upp med `POST /api/v1/intake` så fort den släppts. Fältet visar ett
   filchip per fil: namn, storlek, `laddar upp…`, sedan klart eller fel.
2. `409 duplicate_intake_source` är inget fel: chipet får `existing_id` (§7) och står som klart.
   Samma kvitto två gånger är samma underlag.
3. Vid `↵` skickas `POST /threads/{vk}/messages` med `text` och `attachments` = chipens id:n.
   `↵` är avstängt medan ett chip laddar upp.
4. Ett chip med fel följer inte med. Det står kvar med orsaken tills det tas bort.

Utan text skickas meddelandet ändå (D8). Servern skriver då inget `user_text`-inlägg, bara
`user_file`-inläggen, och turen startar på det första av dem med texten *"(bifogade {n} filer)"*
som meddelande till modellen. Inlägget i tråden hittar inte på en text åt människan.

### 10.3 Vad klienten inte gör

- Läser inga filer och räknar inget: ingen förhandsvisning av belopp, ingen OCR.
- Kopplar ingenting. Kopplingen är agentens eller människans val i tråden, aldrig en bieffekt av
  att en fil släppts.
- Skickar inget base64 i ett meddelande (`SPEC-tradar.md` §6.2).

### 10.4 Kort och vy

**Sektionen `Saknar underlag`.** Panelens vy har två sektioner, *"Kompletteringar först ·
postade nedan"*:

| Sektion | Rader | Källa |
|---|---|---|
| **Saknar underlag** | Postade verifikationer med `missing_attachment`, äldst först | `GET /vouchers?missing_attachment=true&sort_by=age` (`SPEC-oversikt.md` §4) |
| **Postade** | Som i dag, utan dem ovan | `GET /vouchers?status=posted…` |

`Väntar på beslut` och `Utkast` (`SPEC-flode-verifikationer.md` §11.1) står kvar. Ordningen blir
Väntar på beslut, Saknar underlag, Postade, Utkast: ett beslut väntar på människan, en
komplettering på ett papper. En verifikation visas på ett ställe.

| Läge | Meta | Variant |
|---|---|---|
| Saknar underlag | `{serie}-{nummer} · kvitto saknas sedan {n} dgr` | `saknar`, färgad med `aldersTon` (röd från sju dagar) |
| Nyss kopplad | `{serie}-{nummer} · kvitto kopplat HH:MM` (+ ` · {A-n} korrigering` med hänvisning) | `ny` i 6 s, i `Postade` |
| Kopplad | `{serie}-{nummer} · {datum} · kvitto kopplat` | normal |

- `{n}` är serverns `age_days`. Klienten räknar inte.
- Utan rader försvinner sektionen, den står inte tom (panelen: *"Sista kompletteringen: sektionen
  ska försvinna helt, inte stå tom"*).
- `Nyss kopplad` läses ur `view.changed` med `kind: "source_linked"`, på samma sätt som `ny` efter
  en postning. `· A-121 korrigering` kräver att `VoucherResponse` bär hänvisningen:
  `referenced_by: {id, series, number} | null`, joinad i sidfrågan som `corrected_by`
  (`SPEC-flode-verifikationer.md` §7.5), utan N+1.
- Vyns fot byts till panelens: *"Underlag kan släppas i chatten när som helst. Agenten kopplar det
  till rätt verifikation och säger till om något inte stämmer."*
- Bannern (`VyBanner`) står kvar som den är (`SPEC-flode-verifikationer.md` §1).

**Kvittot från verifikationen.** Panelen: *"Kvittot måste kunna öppnas från verifikationen
efteråt, inte bara finnas i tråden."* `GET /vouchers/{id}` returnerar redan de kopplade källorna
(`api/routes/vouchers.py:335`). Radens detalj i `/v4` får en länk till `GET /intake/{id}/file` per
kopplad källa, och för en verifikation med hänvisning en länk till kvittot via
`via_voucher_id`.

**Korten.**

- `user_file`-inlägget finns redan (`lib/chattyta/parse.ts:60`). Kortet får en länk till
  `GET /intake/{id}/file`. Panelens `FilInlagg` visar storlek och sidantal (*"218 kB · 1
  sida"*); sidantalet ingår inte i `user_file`-kroppen i dag och läggs till för pdf (`page_count`,
  ur `pypdf`, `null` för bilder).
- Jämförelsen och kvittot är `receipt` och ritas av `JamforelseRader` som den är, med `note` i
  mono 12 `#52525b` som `consequence` (D7).
- `view.changed` med `kind: "source_linked"` invaliderar `["vouchers"]` och `["overview"]`, som
  `voucher_posted` gör (`SPEC-flode-verifikationer.md` §10). Raden flyttar från `Saknar underlag`
  till `Postade` och räknaren går ned utan omladdning.

---

## 11. Agenten

### 11.1 Vad den ser

`_voucher_dict` (`services/agent_tools.py:458`) får `missing_attachment` och `age_days`, samma
härledda värden som `VoucherResponse` (`SPEC-oversikt.md` §3). Bara svaret ändras. Argumenten och
beskrivningen av `las_verifikationer` är orörda, så det cachade prefixet står stilla, som när
`las_korrigeringar`s svar utökades i F12.

### 11.2 Instruktionen

`docs/to_agent/03_bokforingsinstruktion.md` är körtidsinnehåll (`AGENTS.md`), och
`tests/test_agent_entrypoint.py` får nya påståenden. `SPEC-underlagstolkning.md` §9 punkt 2 skrivs
om. I sak:

1. **Be om underlag** för postade verifikationer med `missing_attachment`, äldst först, med
   verifikationsnumret, beloppet och datumet, och **säg varför** det behövs för just den
   verifikationen (panelen: *"Motiveringen är knuten till verifikationen, inte en allmän
   uppmaning"*). Be om ett i taget.
2. **När en fil kommer:** säg att du läser den innan du anropar verktygen. Ingenting kopplas
   förrän människan sagt ja, utom vid exakt match.
3. **`match.kind = "exact"`**: koppla med `koppla_underlag`, i tråden och i passet. Posta inte
   (stoppet i §8 vägrar ändå).
4. **`amount_diff`** i tråden: lägg fram beslutet i §9.2, med verifikationsnumret och båda
   beloppen i `reason`, och hypotesen som hypotes. I passet: avstå som förut, med
   verifikationsnumret och differensen i motiveringen. Ett avstående kan senare kopplas i tråden.
5. **Bokför skillnaden** görs med `foresla_verifikation` och beslutets `decision_id`, efter
   kopplingen. Aldrig `posta_verifikation`, och aldrig före kopplingen.
6. **`exact_no_date`**: fråga om det är samma köp. Ett ja blir ett beslut med alternativ 2 och 3,
   inte en koppling på fritext.
7. **`match = null` med kandidater**, eller en fil utan sammanhang: fråga vilken verifikation det
   gäller. Svaret blir ett beslut om den verifikationen.
8. **`confidence = "low"`**: be om ett nytt underlag. Koppla inte.
9. **Efter en koppling:** nämn nästa verifikation som saknar underlag, med ålder.

Punkt 4:s avstående i passet är medvetet kvar. Passet har ingen människa att fråga, och en
koppling med differens kräver en.

### 11.3 Passet (D4)

`IntakeRepository.list_pending` och `count_pending` hoppar över källor som har ett
`user_file`-inlägg i någon tråd: `NOT EXISTS (SELECT 1 FROM thread_posts tp WHERE tp.type =
'user_file' AND json_extract(tp.body_json, '$.intake_source_id') = intake_sources.id)`. En fråga,
inte en per källa. Kön i dagens intagssida (`GET /intake/workspace`) påverkas inte: den visar
fortfarande alla väntande.

---

## 12. Beslut

Alla tio tagna av beställaren 2026-09-28, alla enligt förslaget. Resonemanget står kvar under
varje punkt som skäl för beslutet.

### D1 Vem får koppla — **BESLUTAT 2026-09-28: agenten vid exakt match, annars ett besvarat beslut**

Alternativen var (a) att agenten alltid får koppla, och (b) att människan alltid måste. (a) faller
på att en koppling inte kan tas bort (§1): en felkoppling på en differens på 120 kr blir kvar i
spåret. (b) faller på designens *"Exakt match ska hoppa över det här steget"* och gör intagspasset
oförmöget att avsluta det vanligaste fallet. §6.4.

### D2 Bokför skillnaden — **BESLUTAT 2026-09-28: som panelen, en egen verifikation med hänvisning till kvittot**

Panelen bokför differensen som A-121, *"Korrigering pantavgift"*, 120 kr, och A-118 står kvar
som den är. Det krockar med §3.2: kvittot är kopplat till A-118 och kan inte kopplas till A-121
också. Förslaget löser det med `voucher_source_references` (§5): A-121 hänvisar till kvittot via
A-118, raden skrivs av servern i postningens transaktion ur beslutet, och predikatet räknar
hänvisningen som underlag.

Alternativet var en B-rättelse av A-118, som bär originalets underlag genom `correction_of` och
inte behöver någon ny tabell. Den faller på att den återför hela A-118 och bokför om 4 600 kr för
att flytta 120, vilket är en annan bokföring än panelens och en tyngre rad i historiken för en
pantavgift. Priset med förslaget: en tabell till, och ett tredje sätt för en verifikation att ha
underlag.

### D3 Rättelser saknar inte underlag — **BESLUTAT 2026-09-28: undanta `correction_of IS NOT NULL` i predikatet**

§3.1. En rättelses underlag är originalet och `accounting_corrections`. Utan undantaget står varje
rättelse ur flöde 1 i `Saknar underlag` och ber om ett kvitto som inte finns. Det ändrar vad
"saknar underlag" betyder, som SIE4-undantaget gjorde (`SPEC-underlagstolkning.md` §12.5), och
`missing_attachments` i headern sjunker vid driftsättning. Det ska stå i commit-meddelandet.
Frågan gäller oavsett D2.

### D4 Tråden äger sina filer — **BESLUTAT 2026-09-28: passet hoppar över dem**

§3.4, §11.3. Alternativet är att passet tar dem och att tråden får hantera ett underlag som
avståtts under samtalet. Det fungerar tack vare D9, men människan ser då två röster om samma
kvitto. Priset med förslaget: en fil som släppts i tråden och aldrig tagits om hand ligger kvar
som `pending` tills någon frågar i tråden.

### D5 Stoppet i postningen — **BESLUTAT 2026-09-28: ja, som i §8**

Beslutat i princip i `SPEC-underlagstolkning.md` §12.4, att byggas när kopplingsvägen finns. Här
är den vägen. Frågan är bara om formen i §8 stämmer: bara `exact`, bara `still_open`, i servicen
och i förslaget.

### D6 Tolkning i en tråd skriver jämförelsen — **BESLUTAT 2026-09-28: ja, servern skriver den**

Alternativet är att agenten skriver talen i sin text. Det faller på `ANALYS.md` §7 och designens
regel att siffror visas som två tal i `JamforelseRader`, aldrig som modellens text. Priset: ett
klart verktyg (`tolka_underlag`) får en bieffekt i tråden, dock inte i bokföringen.

### D7 `note` i `receipt` — **BESLUTAT 2026-09-28: ja, valfritt fält för serverns hypotes**

En ändring i `chattyta`s kontrakt (`SPEC-chattyta.md` §4.3), och därför ett "fråga först"
(`SPEC-flode-verifikationer.md` §15). Alternativet är att hypotesen bara står i agentens text.
Då står beläggen (en rad på kvittot) och agentens gissning i samma röst, och det är skillnaden
mellan dem `SPEC-underlagstolkning.md` §12.3 byggde för att bevara.

### D8 Meddelande utan text — **BESLUTAT 2026-09-28: tillåt när det finns bilagor**

`ThreadMessageRequest.text` har `min_length=1` (`api/schemas.py:531`). Att släppa ett kvitto
utan att skriva något är det vanliga fallet på mobil. Alternativet är att klienten fyller i en
text åt människan, vilket lägger ord i hennes mun i ett spår som ser ut som hennes.

### D9 Koppling från `failed` — **BESLUTAT 2026-09-28: ja, också `needs_attention`**

§3.3. Utan det går underlaget som passet avstod från just för att det matchade inte att koppla,
och flöde 4 har ingen utväg ur sitt eget vanligaste avstående. `_ensure_can_record_outcome` rörs
inte; postningen släpper fortfarande bara igenom `pending`/`processing`. En koppling från `failed`
tar också det syntetiska beslutet `intake:…` ur `GET /decisions`, eftersom källan blir
`processed`.

### D10 Ersätta ett felkopplat underlag — **BESLUTAT 2026-09-28: egen modul efter den här, inte här**

Panelen kräver det i två kanter (§1). Det kräver att en källa kan bära en ny länk medan den
gamla står kvar som spår: `UNIQUE(intake_source_id)` i `voucher_intake_sources` måste bytas mot
en regel om en **gällande** länk per källa, och det kräver en ombyggnad av tabellen (SQLite tar
inte bort ett `UNIQUE` med `ALTER`), en frånkopplingsrad i en append-only-tabell, och ett nytt
predikat som bara läser gällande länkar. Samma storlek och samma risk som migration 027 i
`flode-verifikationer`, på den tabell som skyddar mot dubbelbokförda kvitton.

Förslaget är att bygga flöde 4:s fyra steg först, med D1:s strikta belägg som skydd mot
felkopplingar, och ta ersättningen som modulen `underlag-ersatt` direkt efter. Alternativet är att
ta den här; då växer modulen med en tabellombyggnad och §15:s "fråga först" om `UNIQUE` blir ett
ja. Så länge ersättningen saknas avviker `/v4` från panelens *"vägen tillbaka måste vara lika
lätt som vägen fram"*, och det ska stå i kvarlistan när modulen stängs.

---

## 13. Öppna frågor

Ingen av dem blockerar starten.

1. **Tröskeln.** Panelens *"Skillnader över en tröskel bör bli ett beslutskort"* är besvarad av
   `SPEC-beslut.md` §11.1: varje alternativ som ändrar böckerna ligger under ett beslut, oavsett
   belopp. En differens på 2 kr blir alltså också ett beslutskort. Om det blir för tungt i
   praktiken är det en ändring i `beslut`, inte här.
2. **Påminnelse om gamla kompletteringar.** Designen säger att de hör hemma i en påminnelse.
   `DecisionService.send_reminders` finns i intagspassets cykel och kunde bära en, men en
   komplettering är inget beslut. Förslag: vänta tills passet körs schemalagt
   (`SPEC-agentruntime.md` §12.3).
3. **Flera sidor och flera köp.** Panelen: *"Både bild och pdf måste fungera, liksom flera sidor
   i samma dokument"* — det gör de redan (`SPEC-agentruntime.md` §6.3). *"Ett kvitto kan innehålla
   flera köp"* är inte budgeterat (§1).
4. **Fritextsvar på ett kopplingsbeslut.** Servern släpper igenom fritext (§6.4), eftersom den
   inte kan läsa den. Ett *"nej, det är inte samma"* i fritext kopplas alltså om agenten läser
   det fel. Alternativet är att ett kopplingsbeslut bara kan besvaras med ett alternativ, vilket
   bryter mot `README.md`s regel om fritext. Förslag: låt stå, och se efter i den visuella
   kontrollen med riktig LLM.
5. **Årsskiftet.** En verifikation i förra årets tråd som får sitt kvitto i år. Kopplingen bryr
   sig inte om räkenskapsår; kvittot skrivs i tråden där filen släpptes. Ärvd från
   `SPEC-tradar.md` §13.2.

---

## 14. Teststrategi

`pytest` för backenden, i `tests/test_flode_underlag.py`, och `vitest` för klienten. Testerna
skrivs **före** implementationen. Ingen riktig LLM i test: verktygen körs via `execute_tool` med
en falsk tråd i `tool_context`, och passet med den skriptade klienten, som i
`tests/test_underlagstolkning.py`.

### 14.1 Kopplingen

| # | Fall | Förväntat |
|---|---|---|
| 1 | Exakt match, `still_open`, utan beslut | Kopplad; `basis = exact_match`; källan `processed`; `missing_attachment = false` på verifikationen |
| 2 | `amount_diff` utan beslut | `link_requires_decision`, inget skrivet |
| 3 | `exact_no_date` utan beslut | `link_requires_decision` |
| 4 | `amount_diff` med besvarat beslut, alternativ 1 | Kopplad; `basis = decision`; `decision_id` i belägget |
| 5 | Beslutet besvarat med exit-alternativet | `decision_declined` |
| 6 | Beslutet besvarat med fritext | Kopplad |
| 7 | Beslutet öppet / ersatt / om ett annat underlag / i en annan tråd | `decision_still_open` / `decision_superseded` / `decision_not_for_source` / `decision_not_in_thread` |
| 8 | Ingen tolkning | `interpretation_required` |
| 9 | Verifikation som inte står i tolkningen | `voucher_not_in_interpretation` |
| 10 | Verifikation som bara står som `expected` (SIE4-importerad) med beslut | Kopplad |
| 11 | Källan `failed` efter passets avstående, med beslut | Kopplad; det syntetiska `intake:`-beslutet borta ur `GET /decisions` |
| 12 | Källan `deleted` | `source_deleted` |
| 13 | Samma källa, samma verifikation, två gånger | En länk, ett belägg, `replayed: true` |
| 14 | Samma källa, annan verifikation | `intake_already_linked` med numret |
| 15 | Verifikation i `IB` / utkast | `voucher_is_opening_balance` / `voucher_not_posted` |
| 16 | Fel halvvägs i transaktionen | Ingen länk, inget försök, ingen status, inget belägg |
| 17 | `UPDATE`/`DELETE` på `intake_link_basis` | Triggern avbryter |
| 18 | Kopplingen | Ingen `INSERT`, `UPDATE` eller `DELETE` i `vouchers` eller `voucher_rows` |
| 19 | `exact_match` och verifikationen har fått underlag emellan | `link_requires_decision` (`still_open` är falsk) |

### 14.2 Stoppet

| # | Fall | Förväntat |
|---|---|---|
| 20 | `posta_verifikation` med ett underlag vars tolkning är `exact` och öppen | `source_matches_posted_voucher`, ingen verifikation, ingen nyckel reserverad |
| 21 | Samma över `POST /agent/vouchers` | `409 source_matches_posted_voucher` |
| 22 | `foresla_verifikation` med samma underlag | Samma fel, inget utkast |
| 23 | Tolkningen `amount_diff` / `exact_no_date` / ingen tolkning | Inget stopp |
| 24 | Tolkningen `exact` men verifikationen har fått underlag | Inget stopp |

### 14.3 Tråden

| # | Fall | Förväntat |
|---|---|---|
| 25 | `tolka_underlag` i en tråd, `amount_diff` med hypotes | Ett `receipt` med `labels ["kvitto","A-118"]`, belopp och moms, `note` = hypotesen |
| 26 | `tolka_underlag` i en tråd, `exact` | Inget jämförelseinlägg |
| 27 | `tolka_underlag` utan tråd / över `POST …/interpretation` | Inget inlägg |
| 28 | `match` och `expected` mot olika verifikationer | Två inlägg, `expected` först |
| 29 | Koppling i en tråd | Ett kvitto med `source_id` och traces; `view.changed` `source_linked` på trådens vy och på `bocker.verifikationer` |
| 30 | Kvittot misslyckas efter commit | Kopplingen står; uppspelning skriver kvittot, en gång |
| 31 | Koppling i passet | Inget kvitto; `view.changed` på `bocker.verifikationer` |
| 32 | `actor` på kvittot | `agent` vid `exact_match`, människan vid `decision` |
| 33 | Meddelande utan text med en bilaga | Inget `user_text`; ett `user_file`; turen startar på det |
| 34 | Meddelande utan text och utan bilaga | `422` som i dag |
| 35 | `409 duplicate_intake_source` | Kroppen har `existing_id` |

### 14.4 Agenten och passet

| # | Fall | Förväntat |
|---|---|---|
| 36 | `AGENT_TOOL_DEFINITIONS` | `koppla_underlag` sist; de tolv före oförändrade byte för byte |
| 37 | `las_verifikationer` | Svaret har `missing_attachment` och `age_days`; argument och beskrivning byte för byte som före |
| 38 | `list_pending` | En källa med `user_file`-inlägg är inte med; en utan är det; en fråga |
| 39 | Skriptat pass: kvitto som matchar A-118 exakt | `koppla_underlag`, ingen ny verifikation, inget avstående |
| 40 | Skriptat pass: kvitto med differens | Avstående med `A-118` i motiveringen, ingen koppling |
| 41 | Skriptad tråd hela vägen: fil → tolkning → beslut → svar alternativ 2 → koppling → kvitto | Kopplad; ingen ny verifikation; beslutet i belägget |
| 42 | Skriptad tråd: svar alternativ 1 | Koppling, sedan förslag med `decision_id`; `Posta` ger A-121 och en rad i `voucher_source_references` i postningens transaktion; A-121 saknar inte underlag |
| 42b | Förslag med ett `decision_id` utan koppling bakom sig | Postas som vanligt, ingen hänvisning |
| 42c | `UPDATE`/`DELETE` på `voucher_source_references` | Triggern avbryter |
| 43 | `tests/test_agent_entrypoint.py` | Instruktionen nämner `koppla_underlag` vid exakt match, motiveringen vid begäran, och att skillnaden föreslås efter kopplingen |
| 44 | Predikatet (D3) | En postad rättelse räknas inte som saknar underlag; samma tal i `/overview`, `/vouchers` och `compliance` |

### 14.5 Klienten och regression

| # | Fall | Förväntat |
|---|---|---|
| 45 | Släpp en fil | Uppladdning, chip `klar`, id i `attachments` vid `↵` |
| 46 | Otillåten typ / för stor | Chip med fel före uppladdning; följer inte med |
| 47 | Dubblett | Chip `klar` med `existing_id` |
| 48 | `↵` medan ett chip laddar upp | Avstängd |
| 49 | Urklipp och kamera | Samma väg som filväljaren |
| 49b | Sektionen `Saknar underlag` | Först efter Väntar på beslut, äldst först, meta `kvitto saknas sedan {n} dgr`; borta när tom; en verifikation på ett ställe |
| 49c | Koppling via `view.changed` | Raden flyttar till `Postade` med `kvitto kopplat HH:MM` och, med hänvisning, `· A-121 korrigering` |
| 49d | Verifikationens detalj | Länk till kopplat kvitto; för A-121 länk via A-118 |
| 49e | `referenced_by` i `GET /vouchers` | Ifyllt för A-118 efter postningen av A-121; inga fler SQL-anrop per rad |
| 50 | `receipt` med `note` | `JamforelseRader` ritar noten i mono 12; utan `note` som förut |
| 51 | `view.changed` `source_linked` | Invaliderar vouchers och overview |
| 52 | Regression | `pytest tests/` grön; `chattyta`s, `skal`s och `flode-verifikationer`s tester gröna |

Fall 39–42 är skriptade: de visar att vägen håller när modellen följer instruktionen, inte att en
riktig modell gör det. Det senare är §16 kriterium 7.

---

## 15. Gränser

**Alltid:**
- Tester före implementation.
- Kopplingen i en transaktion: länk, försök, status och belägg tillsammans, eller ingenting.
- Kvittot efter commit, idempotent.
- Ny SQL i `repositories/`, aldrig i en service eller route.
- Belopp i öre, heltal.
- Nya verktyg sist i listan.

**Fråga först:**
- En väg att ta bort eller byta en koppling (D10).
- Att ändra `UNIQUE(intake_source_id)` i `voucher_intake_sources`.
- Att ändra matchningens fönster eller vad `exact` betyder.
- En ändring i `chattyta`s kontrakt utöver `note` (D7).
- Att koppla från `processed` eller `skipped`.

**Aldrig:**
- En koppling utan tolkning, eller till en verifikation som inte stod i tolkningen.
- En koppling vid differens utan ett besvarat beslut.
- Att agenten sätter differens, hypotes eller belägg.
- Att en koppling skapar, ändrar eller tar bort en verifikation.
- `UPDATE` eller `DELETE` på `intake_link_basis`.
- Att klienten kopplar som en bieffekt av en uppladdning, eller räknar ett belopp.
- Att flytta de tolv befintliga verktygen.

---

## 16. Framgångskriterier

Modulen är klar när:

1. Ett underlag kopplas till en postad verifikation i efterhand, över verktyget och över HTTP, med
   belägg i `intake_link_basis` (1, 4, 13).
2. Exakt match kopplas utan människa; allt annat kräver ett besvarat beslut som inte är ett nej
   (1–7).
3. Kopplingen skriver aldrig i `vouchers` och är append-only i tre lager (17, 18, route utan
   `PUT`/`PATCH`/`DELETE`).
4. Postningen vägrar ett underlag som matchar en postad verifikation exakt (20–24).
5. Tråden visar kvittot mot verifikationen med båda talen, och kvitterar kopplingen; raden flyttar
   från `Saknar underlag` till `Postade` och räknaren följer med utan omladdning (25–32, 49b–49c,
   51).
5b. En differens bokförd enligt panelens alternativ 1 har underlag genom hänvisningen och står
   inte i `Saknar underlag` (42, 42c).
6. En fil går att släppa, fota och klistra in i `ChattFalt`, med och utan text (33, 45–49).
7. Flöde 4 fungerar mot riktig backend i `/v4` med en riktig LLM: ett kvitto för en bankbokförd
   verifikation ger en koppling, inte en ny verifikation (41 skriptat, plus visuell kontroll av
   beställaren tillsammans med `underlagstolkning`s kriterium 6).
8. `pytest tests/ -v`, `black`, `isort`, `flake8` rena; `mypy .` inte över baslinjen 61; `npm
   test`, `npm run lint`, `npx tsc --noEmit` och `NEXT_PUBLIC_SKAL=1 npm run build` gröna.
