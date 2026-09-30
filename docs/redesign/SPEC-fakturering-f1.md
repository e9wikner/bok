# SPEC-fakturering F1: agenten och tråden

Fakturering i `/v4` blir en skrivvy. Agenten läser kunder och fakturor i tråden och lägger fram
fakturan som ett kort. Människan trycker `Utfärda`, och servern kvitterar i tråden med PDF:en och
verifikationen.

F0 är byggd och gäller oförändrad. Specen står i git-historiken:
`git show e313c5f:docs/redesign/SPEC-fakturering.md`. Hänvisningar som `F0 §5` pekar dit.
Mönstret för förslag, kort, kvitto och felinlägg är flöde 1:s:
`git show 1a7a7b7:docs/redesign/SPEC-flode-verifikationer.md` (`FV §n` nedan).

Status: **utkast 2026-09-30, väntar på beslut** (§1). Inget är byggt.

---

## Antaganden

1. **F0:s beslut står fast.** Agenten utfärdar aldrig (`403 human_only`). Agenten föreslår numret
   och servern kräver bara att det är unikt. Leveransen är en PDF som användaren skickar själv.
   Allt det gäller i tråden också.
2. **Flödet är designens flöde 3** (`BokAi flöden v1.dc.html`, kundfaktura, fyra steg). Där F0
   ändrade flödet gäller F0. `Skicka fakturan` blir `Utfärda`, och e-faktura och sändning utgår.
   §2 säger var specen avviker från panelen och varför.
3. **Klientens mönster finns.** `VerifikationsForslag`, `PostaKnappar`, `FelKort`,
   `JamforelseRader`, `useForslag`, den optimistiska raden och `view.changed` är byggda i flöde 1.
   F1 bygger fakturans motsvarigheter bredvid dem och ändrar inte verifikationernas.
4. **Utkastet är redigerbart och fakturan är det inte.** `invoice_drafts` får ändras tills det
   utfärdas. Ingenting i F1 rör en utfärdad faktura, en postad verifikation eller migration 038:s
   triggrar.
5. **Ett bolag och en människa**, som i alla tidigare moduler.

---

## 1. Beslut att ta före bygget

Specen är skriven med rekommendationen i varje punkt. Ett annat svar ändrar de paragrafer som
står inom parentes.

1. **En ändring ger ett nytt kort, och utkastet bär en revision** (§4, §6). `andra_fakturautkast`
   ändrar utkastet på plats, räknar upp `invoice_drafts.revision` och skriver ett nytt kort. Det
   gamla kortet står då som `Ändrat`. `Utfärda` skickar kortets revision, och servern vägrar om
   utkastet har ändrats sedan dess (`409 draft_changed`).
   *Varför:* ett inlägg ändras aldrig (`SPEC-tradar.md` §8.4), och trycket ska godkänna exakt det
   som står i kortet (FV §5.4). Utan revisionen kunde människan utfärda en faktura som agenten
   eller en gammal sida ändrat efter att kortet ritades.
   *Alternativet* är flöde 1:s väg, där ett nytt utkast ersätter det gamla (`replaces_draft_id`).
   Det lämnar ett förkastat utkast per ändring och ett nytt `draft_id` varje gång.
2. **Verktygen som skriver hör till Fakturerings tråd** (§5.3). `foresla_faktura` och
   `andra_fakturautkast` vägras i andra trådar med `wrong_view`. Kortet, vyns rad och räknaren
   hör ihop i `betala.fakturering`. Ett fakturaförslag i Verifikationers tråd skulle inte synas i
   Fakturerings lista. De två läsverktygen fungerar i alla trådar.
3. **Ett förslag förkastas genom `andra_fakturautkast` med `reject_reason`** (§5.5). Det sker
   bara när användaren ber om det. Utan en väg att förkasta skulle ett oönskat förslag räknas som
   väntande för alltid. Ett femte verktyg vore alternativet, och det ändrar det cachade prefixet
   en gång till.
4. **`/issue` får ingen `Idempotency-Key`** (§7.2). Det unika indexet på
   `invoices.source_draft_id` är nyckeln redan i dag. Ett andra tryck ger `409
   draft_already_issued` med fakturans id, och klienten visar det som klart. En nyckel skulle
   skydda samma sak en gång till och kräva en ny tabellrad per tryck.
5. **Servern kontrollerar vid förslaget allt som utfärdandet kommer att kontrollera** (§5.3). Det
   gäller numret, adressen, leveransen, `company_info` och perioden. Ett kort med `Utfärda` ska
   gå att utfärda när det visas. Utfärdandet kontrollerar om, eftersom perioden kan låsas och
   numret tas emellan (FV: *"Kontrollera vid bekräftelse, inte vid visning"*).
6. **Servern kvitterar, utan en LLM-tur** (§8), som FV §12.3. Kvittot länkar PDF:en och
   verifikationen.
7. **`Utfärda` står kvar efter `period_locked` och `company_info_incomplete`** (§9). Båda löser
   människan utan att utkastet ändras: hon låser upp perioden eller fyller i inställningarna och
   trycker igen. Efter `number_taken` och andra valideringsfel försvinner knappen. Utkastet måste
   då ändras, och ändringen ger ett nytt kort.
8. **`las_kunder` returnerar också artiklarna** (§5.1). Båda är små tabeller, och ett pris ur en
   artikel är det agenten oftast behöver när den läser en kund. Ett eget verktyg för artiklar är
   alternativet.

---

## 2. Flödet, steg för steg

| Steg | Designen (flöde 3) | Bärs av | Ny här? |
|---|---|---|---|
| 1 Beställningen | Användaren skriver en mening, agenten säger vad den hittade och vad den antar | `las_kunder`, `las_fakturor`, agentens text med spår | Verktygen (§5.1, §5.2) |
| 2 Fakturaförslaget | `FakturaForslag` med rader, moms och förfallodag | `foresla_faktura` → utkast + `draft`-inlägg `kind: "invoice"` | **Ja** (§5.3, §6) |
| 2b Ändra raderna | Rättelse i tråden, inget tappas | `Ändra` fokuserar chatten → `andra_fakturautkast` → nytt kort | **Ja** (§5.4) |
| 3 Utfärdar | Knappen borta, grå rad i vyn | `Utfärda` → `POST /invoice-drafts/{id}/issue` med revision | Knappen, raden (§7, §10) |
| 4 Utfärdad och bokförd | Kvitto med faktura och verifikation, grön rad | `receipt` + `view.changed`, efter commit | **Ja** (§8) |
| — Fel | `FelKort` i tråden | `error`-inlägg | **Ja** (§9) |

Avvikelser från panelen, alla medvetna:

