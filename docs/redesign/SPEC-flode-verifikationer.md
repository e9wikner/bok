# Spec: `flode-verifikationer`

Modul-id `flode-verifikationer` i kapabilitetskartan (`ANALYS.md` §8). Beror på `chattyta` (klar,
C1–C14), och genom den på `beslut`, `tradar`, `skal`, `agentruntime` och `idempotens`. Det är
den sista modulen i första leveransen: när den är klar fungerar Böcker · Verifikationer
agent-first hela vägen, **korrigering inräknad**. `flode-underlag` beror på den här.

Status: **Klar 2026-09-24 (F1–F16).** Skriven och godkänd 2026-09-23. Fem beslut tagna av beställaren
(§12.1–§12.5), ett om driftsättningen (§4.4) och ett om periodlåsningen (§9, 2026-09-24).
Uppgifterna ligger i `tasks/flode-verifikationer/plan.md` och `tasks/flode-verifikationer/todo.md`
(F1–F16).

---

## Antaganden

1. **Flödet är designens flöde 1, sex steg, ordagrant.** Källan är annoteringspanelen i
   `BokAi flöden v1.dc.html` (`README.md`: *"läs den, den är specen för flödena"*). Där specen
   avviker från panelen står det, och varför. Korrigeringen är inte ritad; §7 säger vad den är.
2. **Klienten är byggd.** `VerifikationsForslag`, `Posta`-knappen med härledd nyckel, alla sju
   utfallen, `JamforelseRader` och `FelKort` finns (`SPEC-chattyta.md` §8–§9). Den här modulen
   är i huvudsak **producenten**: det som skriver `draft` och `receipt`, och det som håller vyn i
   takt. Klientändringar görs i vyns rader, där ett kort behöver läsa en ny status, och där ett
   utkast inte längre har ett nummer.
3. **Append-only är oförhandlingsbart.** Ett utkast är en verifikation med `status='draft'`, och
   det får ändras eller tas bort tills det postas. Därefter bara korrigering. Ingenting i den här
   modulen rör en postad rad. Det gäller även migrationen i §4, som bygger om tabellen men
   kopierar varje postad rad oförändrad.
4. **Agenten får fortsätta posta direkt i en tråd** (§12.2). Utkastet är en väg till, inte en
   ersättning. **Korrigeringar postas aldrig direkt** (§12.5).
5. **Enbolag och en människa**, som i alla tidigare moduler.

→ Punkt 3 och 4 är de som kostar om de glöms.

---

## 1. Objektiv

### Problemet, konkret

Varje del av flöde 1 finns, men kedjan är bruten på fyra ställen:

- **Ingen producerar ett förslag.** Agenten har två sätt att skriva: `posta_verifikation`
  postar direkt, och `be_om_beslut` skriver ett kort utan konteringsrader. Designens steg 3,
  *"Valet visas som den verifikation det blir, med debet och kredit i klartext"*, har ingen
  producent.
- **Ett utkast får ett nummer.** `LedgerService.create_voucher` tar `MAX(number) + 1` när
  *utkastet* skapas (`repositories/voucher_repo.py:283`). Ett förslag som ersätts eller aldrig
  postas lämnar ett hål i den postade serien, och numren följer inte postningsordningen. Panelen
  säger själv: *"Verifikationsnumret kommer från bokföringen, inte från klienten, och visas först
  när posten finns."*
- **En postning via knappen hörs inte i tråden.** `POST /vouchers/{id}/post` skriver inget inlägg
  och skickar ingen `view.changed`. Det gör i dag bara agentens egen postning
  (`services/thread_stream.py:449`).
- **Rättelse går inte att be om.** Vyfoten lovar *"Säg vad som blev fel, så skriver agenten en
  korrigeringsverifikation"*, men agenten har inget sätt att lägga fram en korrigering. Och ett
  B-utkast som postas via `/post` skriver ingen korrigeringshistorik; det gör bara `/correct`
  och `correction-notes/…/approve`.

Till det kommer vyn: Verifikationer i `/v4` visar `Utkast` och `Postade`
(`lib/skal/bocker.ts::verifikationerVy`). `Väntar på beslut` saknas, liksom den pågående grå
raden, den gröna nya raden och felmarkeringen.

### Vad vi bygger

1. **Numret sätts vid bokföring** (§4). Utkast har inget nummer. Migrationen bygger om `vouchers`.
2. **`foresla_verifikation`**, agentens elfte verktyg: ett utkast och ett `draft`-inlägg, som
   vanlig verifikation eller som korrigering av en postad (§5).
3. **`thread_drafts`**, kopplingen mellan utkast, tråd, beslut och korrigeringsnotering (§6).
4. **Korrigering via chatten** (§7): B-serieförslag med återföring, målperiod och historik.
5. **Kvittot:** när ett trådutkast postas skriver servern ett `receipt`-inlägg och skickar
   `view.changed`. Vid fel skriver den ett `error`-inlägg (§8–§9).
6. **`GET /api/v1/drafts`**, så att ett förslagskort ser att det är postat eller ersatt (§10).
7. **Vyns rader**, och en räknare som läser samma källa som listan (§11).

### Vad vi inte bygger här

- **Faktura- och löneförslag.** `draft.kind` är alltid `voucher` (`ANALYS.md` §2).
- **Banderollens text.** *"Två bankhändelser är ännu inte bokförda…"* är agentens formulering
  och har ingen källa i dag. `VyBanner` står kvar som den är.
- **`Agenten postar` i headern när människan postar.** `GET /agent/status` rapporterar agentens
  arbete. Det som visar att en knapptryckning pågår är den grå raden (§11).
- **Korrigering över ett räkenskapsårsskifte.** Ligger originalets år stängt och finns ingen
  öppen period i det, avstår verktyget med en orsak (§7.4). Hur ett stängt år korrigeras är en
  bokslutsfråga.
- **Äldre räkenskapsår och modellväljaren**, som i `chattyta`.

### Framgång

En människa öppnar Verifikationer, ser ett beslutskort och väljer ett alternativ. Agenten lägger
fram förslaget, utan nummer. Människan trycker `Posta` två gånger och får **en** verifikation,
som då får nästa nummer i serien. Tråden kvitterar med före- och eftervärden, raden går från grå
till grön och räknaren går ner med ett, utan omladdning.

Samma människa skriver sedan *"A-118 skulle ha varit inventarier"*. Agenten lägger fram en
B-verifikation som återför A-118 och bokför om. Kortet säger vilken period den hamnar i och
varför. Hon postar, och A-118 står i listan som *rättad av B-7*.

Med perioden låst mellan förslag och tryck blir det i stället ett felkort i tråden som säger vem
som låste och när. Ingenting är bokfört, och händelsen ligger kvar som väntande med felmarkering.

---

## 2. Flödet, steg för steg, mot vad som bär det

| Steg | Designen | Bärs av | Ny här? |
|---|---|---|---|
| 1 Beslutet väntar | `BeslutKort` i tråden, räknare i headern | `be_om_beslut` / `registrera_avstaende`, `GET /decisions`, `open_decisions` | Räknaren (§11.3) |
| 2 Agentens förslag | `AlternativLista`, inget förvalt | `be_om_beslut` med `options`, `POST /decisions/{id}/answer` | Nej |
| 3 Bekräfta konteringen | `VerifikationsForslag`, konsekvensnotis | **`foresla_verifikation`** → `draft`-inlägg | **Ja** (§5) |
| 4 Postar | Knappen borta, grå rad `postas…` | `Posta` → `POST /vouchers/{id}/post` med nyckel; **numret sätts här** | Raden (§11.2), numret (§4) |
| 5 Postad och låst | Kvitto i tråden, grön rad, nästa händelse | **Kvittot** → `receipt` + `view.changed` | **Ja** (§8) |
| 6 Om postningen misslyckas | `FelKort` i tråden, raden rullas tillbaka | **`error`-inlägg** vid `period_locked` | **Ja** (§9) |
| — Rättelse (vyfoten) | *"Säg vad som blev fel…"* | **`foresla_verifikation` med `correction_of`** → samma steg 3–6 | **Ja** (§7) |

Fyra avvikelser från panelen, alla medvetna:

- **Steg 3: `Förslag A-118` blir `Förslag · A · 2026-06-03`.** Ett utkast har inget nummer
  (§12.4). Panelens rubrik motsäger panelens egen regel i steg 5, och regeln vinner.
- **Steg 3 → 4: `Ändra kontering`** lägger fokus i `ChattFalt` (`SPEC-chattyta.md` §8 punkt 4)
  i stället för att gå tillbaka till alternativen. Ett nytt förslag ersätter det gamla (§6.2).
- **Steg 5: kvittot är serverns, inte agentens** (§12.3). Panelens kvittotext är fakta om
  bokföringen, och servern vet dem säkrare än modellen, utan kostnad och utan att kunna
  misslyckas efter att postningen redan lyckats. Nästa obesluta händelse ligger redan i tråden
  som kort och i vyn som rad. Den läggs inte fram en gång till.
