# Granskning – implementationsspec

Status: förslag, inte byggt. Specen beskriver en granskningsfunktion som liknar en revisor.
En separat agent som bara kan läsa går igenom ett räkenskapsår (eller ett kvartal). Den
lämnar anmärkningar som en människa besvarar, och slutar med en granskningsrapport som
styrelsen bekräftar att den har tagit del av.

Läs avsnitt 1 innan du bygger något. Det styr namn, texter och vad funktionen får påstå.

---

## 1. Rättslig ram, och vad den betyder för koden

- **Det här är inte en revision.** Bara en godkänd eller auktoriserad revisor, en människa
  som är oberoende av bolaget, kan göra en lagstadgad revision (ABL 9 kap.). Bok får aldrig
  kalla funktionen "revision", resultatet "revisionsberättelse" eller agenten "revisor" i
  gränssnittet, i PDF:er, i API-namn eller i agentens instruktioner.
- **Grunden är styrelsens kontrollansvar.** Enligt ABL 8 kap. 4 § ska styrelsen se till att
  bokföringen och medelsförvaltningen kontrolleras på ett betryggande sätt. Granskningen är ett
  verktyg för den kontrollen, och det gäller både med och utan revisor.
- **Metoden lånas från god revisionssed (ISA):** väsentlighet, riskbedömning, stickprov och
  bevis. Det är metoden som lånas, inte statusen.
- **Rapporten får inte se ut som ett revisionsdokument.** Varje rapport (UI och PDF) bär en fast
  text: *"Granskningen är styrelsens egen kontroll enligt ABL 8 kap. 4 §. Den är inte en revision
  och ersätter inte en revisor."* Texten ligger i kod, inte i agentens svar, så att modellen inte
  kan ändra den.

Namn som används genomgående:

| Begrepp | Svenska i UI | Kodnamn |
|---|---|---|
| En körning | Granskning | `review` |
| Ett fynd | Anmärkning | `review_finding` |
| Slutresultatet | Granskningsrapport | `review_report` |
| Agentrollen | Granskaren | `reviewer` |

### 1.1 Revisionsplikt (ABL 9 kap. 1 §)

Ett privat aktiebolag måste ha revisor om det **under vart och ett av de två senaste
räkenskapsåren** har överskridit **mer än ett** av följande gränsvärden:

| Gränsvärde | Värde | Källa i Bok |
|---|---|---|
| Medelantal anställda | > 3 | `PayrollService` (anställda med lönebesked i året, viktat per månad) |
| Balansomslutning | > 1,5 mkr | `ArsredovisningService` → `summa_tillgangar` |
| Nettoomsättning | > 3 mkr | konto 30xx–37xx för året |

Utan revisionsplikt får bolaget vara utan revisor bara om **bolagsordningen** tillåter det och
ingen aktieägare med minst en tiondel av aktierna begär revisor. Bok kan inte läsa
bolagsordningen. Därför är `has_auditor` och `articles_allow_no_auditor` uppgifter som en
människa anger (avsnitt 7.4).

**Gränsvärdena ska inte hårdkodas i logiken.** Höjda gränser diskuteras 2026, och ingen ändring
var bekräftad när specen skrevs. Lägg dem i en tabell med giltighetsdatum
(`audit_thresholds`, avsnitt 5). En lagändring blir då en ny rad i en ny migration, och gamla år
bedöms med de gränser som gällde då.

---

## 2. Två lägen

`ReviewService.mode(fiscal_year_id)` räknar ut läget utifrån gränsvärdena och de uppgifter
människan har angett.

| Läge | Villkor | Vad granskningen är | Banderoll |
|---|---|---|---|
| `board_control` | Ingen revisionsplikt, ingen revisor | Styrelsens egen kontroll | "Styrelsens kontroll – inte en revision." |
| `auditor_prep` | Revisor vald (oavsett plikt) | Förberedelse inför revisorn | "Förberedelse inför revision. Revisorn gör den lagstadgade granskningen." |
| `auditor_required` | Revisionsplikt, men ingen revisor angiven | Som `board_control`, plus en varning som blockerar | "Ert bolag ska ha revisor (ABL 9 kap. 1 §)." |

`auditor_required` hindrar inte att granskningen körs, men rapportens sammanfattning börjar
alltid med varningen och kan inte bekräftas utan att den visas.

**Tidig varning:** när bokslutet för ett år visar att mer än ett gränsvärde har överskridits och
året före *inte* gjorde det, skapar servern ett beslutskort `foresla_revisorsval` med texten
"Ni har överskridit två gränsvärden i år. Om det händer igen nästa år ska ni välja revisor."
Alternativen är *Noterat* och *Vi har valt revisor* (som sätter `has_auditor`). Kortet skapas av
servern i bokslutsflödet, inte av någon agent. Det följer mönstret i
`services/fiscal_year_proposal.py` och `services/decision_cards.py`, och det är `human_only`.