- **`Skicka fakturan` blir `Utfärda`, och notisen säger att PDF:en skickas av användaren**
  (F0 beslut 2). Panelens steg 3, *"Skickar"*, och dess kanter om e-fakturaadress och om att
  *"bokföringen kan lyckas medan sändningen fallerar"* utgår. Utfärdandet är ett steg som antingen
  blir helt gjort eller inte alls (F0 §3.2).
- **Numret visas i förslaget som föreslaget**, i rubriken. Panelens *"Fakturanumret reserveras
  men används inte förrän den skickas"* blir F0 beslut 4: numret reserveras inte, och servern
  kräver bara att det är unikt när fakturan utfärdas. Ett förkastat utkast lämnar ingen lucka,
  eftersom inget nummer har tagits.
- **Avtal och tidrapporter finns inte i Bok** (F0, utanför scope). Agentens spår i steg 1
  (`avtal 2026-03-02`, `24 h i juni`) blir det agenten fått i tråden och läst i tidigare fakturor.
  Att timmar inte faktureras två gånger kontrollerar agenten, och servern hjälper till med
  `possible_duplicates` (§5.3).
- **Bevakning av förfallodagen och påminnelser** hör till F2–F4. Kvittot säger förfallodagen men
  lovar ingen påminnelse.
- **Leverantörsfakturor att betala** (panelens andra sektion) finns inte i Bok och byggs inte.

---

## 3. Tech stack och kommandon

Oförändrat: FastAPI, SQLite, pydantic, Next.js, TanStack Query. **Inga nya beroenden.**

```bash
pytest tests/test_fakturering_f1.py -v
pytest tests/ -v
black . && isort . && flake8
cd frontend-v3 && npm test && npm run lint && npx tsc --noEmit
cd frontend-v3 && NEXT_PUBLIC_SKAL=1 npm run build
```

Nya och ändrade filer, i huvudsak:

```
db/migrations/039_invoice_proposals.sql      # §4
repositories/invoice_proposal_repo.py        # all SQL för thread_invoice_drafts
repositories/invoice_draft_repo.py           # revision räknas upp i update()
services/invoice_proposal.py                 # föreslå, ändra, förkasta, kvittera, fel (§5–§9)
services/invoice_issue.py                    # check() utan skrivning; expected_revision (§5.3, §7)
services/agent_tools.py                      # fyra verktyg sist i _TOOL_SPECS
services/draft_service.py                    # list_drafts tar med fakturaförslag (§10.1)
services/decision_service.py                 # count_waiting räknar dem (§10.3)
services/overview.py                         # betala får open_decisions (§10.3)
api/routes/invoice_drafts.py                 # /issue: expected_revision, draft_changed, krokarna
api/routes/drafts.py                         # kind och fakturafälten i svaret
docs/to_agent/02_bokforingsprocess.md        # verktygen (runtime-innehåll!)
frontend-v3/lib/chattyta/typer.ts, parse.ts  # draft kind "invoice", receipt med invoice_id/pdf_url
frontend-v3/components/chattyta/FakturaForslag.tsx
frontend-v3/hooks/useUtfardaFaktura.ts
frontend-v3/lib/skal/betala.ts, vyer.ts      # skrivvyn (§10)
tests/test_fakturering_f1.py
```

---

## 4. Datamodell (migration 039)

### 4.1 Revision på utkastet

```sql
ALTER TABLE invoice_drafts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
```

`ADD COLUMN` räcker. Ingen CHECK på `invoice_drafts` ändras, så tabellen byggs inte om.
`InvoiceDraftRepository.update` sätter `revision = revision + 1` i samma `UPDATE` som ändringen.
Det gäller varje väg som ändrar ett utkast: verktyget, `PUT /invoice-drafts/{id}` och de gamla
sidorna. `update_status` till `rejected` räknar också upp, så ett förkastat utkast kan inte utfärdas
från ett gammalt kort. `mark_issued` räknar inte upp.

### 4.2 `thread_invoice_drafts`

Kopplingen mellan ett kort i tråden och utkastet i en viss revision. Den motsvarar
`thread_drafts` (FV §6) men är en egen tabell:

- `thread_drafts.voucher_id` är primärnyckel, och ett fakturautkast har flera kort, ett per
  revision.
- Låsningen av perioder, rättelser, spårbarhet och kontoplanskontroller i `DraftService` läser
  `thread_drafts` och ska inte få fakturarader i sina frågor.

```sql
CREATE TABLE IF NOT EXISTS thread_invoice_drafts (
    post_id             TEXT PRIMARY KEY,       -- kortet
    draft_id            TEXT NOT NULL,          -- invoice_drafts.id
    revision            INTEGER NOT NULL,       -- utkastets revision när kortet skrevs
    thread_id           TEXT NOT NULL,
    view_key            TEXT NOT NULL,
    decision_id         TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    superseded_by       TEXT,                   -- nästa korts post_id
    invoice_id          TEXT,
    issued_at           TIMESTAMP,
    receipt_post_id     TEXT,
    last_error_code     TEXT,
    last_error_post_id  TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES thread_posts(id),
    FOREIGN KEY (draft_id) REFERENCES invoice_drafts(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    UNIQUE (draft_id, revision),
    CHECK (status IN ('pending', 'issued', 'superseded', 'rejected')),
    CHECK (status != 'issued' OR (invoice_id IS NOT NULL AND issued_at IS NOT NULL))
);

-- Högst ett väntande kort per utkast.
CREATE UNIQUE INDEX idx_thread_invoice_drafts_pending
    ON thread_invoice_drafts(draft_id) WHERE status = 'pending';
CREATE INDEX idx_thread_invoice_drafts_view_status
    ON thread_invoice_drafts(view_key, status, created_at);
```

Kontrollera mot migration 034 hur `thread_drafts` och `decisions` följer med när en tråd
nollställs, och gör likadant.

### 4.3 Livscykel

```
pending ──Utfärda lyckas──────────────→ issued
   ├──andra_fakturautkast─────────────→ superseded   (nytt kort, revision + 1)
   ├──PUT från en gammal sida─────────→ superseded   (inget nytt kort, §4.4)
   └──andra_fakturautkast reject──────→ rejected     (utkastet rejected)
```

- `pending → issued` sätts i utfärdandets transaktion (§7.3).
- `pending → superseded` sätts i samma transaktion som ändringen. `superseded_by` pekar på nästa
  kort, eller är `NULL` när ändringen kom utanför tråden.
- Ett misslyckat utfärdande ändrar inte status. `last_error_code` sätts (§9).
- `InvoiceProposalRepository` håller övergångarna. Varje ändring är ett
  `UPDATE … WHERE status='pending'`, och ingen träffad rad ger `ThreadDraftTransitionError`, som i
  FV §6.2.

### 4.4 Ändringar utanför tråden