- **Steg 6: `Försök igen` finns inte vid låst period.** Panelens egen kant, *"Skilj på fel
  användaren kan lösa, som en låst period, och fel som kräver nytt försök"*, säger att ett nytt
  försök mot en låst period inte kan lyckas. Vägen framåt är ett nytt förslag, och det ber
  människan om i chatten. `chattyta` har redan byggt det så (§8, testfall 27).

---

## 3. Tech stack och kommandon

Oförändrat: FastAPI, SQLite med trådlokala anslutningar och WAL, pydantic. Frontend som
`chattyta`. **Inga nya beroenden.**

```bash
pytest tests/ -v
pytest tests/test_numrering.py tests/test_flode_verifikationer.py -v
black . && isort . && flake8 && mypy .
cd frontend-v3 && npm test && npm run lint && npx tsc --noEmit
cd frontend-v3 && NEXT_PUBLIC_SKAL=1 npm run build
```

Nya och ändrade filer, i huvudsak:

```
db/migrations/027_voucher_number_at_posting.sql  # §4 — ombyggnad av vouchers
db/migrations/028_add_thread_drafts.sql          # §6
repositories/voucher_repo.py                      # numret flyttas från create till post
services/ledger.py                                # create_voucher numrerar inte; post_voucher gör det
services/compliance.py                            # lucka-kontrollen per räkenskapsår (§4.5)
domain/models.py, api/schemas.py                  # number: Optional[int]
repositories/thread_draft_repo.py                 # all SQL för thread_drafts
services/draft_service.py                         # skapa, ersätta, korrigera, kvittera (§5–§9)
services/agent_tools.py                           # foresla_verifikation, sist i _TOOL_SPECS
api/routes/drafts.py                              # GET /drafts (§10)
api/routes/vouchers.py                            # post-routen anropar DraftService
services/overview.py                              # räknaren (§11.3)
docs/to_agent/02_bokforingsprocess.md             # verktyget och rättelsen (runtime-innehåll!)
frontend-v3/lib/utils.ts, lib/skal/*.ts           # ett utkast utan nummer
frontend-v3/lib/skal/bocker.ts                    # vyns sektioner och radlägen
tests/test_numrering.py, tests/test_flode_verifikationer.py
```

---

## 4. Numret sätts vid bokföring

**BESLUTAT 2026-09-23** (§12.4): ett utkast har inget nummer. Numret skapas när verifikationen
bokförs.

### 4.1 Varför det är en migration och inte en kodändring

`db/migrations/001_initial_schema.sql`:

```sql
number INTEGER NOT NULL,
...
UNIQUE(series, number, fiscal_year_id),
```

Ett utkast utan nummer kräver `number` nullbar, och SQLite kan inte ta bort `NOT NULL` med
`ALTER TABLE`. Tabellen måste byggas om. Det är den enda gången redesignen rör `vouchers`
schema, och tabellen är den som append-only vilar på. Därför är det modulens första uppgift,
med egna tester, och inget annat byggs förrän den är grön.

### 4.2 Migration 027

SQLites dokumenterade ombyggnadsordning, i en fil:

```sql
PRAGMA foreign_keys = OFF;          -- måste stå utanför transaktionen; executescript kör i autocommit
BEGIN;

CREATE TABLE vouchers_new (
    ... samma kolumner som i dag ...,
    number INTEGER,                                     -- nullbar
    ...,
    UNIQUE(series, number, fiscal_year_id),             -- flera NULL tillåts i SQLite
    CHECK(status IN ('draft', 'posted')),
    CHECK((status = 'draft'  AND number IS NULL) OR
          (status = 'posted' AND number IS NOT NULL))
);

INSERT INTO vouchers_new SELECT
    id, series,
    CASE WHEN status = 'draft' THEN NULL ELSE number END,
    ... ;

-- triggrarna på voucher_rows nämner vouchers; står de kvar vägrar RENAME (test 3)
DROP TRIGGER prevent_update_rows_for_posted_vouchers;
DROP TRIGGER prevent_delete_rows_for_posted_vouchers;

DROP TABLE vouchers;
ALTER TABLE vouchers_new RENAME TO vouchers;

-- index ur 001 och alla fyra triggrarna ur 014, återskapade ordagrant
CREATE INDEX ... ;
CREATE TRIGGER prevent_update_posted_vouchers ... ;
CREATE TRIGGER prevent_delete_posted_vouchers ... ;
CREATE TRIGGER prevent_update_rows_for_posted_vouchers ... ;
CREATE TRIGGER prevent_delete_rows_for_posted_vouchers ... ;

-- ingen PRAGMA foreign_key_check här: executescript kastar resultatet.
-- Test 1 kräver att den är tom efter migrationen.
COMMIT;
PRAGMA foreign_keys = ON;
```

Kolumnlistan i `vouchers_new` är den **faktiska** i dag, inte den i 001. Uppgiften börjar med att
läsa `PRAGMA table_info(vouchers)` och alla migrationer som lagt till kolumner eller triggrar.

Det nya `CHECK`-villkoret gör regeln till schema, på samma sätt som triggrarna gör append-only
till schema: ett postat utan nummer, eller ett utkast med nummer, går inte att skriva.

**Tre risker, och vad som möter dem:**

| Risk | Motdrag |
|---|---|
| `DROP TABLE vouchers` stoppas av `prevent_delete_posted_vouchers` | SQLite kör inga triggrar vid den implicita raderingen i `DROP TABLE`. Verifierat i test 3. Med `foreign_keys` på är `DROP TABLE` däremot en `DELETE` med främmande nycklars följder: den vägras av `correction_notes.voucher_id`, eller kaskaderar bort hela `voucher_rows`. `PRAGMA foreign_keys = OFF` före `BEGIN` är därför bärande; test 1 visar att den verkar genom `Database.init_db` |
| Triggrarna på `voucher_rows` pekar på `vouchers` med namn | **Visat i test 3:** står de kvar när `vouchers` droppas vägrar `ALTER TABLE … RENAME` (`error in trigger prevent_update_rows_for_posted_vouchers: no such table: main.vouchers`). 027 droppar dem i samma transaktion och återskapar dem ordagrant efter `RENAME`. Test 4 försöker ändra och radera rader i en postad verifikation efter migrationen |
| Produktionsdatabasen har något testdatabasen inte har | Beställaren kan börja om och importera SIE4-filerna igen (§4.4), så produktionen är inget skäl att skona migrationen. Test 1 jämför ändå varje postad rad fält för fält före och efter, eftersom migrationen ska vara rätt även där den inte behöver vara det |

### 4.3 Koden

- `LedgerService.create_voucher` sätter aldrig ett nummer och har ingen `number`-parameter längre.
  Ett explicit nummer (SIE4-importen) lagras inte på utkastet utan ges till
  `post_voucher(..., number=)`, som importen anropar direkt efter att utkastet skapats. De är
  två transaktioner, som före F2; `CHECK` gör att utkastet däremellan inte kan bära numret.
  `POST /api/v1/vouchers` tar `number` bara tillsammans med `auto_post` och svarar annars `400
  number_requires_auto_post`.
- `LedgerService.post_voucher` tar nästa nummer, `MAX(number) + 1` över **postade**
  verifikationer i samma serie och räkenskapsår, eller det explicita numret, och skriver det i
  samma `UPDATE` som statusbytet — i en och samma sats, med läsningen som underfråga:
  `UPDATE vouchers SET status='posted', posted_at=?, number=COALESCE(?, (SELECT
  COALESCE(MAX(p.number), 0) + 1 FROM vouchers p WHERE p.series = vouchers.series AND
  p.fiscal_year_id = vouchers.fiscal_year_id AND p.status = 'posted')) WHERE id=? AND
  status='draft'`. Triggern släpper igenom den, eftersom `OLD.status` är `draft`. `UNIQUE` är
  skyddet mot två samtidiga postningar. SQLite har en skrivare åt gången, och eftersom läsning
  och skrivning är samma sats kan de inte hamna i olika transaktioner.
- `VoucherRepository.create_correction` numrerar inte heller.
- `Voucher.number` och `VoucherResponse.number` blir `Optional[int]` (typningen landade redan i
  F2, eftersom utkast annars inte kunde byggas eller serialiseras). Allt som formaterar ett
  nummer hanterar `None`. I backenden (F3) visade genomgången att bara vidareskickande ställen
  kan få ett utkast — `_voucher_dict` i verktygen, `VoucherResponse`, noteringarnas
  ögonblicksbild — och de ger `number: null`. Allt som *formaterar* (`get_account_ledger`,
  huvudboken i `reports.py`, `sie4_export`, `compliance`) läser bara postade, och
  korrigeringstexterna läser originalet, som måste vara postat; där ändras ingenting.
  `list_all(sort_by="number")` lägger utkasten sist i båda riktningarna. I klienten
  (`lib/utils.ts`, `lib/skal/*.ts`) är det F4. Utkast exporteras inte i SIE4
  (`sie4_export.py:224` läser bara postade), så exporten påverkas inte i praktiken.