---

## 3. Arkitektur

```
            ┌──────────────────────── ReviewService ─────────────────────────┐
  människa ─┤ start → planering → maskinkontroller → bedömning → anmärkningar ├─→ rapport
  (JWT)     └──────┬──────────────────────┬────────────────────┬───────────────┘
                   │                      │                    │
          services/review_checks.py   agent (läsande,     review_findings
          (deterministiska,           egen modell,        (append-only)
           ingen LLM)                 egna verktyg)
```

### 3.1 Principer

1. **Servern räknar, modellen bedömer.** Alla summor, avstämningar och luckor räknas i Python
   (`services/review_checks.py`). Modellen får färdiga resultat och tar aldrig fram egna summor
   som underlag för en anmärkning.
2. **Granskaren kan bara läsa.** Den har en egen verktygslista utan skrivande verktyg (avsnitt
   4.2). Det enda den skriver är anmärkningar, och de skrivs genom ett eget verktyg som bara rör
   granskningens tabeller.
3. **Ett fynd utan bevis går inte att skapa.** `skapa_anmarkning` kräver minst en
   bevisreferens som servern slår upp och verifierar (avsnitt 4.3). Det skyddar mot påhittade
   fynd.
4. **Ett annat perspektiv än bokföringsagentens.** Granskaren kör en annan modell
   (`LLM_REVIEW_MODEL`). Den läser inte bokföringsagentens trådar, resonemang eller företagets
   instruktioner (`uppdatera_instruktioner`) som sanning. Den granskar mot lag och god sed.
5. **Inget ändras i böckerna.** En rättelse går genom det vanliga flödet (en B-verifikation via
   bokföringsagentens tråd eller manuellt). Granskningen kopplar sedan anmärkningen till den nya
   verifikationen.

### 3.2 Moduler

| Fil | Ansvar |
|---|---|
| `services/review.py` | `ReviewService`: läge, start, steg, status, rapport. Orkestrerar. |
| `services/review_checks.py` | Deterministiska kontroller (avsnitt 6.2). Ren Python, ingen LLM. |
| `services/review_sampling.py` | Stickprovsurval (avsnitt 6.3). Deterministiskt med frö. |
| `services/review_tools.py` | Granskarens verktyg: specar och handlers, samma form som `_TOOL_SPECS` i `services/agent_tools.py`. |
| `services/review_report.py` | Sammanställer rapporten och PDF:en, och räknar kontrollsumman. |
| `repositories/review_repository.py` | All SQL för granskningens tabeller. |
| `api/routes/review.py` | HTTP. |
| `docs/to_reviewer/*.md` | Granskarens systeminstruktion. Det är runtime-innehåll (som `docs/to_agent`), och den läses **inte** av bokföringsagenten. |
| `db/migrations/055_review.sql` | Tabeller och triggers (avsnitt 5). |

Agentloopen återanvänds: `services/agent_session.py::run_tool_loop` med granskarens verktyg och
klienten från `build_llm_client(settings.llm_review_model, ...)`. Kostnaden räknas med
`compute_cost_ore` och skrivs till `agent_runs` med `trigger = 'review'` (lägg till värdet i
CHECK-villkoret i migrationen).

---

## 4. Granskaren (agenten)

### 4.1 Modell och konfiguration (`config.py`)

```python
# The reviewer's model. Deliberately not the bookkeeping model: a second model
# catches errors the first one repeats. Must have a price row in services/llm.
llm_review_model: str = os.getenv("LLM_REVIEW_MODEL", "")
review_max_tool_turns: int = int(os.getenv("REVIEW_MAX_TOOL_TURNS", "60"))
review_max_output_tokens: Optional[int] = None   # opt-in cap, as for the agent
```

- Är `llm_review_model` tomt vägrar `POST /reviews` med `409 review_model_not_configured`.
  Det finns ingen tyst återgång till `llm_default_model`.
- Är `llm_review_model == llm_default_model` startar granskningen, men rapporten noterar
  "Samma modell som bokföringen – oberoendet är svagare." Det är en upplysning, inte ett stopp.
- Granskningen räknas mot `agent_daily_budget_ore`. Är taket nått stannar den mellan två steg,
  med status `paused_budget`. Den byter aldrig till en billigare modell (samma regel som i
  `agent_runtime.py`).

### 4.2 Verktyg

Alla verktyg utom `skapa_anmarkning` och `avsluta_granskningssteg` är rena läsningar. Där det går
ska de återanvända handlers från `agent_tools.py`.