Ett utkast med ett väntande kort kan ändras via `PUT /invoice-drafts/{id}`, till exempel på den
gamla sidan `invoices/drafts/[id]`. Revisionen räknas upp, och kortet sätts `superseded` i samma
transaktion, via `InvoiceProposalService.on_draft_changed(draft_id)`, som `InvoiceDraftService`
anropar. Inget nytt kort skrivs, eftersom ingen agenttur pågår. Det gamla kortet säger
`Utkastet har ändrats utanför tråden`, och agenten får be om ett nytt kort. Samma sak gäller
`POST /invoice-drafts/{id}/reject`, som ger `rejected`.

Ett utkast som utfärdas från en gammal sida medan ett kort väntar får sitt kvitto i tråden
(§8.1), eftersom kroken går på `draft_id` och inte på varifrån trycket kom.

---

## 5. Verktygen

Fyra verktyg läggs sist i `_TOOL_SPECS`, i den här ordningen, efter `koppla_banktransaktion`:

| # | Namn | Skriver |
|---|---|---|
| 18 | `las_kunder` | Nej |
| 19 | `las_fakturor` | Nej |
| 20 | `foresla_faktura` | Utkast, kort och kopplingsrad |
| 21 | `andra_fakturautkast` | Utkastet, nytt kort och kopplingsrad |

De sjutton befintliga flyttas inte. Ordningen är en del av det cachade prefixet (FV §5.7), och
testet för verktygsordningen utökas med de fyra. Inget av verktygen kan utfärda, och ingen
beskrivning får antyda att det kan. Testfall 17 i `agentruntime` körs mot den utökade listan.

Verktygsbeskrivningarna nedan är förslag. Den slutliga texten granskas i PR:en, eftersom den blir
en del av prefixet.

### 5.1 `las_kunder`

> Läs kundregistret och artiklarna. Skrivskyddat -- ändrar ingenting. Ange query för att söka på
> namn eller organisationsnummer, eller customer_id för en kund.

```python
class LasKunderArgs(BaseModel):
    query: Optional[str] = None          # delsträng i namn eller org.nr, skiftlägesokänslig
    customer_id: Optional[str] = None
    include_inactive: bool = False
```

Svar:

```jsonc
{
  "customers": [
    {
      "id": "…", "name": "Ateljé Vind AB", "org_number": "556…", "email": "…",
      "address": "Storgatan 1\n123 45 Staden", "payment_terms_days": 30,
      "contact_person": "Anna Berg", "active": true,
      "last_invoice": { "invoice_number": "1044", "invoice_date": "2026-05-31" }   // eller null
    }
  ],
  "articles": [
    { "id": "…", "article_number": "KONS", "name": "Konsultation", "unit": "h",
      "unit_price": 115000, "vat_code": "MP1", "revenue_account": "3011" }
  ]
}
```

- `last_invoice` läses ur `invoices` på kundens namn, med en fråga för hela sidan och inte en per
  kund. `invoices` har ingen `customer_id`.
- `articles` är de aktiva artiklarna, alltid hela listan. Belopp är i öre, som överallt i
  verktygen.
- Högst 50 kunder. Är de fler står `truncated: true` i svaret.

### 5.2 `las_fakturor`

> Läs kundfakturor och fakturautkast. Skrivskyddat. Utan invoice_id: en lista, nyast först, och
> latest_numbers, numren på de senast utfärdade fakturorna, för att föreslå nästa nummer i serien.
> Med invoice_id: en faktura med rader och leveranser. drafts=true läser utkasten i stället.

```python
class LasFakturorArgs(BaseModel):
    invoice_id: Optional[str] = None
    customer: Optional[str] = None       # delsträng i kundnamnet
    status: Literal["unpaid", "overdue", "paid", "all"] = "all"
    drafts: bool = False                 # utkast (draft/needs_review) i stället för fakturor
    limit: int = Field(20, ge=1, le=100)
```

Svar utan `invoice_id`:

```jsonc
{
  "invoices": [
    { "id", "invoice_number", "customer_name", "invoice_date", "due_date",
      "amount_inc_vat", "remaining_amount", "status", "is_overdue",
      "voucher": "A-120" | null, "issued_in_bok": true, "pdf_url": "…" | null }
  ],
  "latest_numbers": ["2026-14", "2026-13", "2026-12"],
  "total": 37
}
```

- `latest_numbers` är de fem senast skapade fakturornas nummer, oavsett filter. Fakturor
  utfärdade i Bok sorteras på `issued_at`, äldre på `created_at`. Det är underlaget för F0 §8:s
  regel om att agenten föreslår nästa nummer i samma serie. Servern räknar inte fram något nummer.
- `status`: `unpaid` är `sent`/`partially_paid`/`overdue`, samma mängd som vyns `Obetalda`.
- Med `invoice_id` är svaret en faktura med `rows[]` (beskrivning, antal, enhet, á-pris, moms,
  leverans som text), `customer_address`, `customer_reference` och betalningarna. Det är vad
  agenten behöver för att se om samma timmar redan fakturerats.
- Med `drafts=true` är svaret `drafts[]`: `id`, `invoice_number`, `customer_name`,
  `invoice_date`, `amount_inc_vat`, `status`, `revision` och `pending_post_id` (kortet som väntar,
  eller `null`).

### 5.3 `foresla_faktura`

> Lägg fram en kundfaktura som ett förslag för användaren att utfärda: skapar ett fakturautkast
> och ett kort i Fakturerings tråd. Utfärdar aldrig -- användaren utfärdar med ett tryck, och först
> då bokförs fakturan och PDF:en skapas. Föreslå numret som nästa i serien (las_fakturor,
> latest_numbers). Ändra ett väntande förslag med andra_fakturautkast, inte med ett nytt.

```python
class FakturaRad(BaseModel):
    article_id: Optional[str] = None
    description: Optional[str] = None     # krävs utan article_id
    quantity: Decimal = Field(..., gt=0)  # 7.5 → quantity_centi 750
    unit: Optional[str] = None            # "h", "st"; ur artikeln annars
    unit_price: Optional[int] = None      # öre ex moms; ur artikeln annars
    vat_code: Optional[Literal["MP1", "MP2", "MP3", "MF"]] = None
    revenue_account: Optional[str] = None
    article_number: Optional[str] = None
    delivery_from: Optional[date] = None
    delivery_to: Optional[date] = None
    delivery_month: Optional[str] = None  # YYYY-MM

class ForeslaFakturaArgs(BaseModel):
    invoice_number: str
    invoice_date: date
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None       # krävs utan customer_id
    customer_org_number: Optional[str] = None
    customer_address: Optional[str] = None    # krävs om kunden saknar adress
    customer_email: Optional[str] = None
    reference: Optional[str] = None           # Er referens
    due_date: Optional[date] = None           # ur kundens villkor annars
    delivery_from: Optional[date] = None      # gäller rader utan egen leverans
    delivery_to: Optional[date] = None
    delivery_month: Optional[str] = None
    rows: list[FakturaRad] = Field(..., min_length=1)
    footnote: Optional[str] = None
    decision_id: Optional[str] = None
```