- De gamla sidorna i `frontend-v3` visar `Utkast` där de i dag visar ett utkasts nummer. Regeln
  bor i `formatVerifikationsnummer` i `lib/utils.ts`, som även `/v4` (`lib/skal/bocker.ts`)
  använder. Det kräver ändringar i fem gamla sidor (`app/page.tsx`, `app/vouchers/page.tsx`,
  `app/vouchers/[id]/page.tsx`, `app/learning/page.tsx`, `app/audit/page.tsx`), vilket
  `SPEC-skal.md` testfall 18 annars förbjuder; vakten har ett namngivet undantag för just dem.

### 4.4 Utkast som finns i dag

Migrationen nollar deras nummer. Nummer som redan hoppats över i den postade serien, eftersom ett
numrerat utkast raderats eller aldrig postats, kan inte lagas i en befintlig databas: postade
rader ändras inte.

**Beslutat 2026-09-23:** det behöver de inte heller. Beställaren börjar om med en tom databas och
importerar SIE4-filerna igen efter driftsättningen. Importen bevarar filens nummer (testfall 10),
så serien blir precis den som står i filerna. Den lagade kontrollen i §4.5 visar om filerna själva
har luckor. Det ingår i verifieringen efter driftsättningen, inte i migrationen.

### 4.5 Kontrollen av luckor är trasig i dag

`services/compliance.py::_check_voucher_sequence` grupperar på `series`, men numren börjar om på
1 varje räkenskapsår (`get_next_number`s docstring). Över två år blir `MAX - MIN + 1` mindre än
antalet verifikationer, och en lucka syns inte. Den grupperas om på `series, fiscal_year_id`, och
rubriken nämner räkenskapsåret (gjort i F3). Det är samma sorts fynd som `SPEC-oversikt.md` §2: en kontroll som ser grön ut för att den inte kan
bli röd.

---

## 5. `foresla_verifikation`

### 5.1 Vad det gör

Skapar en verifikation i `status='draft'`, utan nummer, och binder den till tråden i
`thread_drafts`: till beslutet om det finns, och till korrigeringsnoteringen om det finns. Sedan
skriver det ett `draft`-inlägg i tråden. Allt det i **en transaktion**, samma mönster som
`record_outcome` använder för `decision` och dess rad (`services/thread_service.py`).

Verktyget **postar aldrig**. Det är inte terminalt: turen fortsätter och slutar som vanligt med
ett svar, som efter `be_om_beslut`.

### 5.2 Argumenten

```python
class ForeslaVerifikationArgs(BaseModel):
    description: str                  # blir verifikationens description vid postning (§5.4)
    rows: list[PostaVerifikationRow] = Field(..., min_length=2)
    date: Optional[DateType] = None   # krävs utan correction_of; sätts av servern med (§7.2)
    period_id: Optional[str] = None   # dito
    footnote: Optional[str] = None
    decision_id: Optional[str] = None
    replaces_draft_id: Optional[str] = None
    correction_of: Optional[str] = None       # postad verifikation som rättas (§7)
    correction_note_id: Optional[str] = None  # befintlig notering som rättelsen besvarar (§7.3)
    intake_source_ids: list[str] = Field(default_factory=list)
    bank_input_ids: list[str] = Field(default_factory=list)
    bank_transaction_ids: list[str] = Field(default_factory=list)
```

Radtypen och spårbarhetsfälten är **samma** som `posta_verifikation`. Ett förslag som postas ska
bära exakt det en direkt postning hade burit.

Serien väljs inte av modellen: `A` utan `correction_of`, `B` med. Samma regel som `LedgerService`
redan följer för korrigeringar.

### 5.3 Kontrollerna, före något skrivs

| Kontroll | Fel till modellen |
|---|---|
| Anropat utanför en trådtur (`tool_context["thread"]` saknas) | `draft_requires_thread`, som `be_om_beslut` |
| Obalanserat, okänt konto, fel moms mot kontoplanen | `VoucherValidator`s egna koder |
| Perioden låst (vanligt förslag) | `period_locked` med vem/när |
| `decision_id` finns inte, hör till en annan tråd, eller är `superseded` | `decision_not_found` / `decision_not_in_thread` / `decision_superseded` |
| `decision_id` är fortfarande `open` | `decision_still_open`: ett förslag följer på ett svar, inte i stället för ett |
| `replaces_draft_id` är inte ett väntande utkast i samma tråd | `draft_not_replaceable` |
| `date` eller `period_id` saknas utan `correction_of` | `draft_requires_date_and_period` |
| Spårbarhetsfälten: samma kontroller som `posta_verifikation` kör (underlaget obearbetat och olänkat, bankunderlaget bearbetat, transaktionen ledig) | `IntakeError`/`BankInputError`s egna koder |
| Korrigeringens kontroller | §7.4 |

Valideringen är samma `VoucherValidator` som postningen kör. Designens kant, *"Kontrollera vid
bekräftelse, inte vid visning"*, gäller ändå: perioden kan låsas och kontoplanen ändras
emellan, och postningen validerar om.

### 5.4 Var agentens text hamnar

Stänger `SPEC-beslut.md` öppen fråga 3 och `ANALYS.md` §9.4.

- `description` är agentens formulering och **blir verifikationens `description`**. Den visas som
  kortets rubrik, ordagrant, före trycket. Trycket på `Posta` är människans godkännande av exakt
  den texten. Det är linjen: agentens text blir aldrig `description` utan att en människa sett
  just den strängen i kortet och postat den.
- `footnote` visas i kortet men lagras bara i inlägget, aldrig på verifikationen.
- Agentens resonemang i tråden blir aldrig något av dem.

### 5.5 Idempotens

Samma avsikt ska ge samma utkast. Nyckeln är `thread:{thread_id}:{post_id}:{n}`, där `n` är
verktygsanropets ordning i turen. Den reserveras under en egen endpoint-sträng,
`TOOL foresla_verifikation`. En tur som körs om efter en krasch spelar då upp samma utkast i
stället för att skapa ett andra. Två förslag i samma tur får två nycklar, och ett förslag och en
postning ur samma inlägg krockar aldrig.

Så byggdes det (F6): trådens ingång lägger en `ProposalSequence(thread_id, post_id)` i
`tool_context["proposals"]`, ny per tur, bredvid `thread`. `run_tool_loop` skickar den vidare
oläst, så körtiden vet fortfarande inte vad en tråd är. `n` räknar bara förslag som skapats eller
spelats upp. Ett anrop som en kontroll avvisar tar ingen plats, eftersom nyckeln släpps. Då blir
nyckeln densamma när turen körs om, hur många rättade försök modellen än behövde första gången.
Nyckeln reserveras före kontrollerna, så en uppspelning ger samma utkast även om perioden låsts
sedan dess. Utan `proposals` (ett bart `execute_tool`-anrop) görs förslaget utan nyckel.

### 5.6 Kroppen

Exakt `SPEC-chattyta.md` §4.3, med fält som servern räknar och agenten inte skickar:

| Fält | Källa |
|---|---|
| `draft_id` | Utkastets `vouchers.id` |
| `title` | `description` |
| `meta` | Servern: `"Förslag · {serie} · {datum}"`. Inget nummer finns att visa |
| `rows[].name` | Servern, ur kontoplanen. Modellen skickar bara kontot |
| `footnote` | Agentens, ordagrant |
| `consequence` | Servern: `"Låses vid postning · får nästa nummer i {serie}-serien · period {namn} {läge}"`, och för en korrigering även §7.2:s rad. `{namn}` är `september 2026`, `{läge}` är `öppen` (ett vanligt förslag i en låst period avvisas). Fixturens *"öppen till 2026-10-12"* byggs inte: ingen tabell vet när en period stängs |
| `kind` | Alltid `"voucher"` |
| `decision_id` | Argumentet |

`consequence` är serverns eftersom den är fakta om perioden och serien. *"Agenten formulerar"*
gäller resonemang. Panelens kant *"Om posten ändrar en tidigare stängd period måste det sägas
explicit"* uppfylls av samma rad.

### 5.7 Placering i verktygslistan

Sist, efter `be_om_beslut`. Ordningen är en del av det cachade prefixet, och att lägga till sist
är den enda ändringen som inte flyttar de tio första. `agentruntime`s testfall 17 och `beslut`s
testfall 26 körs mot den utökade listan. `beslut`s testfall 25 (*"`be_om_beslut` sist"*) blir
*"`be_om_beslut` tionde"*: det skyddar fortfarande sin plats och de nio före; resten är testfall 22. `docs/to_agent/02_bokforingsprocess.md` får ett stycke
om när verktyget används, och om att en rättelse alltid går genom det (§12.5). Filen är
runtime-innehåll och testas av `tests/test_agent_entrypoint.py`.

---

## 6. `thread_drafts`

### 6.1 Tabellen

```sql
-- Migration 028
CREATE TABLE IF NOT EXISTS thread_drafts (
    voucher_id          TEXT PRIMARY KEY,   -- utkastet; överlever inte alltid (§6.2)
    thread_id           TEXT NOT NULL,
    post_id             TEXT NOT NULL UNIQUE,
    view_key            TEXT NOT NULL,
    decision_id         TEXT,
    correction_of       TEXT,               -- samma som vouchers.correction_of, för uppslag utan join
    correction_note_id  TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    replaced_by         TEXT,
    posted_at           TIMESTAMP,
    receipt_post_id     TEXT,
    last_error_code     TEXT,
    last_error_post_id  TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES thread_posts(id),
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (correction_note_id) REFERENCES correction_notes(id),
    CHECK (status IN ('pending', 'posted', 'superseded')),
    CHECK (status != 'posted' OR posted_at IS NOT NULL)
);
```