| Verktyg | Gör | Källa |
|---|---|---|
| `las_kontoplan` | Kontoplanen | återanvänd |
| `las_verifikationer` | Postade verifikationer, filtrerbart | återanvänd |
| `las_verifikation` | En verifikation med rader, underlag, avstående, banklänkar och rättelser | ny, samlar befintliga läsningar |
| `hamta_underlagsfil` | Underlagets innehåll | återanvänd |
| `las_korrigeringar` | B-serien | återanvänd |
| `las_saldon` | Ingående balans, rörelse och utgående balans per konto och period, **via `OpeningBalanceService`** | ny |
| `las_kontroller` | Resultatet av maskinkontrollerna för granskningen | ny |
| `las_stickprov` | Granskningens stickprov (avsnitt 6.3) | ny |
| `las_momsdeklarationer` | Sparade deklarationer | ny, läser `vat_report` |
| `las_loner` | Lönekörningar, lönebesked och AGI | återanvänd |
| `las_bokslut` | `BokslutService.overview`, årsredovisningens utkast, INK2 | ny |
| `las_bolagsinfo` | `company_info` plus `review_company_facts` | ny |
| `skapa_anmarkning` | Skriver en anmärkning (avsnitt 4.3) | ny, skriver bara `review_findings` |
| `avsluta_granskningssteg` | Markerar att ett steg är klart, med en kort sammanfattning | ny |

**Tester som vaktar gränsen** (`tests/test_review_tools.py`):

- Granskarens verktygsnamn är en delmängd av en uttrycklig vitlista, och mängden skärs inte med
  `posta_verifikation`, `koppla_*`, `koppla_bort_*`, `stang_perioder`, `foresla_*`,
  `registrera_*`, `uppdatera_instruktioner` eller `bokfor_agi`.
- `execute_tool` för granskaren vägrar ett namn utanför vitlistan med `unknown_tool`.
- Antalet rader i ledger-tabellerna är oförändrat efter en hel granskning mot en fixtur.

### 4.3 `skapa_anmarkning`

```jsonc
{
  "step": "bedomning",                     // planering|maskin|bedomning|bokslut|forvaltning
  "severity": "material",                  // material | should_fix | observation
  "area": "moms",                          // moms|periodisering|privat|representation|
                                           // avstamning|underlag|bokslut|forvaltning|ovrigt
  "title": "Utländsk tjänst bokförd utan omvänd moms",
  "description": "…",
  "rule": "ML 1 kap. 2 § första st. 2 (omvänd skattskyldighet)",
  "evidence": [
    {"kind": "voucher", "id": "…"},
    {"kind": "intake_source", "id": "…"},
    {"kind": "check", "id": "moms_avstamning"}
  ],
  "amount_ore": 125000,                    // beloppet som påverkas, om det kan anges
  "suggested_correction": {                // valfritt
    "text": "Boka 2614/2645 med 25 % på 5 000 kr.",
    "rows": [{"account": "2645", "debit": 125000}, {"account": "2614", "credit": 125000}]
  }
}
```

Servern validerar innan raden skrivs:

- `evidence` får inte vara tom. Varje `voucher`-id måste vara en postad verifikation **i
  granskningens år**, varje `intake_source` måste finnas, och varje `check` måste vara ett id
  från granskningens egna kontroller. Är ett id fel vägrar servern med `invalid_evidence`.
- `severity = material` kräver `amount_ore` eller ett `check`-bevis.
- `suggested_correction.rows`, om de finns, måste balansera och använda konton som finns. De
  bokförs aldrig av granskaren.
- Dubbletter (samma `area` och samma mängd bevis-id i samma granskning) avvisas med
  `duplicate_finding`.

### 4.4 Instruktion (`docs/to_reviewer/`)

Filerna ska innehålla minst följande:

1. Rollen, och att den inte är revisor (avsnitt 1).
2. Ordningen: bilda dig en egen uppfattning från verifikationen och underlaget innan du läser
   rättelsehistorik eller kommentarer.
3. Företagets instruktioner är **påståenden att pröva**, inte regler. Om en instruktion strider
   mot lag (exempel: "utan moms" på en tjänst köpt från ett land utanför EU) är det en
   anmärkning mot instruktionen.
4. Väsentlighet: en avvikelse under `materiality.trivial_ore` får bli en `observation`, aldrig
   `material`.
5. Varje anmärkning ska ha ett bevis. "Jag hittade inget fel" är ett giltigt utfall.
6. Riskområdena för ett litet aktiebolag (avsnitt 6.4).

Instruktionens innehåll hashas (sha256) och sparas på granskningen (`instruction_sha256`).

---

## 5. Datamodell (`db/migrations/055_review.sql`)

Allt utom statusfält är append-only, enligt husets regel. En granskning kan inte raderas.