Fälten och förvalen är desamma som i `POST /invoice-drafts`. Utkastet skapas med
`InvoiceDraftService.create_draft(..., status="needs_review", created_by="agent", _commit=False)`,
så normaliseringen (kunden, adressen, villkoren, artiklarna, momsen) finns på ett ställe.

**Kontrollerna, före något skrivs:**

| Kontroll | Fel till modellen |
|---|---|
| Anropat utanför en trådtur | `draft_requires_thread` |
| Tråden är inte `betala.fakturering` (beslut 2) | `wrong_view` |
| Utkastets egna kontroller i `create_draft` | deras koder (`missing_customer`, `invalid_vat_code`, …) |
| `InvoiceIssueService.check(draft)`: numret saknas, är ett datum, eller är redan taget | `invoice_number_missing` / `number_is_date` / `number_taken` med fakturans id |
| Samma: adress, leverans, `company_info`, perioden | `customer_address_missing` / `delivery_date_missing` / `company_info_incomplete {missing}` / `period_locked` / `period_not_found` |
| `decision_id` finns inte, hör till en annan tråd, är öppet eller ersatt | som FV §5.3 |

`InvoiceIssueService.check` är utfärdandets steg 1–2 (F0 §5) utan skrivning: samma metoder som
`issue` redan kör före transaktionen (`_check_draft`, `_company`, `_open_period`,
`_refuse_taken_number`), samlade så att båda vägarna kör exakt samma kontroller. Den körs på
utkastet inuti förslagets transaktion. Ett fel rullar tillbaka utkastet, och ingenting är skrivet.

Ett väntande förslag i en annan tråd eller ett annat utkast med samma nummer stoppar inte ett nytt
förslag. Två utkast får föreslå samma nummer (F0 §4.1), och det som utfärdas sist får
`number_taken`. Agenten ser andra utkast med `las_fakturor(drafts=true)`.

**Skrivningen**, i en transaktion: utkastet och raderna, `draft`-inlägget (§6.1) och raden i
`thread_invoice_drafts` med `revision=1`. Därefter audit, som `create_draft` redan gör.

**`possible_duplicates`.** Servern letar efter utfärdade fakturor till samma kund, på namnet,
där en rad har samma artikelnummer eller samma beskrivning och en leverans som överlappar
förslagets rad. Träffarna står i verktygets svar och stoppar ingenting. Agentinstruktionen säger
att agenten då frågar användaren med `be_om_beslut` innan fakturan utfärdas. Designens kant
*"Timmar som redan fakturerats får inte komma med igen. Kontrollen hör till agenten"* bärs på det
sättet: servern hittar, agenten frågar och människan avgör.

**Idempotens.** Samma nyckel som FV §5.5, `thread:{thread_id}:{post_id}:{n}` ur
`tool_context["proposals"]`, reserverad under `TOOL foresla_faktura`. En omkörd tur spelar upp
samma utkast i stället för att skapa ett andra. `ProposalSequence` delas med
`foresla_verifikation`, så `n` räknar alla förslag i turen.

**Svar:** `draft_id`, `post_id`, `revision`, `invoice_number`, `invoice_date`, `due_date`,
`amount_ex_vat`, `vat_amount`, `amount_inc_vat`, `meta`, `consequence`, `possible_duplicates[]`
och `idempotent_replay` vid en uppspelning.

Verktyget är inte terminalt. Turen slutar med agentens text, som i panelens steg 2: *"Så här blir
fakturan."*

### 5.4 `andra_fakturautkast`

> Ändra ett fakturautkast som inte är utfärdat: ange draft_id och bara de fält som ska ändras;
> rows ersätter alla rader. Skriver ett nytt kort i tråden, och det gamla står som ändrat.
> reject_reason förkastar utkastet -- bara när användaren ber om det. Kan aldrig ändra en utfärdad
> faktura; en sådan rättas med en kreditfaktura.

```python
class AndraFakturautkastArgs(BaseModel):
    draft_id: str
    # Samma fält som ForeslaFakturaArgs, alla valfria; utelämnat = oförändrat.
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    ...
    rows: Optional[list[FakturaRad]] = Field(None, min_length=1)
    footnote: Optional[str] = None
    decision_id: Optional[str] = None
    reject_reason: Optional[str] = None   # förkastar; inget annat fält får anges då
```

Designens kant *"Ändra raderna får inte tappa det agenten redan hämtat"* är skälet till att
verktyget tar bara det som ändras. Servern slår ihop ändringen med utkastet som det är, och
modellen behöver inte skicka tillbaka adressen för att ändra ett antal. `rows` ersätter alla rader,
eftersom en rad inte har något stabilt id för modellen att peka på.

Ett utelämnat fält som går att nollställa (`reference`, `delivery_*`) nollställs med en tom sträng.
`null` betyder oförändrat. Detta står i fältens beskrivning i schemat.

**Kontrollerna:** samma som §5.3, på det sammanslagna utkastet, plus:

| Kontroll | Fel |
|---|---|
| Utkastet finns inte | `draft_not_found` |
| Utkastet är utfärdat | `draft_already_issued` med `invoice_id` |
| Utkastet är förkastat | `draft_rejected` |
| `reject_reason` tillsammans med ett annat fält | `reject_is_exclusive` |
| Ingen ändring alls (sammanslaget lika med nuvarande) | `nothing_changed` |

Utkastet behöver inte ha något kort i tråden. Ett utkast från en gammal sida kan ändras, och då
blir det kortet dess första.

**Skrivningen**, i en transaktion: `InvoiceDraftService.update_draft(..., _commit=False)` (som
räknar upp revisionen, §4.1), den väntande raden `superseded` med `superseded_by`, ett nytt
`draft`-inlägg och en ny rad med den nya revisionen. Med `reject_reason`: `reject(...)`, raden
`rejected` och inget nytt kort. Skälet står i auditloggen.

**Idempotens:** som §5.3, under `TOOL andra_fakturautkast`. En uppspelning räknar inte upp
revisionen en gång till.

**Svar:** som §5.3, plus `superseded_post_id`, eller `{draft_id, status: "rejected"}`.

### 5.5 Vad verktygen inte gör

- De utfärdar inte, bokför inte och skapar ingen PDF.
- De skapar ingen kund och ingen artikel. En ny kunds uppgifter står på utkastet (`customer_name`,
  `customer_address`, …) och följer med till fakturan. Kundregistret ändras bara i de gamla
  sidorna tills vidare (§12, fråga 1).
- De rör ingen utfärdad faktura. Kreditfakturan är F4.

---

## 6. Kortet

### 6.1 `draft`-kroppen, `kind: "invoice"`