Ingen främmande nyckel mot `vouchers`. Ett ersatt utkast tas bort (§6.2) medan raden här står
kvar, eftersom inlägget i tråden står kvar och måste kunna säga vad som hände med det.

**Ingen ny kolumn på `vouchers`.** Kopplingen lever bredvid huvudboken, inte i den.

**Migration 029 (F6):** `traceability_json TEXT` på `thread_drafts`, med förslagets
`intake_source_ids`, `bank_input_ids` och `bank_transaction_ids`. En länk till underlag eller
banktransaktion får bara skrivas mot en postad verifikation, eftersom länken markerar underlaget
bearbetat och transaktionen bokförd. Id:na måste därför ligga någonstans fram till postningen, och
`vouchers` får ingen kolumn. De länkas i postningens transaktion (§8.1, F8), efter att samma
kontroller körts om. `ThreadDraft` bär dem som tre listor.

### 6.2 Livscykel

```
pending ──Posta lyckas──→ posted
   │
   └──nytt förslag med replaces_draft_id──→ superseded   (utkastet tas bort)
```

- **`pending → posted`** sätts i postningens transaktion (§8.1).
- **`pending → superseded`** sätts av `foresla_verifikation` när `replaces_draft_id` anges. Det
  gamla utkastet tas bort med `VoucherRepository.delete_draft`. Eftersom utkast inte har något
  nummer (§4) lämnar det inget hål.
- **Ett misslyckat försök ändrar inte status.** `last_error_code` sätts och utkastet ligger kvar,
  som panelen säger: *"förslaget ligger kvar så att försöket kan göras om"*.
- **En låsning av perioden ändrar inte heller status** (beslut 2026-09-24, F16). Ett väntande
  förslag i perioden får `last_error_code='period_locked'` och ligger kvar `pending`, som utkast i
  den låsta perioden, tills agenten ersätter det med `replaces_draft_id` i en öppen period (då tas
  det bort som vanligt; ingen trigger hindrar att ett utkast i en låst period tas bort). Se §9.
- Ett ersatt eller postat utkast kan aldrig gå tillbaka.

`ThreadDraftRepository` håller livscykeln, inte anroparna: varje ändring är ett `UPDATE … WHERE
status='pending'` (kvittot: `WHERE status='posted' AND receipt_post_id IS NULL`), och ingen
träffad rad ger `ThreadDraftTransitionError` med raden orörd. Det gäller även `set_error`: ett
postat eller ersatt utkast har inget försök som kan misslyckas. Ett andra kvitto för samma
utkast vägras i stället för att skriva över det första. Två index: `(view_key, status,
created_at)` för §10, och `correction_of WHERE status='pending'` för §7.4.

### 6.3 Beslutet

Ett besvarat beslut står kvar som `answered` genom hela flödet. Modulen ändrar inte beslutets
tillståndsmaskin. Vad vyn kallar *väntar på beslut* härleds i stället (§11.1). Då behövs ingen
övergång tillbaka från `answered` till `open`.

`SPEC-beslut.md` öppen fråga 2, *"vem sätter `superseded`"*: inget i flöde 1 gör det. En låst
period gör utkastets period oanvändbar, inte beslutet. Frågan står kvar öppen, men
korrigeringsvägen ger den inget nytt fall: en rättelse skapar inget nytt beslut, och den gör inget
befintligt inaktuellt.

---

## 7. Korrigering via chatten

**BESLUTAT 2026-09-23:** korrigeringen hör till den här leveransen. Designen ritar den inte
utöver vyfoten och steg 5:s platshållare, *"Säg till om något blev fel i A-118"*. Den byggs
därför som steg 3–6 en gång till, med ett B-serieförslag i stället för ett A-serieförslag. Inga
nya kort och inga nya inläggstyper.

### 7.1 Vägen

1. Människan skriver i tråden vad som blev fel, i fritext. Ingen knapp, inget formulär.
2. Agenten läser originalet (`las_verifikationer`) och kallar `foresla_verifikation` med
   `correction_of` och **de rättade raderna**, alltså hur verifikationen borde ha sett ut.
3. Servern bygger B-utkastet med `LedgerService.create_correction`: återföringsraderna för
   originalet, sedan de rättade raderna. Det är samma uppbyggnad som `/correct` redan använder
   (`create_posted_correction`), men utan att posta.
4. Kortet, knappen, kvittot och felen är desamma som för ett vanligt förslag.
5. Vid postning skrivs korrigeringshistoriken (`_record_correction_history`) **i postningens
   transaktion**, liksom en eventuell korrigeringsnotering (§7.3).

Agenten skickar bara de rättade raderna, aldrig återföringen. Återföringen är mekanisk: varje rad
i originalet med debet och kredit omkastade. Den ska inte kunna bli fel för att en modell
räknade.

### 7.2 Målperioden

Servern väljer, med `LedgerService._target_correction_period`: originalets period om den är
öppen, annars den senaste öppna perioden i samma räkenskapsår. Datumet blir dagens datum om det
ligger i målperioden, annars målperiodens sista dag.

Det här är korrigeringens svåra fall, och panelens kant gäller ordagrant: *"Om posten ändrar en
tidigare stängd period måste det sägas explicit."* `consequence` får då en rad till:

> `Rättar A-118 (juni 2026, låst sedan 2026-07-05) · bokförs i september 2026, inte i juni 2026`

Både den låsta och den öppna perioden står i kortet, före trycket.

Så byggdes det (F11): raden står efter §5.6:s rad, avskild med `\n`. Perioderna heter som
överallt annars, med år (`period_name`). När originalets period är öppen är raden bara
`Rättar A-118`. Saknar perioden `locked_at` (låst före migration 023) står bara `låst`. Datumet
räknas i `LedgerService.correction_target`, som använder `_target_correction_period`;
`create_correction` fick `voucher_date` och `description`, med originalets datum och `Correction
of voucher …` som förval, så `/correct` och noteringarnas väg är oförändrade.

F12 ändrade förvalet: originalets datum hamnade utanför målperioden när originalets period var
låst (`voucher_date_outside_period`), i `/correct` (`create_posted_correction`), i
`CorrectionNoteService.suggest` och i `create_draft`. Utan `voucher_date` väljer
`create_correction` nu datum och period med `correction_target(original, idag)`, och
`create_posted_correction` gör detsamma. Saknar räkenskapsåret öppen period svarar de därför
`no_open_period` redan när rättelsen skapas, i stället för `period_locked` vid postningen.

### 7.3 Korrigeringsnoteringar