```sql
-- Gränsvärden för revisionsplikt, med giltighet. En lagändring = en ny rad.
CREATE TABLE audit_thresholds (
    id                  TEXT PRIMARY KEY,
    valid_from          DATE NOT NULL,          -- gäller räkenskapsår som börjar fr.o.m.
    max_employees       INTEGER NOT NULL,       -- 3
    max_balance_ore     INTEGER NOT NULL,       -- 150000000
    max_revenue_ore     INTEGER NOT NULL,       -- 300000000
    source              TEXT NOT NULL           -- "ABL 9 kap. 1 §, SFS ..."
);
INSERT INTO audit_thresholds VALUES
  ('abl-2010', '2010-11-01', 3, 150000000, 300000000, 'ABL 9 kap. 1 § (SFS 2010:834)');

-- Uppgifter om bolaget som bara en människa kan lämna. Append-only, senaste raden gäller.
CREATE TABLE review_company_facts (
    id                          TEXT PRIMARY KEY,
    has_auditor                 INTEGER NOT NULL CHECK (has_auditor IN (0,1)),
    auditor_name                TEXT,
    articles_allow_no_auditor   INTEGER CHECK (articles_allow_no_auditor IN (0,1)),
    shareholder_capital_ore     INTEGER,        -- aktiekapital, för ABL 25 kap.
    created_by                  TEXT NOT NULL,
    created_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reviews (
    id                  TEXT PRIMARY KEY,
    fiscal_year_id      TEXT NOT NULL REFERENCES fiscal_years(id),
    scope_start         DATE NOT NULL,          -- helår eller kvartal
    scope_end           DATE NOT NULL,
    mode                TEXT NOT NULL CHECK (mode IN
                          ('board_control','auditor_prep','auditor_required')),
    status              TEXT NOT NULL CHECK (status IN
                          ('running','paused_budget','failed','awaiting_answers',
                           'ready','acknowledged','superseded')),
    model               TEXT NOT NULL,
    instruction_sha256  TEXT NOT NULL,
    data_sha256         TEXT,                   -- avsnitt 8.2, sätts när maskinsteget är klart
    materiality_json    TEXT NOT NULL,          -- avsnitt 6.1
    agent_run_id        TEXT REFERENCES agent_runs(id),
    rereview_of         TEXT REFERENCES reviews(id),  -- omgranskning
    started_by          TEXT NOT NULL,
    started_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Trigger: bara `status`, `data_sha256` (från NULL) och `agent_run_id` (från NULL) får ändras.

CREATE TABLE review_steps (
    id          TEXT PRIMARY KEY,
    review_id   TEXT NOT NULL REFERENCES reviews(id),
    step        TEXT NOT NULL,                  -- planering|maskin|bedomning|bokslut|forvaltning
    summary     TEXT NOT NULL,
    finished_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (review_id, step)
);                                              -- append-only

CREATE TABLE review_check_results (
    id          TEXT PRIMARY KEY,
    review_id   TEXT NOT NULL REFERENCES reviews(id),
    check_id    TEXT NOT NULL,                  -- t.ex. 'bank_1930', se 6.2
    level       TEXT NOT NULL CHECK (level IN ('ok','varning','fel','ej_tillamplig')),
    title       TEXT NOT NULL,
    detail_json TEXT NOT NULL,                  -- belopp, differens, berörda id
    UNIQUE (review_id, check_id)
);                                              -- append-only

CREATE TABLE review_samples (
    id          TEXT PRIMARY KEY,
    review_id   TEXT NOT NULL REFERENCES reviews(id),
    voucher_id  TEXT NOT NULL REFERENCES vouchers(id),
    reason      TEXT NOT NULL,                  -- 'key_item'|'risk:<omrade>'|'random'
    UNIQUE (review_id, voucher_id)
);                                              -- append-only

CREATE TABLE review_findings (
    id                      TEXT PRIMARY KEY,
    review_id               TEXT NOT NULL REFERENCES reviews(id),
    step                    TEXT NOT NULL,
    severity                TEXT NOT NULL CHECK (severity IN ('material','should_fix','observation')),
    area                    TEXT NOT NULL,
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL,
    rule                    TEXT,
    amount_ore              INTEGER,
    suggested_correction    TEXT,               -- JSON
    carried_from            TEXT REFERENCES review_findings(id),  -- vid omgranskning
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);                                              -- append-only

CREATE TABLE review_finding_evidence (
    finding_id  TEXT NOT NULL REFERENCES review_findings(id),
    kind        TEXT NOT NULL CHECK (kind IN ('voucher','intake_source','check','bank_transaction','account')),
    ref_id      TEXT NOT NULL,
    PRIMARY KEY (finding_id, kind, ref_id)
);                                              -- append-only

-- Människans svar. Append-only. Senaste svaret gäller; ett nytt svar ersätter, raderar inte.
CREATE TABLE review_finding_answers (
    id                  TEXT PRIMARY KEY,
    finding_id          TEXT NOT NULL REFERENCES review_findings(id),
    answer              TEXT NOT NULL CHECK (answer IN ('corrected','accepted','not_an_error')),
    motivation          TEXT,                   -- krävs för accepted och not_an_error
    correction_voucher_id TEXT REFERENCES vouchers(id),  -- krävs för corrected
    answered_by         TEXT NOT NULL,
    answered_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE review_reports (
    id                  TEXT PRIMARY KEY,
    review_id           TEXT NOT NULL UNIQUE REFERENCES reviews(id),
    content_json        TEXT NOT NULL,
    pdf                 BLOB NOT NULL,          -- lagras, renderas aldrig om
    report_sha256       TEXT NOT NULL,
    acknowledged_by     TEXT NOT NULL,
    acknowledged_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);                                              -- append-only
```