`SPEC-chattyta.md` §4.3 reserverade `kind: "invoice"` och sa att det renderas som
`okant_kontrakt`. F1 spikar kroppen:

```jsonc
{
  "draft_id": "<invoice_drafts.id>",
  "kind": "invoice",
  "revision": 2,
  "title": "Faktura 1045 · Ateljé Vind AB",
  "meta": "förslag · fakturadatum 2026-06-12",
  "recipient": {
    "name": "Ateljé Vind AB",
    "address": "Storgatan 1\n123 45 Staden",
    "reference": "Anna Berg"                       // Er referens, eller null
  },
  "rows": [
    {
      "text": "Konsultation juni",
      "article_number": "KONS",                    // eller null
      "delivery": "juni 2026",                     // samma text som PDF:ens KOMMENTAR
      "quantity_centi": 2400,
      "unit": "h",
      "unit_price_ore": 115000,
      "amount_ore": 2760000                        // ex moms
    }
  ],
  "totals": [
    { "key": "net",   "text": "Netto",                        "amount_ore": 2760000 },
    { "key": "vat",   "text": "Moms 25 %",                    "amount_ore":  690000 },
    { "key": "total", "text": "Att betala senast 2026-07-12", "amount_ore": 3450000 }
  ],
  "terms": "30 dagar",
  "footnote": "Timmarna ur ditt meddelande · villkor som faktura 1044",
  "consequence": "Utfärdas och bokförs i ett steg · 1510 mot 3011 och 2610 · period juni 2026 öppen\nPDF:en laddar du ner och skickar själv",
  "decision_id": null
}
```

Allt utom `footnote` är serverns, byggt ur utkastet efter normaliseringen:

| Fält | Källa |
|---|---|
| `title` | `Faktura {nummer} · {kundens namn}`. Numret är det föreslagna |
| `meta` | `förslag · fakturadatum {datum}`. Efter en ändring: `förslag, ändrat · fakturadatum {datum}` |
| `recipient` | Utkastets kund, adress och Er referens. Adressen visas med sina radbrytningar |
| `rows[].delivery` | Radens leverans, annars utkastets, formaterad med samma funktion som PDF:en (`format_delivery`, som text utan HTML) |
| `rows[]` belopp | Samma uträkning som utfärdandet (`amount_ex_vat_from_centi`) |
| `totals` | Netto, en rad per momssats som förekommer (`Moms 25 %`, `Moms 12 %`, `Moms 6 %`), `Momsfritt` när det finns momsfri försäljning, och `Att betala senast {förfallodag}` |
| `terms` | `{dagar} dagar`, ur fakturadatum och förfallodag, som på PDF:en |
| `consequence` | Rad 1: kontona fakturan bokförs på och periodens läge. Kontona är 1510, radernas intäktskonton och momskontona per momskod. De tas ur samma gruppering som `create_booking_for_invoice`, som bryts ut till en funktion som båda anropar, så att kortet och verifikationen inte kan skilja sig. Rad 2 är alltid densamma |
| `footnote` | Agentens, ordagrant |

Det som står i kortet är det som blir fakturan. Trycket på `Utfärda` godkänner exakt den
revisionen (§7.1). Agentens resonemang blir aldrig ett fält på fakturan. `description` på
utkastet sätts inte av verktygen, eftersom det inte står på PDF:en och inte visas i kortet.

### 6.2 `FakturaForslag`

Designens namn (`komponenter.md`: *"`FakturaForslag` (Rad / Antal / Belopp)"*). Samma skal som
`VerifikationsForslag`: max-bredd 560, radius 12, rubrikrad med titel och meta, fot 13/1.55
`#78716c`, knapprad med konsekvensnotis i mono 12 `#52525b`, som inte är metatext.

- **Mottagaren** står under rubrikraden i 13/1.5: namnet, adressen och `Er referens: {namn}`.
- **Kolumnerna** är `Rad`, `Antal` och `Belopp`, mono 10 versalt, de två högra 92 px
  högerställda.
- **En rad** (`FakturaRad`): texten i 14, under den i mono 12 metagrå leveransen och
  `{á-pris} kr/{enhet}`. `Antal` är `24 h`, och decimaler skrivs med komma (`7,5 h`). `Belopp` är
  netto för raden. Klienten formaterar talen och räknar ingenting.
- **Summeringen** står under raderna, i `totals`-ordning, med `total`-raden i 500.
- **Knappraden:** `Utfärda` primär, `Ändra` sekundär (fokuserar `ChattFalt`, som `Ändra` i
  `PostaKnappar`, och skickar ingenting), och konsekvensnotisen. Ingen bekräftelsedialog.
  Konsekvensen står i kortet (`README.md` regel 4).

### 6.3 Kortets lägen

Läget kommer ur raden i `GET /drafts` (§10.1), uppslagen på kortets `post_id`, inte på
`draft_id`, eftersom ett utkast har flera kort.

| Status | Kortet |
|---|---|
| `pending` | `Utfärda`, `Ändra`, notisen |
| `pending` + `last_error_code` | Felraden (§9). `Utfärda` bara vid `period_locked` och `company_info_incomplete` (beslut 7) |
| `issued` | `Utfärdad · {nummer} · {serie}-{nr}` och knappen `PDF`, inga andra knappar |
| `superseded` med `superseded_by` | `Ändrat · se förslaget nedan`, inga knappar |
| `superseded` utan `superseded_by` | `Utkastet har ändrats utanför tråden`, inga knappar |
| `rejected` | `Förkastat`, inga knappar |

Notisen står kvar i alla lägen. Innan `GET /drafts` har svarat står kortet som `pending`.

---

## 7. Utfärda

### 7.1 Klienten

`useUtfardaFaktura(draftId, revision)` anropar

```
POST /api/v1/invoice-drafts/{draft_id}/issue
{ "expected_revision": 2 }
```