`correction_notes` med status `pending` eller `suggested` visas i dag som syntetiska beslut som
inte går att besvara (`SPEC-beslut.md` §5: *"`correction`-raderna lever tills
`flode-verifikationer` äger korrigeringsvägen"*). Nu äger den här modulen vägen:

- Agenten ser öppna noteringar för en verifikation (`las_korrigeringar` utökas med dem, som en
  läsning).
- `foresla_verifikation` med `correction_note_id` binder förslaget till noteringen.
- När förslaget postas sätts noteringen `applied` i postningens transaktion
  (`CorrectionNoteRepository.set_applied`), och det syntetiska beslutet försvinner ur
  `GET /decisions` av sig självt.
- `POST /decisions/correction:…/answer` förblir `409 decision_not_answerable`. Svaret på en
  notering är en postad rättelse, inte ett klick. Pekaren i `409`-kroppen byts till att säga
  *"skriv i Verifikationers chatt"* i stället för att peka på `…/suggest`.

De gamla routerna för noteringar (`suggest`, `approve`, `dismiss`, `reject`) står kvar orörda,
enligt `SPEC-skal.md` §3: de gamla sidorna tas bort vy för vy, inte här.

Så byggdes det (F12):

- `las_korrigeringar` med `voucher_id` svarar `{voucher_id, open_notes, history}`, där
  `open_notes` är noteringarna med `pending`/`suggested` (`id`, `status`, `text`, `created_by`,
  `created_at`). Utan `voucher_id` är svaret listan som förut. Argumenten och
  verktygsbeskrivningen är orörda (cachat prefix); agentinstruktionen
  (`docs/to_agent/02_bokforingsprocess.md`) säger var noteringarna finns.
- Noteringen rörs inte vid förslaget. En `pending` notering går `pending → suggested → applied`
  (`set_suggested` med B-verifikationens id, sedan `set_applied`) i postningens transaktion. Sattes
  den `suggested` vid förslaget kunde den gamla sidans `…/approve` posta trådens utkast förbi
  krokarna. En `suggested` notering från den gamla vägen blir `applied`; dess
  `suggested_voucher_id` pekar kvar på den gamla sidans utkast, som blir liggande som utkast.
- En notering som stängts medan förslaget väntade (avfärdad, avvisad, eller tillämpad av en
  annan rättelse) vägrar postningen med `400 correction_note_mismatch`, och §9:s felinlägg
  skrivs: en postad rättelse ska stänga sin notering.
- `409`-kroppens `details` är: *"Svaret på en korrigeringsnotering är en postad rättelse: skriv
  i Verifikationers chatt (view_key=bocker.verifikationer), där agenten föreslår rättelsen med
  correction_of=…, correction_note_id=…"*.

### 7.4 Korrigeringens kontroller

| Kontroll | Fel till modellen |
|---|---|
| Originalet finns inte eller är inte postat | `voucher_not_found` / `not_posted` |
| Originalet är självt en korrigering | Tillåtet: en rättelse kan rättas, som i `/correct` |
| Ett väntande förslag rättar redan samma original, i vilken tråd som helst | `correction_already_pending`, med förslagets `draft_id`. Ersätt det med `replaces_draft_id` i stället |
| Ingen öppen period i originalets räkenskapsår | `no_open_period`. Agenten avstår och säger det; korrigering över årsskifte är ur scope |
| `correction_note_id` hör till en annan verifikation, eller är inte `pending`/`suggested` | `correction_note_mismatch` |
| `date` eller `period_id` angivna tillsammans med `correction_of` | `correction_period_is_derived`: servern väljer, inte modellen |

Så byggdes det (F11): kontrollerna körs i ordningen `correction_period_is_derived`,
`voucher_not_found`/`not_posted`, `correction_note_mismatch`, `correction_already_pending`,
`no_open_period`, och sedan §5.3:s gemensamma (beslut, `replaces_draft_id`, spårbarhet). En
okänd notering, och `correction_note_id` utan `correction_of`, ger också
`correction_note_mismatch`. `correction_already_pending` bär förslagets id i `details`
(`draft_id=…`). Utkastet byggs av `LedgerService.create_correction` med
`LedgerService.reversal_rows(original)` följt av agentens rader; `create_posted_correction`
(`/correct`) bygger återföringen med samma metod. Hela B-utkastet valideras av
`validate_complete_voucher` i förslagets transaktion.

### 7.5 Vyn

En postad verifikation som har rättats får meta `… · rättad av B-7`. En B-verifikation får
`… · rättar A-118`. Båda härleds ur `vouchers.correction_of`, med en join i sidfrågan och inte en
fråga per rad, samma krav som `SPEC-oversikt.md` §3.

Byggt i F14: `VoucherResponse` har `corrected_by` och `corrects`, båda `{id, series, number} |
null`. `corrected_by` är den senast postade verifikationen vars `correction_of` pekar hit (en
väntande rättelse räknas inte); `corrects` är verifikationen `correction_of` pekar på, också på
ett utkast. Båda joinas in i sidfrågan (`VOUCHER_SELECT_SQL` i `voucher_repo.py`), som `get`,
`list_all` och `list_for_period` delar. N+1 i listan är lagat i samma svep: sidans rader läses i
en fråga (`_rows_for`), och kontonamnen en gång per sida i stället för per verifikation.
Klienten visar `· rättar A-118` bara på en postad verifikation.

---

## 8. Postningen och kvittot

### 8.1 Vägen

Klienten anropar som i dag `POST /vouchers/{draft_id}/post` med nyckeln
`uuid5(BOK_KLIENT_NS, "draft:" + draft_id)`. Routen ändras på två ställen.

**I postningens transaktion**, via `DraftService.on_posting(voucher)`, om utkastet finns i
`thread_drafts` med `status='pending'`:

0. Kontoplanen som den är nu (F9): varje rads konto ska finnas och vara aktivt
   (`VoucherValidator.validate_accounts_exist`/`validate_accounts_active`). `post_voucher` kör inte
   de kontrollerna, så ett konto som inaktiverats medan förslaget låg hade annars postats. Ett fel
   här rullar tillbaka postningen och blir `400 inactive_account` eller `400 account_not_found`.
1. `status='posted'`, `posted_at`.
2. Om `correction_of`: korrigeringshistoriken och, om den finns, noteringen `applied` (§7).
   Så byggdes det (F12): `LedgerService.record_correction_history` (förut
   `_record_correction_history`, som svalde alla fel) med originalet, den postade
   B-verifikationen och de rättade raderna, alltså B-utkastets rader efter de första
   `len(original.rows)`. `correction_reason` är B-verifikationens `description`, den text
   människan såg på kortet och postade, följd av ` · notering: {note_text}` när rättelsen svarar
   på en notering. `corrected_data.description` förblir originalets: `corrected_data` är
   originalet så som det borde ha sett ut, inte B-verifikationen. Ett fel i historiken rullar
   tillbaka hela postningen (`500`, inget nummer förbrukat). `/correct` beter sig likadant: där
   svaldes felet förut och rättelsen postades utan historik; nu rullas den tillbaka och svarar
   `500`, och `create_posted_correction` utan `_commit=False` öppnar en egen transaktion.
3. Radens spårbarhet (migration 029, §6.1) länkas som en direkt postning gör det:
   `IntakeService.link_existing_voucher` och `BankInputService.link_posted_voucher`, med
   `_commit=False`.

Det här måste ligga i transaktionen. En korrigering utan historik, eller en notering som fortsatt
står öppen efter att rättelsen postats, är fel i bokföringen, inte i tråden.

**Underlaget hann bokföras (F8).** Medan ett förslag väntar står dess underlag som `pending`, så
intagsflödet kan posta samma underlag direkt. Vägrar länkningen i steg 3 för att underlaget eller
banktransaktionen redan bär en verifikation, kastar `on_posting` `SourceAlreadyBookedError` och
**hela postningen rullas tillbaka**: inget nummer förbrukat, utkastet kvar som utkast, raden kvar
som `pending`, nyckeln släppt. Routen svarar `409 source_already_booked` med `booked_by:
{source_kind, source_id, voucher_id, voucher_number}`. Vägrar länkningen av något annat skäl blir
det `409 source_not_linkable` med tjänstens kod i `details`. `on_posting` tar även `actor`, som
blir länkarnas `linked_by`.

**Efter commit**, via `DraftService.on_posted(voucher, actor)`:

4. Skriver `receipt`-inlägget och sätter `receipt_post_id`.
5. Publicerar `message.completed` för kvittot och `view.changed` med
   `{voucher_id, kind: "voucher_posted"}` på trådens `view_key`.

Utkast som inte kommer från en tråd berörs inte, och routen beter sig som i dag för dem.

**Varför kvittot skrivs efter commit.** Postningen är BFL-kritisk och kvittot är det inte. Ett fel
i trådlagret får inte kunna rulla tillbaka en verifikation. Priset är att kvittot kan saknas trots
att postningen lyckats. Därför är steg 4–5 **idempotenta och återupptagbara**: en uppspelning med
samma nyckel (`Idempotent-Replay` eller `409 already_posted`) kör om dem om `receipt_post_id` är
`NULL`. Klientens `Försök igen` vid nätverksfel gör det av sig självt.

### 8.2 `receipt`-kroppen

Exakt `SPEC-chattyta.md` §4.3:

```jsonc
{
  "title": "A-118 postad",             // korrigering: "B-7 postad · rättar A-118"
  "labels": ["var", "blir"],
  "rows": [
    { "key": "1930", "text": "Företagskonto",           "left_ore": 8412000, "right_ore": 7964000 },
    { "key": "5410", "text": "Förbrukningsinventarier", "left_ore":  312000, "right_ore":  670400 },
    { "key": "2641", "text": "Ingående moms",           "left_ore":  144000, "right_ore":  233600 }
  ],
  "voucher_id": "<id>"
}
```

- En rad per konto som verifikationen rör, i verifikationens radordning. För en korrigering
  alltså varje konto som återföringen eller de rättade raderna rör, en gång var, och ett konto
  vars saldo inte ändrats netto står ändå med. Båda talen, alltid.
- `left_ore`/`right_ore` är kontots saldo i räkenskapsåret före och efter verifikationen, räknat
  på servern ur postade rader (`VoucherRepository.account_balances_around`, en fråga). *Före* är
  summan av postade rader i samma räkenskapsår på verifikationer postade tidigare (`posted_at`,
  sedan `rowid`), så att ett kvitto som skrivs sent, vid en återupptagning, fortfarande säger vad
  postningen ändrade när den skedde. *Efter* är före plus verifikationens egen nettorad på kontot.
- Numret i `title` kommer ur den postade verifikationen, alltså det som just satts (§4).
- `traces[]`: `verifikation postad` · `{serie}-{nummer}`, `kompletteringsflagga satt` när
  verifikationen saknar bilaga (`SPEC-oversikt.md` §3), `{n} kvar` ur räknaren i §11.3, och för
  en korrigering även `rättar {serie}-{nummer}`.
- `actor` är människan som postade, inte `agent`.
- Chipens `tool` (F8): `posta_utkast` för `verifikation postad` (med `detail` och `voucher_id`),
  `kompletteringsflagga` för `kompletteringsflagga satt`, `vantar` för `{n} kvar` (F10), som
  står sist och räknas med `count_waiting(trådens vy)` efter postningens commit, så att det
  postade förslaget inte längre räknas. `rättar …` (F12) har `tool: "rattar"`, `detail`
  `{serie}-{nummer}` och originalets `voucher_id`, och står direkt efter `verifikation postad`.

Panelens *"Sista händelsen i kön: då slutar tråden med att juni är avstämd"* blir chipet
`0 kvar`. Att juni är *avstämd* är ett omdöme, och omdömen är agentens.

---

## 9. När postningen misslyckas

| Fel | Utkastet | Tråden | Kortet (klart i `chattyta`) |
|---|---|---|---|
| `409 period_locked` | `last_error_code='period_locked'` | Ett `error`-inlägg (§9.1) | Inline med vem/när, ingen `Försök igen` |
| `400` validering (kontoplanen ändrad sedan förslaget, §8.1 steg 0) | `last_error_code` = valideringens kod | Ett `error`-inlägg med valideringens orsak | Inline fel |
| `422 idempotency_key_reuse` | Oförändrat | Inget | Inline, som i dag |
| `409 source_already_booked` (§8.1) | `last_error_code='source_already_booked'`, postningen rullad tillbaka | Ett `error`-inlägg som säger vilken verifikation som bär underlaget | Inline fel |
| `409 source_not_linkable` (§8.1) | `last_error_code='source_not_linkable'`, postningen rullad tillbaka | Ett `error`-inlägg som namnger underlaget | Inline fel |
| Nätverksfel, `5xx` | Oförändrat | Inget: servern vet inte att det hände | Inline med `Försök igen`, samma nyckel |

Valideringsfel vid postning har alltid mappats till `400` av routen (`_posting_http_error`); F9
ändrar inga HTTP-svar. Felinlägget skrivs av `DraftService.on_posting_failed` efter postningens
rollback, i en egen transaktion (inlägget och `set_error` tillsammans), och publiceras som
`message.completed`. Ett fel där loggas och ändrar inte svaret. `already_posted` är inget fel för
tråden: där tar kvittot över (§8.1).

Ett B-utkast kan också träffas av `period_locked`, om målperioden låses emellan. Svaret är
detsamma. Agentens nästa förslag hamnar i nästa öppna period, och §7.2:s rad säger det.

**Låsningen och väntande förslag — BESLUTAT 2026-09-24 (F16).** F15 fann att
`LedgerService.lock_period` vägrade låsa en period med utkast (`400 draft_vouchers_exist`), så ett
väntande förslag stoppade månadsstängningen och läget ovan nåddes bara förbi tjänsten. Beställarens
beslut: låsningen går igenom och markerar väntande förslag i perioden som låsta. Så här:

- `POST /periods/{id}/lock` låser i en transaktion: `UPDATE periods` först, sedan kontrollen av
  utkast, där trådförslag med `status='pending'` räknas bort. **Andra utkast** (de gamla sidornas,
  korrigeringsnoteringarnas, IB) stoppar som förut med `draft_vouchers_exist`, och då markeras
  inget. Varje väntande förslag i perioden får `last_error_code='period_locked'` i samma commit.
- Efter commit: ett `error`-inlägg per förslag i dess tråd, samma text som ovan (§9.1, vem/när ur
  perioden), `message.completed` för inlägget och ett `view.changed` per tråd med
  `{"period_id": …, "kind": "period_locked"}`. Aktören är låsaren.
- Dedupliceringen gäller: ett förslag som redan har sitt `period_locked`-inlägg får inget nytt, och
  ett senare `Posta` ger `409 period_locked` utan nytt inlägg. Misslyckas inlägget loggas det och
  låsningen står kvar; `last_error_post_id` är då tomt, så nästa `Posta` skriver inlägget.
- Förslaget räknas fortfarande som väntande (§11.3): det kräver människans eller agentens handling.
  Vyn visar raden i `fel`-läget (§11.1) ur `last_error_code`; för `period_locked` är metan
  *"perioden låst · ligger kvar"*, eftersom ingen postning behöver ha misslyckats.

### 9.1 `error`-inlägget

```jsonc
{
  "cause": "Perioden juni låstes 2026-06-30 09:14 av stefan medan förslaget låg.",
  "consequence": "Ingenting har ändrats i bokföringen. Förslaget ligger kvar men kan inte postas i juni.",
  "retry_draft_id": null
}
```

- Texterna är serverns, byggda ur felet: orsak *och* konsekvens, i bokföringstermer, aldrig en
  statuskod.
- `retry_draft_id` är `null` vid alla fel i tabellen ovan, eftersom inget av dem kan lyckas vid
  ett nytt försök med samma utkast.
- Texterna (F9), med `Ingenting har ändrats i bokföringen.` först i varje konsekvens:

  | Kod | `cause` | `consequence` fortsätter |
  |---|---|---|
  | `period_locked` | `Perioden {period} låstes {YYYY-MM-DD HH:MM} av {locked_by} medan förslaget låg.` (`av …` utelämnas om låsaren saknas) | `Förslaget ligger kvar men kan inte postas i {period}.` |
  | `inactive_account` | `Konto {kod} {namn} har inaktiverats i kontoplanen sedan förslaget lades fram.` | `Förslaget ligger kvar men kan inte postas som det står.` |
  | `account_not_found` | `Konto {kod} finns inte längre i kontoplanen.` | som ovan |
  | `source_already_booked` | `Underlaget {filnamn}` / `Banktransaktionen` `bokfördes på verifikation {A-n} medan förslaget låg.` | `Samma underlag bokförs inte två gånger: {A-n} står kvar och förslaget ligger kvar opostat.` |
  | `source_not_linkable` | `Underlaget {filnamn}` / `Bankunderlaget` `kan inte längre kopplas till en verifikation.` | `Förslaget ligger kvar men kan inte postas med det underlaget.` |
  | övriga | `Förslaget klarade inte bokföringens kontroller vid postningen ({meddelande}).` | `Förslaget ligger kvar men kan inte postas som det står.` |
- **Ett inlägg per utkast och felkod.** Panelens *"samla dem till ett inlägg med en räknare"* går
  inte att göra ordagrant, eftersom inlägg aldrig ändras (`SPEC-tradar.md` §8.4). Det görs i
  stället genom att inte skriva det andra inlägget: finns `last_error_post_id` redan för samma
  kod, skrivs inget nytt.

---

## 10. `GET /api/v1/drafts`

Förslagskortet måste veta om det redan är postat eller ersatt, efter en omladdning, i en annan
flik, eller om agenten har lagt fram ett nytt. Inlägget kan inte säga det, eftersom det inte
ändras. Lösningen är densamma som för besluten (`SPEC-chattyta.md` §7): ett anrop per vy, med
uppslag lokalt i klienten.

```
GET /api/v1/drafts?view_key={vk}&status=pending|posted|superseded|all&limit=200
→ { "drafts": [ { "draft_id", "post_id", "decision_id", "correction_of", "status",
                  "replaced_by", "posted_at", "voucher": { "series", "number" } | null,
                  "last_error_code", "created_at" } ], "total": n }
```

`voucher` är ifyllt bara när `status='posted'`, och det är enda stället klienten får ett nummer
ifrån. Numren hämtas ur `vouchers` i en fråga för hela sidan (`VoucherRepository.numbers_for`).

Parametrarna (F10): `view_key` krävs (saknas → `422`, okänd → `404 unknown_view_key`, som
`GET /decisions`); `status` är `all` om den utelämnas, okänd → `400 unknown_status`; `limit` är
`1–200`, förval `200`. Äldst först (`created_at`, sedan `rowid`); `total` räknas före `limit`.
Bearer-auth. `posted_at` och `created_at` är ISO-8601-tider.

`VerifikationsForslag` får sina lägen ur den här statusen:

| Status | Kortet |
|---|---|
| `pending` | Som i dag: `Posta`, `Ändra`, konsekvensnotis |
| `pending` + `last_error_code` | Som i dag, med felraden kvar. Ingen `Posta` vid någon kod (se nedan) |
| `posted` | Klart: `Postad · {serie}-{nummer}`, inga knappar |
| `superseded` | `Ersatt av ett nytt förslag`, inga knappar |

Frågan invalideras på `view.changed`, på `message.completed` med typen `draft`, `receipt` eller
`error`, och efter varje svar på `Posta`.

Klienten (F13): `useForslag(viewKey)` (`frontend-v3/hooks/useForslag.ts`) frågar
`status=all&limit=200` under `["drafts", viewKey]` och ger ett uppslag `draft_id → rad`, eller
`undefined` innan svaret finns (kortet står då som `pending`). `view.changed` invaliderar också
`["vouchers"]` (testfall 47). **Avvikelser:** ingen `Posta` vid *någon* `last_error_code`, inte
bara `period_locked`: varje kod i §9 kommer ur ett fel som samma utkast inte kan komma förbi
(`retry_draft_id` är `null` för alla). Felraden efter en omladdning är klientens korta mening per
kod (`forslagFelText`), utan vem/när eller nummer, eftersom raden bara bär koden; klickets eget
svar går före och bär `booked_by.voucher_number`. Kortets statusläsning per kort
(`GET /vouchers/{id}`, från `chattyta` C12) är borttagen: ett anrop per vy. Kvittots `traces[]`
ritas nu som chip under jämförelsen; det gjordes inte förut.

---

## 11. Vyn Verifikationer

### 11.1 Sektionerna

| Sektion | Rader | Källa |
|---|---|---|
| **Väntar på beslut** | Öppna beslut i vyn, **plus** väntande trådförslag (vanliga och korrigeringar) | `GET /decisions?view_key=…&status=open`, `GET /drafts?…&status=pending` |
| **Postade** | Som i dag, senast först, utan IB, med `rättad av`/`rättar` (§7.5) | `GET /vouchers?status=posted…` |
| **Utkast** | Utkast som **inte** finns i `thread_drafts` | `GET /vouchers?status=draft`, minus trådens utkast |

Ett trådutkast visas på ett enda ställe.

| Läge | Meta | Variant |
|---|---|---|
| Öppet beslut | `väntar på dig · {källdatum}` | `vantar`, röd från sju dagar (`aldersTon`) |
| Förslag väntar | `förslag väntar · {datum}` | `vantar` |
| Rättelse väntar | `rättelse av {serie}-{nummer} väntar` | `vantar` |
| Förslag med fel, `period_locked` | `perioden låst · ligger kvar` | `fel` |
| Förslag med fel, övriga koder | `postning misslyckades · ligger kvar` | `fel` |
| Postas just nu | `{serie} · postas…`, grå, **inget nummer** | `pagaende` |
| Nyss postad | `{serie}-{nummer} · postad HH:MM · {vem} · låst` | `ny` i 6 s |

### 11.2 Den optimistiska raden

- Vid tryck på `Posta` läggs en `pagaende`-rad överst i `Postade`, med nyckeln `draft_id`, och
  händelsen tas bort ur `Väntar på beslut`. Raden har inget nummer, eftersom numret inte finns
  än. Det är det panelen menar med *"visas först när posten finns"*.
- Vid `200`, uppspelning eller `already_posted` byts raden mot serverns verifikation på samma
  nyckel (`draft_id` = `vouchers.id`) och får läget `ny`, nu med nummer.
- Vid fel tas raden bort, och händelsen går tillbaka till `Väntar på beslut`, med läget `fel` vid
  `period_locked` eller som den var.
- Dröjer svaret mer än 3 s byter kortets knapptext till `Postar fortfarande…`.
- Den optimistiska raden lever bara i klientens cache. Efter en omladdning mitt i en postning
  visar vyn det servern svarar, och postningen är ett enda synkront anrop, så något mellanläge
  behövs inte.

Byggt i F14 (klienten): `verifikationerVy(ar, postade, utkast, {beslut, forslag, postningar})`
i `lib/skal/bocker.ts`; `useVyer` läser besluten och förslagen under samma nycklar och i samma
cachade form som trådens `useBeslut`/`useForslag` (`status=all`, en fråga per vy som kort och vy
delar), och verifikationslistorna under `["vouchers", "skal", …]` så att `view.changed` och
`Posta` når dem. Den optimistiska raden ligger i TanStack-cachen under `["postningar"]`
(`lib/chattyta/postningar.ts`): `usePostaUtkast` skriver den vid trycket och vid svaret, även om
kortet hunnit försvinna, och tar bort den efter 6 s (`NY_POSTNING_MS` = `NY_MARKERING_MS`).
**Avvikelser:**

- **Sektionernas ordning** är Väntar på beslut, Postade, Utkast, och rubriken är `Postade` (förut
  `Utkast` överst och `Senast postade`). Ett utkast utanför tråden behåller varianten `vantar`.
- **Ett förslag på ett öppet beslut står i beslutets ställe.** Förslag som svarar på ett öppet
  beslut i vyn (`decision_id`, eller `correction:{correction_note_id}` för en rättelse på en
  notering) ersätter beslutsraden — även medan det postas, så att beslutet inte dyker upp i
  Väntar under postningen. För det har `GET /drafts` fått fältet `correction_note_id`.
- **Vyns status** är `{n} väntar på dig`, där `n` räknas med §11.3:s regel: en gång per beslut,
  per notering och per fristående förslag. Två väntande förslag på samma besvarade beslut är två
  rader men ett i talet. Utan något som väntar: `{n} utkast`, annars `{n} postade`.
- **`{vem}` i `Nyss postad` är `du`.** `VoucherResponse` har ingen `posted_by`, och bara
  klientens eget tryck ger läget `ny`. Klockslaget skärs ur `posted_at` som servern skrev det.
- `förslag väntar · {datum}` tar verifikationens datum. Förslagsrader färgas inte med åldern;
  bara beslutsraden får `ageDays` (`aldersTon`), som tabellen säger.
- **Vid fel** tas raden bort och vyns förslagsfråga hämtas om; läget `fel` kommer ur serverns
  `last_error_code`, alltså vid varje kod i §9, inte bara `period_locked`. Ett nätverksfel lägger
  tillbaka händelsen som den var.
- Headerns tal (`open_decisions`) räknas utan `view_key` (§11.3, sista stycket), vyns för
  `bocker.verifikationer`. De är lika så länge inget väntar i Balansräkningens eller
  Resultaträkningens trådar; de syntetiska besluten ligger alltid i Verifikationer.

### 11.3 Räknaren

Panelen: *"Räknaren i headern och vyns lista läser samma fält."* En funktion,
`DecisionService.count_waiting(view_key=None)`: öppna beslut plus `thread_drafts` med
`status='pending'`, **utan dubbelräkning**. Ett beslut och dess väntande förslag räknas en gång.
En rättelse som väntar räknas också, eftersom den väntar på människan. `open_decisions` i
`GET /overview`, `VyHeaderStatus` och mobilens märke läser funktionen. Fältnamnet behålls och
payloaden ändras inte, bara uträkningen.

Regeln, som den byggdes i F10:

1. Öppna beslut som `list_decisions(status="open", view_key=…)` skulle visa: `decisions` med
   `status='open'` i vyn (alla vyer utan `view_key`), plus de syntetiska (`intake:`,
   `correction:`) när `view_key` saknas eller är `bocker.verifikationer`.
2. Plus väntande förslag i vyn, **utom** de vars `decision_id` är ett öppet beslut som räknas i
   1, eller vars `correction_note_id` är en öppen notering som räknas i 1.
3. De som återstår räknas en gång per `decision_id` (ett besvarat eller ersatt beslut med
   väntande förslag är en sak som väntar), en gång per `correction_note_id`, och ett vardera när
   de svarar på ingetdera (ett fristående förslag, eller en rättelse utan beslut).

Ett öppet beslut med väntande förslag räknas alltså via beslutet, ett besvarat beslut med ett
ersatt och ett väntande förslag via det väntande. Postade och ersatta förslag räknas aldrig. Utan
trådförslag är talet exakt `count_open()`. `open_decisions` finns bara på `bocker` och räknas
utan `view_key`.

---

## 12. Beslut

### 12.1 Ett elfte verktyg, `foresla_verifikation` — **BESLUTAT 2026-09-23**

Att låta servern bygga utkastet ur det valda alternativet föll på att ett alternativ bär konto och
belopp, men ingen kontering. `SPEC-beslut.md` §11.3 sa att `be_om_beslut` var *"den enda modulen
i redesignen som lägger till ett verktyg"*. Det stämmer inte längre, och det här är skälet.

### 12.2 Agenten får fortsätta posta direkt i tråden — **BESLUTAT 2026-09-23**

`posta_verifikation` är oförändrat. Förslaget är vägen när agenten har avstått och människan har
valt. `SPEC-beslut.md` §11.1 gäller fortfarande. Priset: två vägar till huvudboken från samma
chatt. Båda går genom `VoucherValidator` och idempotensnyckeln, och båda syns i tråden.

### 12.3 Servern kvitterar — **BESLUTAT 2026-09-23**

Ingen LLM-tur efter ett tryck. Kvittot är fakta om bokföringen, räknat där bokföringen finns.

### 12.4 Utkast har inget nummer — **BESLUTAT 2026-09-23**

*"Ett utkast på en verifikation skall inte få ett nummer. Numret skapas när verifikationen
bokförs."* Gäller alla utkast, inte bara agentens: korrigeringsutkast, IB-utkast och de gamla
sidornas. Se §4.

### 12.5 Korrigering i den här leveransen — **BESLUTAT 2026-09-23**

Se §7. Följd av §12.2: agenten får posta direkt, men **inte en rättelse**. En rättelse går alltid
genom ett förslag som människan postar. `posta_verifikation` har ingen `correction_of` och får
ingen. En B-verifikation utan koppling till originalet vore en rättelse som inte syns som rättelse
i historiken. Verktygsbeskrivningen säger det redan: *"felaktiga postningar rättas genom en ny
B-serieverifikation, inte genom detta verktyg."*

---

## 13. Öppna frågor

Ingen av dem blockerar starten.

1. **Årsskiftet.** Ett förslag i förra årets tråd som postas efter årsskiftet. Ärvd från
   `SPEC-tradar.md` §13.2 och `SPEC-beslut.md` öppen fråga 4. Kvittot skrivs i utkastets tråd,
   och det är rätt tills frågan besvaras. Korrigering över årsskiftet är ur scope (§7.4).
2. **`ny`-markeringens varaktighet.** 6 s, ärvd (`SPEC-skal.md` öppen fråga 3). Samma konstant.

---

## 14. Teststrategi

`pytest` för backenden och `vitest` för klienten. Testerna skrivs **före** implementationen. Den
riktiga LLM:en används aldrig i test. Verktyget körs via `execute_tool` med en falsk tråd i
`tool_context`, som i `tests/test_beslut.py`.

### 14.1 Numreringen (`tests/test_numrering.py`)

| # | Fall | Förväntat |
|---|---|---|
| 1 | Migrationen mot en databas med postade och utkast | Varje postad rad identisk fält för fält; utkastens `number` är `NULL`; `foreign_key_check` tom |
| 2 | Schemat efter migrationen | Utkast med nummer avvisas; postad utan nummer avvisas |
| 3 | `DROP TABLE` under migrationen | Stoppas inte av `prevent_delete_posted_vouchers`; ingen postad rad förlorad |
| 4 | Triggrarna efter migrationen | `UPDATE`/`DELETE` på postad verifikation och på dess rader avvisas, som före |
| 5 | Skapa utkast | `number` är `None` |
| 6 | Posta | Nästa nummer bland postade i serien och året |
| 7 | Två utkast, det senare postas först | Det senare får det lägre numret |
| 8 | Ett utkast tas bort | Ingen lucka i den postade serien |
| 9 | Nytt räkenskapsår | Numret börjar på 1 |
| 10 | SIE4-import med explicita nummer | Numren bevaras |
| 11 | Korrigering via `/correct` | B-nummer sätts vid postning, som förut |
| 12 | Luckkontrollen över två räkenskapsår | Hittar en lucka i år två, som den i dag missar |
| 13 | API och gamla sidor | `number: null` för utkast; `lib/utils.ts` visar `Utkast` |

### 14.2 Flödet (`tests/test_flode_verifikationer.py` och `vitest`)

| # | Fall | Förväntat |
|---|---|---|
| 14 | `foresla_verifikation` i en trådtur | Ett utkast utan nummer, en `thread_drafts`-rad, ett `draft`-inlägg; kroppen passerar `chattyta`s `parseInlagg`-fixtur |
| 15 | Samma tur körd två gånger | Samma utkast, inget andra |
| 16 | Två förslag i samma tur | Två utkast, två nycklar |
| 17 | Utan tråd / obalanserat / låst period / beslut i fel läge | Respektive fel, inget skrivet |
| 18 | Fel halvvägs i transaktionen | Inget utkast, inget inlägg, ingen rad |
| 19 | `replaces_draft_id` | Gammalt utkast borttaget, raden `superseded`; ingen lucka |
| 20 | `description` → verifikationens `description`; `footnote` bara i inlägget | Som §5.4 |
| 21 | `meta` utan nummer; `consequence` med serie och periodläge | Som §5.6 |
| 22 | Verktyget sist; de tio första i oförändrad ordning | `agentruntime` 17, `beslut` 26 |
| 23 | Posta ett trådutkast | `posted`; nummer satt; ett `receipt` med det numret; `view.changed` |
| 24 | Posta två gånger med samma nyckel | En verifikation, ett nummer, **ett** kvitto |
| 25 | Kvittot misslyckas efter commit | Postningen står kvar; uppspelning skriver kvittot |
| 26 | `receipt`-raderna | Före- och eftersaldo per konto; stämmer mot `GET /reports/general-ledger/{konto}` |
| 27 | Posta ett utkast som inte är trådens | Inget kvitto, ingen `view.changed`, routen som i dag |
| 28 | Perioden låses mellan förslag och tryck | `409 period_locked`; ett `error`-inlägg med vem/när; inget bokfört, inget nummer förbrukat |
| 29 | Samma låsta utkast postas tre gånger | Ett `error`-inlägg, inte tre |
| 30 | `GET /drafts` | Status; `voucher` bara när postad |
| 31 | `count_waiting` | Öppet beslut + väntande förslag + väntande rättelse, utan dubbelräkning; samma tal i `/overview` |

### 14.3 Korrigeringen

| # | Fall | Förväntat |
|---|---|---|
| 32 | Rättelse av A-118 i öppen period | B-utkast utan nummer: återföring av A-118 följd av de rättade raderna; agentens rader oförändrade |
| 33 | Originalet i låst period | Målperiod = senaste öppna; `consequence` nämner båda perioderna |
| 34 | Ingen öppen period i året | `no_open_period`, inget skrivet |
| 35 | Andra rättelsen av samma original medan den första väntar | `correction_already_pending` med `draft_id` |
| 36 | `date`/`period_id` med `correction_of` | `correction_period_is_derived` |
| 37 | Posta rättelsen | B-nummer vid postning; historik i `accounting_corrections` i samma transaktion; kvittot `B-7 postad · rättar A-118` |
| 38 | Historiken misslyckas | Hela postningen rullas tillbaka; inget B-nummer förbrukat |
| 39 | Med `correction_note_id` | Noteringen `applied` i postningens transaktion; det syntetiska beslutet borta ur `GET /decisions` |
| 40 | `correction_note_id` för annan verifikation | `correction_note_mismatch` |
| 41 | `POST /decisions/correction:…/answer` | Fortfarande `409`, med ny pekare |
| 42 | Vyns meta | `rättad av B-7` och `rättar A-118`, utan N+1 |
| 43 | `posta_verifikation` | Oförändrad; har ingen `correction_of` |

### 14.4 Klienten och regression

| # | Fall | Förväntat |
|---|---|---|
| 44 | `VerifikationsForslag` ur `GET /drafts` | Fyra lägen enligt §10 |
| 45 | Vyns sektioner | Trådutkast bara i `Väntar på beslut`; övriga utkast i `Utkast` |
| 46 | Optimistisk rad | `pagaende` utan nummer; `ny` med nummer; bort vid fel, händelsen tillbaka med `fel` |
| 47 | `view.changed` | Invaliderar vouchers, decisions, drafts och overview |
| 48 | Hela flödet, backend | Beslut → svar → förslag → post → kvitto, och rättelse → post → kvitto, med skriptade verktygsanrop |
| 49 | Append-only | Ingen `UPDATE`/`DELETE` på en postad rad i någon väg ovan |
| 50 | Regression | `pytest tests/` grön; `chattyta`s och `skal`s tester gröna |

---

## 15. Gränser

**Alltid:**
- Tester före implementation.
- Numreringen (§4) först, med sina tester gröna, innan något annat i modulen byggs.
- Efter driftsättningen: tom databas, SIE4-filerna importerade igen, luckkontrollen körd (§4.4).
- Varje skrivning som binder ett inlägg till en rad sker i en transaktion.
- `VoucherValidator` vid förslag **och** vid postning.
- Nya SQL-frågor i `repositories/`, aldrig i en service eller route.

**Fråga först:**
- Allt i migration 027 utöver att göra `number` nullbar och lägga till `CHECK`-villkoret.
- En ändring i beslutens tillståndsmaskin.
- En ändring i `chattyta`s kontrakt (§4.3) utöver fälten som redan står där.
- Korrigering över räkenskapsårsskifte.

**Aldrig:**
- En `UPDATE` eller `DELETE` på en postad verifikation, eller en uppmjukad trigger, i migrationen
  eller någon annanstans.
- Ett nummer på ett utkast, eller ett nummer som sätts någon annanstans än i postningens
  transaktion.
- Att kvittot skrivs i postningens transaktion, eller att korrigeringshistoriken skrivs utanför
  den.
- Att agenten räknar fram en återföring, eller väljer en rättelses period.
- Att agentens resonemang hamnar i `description` utan att ha stått ordagrant i kortet.
- Att klienten räknar ett saldo, ett nummer eller en räknare.
- Att flytta de tio befintliga verktygen i listan.

---

## 16. Framgångskriterier

1. Utkast har inget nummer. Numret sätts vid postning, i postningsordning, utan luckor, och
   migrationen har kopierat varje postad rad oförändrad (testfall 1–13).
2. Beslut → svar → förslag → `Posta` → kvitto fungerar mot riktig backend i `/v4`, med agentens
   turer från en riktig LLM (48 skriptat, plus visuell kontroll).
3. En rättelse i chatten ger ett B-förslag som säger vilken period det hamnar i. Postad får den
   historik, och originalet visas som rättat (32–43).
4. Två tryck ger en verifikation, ett nummer och ett kvitto (24).
5. Låst period mitt i ger ett felkort med vem och när, inget bokfört och inget nummer förbrukat
   (28, 29, 46).
6. Räknaren i headern, mobilens märke och vyns väntar-sektion visar samma tal i varje steg (31, 45).
7. Ett förslagskort visar rätt läge efter omladdning och i en annan flik (44).
8. Ingen postad rad ändras och triggrarna fungerar som före. Ingen ny kolumn på `vouchers`; den
   enda schemaändringen är nullbart `number` och `CHECK`-villkoret (1–4, 49).
9. `pytest tests/ -v`, `black`, `isort` och `flake8` rena; inga nya `mypy`-fel i modulens filer;
   `npm test`, `npm run lint`, `npx tsc --noEmit` och `NEXT_PUBLIC_SKAL=1 npm run build` gröna.