Triggers: `BEFORE UPDATE` och `BEFORE DELETE` med `RAISE(ABORT, ...)` på alla tabeller ovan
utom de tillåtna statusövergångarna på `reviews`. Mönstret finns i migration 035 och 051.

**Statusövergångar på `reviews`** (kontrolleras i `ReviewService`, och för de terminala
tillstånden även i en trigger):

```
running → awaiting_answers → ready → acknowledged
running → paused_budget → running
running → failed
(valfritt icke-terminalt) → superseded       -- när en ny granskning av samma omfång startas
```

`acknowledged` och `superseded` är terminala.

---

## 6. Granskningen steg för steg

`ReviewService.run(review_id)` körs i en bakgrundstråd (samma mönster som agentpasset). Varje
steg avslutas med en rad i `review_steps`, så att en avbruten granskning kan fortsätta där den
stannade.

### 6.1 Planering (server + modell)

Servern räknar väsentligheten och lagrar den i `reviews.materiality_json`:

```jsonc
{
  "base": "revenue",               // revenue, eller total_assets om omsättningen är liten
  "base_ore": 210000000,
  "overall_ore": 4200000,          // 2 % av omsättningen, alt. 1 % av balansomslutningen
  "performance_ore": 3150000,      // 75 % av overall
  "trivial_ore": 210000            // 5 % av overall, men minst 10 000 öre (100 kr)
}
```

Procentsatserna ligger som konstanter i `review.py` med en kommentar om ISA 320. Modellen får
siffrorna och gör en kort riskbedömning som sparas i stegets `summary`: vilka områden som
väger tyngst för just det här bolaget. Planeringen påverkar stickprovet (6.3) men skapar inga
anmärkningar.

### 6.2 Maskinkontroller (bara server)

`services/review_checks.py` kör följande. Resultatet skrivs till `review_check_results`.
Granskaren läser det med `las_kontroller` och gör en anmärkning av varje `fel` eller
`varning` som den bedömer är väsentlig.

| `check_id` | Kontroll | Återanvänd |
|---|---|---|
| `balans` | Summa debet = summa kredit per verifikation och totalt; balansräkningen går ihop | `BokslutService._kontroller` |
| `serie_luckor` | Inga luckor eller dubbletter i verifikationsnumren per serie | `ComplianceService._check_voucher_sequence` |
| `ib_ub` | Årets ingående balans = fjolårets utgående, per konto | `OpeningBalanceService`, `balance_differences` |
| `bank_1930` | Bokfört saldo mot senaste importerade kontoutdrag; okopplade transaktioner | `bank_reconciliation`, `BokslutService._bank_checks` |
| `skattekonto_1630` | Saldo på 1630 mot skattekontot | befintlig skattekontoimport |
| `moms_avstamning` | 26xx per period mot sparade momsdeklarationer; att 2650 nollställs | `VatReportService.preview_for_dates` |
| `lon_agi` | 7010/7210 och 2710/2731 mot lönebesked och bokförda AGI | `PayrollService` |
| `underlag` | Varje verifikation har ett aktuellt underlag eller ett gällande avstående | `MISSING_DOCUMENT_SQL` **med** avstående |
| `bokforing_i_tid` | Kontanta betalningar senast nästa arbetsdag, övrigt inom rimlig tid (BFL 5 kap. 2 §) | `ComplianceService._check_booking_timeliness` |
| `perioder_last` | Årets perioder är låsta inför bokslut | `ComplianceService._check_period_closing` |
| `stora_belopp` | Verifikationer över `performance_ore` | `_check_large_amounts`, med väsentligheten som gräns |
| `avrakning_agare` | Saldo på 2893/1680-intervallet (avräkning med delägare) per månad | ny |
| `eget_kapital` | Eget kapital mot halva aktiekapitalet (ABL 25 kap.) | ny, använder `review_company_facts` |
| `utdelning` | Beslutad utdelning (2898) mot fritt eget kapital vid föregående bokslut (ABL 17 kap. 3 §) | ny |
| `skatter_i_tid` | Moms- och AGI-dragningar på skattekontot mot förfallodag | ny, använder skattekontoraderna |
| `ar_huvudbok` | Årsredovisningens siffror = huvudbokens, rad för rad | `ArsredovisningService` |
| `ink2_huvudbok` | INK2/SRU-värdena = huvudbokens | `sru_export`, `ink2_declaration` |