med JWT, som de gamla sidorna. Knappen tas bort vid trycket (panelen: *"en dubbelskickad faktura
är ett kundproblem"*). Dröjer svaret mer än 3 s står det `Utfärdar fortfarande…`, som FV §11.2.

| Svar | Kortet |
|---|---|
| `201` | `Utfärdad · …` och `PDF` |
| `409 draft_already_issued` | Samma som `201`. Fakturans id står i svaret, och resten hämtas med `GET /drafts` |
| `409 draft_changed` | `Ändrat …` enligt §6.3, efter att `GET /drafts` hämtats om |
| `409 number_taken`, `period_locked`; `422` | Felraden, och felinlägget kommer i tråden (§9) |
| Nätverksfel, `5xx` | Inline med `Försök igen`, samma anrop. Ett andra lyckat tryck är omöjligt tack vare `source_draft_id` |

### 7.2 Servern: ändringar i `/issue`

- Kroppen är valfri. De gamla sidorna skickar ingen och beter sig som i dag.
- `expected_revision` jämförs i utfärdandets transaktion, efter att utkastet lästs om. Olika ger
  `409 draft_changed {revision: <nuvarande>}`, och ingenting skrivs.
- Ingen `Idempotency-Key` (beslut 4). `source_draft_id UNIQUE` gör redan att ett utkast ger högst
  en faktura, och `409 draft_already_issued` bär fakturans id.
- `InvoiceIssueService.issue` delas upp så att kontrollerna blir `check(draft)` (§5.3). Beteendet
  är oförändrat. F0:s testfall 1–15 ska gå igenom utan ändring.

### 7.3 I utfärdandets transaktion

Om utkastet har en väntande rad i `thread_invoice_drafts`:
`InvoiceProposalService.on_issuing(draft_id, invoice_id)` sätter raden `issued` med `invoice_id`
och `issued_at`. Det sker i samma transaktion som fakturan, eftersom ett kort som säger väntande om
en utfärdad faktura skulle erbjuda ett andra tryck. Det trycket vägras av indexet, men kortet ska
inte ljuga.

Ett utkast utan väntande rad berörs inte.

### 7.4 Efter commit

`InvoiceProposalService.on_issued(draft_id, actor)` skriver kvittot (§8) och publicerar
`message.completed` för det och `view.changed` på trådens `view_key` med
`{invoice_id, draft_id, voucher_id, kind: "invoice_issued"}`.

Kvittot skrivs efter commit, av samma skäl som FV §8.1: ett fel i trådlagret får inte kunna rulla
tillbaka en bokförd faktura. Steget är idempotent och återupptagbart. Ett `409
draft_already_issued` kör det om när `receipt_post_id` är `NULL`, så klientens `Försök igen`
lagar ett kvitto som saknas.

---

## 8. Kvittot

### 8.1 `receipt`-kroppen

```jsonc
{
  "title": "Faktura 1045 utfärdad · A-120",
  "labels": ["var", "blir"],
  "rows": [
    { "key": "1510", "text": "Kundfordringar",           "left_ore": 14850000, "right_ore": 18300000 },
    { "key": "3011", "text": "Försäljning tjänster 25 %", "left_ore": 41200000, "right_ore": 43960000 },
    { "key": "2610", "text": "Utgående moms 25 %",        "left_ore":  2100000, "right_ore":  2790000 }
  ],
  "voucher_id": "<vouchers.id>",
  "invoice_id": "<invoices.id>",
  "pdf_url": "/api/v1/invoices/<id>/pdf"
}
```

- `rows` byggs som ett verifikationskvitto (FV §8.2), med
  `VoucherRepository.account_balances_around(voucher_id)`. Kvittot säger vad utfärdandet gjorde med
  böckerna: fordran och intäkten, före och efter, båda talen.
- `invoice_id` och `pdf_url` är nya, valfria fält i `receipt`. De utvidgar `SPEC-chattyta.md`
  §4.3, och kvitton utan dem renderas som i dag.
- `actor` är människan som utfärdade.
- `traces[]`:
  - `faktura utfärdad · {nummer}` (`tool: "utfarda_faktura"`, `invoice_id`)
  - `verifikation postad · {serie}-{nr}` (`tool: "posta_utkast"`, `voucher_id`)
  - `pdf sparad` (`tool: "pdf"`)
  - `förfaller {datum}` (`tool: "forfallodag"`)
  - `{n} kvar` (`tool: "vantar"`) sist, räknat med `count_waiting("betala.fakturering")` efter
    commit.

Panelens kvittorad *"1045 · Ateljé Vind · e-faktura levererad"* utgår, eftersom Bok inte levererar
något. Panelens *"Leverans och bokföring kvitteras som två rader"* blir fakturan och
verifikationen, som två chip.

### 8.2 I klienten

`JamforelseRader` som i dag, och när `pdf_url` finns en sekundärknapp `Öppna PDF` under raderna.
Den hämtar filen med bearer-auth via `apiClient` som en blob, som `invoices/[id]` redan gör, och
öppnar den. En vanlig länk fungerar inte, eftersom routen kräver auth.

---

## 9. När utfärdandet misslyckas

`InvoiceProposalService.on_issue_failed(draft_id, error, actor)` körs efter rollback, i en egen
transaktion. Det skriver `last_error_code` och ett `error`-inlägg. Precis som i FV §9 skrivs ett
inlägg per kort och felkod, inte ett per tryck. Ett fel där loggas och ändrar inte svaret.

| Fel | `cause` | `consequence` fortsätter efter *"Ingenting har bokförts och ingen faktura är utfärdad."* | `Utfärda` kvar |
|---|---|---|---|
| `409 number_taken` | `Nummer {nr} användes av faktura {id-nummer} medan förslaget låg.` | `Be agenten föreslå nästa nummer.` | Nej |
| `409 period_locked` | `Perioden {period} låstes {tid} av {vem} medan förslaget låg.` | `Lås upp perioden och tryck igen, eller be agenten ändra fakturadatumet.` | Ja |
| `422 company_info_incomplete` | `Företagsuppgifter saknas: {fält på svenska}.` | `Fyll i dem under Inställningar och tryck igen.` | Ja |
| Övriga `422` | `Fakturan klarade inte kontrollerna vid utfärdandet ({meddelande}).` | `Förslaget ligger kvar men kan inte utfärdas som det står.` | Nej |
| `409 draft_changed`, `draft_already_issued` | Inget inlägg. Kortets läge säger det (§6.3, §7.1) | | |
| Nätverksfel, `5xx` | Inget. Servern vet inte att det hände | | Inline `Försök igen` |

`retry_draft_id` är `null` i alla. Att `Utfärda` står kvar är kortets läge, inte felkortets.
Fälten i `company_info_incomplete` får svenska namn (`seat` → `säte`, `vat_number` →
`momsregistreringsnummer`, …), och tabellen ligger i tjänsten.

Perioden kan låsas medan ett förslag väntar. Till skillnad från verifikationsutkast (FV §9, F16)
markerar låsningen inte fakturaförslagen, eftersom ett fakturautkast inte ligger i någon period
förrän det utfärdas. Kortets konsekvensrad säger fortfarande `öppen`, och felet kommer först vid
trycket.

---

## 10. Vyn Fakturering

### 10.1 `GET /api/v1/drafts`

Svaret får fakturaförslagen i samma lista, äldst först:

```jsonc
{ "drafts": [
  { "kind": "voucher", … oförändrat … },
  { "kind": "invoice", "post_id", "draft_id", "revision", "decision_id",
    "status": "pending" | "issued" | "superseded" | "rejected",
    "superseded_by", "last_error_code", "created_at",
    "invoice": { "invoice_id", "invoice_number", "voucher_id", "voucher": "A-120",
                 "pdf_url" } | null }
], "total": n }
```

- Verifikationsraderna får `kind: "voucher"` och ändras inte i övrigt.
- `status`-parametern tar också `issued` och `rejected`. `posted` ger bara verifikationer och
  `issued` bara fakturor.
- `invoice` fylls bara när `status='issued'`, med en fråga för hela sidan.

`useForslag` slår upp verifikationer på `draft_id` som i dag och fakturor på `post_id`.

### 10.2 Sektionerna

`lasvy: false` för `betala.fakturering`. Löner förblir läsvy.

| Sektion | Rader | Källa |
|---|---|---|
| **Väntar på dig** | Väntande fakturaförslag och öppna beslut i vyn | `GET /drafts?view_key=betala.fakturering`, `GET /decisions?…&status=open` |
| **Obetalda** | Som i dag | `GET /invoices` |
| **Utkast** | Fakturautkast som inte har ett väntande kort, och gamla fakturor med `status='draft'` | `GET /invoice-drafts`, `GET /invoices` |
| **Senast betalda** | Som i dag | `GET /invoices` |

| Läge | Titel · meta | Höger | Variant |
|---|---|---|---|
| Förslag väntar | kund · `förslag {nr} · fakturadatum {datum}` | totalt | `vantar` |
| Förslag med fel | kund · `utfärdandet misslyckades · ligger kvar` | totalt | `fel` |
| Utfärdas just nu | kund · `{nr} · utfärdas…`, grå | totalt | `pagaende` |
| Nyss utfärdad | kund · `{nr} · utfärdad HH:MM · förfaller {datum}` | totalt | `ny` i 6 s, i `Obetalda` |
| Utkast utanför tråden | kund · `utkast {nr eller "utan nummer"}` | totalt | ingen |

Den optimistiska raden fungerar som FV §11.2: den bär `draft_id`, ligger i TanStack-cachen under
`["utfardanden"]`, byts mot serverns faktura vid `201` eller `draft_already_issued`, och tas bort
vid fel. Förslagsraden går då tillbaka till `Väntar på dig`.

Vyns status: `{n} väntar på dig` när något väntar, annars som i dag (förfallna, sedan obetalda).
Foten: *"Beskriv vad som ska faktureras, så lägger agenten fram fakturan. Du utfärdar den, och
PDF:en skickar du själv."* Chattfältets platshållare är *"Beskriv vad som ska faktureras"*.

`view.changed` med `kind: "invoice_issued"` invaliderar `["drafts", vy]`, fakturorna, utkasten
och översikten.

### 10.3 Räknaren

`DecisionService.count_waiting` räknar väntande rader i `thread_invoice_drafts` med samma regel
som `thread_drafts` (FV §11.3): ett förslag på ett öppet beslut räknas via beslutet, och
förslagen räknas en gång per `decision_id` och annars ett vardera. Eftersom det finns högst ett
väntande kort per utkast räknas ett utkast högst en gång.

`GET /overview` ger `betala` ett `open_decisions`, räknat med `count_waiting` för sidans två vyer.
`bocker.open_decisions` räknas som i dag utan `view_key`, så headerns tal tar med
fakturaförslagen. Sidväljarens prick för Fakturering och löner tänds av `open_decisions` eller
`overdue_invoices`.

---

## 11. Agentinstruktionen

`docs/to_agent/02_bokforingsprocess.md`, avsnittet *Fakturautkast*, är runtime-innehåll och
testas av `tests/test_agent_entrypoint.py`. Det får ett stycke om tråden:

- I Fakturerings tråd används verktygen. HTTP-vägen (`/invoice-drafts`) gäller en agent utanför
  Bok och står kvar.
- Börja med `las_kunder` och `las_fakturor`. Säg vad du hittade och vad du antar innan du lägger
  fram fakturan: kund, adress, villkor, antal, pris och leverans. Saknas något, fråga om just
  det, en fråga i taget.
- Flera möjliga kunder, perioder eller priser: `be_om_beslut` med alternativen. Välj inte själv.
- Numret: nästa i serien ur `latest_numbers`. Vid `number_taken`, föreslå nästa. Försök inte igen.
- `possible_duplicates` i svaret: fråga med `be_om_beslut` om raden redan är fakturerad.
- En ändring görs med `andra_fakturautkast`, inte med ett nytt förslag. Förkasta bara när
  användaren ber om det.
- Du utfärdar aldrig. Säg inte att fakturan är skickad eller bokförd innan kvittot står i tråden.
- En utfärdad faktura ändras inte. Rättelse är en kreditfaktura, och den finns inte ännu (F4).
  Säg det.

---

## 12. Öppna frågor

Ingen av dem blockerar bygget.

1. **Nya kunder.** Verktygen skapar ingen kund, så en ny kunds uppgifter står bara på fakturan.
   Frågan är om utfärdandet ska lägga till kunden i registret, eller om ett eget verktyg behövs.
   Det kan vänta tills det blir ett problem i praktiken.
2. **Årsskiftet.** Ett förslag i förra årets tråd som utfärdas efter årsskiftet. Kvittot skrivs i
   förslagets tråd, som FV §13.1.
3. **Headerns tal räknas utan `view_key`** och tar därför med fakturaförslagen även på Böcker. Det
   är konsekvent med FV §11.3, men kanske inte önskvärt när det finns fler sidor som väntar.

---

## 13. Tester (skrivs först)

`tests/test_fakturering_f1.py` och `vitest`. Verktygen körs via `execute_tool` med en falsk tråd i
`tool_context`, som i `tests/test_beslut.py`. Den riktiga LLM:en används aldrig.

### 13.1 Verktygen

| # | Fall | Förväntat |
|---|---|---|
| 1 | Verktygslistan | De fyra sist, i ordningen §5; de sjutton första oförändrade byte för byte; ingen beskrivning nämner utfärda som något verktyget gör |
| 2 | `las_kunder` med `query` | Träffar på namn och org.nr; `last_invoice` utan N+1; alla aktiva artiklar |
| 3 | `las_fakturor` | `latest_numbers` i utfärdandeordning, äldre fakturor efter `created_at`; `status=unpaid`; `invoice_id` med rader och leverans |
| 4 | `las_fakturor(drafts=true)` | `revision` och `pending_post_id` |
| 5 | `foresla_faktura` i Fakturerings tråd | Ett utkast `needs_review`, `revision=1`, ett `draft`-inlägg `kind=invoice`, en `pending`-rad; kroppen passerar klientens `parseInlagg`-fixtur |
| 6 | Kroppen | Belopp, momsrader per sats, `Momsfritt`, `terms`, `delivery` som PDF:ens text, `consequence` med konton och period |
| 7 | Utan tråd / i Verifikationers tråd | `draft_requires_thread` / `wrong_view`, inget skrivet |
| 8 | Numret taget, ett datum, saknas | `number_taken` med id / `number_is_date` / `invoice_number_missing`, inget skrivet |
| 9 | Utan adress, leverans; `company_info` ofullständig; låst period | Respektive kod, inget skrivet |
| 10 | Samma tur två gånger | Samma utkast, inget andra |
| 11 | Ett förslag och en verifikation i samma tur | Två nycklar i samma `ProposalSequence`, ingen krock |
| 12 | Överlappande leverans mot en utfärdad faktura | `possible_duplicates` med fakturan; förslaget skapat ändå |
| 13 | `andra_fakturautkast` med nytt antal | Revision 2; adressen oförändrad; gamla raden `superseded` med `superseded_by`; nytt kort |
| 14 | `andra_fakturautkast` på utfärdat / förkastat / okänt | `draft_already_issued` / `draft_rejected` / `draft_not_found` |
| 15 | `reject_reason` | Utkastet `rejected`, raden `rejected`, inget nytt kort; med ett annat fält: `reject_is_exclusive` |
| 16 | Ingen ändring | `nothing_changed`, revisionen oförändrad |
| 17 | Uppspelning av en ändring | Revisionen räknas upp en gång |
| 18 | Utkast från en gammal sida ändras med verktyget | Dess första kort, revision 2 |

### 13.2 Utfärdandet

| # | Fall | Förväntat |
|---|---|---|
| 19 | Utfärda med rätt `expected_revision` | `201`; raden `issued` i samma transaktion; kvitto med 1510/30xx/26xx före och efter, `invoice_id`, `pdf_url`; `view.changed` |
| 20 | Två tryck | En faktura, en verifikation, ett kvitto; det andra `409 draft_already_issued` med samma id |
| 21 | Kvittot kastar efter commit | Fakturan står kvar; nästa tryck (`409`) skriver kvittot |
| 22 | `expected_revision` gammal | `409 draft_changed`, inget skrivet |
| 23 | `PUT /invoice-drafts/{id}` medan ett kort väntar | Revisionen upp; kortet `superseded` utan `superseded_by`; ett tryck på det gamla ger `draft_changed` |
| 24 | Utfärda från en gammal sida utan `expected_revision`, med väntande kort | `201`; kortet `issued`; kvittot i tråden |
| 25 | Numret taget mellan förslag och tryck | `409 number_taken`; ett `error`-inlägg; kortet utan `Utfärda` |
| 26 | Perioden låst mellan förslag och tryck; sedan upplåst | `409 period_locked` med vem/när och ett inlägg; efter upplåsning lyckas samma kort |
| 27 | `company_info` tömd emellan | `422` med svenska fältnamn i inlägget; `Utfärda` kvar |
| 28 | Samma fel tre gånger | Ett inlägg |
| 29 | API-nyckeln mot `/issue` | Fortfarande `403 human_only` |
| 30 | F0:s testfall 1–15 | Gröna utan ändring |

### 13.3 Vyn och räknaren

| # | Fall | Förväntat |
|---|---|---|
| 31 | `GET /drafts?view_key=betala.fakturering` | `kind`, status, `invoice` bara när utfärdad; verifikationsraderna oförändrade utom `kind` |
| 32 | `count_waiting` | Ett förslag på ett öppet beslut räknas en gång; en ändring ger inget extra; `issued`/`superseded`/`rejected` räknas inte; `/overview` betala och headern lika |
| 33 | `parseInlagg` | `kind=invoice` med fixturen blir `DraftInlagg`; utan `revision` eller med en rad utan belopp blir den `okant_kontrakt`; `kind=payroll` fortfarande `okant_kontrakt` |
| 34 | `FakturaForslag` | Sex lägen enligt §6.3; `7,5 h`; inga uträkningar i klienten |
| 35 | `Utfärda` | Skickar kortets revision; knappen borta vid tryck; `Utfärdar fortfarande…` efter 3 s; utfallen i §7.1 |
| 36 | Kvittot | `Öppna PDF` bara med `pdf_url`; hämtar med auth |
| 37 | Vyns sektioner | Förslaget bara i `Väntar på dig`; utkast utan kort i `Utkast`; optimistisk rad `pagaende` → `ny` i `Obetalda`; tillbaka vid fel |
| 38 | Läsvyer | Bara Löner är läsvy |
| 39 | Hela flödet, backend | Meddelande → `las_kunder` → `foresla_faktura` → `andra_fakturautkast` → utfärda → kvitto, med skriptade verktygsanrop |
| 40 | Append-only | Ingen `UPDATE`/`DELETE` på en utfärdad faktura eller postad verifikation i någon väg ovan; 038:s triggrar orörda |

---

## 14. Gränser

**Alltid:**
- Tester före implementation.
- Kort, rad och utkast skrivs i en transaktion. Kvittot skrivs efter commit.
- Samma kontroller vid förslaget och vid utfärdandet, ur samma metod.
- Nya SQL-frågor i `repositories/`, aldrig i en service eller route.
- De fyra verktygen sist i `_TOOL_SPECS`.

**Fråga först:**
- En ändring i `SPEC-chattyta.md` §4.3 utöver `kind: "invoice"`-kroppen och kvittots två fält.
- En ändring i `/issue` utöver `expected_revision` och krokarna.
- Att låta verktygen skapa eller ändra kunder och artiklar.

**Aldrig:**
- Ett verktyg som utfärdar, eller en beskrivning som antyder det.
- Att ändra en utfärdad faktura, eller att röra 038:s triggrar.
- Att utfärda en annan revision än den kortet visar när kortet skickar sin revision.
- Att klienten räknar ett belopp, en moms eller ett nummer.
- Att flytta de sjutton befintliga verktygen.
- Att kvittot skrivs i utfärdandets transaktion.

---

## 15. Framgångskriterier

1. En människa skriver *"Fakturera Ateljé Vind för junikonsultationen"* i Fakturering. Agenten
   läser kunden och de senaste fakturorna, säger vad den antar och lägger fram fakturan med nästa
   nummer.
2. Hon skriver *"det var 26 timmar"*. Ett nytt kort ersätter det gamla, och ingenting annat på
   fakturan ändras.
3. Hon trycker `Utfärda` två gånger och får en faktura, en verifikation, en PDF och ett kvitto.
   Kvittot visar 1510 före och efter och öppnar PDF:en. Raden går från grå till grön i
   `Obetalda`, och räknaren går ner, utan omladdning.
4. Med perioden låst mellan förslag och tryck blir det ett felkort med vem och när. Ingenting
   bokförs. Efter upplåsning lyckas samma kort.
5. Ett kort som ändrats efter att det ritades kan inte utfärdas.
6. `pytest tests/ -v`, `black`, `isort` och `flake8` rena. Inga nya `mypy`-fel i modulens filer.
   `npm test`, `npm run lint`, `npx tsc --noEmit` och `NEXT_PUBLIC_SKAL=1 npm run build` gröna.