Regler för kontrollerna:

- De är rena funktioner av databasen och omfånget, och de får inte skriva någon annanstans än i
  `review_check_results`.
- `ej_tillamplig` används när underlaget saknas (inga löner, inget skattekonto importerat). En
  kontroll som inte kan köras får inte se ut som `ok`.
- Alla belopp räknas i öre. Avrundning till kronor sker bara i presentationen.

### 6.3 Stickprov (`services/review_sampling.py`)

Urvalet är deterministiskt: fröet är `review_id`, så att samma granskning ger samma urval och
kan förklaras i efterhand. Det består av tre delar, utan dubbletter:

1. **Nyckelposter:** alla verifikationer med ett belopp ≥ `performance_ore`.
2. **Riskposter**, högst 10 per område:
   - verifikationer mot konton för representation (6071/6072), gåvor, resor, fordon, och
     avräkning med ägaren,
   - inköp från en utländsk motpart (enligt underlagets tolkning eller valuta),
   - verifikationer under de sista 15 och första 15 dagarna kring årsskiftet (periodisering),
   - verifikationer med ett avstående `none`,
   - verifikationer som rättats med B-serien.
3. **Slumpurval** bland resten, viktat efter belopp (monetary unit sampling). Antalet är
   `min(25, ceil(rest_ore / performance_ore))`.

Granskaren går igenom varje stickprov med `las_verifikation` och `hamta_underlagsfil` och
prövar belopp, datum, konto, moms och period mot underlaget.

### 6.4 Bedömning (modell)

Riskområdena granskaren ska täcka, i den här ordningen:

1. Moms: avdragsrätt, omvänd skattskyldighet (inom och utanför EU), representation (avdrag på
   högst underlaget för 300 kr per person), momssats.
2. Privata kostnader och förmåner: kostnader som borde vara lön eller förmån, eller ett lån
   till ägaren.
3. Periodisering: förutbetalda och upplupna poster (17xx/29xx) vid årsskiftet.
4. Underlag: att underlaget faktiskt stöder verifikationen (belopp, motpart, datum), och att
   samma kvitto inte ligger bakom två kostnader.
5. Avtal: att lån, leasing och abonnemang bokförs konsekvent över året.

### 6.5 Bokslut och årsredovisning (modell + kontroller)

- Avskrivningar enligt K2 (BFNAR 2016:10): nyttjandeperiod, början av avskrivningen.
- Upplupna kostnader och förutbetalda intäkter, och K2:s förenklingsregel för poster under
  5 000 kr.
- Skatteberäkningen: årets skatt mot INK2 och `tax_adjustments`.
- Förvaltningsberättelsen och noterna: att de obligatoriska uppgifterna finns (medelantal
  anställda, väsentliga händelser, förslag till resultatdisposition).

### 6.6 Förvaltning (modell + kontroller)

| Område | Regel | Bevis |
|---|---|---|
| Otillåtet lån till ägare eller närstående | ABL 21 kap. 1 § | `avrakning_agare` |
| Utdelning större än fritt eget kapital | ABL 17 kap. 3 § | `utdelning` |
| Kontrollbalansräkning | ABL 25 kap. 13 § | `eget_kapital` |
| Skatter och avgifter betalda i tid | SFL 62 kap. | `skatter_i_tid` |
| Bokföringen sköts löpande | BFL 5 kap. 2 § | `bokforing_i_tid` |

Är `shareholder_capital_ore` okänt blir `eget_kapital` `ej_tillamplig`, och granskaren skriver en
`observation` om att uppgiften saknas.

---

## 7. Människans del

### 7.1 Svara på anmärkningar

Varje anmärkning visas som ett kort på granskningssidan (inte i bokföringens beslutskö, eftersom
det inte är bokföringsbeslut). Svaren:

| Svar | Krav | Effekt |
|---|---|---|
| **Rätta** (`corrected`) | `correction_voucher_id`: en postad verifikation (normalt B-serien) i samma räkenskapsår, postad efter att anmärkningen skapades | Anmärkningen räknas som rättad i rapporten. |
| **Godta** (`accepted`) | `motivation`, minst 10 tecken | Står i rapporten som "godtagen av styrelsen", med motiveringen. |
| **Inte fel** (`not_an_error`) | `motivation` | Står i rapporten som "bestriden", med motiveringen. Räknas för träffsäkerheten (avsnitt 10). |

Knappen **Rätta** öppnar bokföringstråden med anmärkningen som förifylld text och
`suggested_correction` som förslag. Bokföringsagenten lägger fram en verifikation som vanligt,
och en människa postar den. Granskningen bokför aldrig själv.

Alla svar är `human_only`: API-nyckeln får `403 human_only`.

### 7.2 Omgranskning

När alla anmärkningar av typen `material` och `should_fix` har ett svar, kan människan välja
**Granska rättelserna**. Det skapar en ny granskning med `rereview_of` satt. Den:

- kör om de maskinkontroller som berörs av de rättade verifikationerna,
- låter modellen pröva bara de rättade anmärkningarna och deras rättelseverifikationer,
- för över övriga anmärkningar med `carried_from` och deras senaste svar.

Den gamla granskningen blir `superseded`.

### 7.3 Bekräfta rapporten

När varje anmärkning har ett svar går granskningen till `ready`. En inloggad människa trycker
**Styrelsen har tagit del av granskningen** (`POST /reviews/{id}/acknowledge`). I samma
transaktion händer följande:

1. Rapporten sammanställs (avsnitt 8), PDF:en renderas en gång och lagras i `review_reports.pdf`.
2. `reviews.status` blir `acknowledged`.
3. Händelsen skrivs till audit-loggen.

Därefter serveras PDF:en byte för byte (`GET /reviews/{id}/report.pdf`) och renderas aldrig
om. Det är samma regel som för fakturans PDF.

### 7.4 Bolagsuppgifter

`PUT /review/company-facts` (`human_only`) skriver en ny rad i `review_company_facts`.
Formuläret frågar efter revisor (ja/nej, namn), om bolagsordningen tillåter att bolaget är utan
revisor, och aktiekapitalet. `GET` är läsbar med API-nyckeln.

---

## 8. Rapporten

### 8.1 Innehåll (`content_json`)

1. Den fasta texten från avsnitt 1, och lägesbanderollen från avsnitt 2.
2. Omfång (datum), räkenskapsår, väsentlighet, modell, instruktionens hash och datans hash.
3. Revisionsplikt: de tre gränsvärdena för året och året före, värdena i Bok och slutsatsen.
4. Maskinkontrollerna: en rad per kontroll med nivå.
5. Stickprovet: antal per kategori och täckning i kronor.
6. Anmärkningarna, grupperade efter allvarlighet, med svar, motivering och rättelseverifikation.
7. Det som inte granskades: lager, fysiska tillgångar, externa bekräftelser och sådant som är
   `ej_tillamplig` (avsnitt 9).
8. Bekräftelsen: vem och när.

### 8.2 Kontrollsumman över den granskade datan

`data_sha256` räknas när maskinsteget är klart, som sha256 över en kanonisk JSON med:

- id och `posted_at` för alla postade verifikationer i omfånget, i ordning,
- id för varje aktuell underlagslänk, banklänk och gällande avstående för dem,
- de ingående balanserna per konto.

Den gör det möjligt att visa senare exakt vilken data som granskades. Om en verifikation postas
i omfånget efter att hashen räknats, visar granskningssidan "Böckerna har ändrats sedan
granskningen" (räkna om och jämför vid läsning). Rapporten går fortfarande att bekräfta, men
varningen kommer med i rapporten.

---

## 9. Begränsningar som ska stå i produkten

- Granskaren kan inte inventera lager, se fysiska tillgångar eller hämta bekräftelser från bank,
  kunder eller leverantörer. Importerade kontoutdrag och skattekontoutdrag är de externa bevis
  som finns.
- Den kan missa avsiktligt fusk, särskilt om underlaget är förfalskat.
- Den kan inte bedöma bolagsordningen, aktieboken eller stämmoprotokoll som inte finns i Bok.

Texten står i rapporten (avsnitt 8.1 punkt 7) och på granskningssidan.

---

## 10. API (`api/routes/review.py`)

Alla rutter kräver bearer. Rutter markerade **H** är `human_only` (JWT). API-nyckeln får
`403 human_only`.

| Metod och sökväg | | Beskrivning |
|---|---|---|
| `GET /api/v1/review/mode?fiscal_year_id=` | | Läge, gränsvärden och nyckeltal |
| `GET /api/v1/review/company-facts` | | Senaste bolagsuppgifterna |
| `PUT /api/v1/review/company-facts` | H | Ny rad |
| `POST /api/v1/reviews` | H | Starta: `{fiscal_year_id, scope_start?, scope_end?}`. `409 review_running` om en granskning av samma omfång redan körs. |
| `GET /api/v1/reviews?fiscal_year_id=` | | Lista |
| `GET /api/v1/reviews/{id}` | | Status, steg, kontroller, stickprov och antal anmärkningar |
| `GET /api/v1/reviews/{id}/findings` | | Anmärkningar med bevis och senaste svar |
| `POST /api/v1/reviews/{id}/findings/{fid}/answer` | H | `{answer, motivation?, correction_voucher_id?}` |
| `POST /api/v1/reviews/{id}/rereview` | H | Omgranskning (avsnitt 7.2) |
| `POST /api/v1/reviews/{id}/resume` | H | Fortsätt efter `paused_budget` eller `failed` |
| `POST /api/v1/reviews/{id}/acknowledge` | H | `409 findings_unanswered` om något saknar svar |
| `GET /api/v1/reviews/{id}/report` | | `content_json` |
| `GET /api/v1/reviews/{id}/report.pdf` | | Lagrad PDF (blob via `apiClient`) |

Bokföringsagenten får inget verktyg för att starta, läsa eller besvara en granskning. Det håller
granskningen fri från den agent den granskar. Lägg till rutterna i testet för publika rutter i
`tests/test_api.py` (inga av dem är publika).

---

## 11. Frontend (`frontend-v3`)

- En ny vy **Granskning** under Bokslut, per räkenskapsår.
- Överst finns lägesbanderollen (avsnitt 2) och revisionspliktens nyckeltal.
- Stegen visas som en tidslinje med status (planering, maskin, bedömning, bokslut,
  förvaltning).
- Under den finns kontrolltabellen: nivå, rubrik och detalj, med länk till berörda
  verifikationer.
- Anmärkningskorten är sorterade efter allvarlighet, med bevislänkar som öppnar verifikationen
  eller underlaget, och knapparna Rätta, Godta och Inte fel.
- Knappen Bekräfta är aktiv först när allt har ett svar. PDF:en hämtas som blob.
- Gränssnittet har inga texter med "revision", "revisor" (utom i lägestexten om att välja
  revisor) eller "revisionsberättelse". Ett vitest-test söker igenom vyns strängar efter det.

---

## 12. Tester

| Fil | Vad |
|---|---|
| `tests/test_review_mode.py` | Revisionsplikt: två år över mer än ett gränsvärde; ett år över; gränsvärden med giltighet; `foresla_revisorsval` skapas en gång |
| `tests/test_review_checks.py` | Varje `check_id` mot en fixtur med ett inplanterat fel (lucka i serien, momsdifferens, negativt saldo på avräkningen, eget kapital < ½ aktiekapital, för stor utdelning) |
| `tests/test_review_sampling.py` | Determinism med samma frö; nyckelposter alltid med; inga dubbletter |
| `tests/test_review_tools.py` | Vitlistan (avsnitt 4.2); `invalid_evidence`; `duplicate_finding`; ledgern är orörd |
| `tests/test_review_append_only.py` | Triggers: UPDATE och DELETE vägras; bara tillåtna statusövergångar |
| `tests/test_review_api.py` | `human_only` på alla H-rutter; `findings_unanswered`; PDF:en är byte för byte densamma vid två hämtningar |
| `tests/test_review_flow.py` | Hela flödet med en skriptad LLM-klient (som i befintliga agenttester): start → anmärkning → Rätta med en B-verifikation → omgranskning → bekräftelse |

---

## 13. Byggordning

Varje steg går att leverera och testa för sig.

1. **Migration 055 och `review_checks.py`** med kontrollerna i avsnitt 6.2, plus `GET /review/mode`.
   Det ger värde utan någon LLM: en bokslutskontroll med revisionsplikt.
2. **Bolagsuppgifter, `foresla_revisorsval`** och lägesbanderollen i UI.
3. **Stickprov, granskarens verktyg och agentloopen** med `skapa_anmarkning`, och
   `LLM_REVIEW_MODEL` i `config.py` och i `deploy/hubbabubba`-miljön.
4. **Svar, omgranskning, rapport och PDF.**
5. **Kvartalsgranskning:** samma flöde med `scope_start` och `scope_end` för ett kvartal. Steg
   6.5 hoppas över, och 6.6 körs bara för `avrakning_agare` och `skatter_i_tid`.

## 14. Öppna frågor

Flytta det som återstår till `docs/oppna-beslut.md` när bygget börjar.

1. Vilken modell som är granskare, och vad en körning får kosta. Mät med `compute_cost_ore` på
   ett riktigt år innan ett tak sätts.
2. Om gränsvärdena för revisionsplikt höjs: ny rad i `audit_thresholds` med rätt `valid_from`
   när lagen är beslutad.
3. Om kvartalsgranskningen ska kunna schemaläggas. Det hör ihop med punkt 4 i
   `oppna-beslut.md`.
4. Om en `material` anmärkning som står som "godtagen" ska blockera att perioden eller året låses.
   Förslaget är nej: styrelsen äger beslutet, och rapporten visar det.
5. Vilka konton som räknas som avräkning med ägaren i bolagets kontoplan. Förslaget är
   2893 och 1680–1689, gjort konfigurerbart per bolag.
