# Granskning – implementationsspec

Status: backend byggd (avsnitt 3–6 och 8); frontend under bygge.

En extern agent pekas på en publik ingång. Ingången säger hur den ska autentisera sig och var
instruktionen finns. Agenten läser böckerna genom API:et, granskar ett räkenskapsår enligt
instruktionen och laddar upp en rapport. Rapporten syns i BokAI.

Samma ingång och samma instruktion fungerar för vilken agent och modell som helst. Kör flera, så
får du flera oberoende rapporter om samma år och kan jämföra vad var och en hittade.

Bok kör ingen granskning själv. Det finns ingen modellkonfiguration, ingen agentloop och inga
maskinkontroller som är byggda för granskningen.

---

## 1. Namn och ram

- **Det är inte en revision.** Granskningen är ett verktyg för styrelsens kontrollansvar (ABL 8
  kap. 4 §). Funktionen, rapporten och agenten får inte kallas "revision",
  "revisionsberättelse" eller "revisor", varken i UI, API-namn eller instruktionen.
- Varje rapport visas med en fast text som ligger i frontend, inte i agentens rapport: *"Granskningen
  är styrelsens egen kontroll. Den är inte en revision och ersätter inte en revisor."*
- Bok bedömer inte revisionsplikt. Det får bolagets ägare hålla koll på själv.

| Begrepp | Svenska i UI | Kodnamn |
|---|---|---|
| Rapporten en agent laddar upp | Granskningsrapport | `review_report` |
| Ett fynd i rapporten | Anmärkning | `review_finding` |

---

## 2. Flödet

```
människa ──"granska 2025, börja här: <url>"──→ agent
agent ── GET  /api/v1/review/entrypoint            (publik)
      ── GET  /api/v1/review/instructions?fiscal_year_id=…
      ── GET  …läsrutter: SIE4, verifikationer, underlag, rapporter, bokslut
      ── POST /api/v1/review/reports               (rapporten)
människa ── Bokslut → Granskning: läser rapporterna
```

Agenten skriver ingenting i böckerna. Ett fel som rapporten pekar ut rättas i det vanliga flödet,
med en B-verifikation.

---

## 3. Åtkomst: en granskningsnyckel som bara kan läsa

En granskare ska aldrig få bokföringsagentens nyckel. Det finns en egen nyckel för granskning:

```python
# config.py. Tom = granskning med egen nyckel är avstängd.
review_api_key: str = os.getenv("BOKFOERING_REVIEW_KEY", "")
```

`verify_api_key` (`api/deps.py`) tar emot nyckeln och släpper igenom:

- `GET` och `HEAD` på alla autentiserade rutter,
- `POST /api/v1/review/reports`.

Allt annat får `403 review_key_read_only`. Nyckeln jämförs i konstant tid, som API-nyckeln. Den
räknas inte som en människa, så `human_only`-rutterna vägrar den som förut.

Den vanliga API-nyckeln och en inloggad människas JWT får också ladda upp en rapport. Det gör det
möjligt att testa utan att sätta en ny nyckel.

**Tester** (`tests/test_review_api.py`):

- Granskningsnyckeln får `200` på ett urval `GET`-rutter och `403 review_key_read_only` på
  `POST /api/v1/agent/vouchers`, `POST /vouchers/{id}/correct` och `PUT /agent-instructions/accounting`.
- Ett test går igenom `app.routes` och kontrollerar att varje rutt som inte är `GET`/`HEAD` vägrar
  nyckeln, utom `POST /api/v1/review/reports`.
- Är `BOKFOERING_REVIEW_KEY` tom ger en tom bearer `401`, inte åtkomst.

### 3.1 Tillfällig nyckel med uppdraget (`services/review_token.py`, migration 056)

Det enklaste sättet att starta en granskning är knappen **Kopiera uppdrag till agent** i vyn. Den
anropar `POST /api/v1/review/tokens` med `{fiscal_year_id, entrypoint_url}` och får tillbaka
`{id, token, expires_at, prompt}`. `prompt` är ett färdigt uppdrag med året, ingången och nyckeln. Det
klistras in hos vilken agent som helst.

- Nyckeln börjar med `bokrev_`. Den gäller `REVIEW_TOKEN_TTL_MINUTES` (standard 60) och har exakt
  granskningsnyckelns rättigheter: `_key_kind` kallar den `"review"`.
- Bara en inloggad människa får skapa, lista (`GET /api/v1/review/tokens`) och återkalla
  (`POST /api/v1/review/tokens/{id}/revoke`) en nyckel. API-nyckeln och en granskningsnyckel får `403`.
- Bara nyckelns sha256 sparas, och klartexten visas en gång. `review_tokens` och
  `review_token_revocations` är append-only. Att skapa och återkalla en nyckel loggas i `audit_log`.
- En utgången eller återkallad nyckel ger `401`. Den statiska `BOKFOERING_REVIEW_KEY` fungerar som
  förut, oberoende av detta.

Tester: `tests/test_review_tokens.py`.

---

## 4. API (`api/routes/review.py`)

### 4.1 `GET /api/v1/review/entrypoint` (publik)

Har samma form som `/api/v1/agent-instructions/entrypoint`, men är kortare:

```jsonc
{
  "service": "bokfoering-api",
  "purpose": "Granska ett räkenskapsår och ladda upp en granskningsrapport.",
  "auth": {"type": "bearer", "value_format": "Bearer <BOKFOERING_REVIEW_KEY>",
           "check": {"method": "GET", "path": "/api/v1/review/instructions"}},
  "startup_sequence": [
    {"step": 1, "action": "read_instructions", "method": "GET",
     "path": "/api/v1/review/instructions?fiscal_year_id={id}"},
    {"step": 2, "action": "review", "guidance": "Följ instruktionen. Läs bara, skriv inget."},
    {"step": 3, "action": "upload_report", "method": "POST", "path": "/api/v1/review/reports"}
  ],
  "links": {"openapi": "/openapi.json"}
}
```

Lägg till rutten bland de publika i `api/main.py` och i testet för publika rutter i `tests/test_api.py`.

### 4.2 `GET /api/v1/review/instructions?fiscal_year_id=`

Utan `fiscal_year_id` gäller det senaste räkenskapsåret. Svaret:

```jsonc
{
  "fiscal_year": {"id": "…", "start_date": "2025-01-01", "end_date": "2025-12-31", "locked": true},
  "fiscal_years": [ … ],                 // så att agenten kan välja ett annat år
  "instructions_markdown": "…",          // docs/to_reviewer/*.md, ihopslaget i ordning
  "instruction_sha256": "…",             // sha256 över instructions_markdown
  "read_endpoints": {                    // var datan finns, med året ifyllt
    "sie4": "/api/v1/bokslut/{fy}/filer/bokforing.si",
    "vouchers": "/api/v1/vouchers?fiscal_year_id={fy}",
    "voucher": "/api/v1/vouchers/{voucher_id}",
    "source_context": "/api/v1/vouchers/{voucher_id}/source-context",
    "intake_file": "/api/v1/intake/{source_id}/file",
    "bank_input_file": "/api/v1/bank-inputs/{bank_input_id}/file",
    "balance_sheet": "/api/v1/reports/balance-sheet?…",
    "income_statement": "/api/v1/reports/income-statement?…",
    "general_ledger": "/api/v1/reports/general-ledger/{account_code}?…",
    "bokslut": "/api/v1/bokslut/{fy}",
    "company_instructions": "/api/v1/agent-instructions/accounting"
  },
  "report_schema": { … }                 // JSON Schema för POST /review/reports
}
```

Bara läsrutter som redan finns används. Granskningen behöver inga nya.

### 4.3 `POST /api/v1/review/reports`

```jsonc
{
  "id": "…",                             // UUID som agenten skapar. Samma id igen ger
                                         // den sparade rapporten tillbaka (200), ingen dubblett.
  "fiscal_year_id": "…",
  "reviewer": {"agent": "Claude Code", "model": "claude-opus-5-5"},   // agentens egen uppgift
  "instruction_sha256": "…",             // från 4.2
  "summary_markdown": "…",               // helhetsbedömning, vad som granskades och hur
  "examined_voucher_ids": ["…"],         // valfritt: verifikationer agenten faktiskt prövade
  "findings": [
    {
      "severity": "material",            // material | should_fix | observation
      "area": "moms",                    // moms|periodisering|privat|underlag|avstamning|
                                         // bokslut|forvaltning|ovrigt
      "title": "Utländsk tjänst bokförd utan omvänd moms",
      "description": "…",
      "rule": "ML 1 kap. 2 § första st. 2",   // valfritt
      "voucher_ids": ["…"],              // valfritt, men varje id prövas
      "amount_ore": 125000,              // valfritt
      "suggested_correction": "Boka 2645/2614 med 25 % på 5 000 kr."   // valfritt, fri text
    }
  ]
}
```

Servern kontrollerar följande innan något sparas, och vägrar hela rapporten med `422` om något är fel:

- `fiscal_year_id` finns.
- Varje id i `voucher_ids` och `examined_voucher_ids` är en postad verifikation i året
  (`invalid_voucher_id`, med de felaktiga id:na). Det hindrar påhittade hänvisningar.
- `severity` och `area` har tillåtna värden. Texterna har en övre längdgräns.
- `findings` får vara tom. "Inga anmärkningar" är ett giltigt utfall.

`instruction_sha256` lagras som det är. Om värdet inte matchar den aktuella instruktionen visas
det i UI som "granskad mot en äldre instruktion". Rapporten vägras inte för det.

Servern lagrar också vem som laddade upp (`review_key`, `api_key` eller användarnamnet) och när.

### 4.4 Läsa rapporter

| Metod och sökväg | Beskrivning |
|---|---|
| `GET /api/v1/review/reports?fiscal_year_id=` | Lista: granskare, modell, datum, antal anmärkningar per allvarlighet |
| `GET /api/v1/review/reports/{id}` | Hela rapporten med anmärkningar |
| `GET /api/v1/review/coverage?fiscal_year_id=` | Per verifikation: hur många rapporter som prövade den och vilka som anmärkte på den |

Bokföringsagenten får inget verktyg för granskningen. Bokföringsagenten granskar inte sig själv.

---

## 5. Datamodell (`db/migrations/055_review_reports.sql`)

Allt är append-only. Det finns triggers `BEFORE UPDATE` och `BEFORE DELETE` med `RAISE(ABORT, …)`
på alla tabeller, enligt mönstret i migration 035. En rapport som är fel ersätts av en ny rapport,
inte av en ändring.

```sql
CREATE TABLE review_reports (
    id                  TEXT PRIMARY KEY,           -- agentens UUID
    fiscal_year_id      TEXT NOT NULL REFERENCES fiscal_years(id),
    reviewer_agent      TEXT NOT NULL,
    reviewer_model      TEXT NOT NULL,
    instruction_sha256  TEXT NOT NULL,
    summary_markdown    TEXT NOT NULL,
    uploaded_by         TEXT NOT NULL,              -- review_key | api_key | <användare>
    uploaded_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE review_findings (
    id                    TEXT PRIMARY KEY,
    report_id             TEXT NOT NULL REFERENCES review_reports(id),
    position              INTEGER NOT NULL,         -- ordningen i rapporten
    severity              TEXT NOT NULL CHECK (severity IN ('material','should_fix','observation')),
    area                  TEXT NOT NULL,
    title                 TEXT NOT NULL,
    description           TEXT NOT NULL,
    rule                  TEXT,
    amount_ore            INTEGER,
    suggested_correction  TEXT
);

CREATE TABLE review_finding_vouchers (
    finding_id  TEXT NOT NULL REFERENCES review_findings(id),
    voucher_id  TEXT NOT NULL REFERENCES vouchers(id),
    PRIMARY KEY (finding_id, voucher_id)
);

CREATE TABLE review_examined_vouchers (
    report_id   TEXT NOT NULL REFERENCES review_reports(id),
    voucher_id  TEXT NOT NULL REFERENCES vouchers(id),
    PRIMARY KEY (report_id, voucher_id)
);
```

Moduler: `services/review.py` (validering och sparande, i en transaktion),
`repositories/review_repository.py` (all SQL) och `api/routes/review.py`.

---

## 6. Instruktionen (`docs/to_reviewer/*.md`)

Instruktionen är runtime-innehåll, på samma sätt som `docs/to_agent`. Den läses av
`repositories/system_instructions.py` (en egen fillista) och läses **inte** av
bokföringsagenten. Ett test kontrollerar att den finns och innehåller rubrikerna nedan.

Instruktionen är det enda som styr hur granskningen görs. Om den ändras ändras granskningen för
alla agenter, och `instruction_sha256` visar vilken version en rapport gjordes mot.

Innehåll:

1. **Roll.** Du granskar för styrelsens räkning. Du är inte revisor och skriver ingen
   revisionsberättelse. Du läser bara. Granskningsnyckeln kan inte skriva, och du ska inte försöka.
2. **Ordning.** Hämta SIE4-filen för en överblick. Bilda dig sedan en egen uppfattning från
   verifikationen och underlaget innan du läser rättelsehistorik eller kommentarer.
3. **Företagets instruktioner är påståenden att pröva**, inte regler. En instruktion som strider
   mot lag är en anmärkning mot instruktionen.
4. **Urval.** Pröva alla stora poster, posterna inom riskområdena och ett slumpvis urval av resten.
   Ange i `summary_markdown` hur urvalet gjordes, och lista de prövade verifikationerna i
   `examined_voucher_ids`.
5. **Riskområden för ett litet aktiebolag:**
   - Moms: avdragsrätt, omvänd skattskyldighet inom och utanför EU, representation, momssats.
     Stäm av 26xx mot momsdeklarationerna.
   - Privata kostnader och förmåner, och lån till ägaren (ABL 21 kap.).
   - Periodisering kring årsskiftet (17xx/29xx).
   - Underlag: att det stöder verifikationen (belopp, motpart, datum), och att samma kvitto inte
     ligger bakom två kostnader.
   - Avstämningar: bank 1930 och skattekonto 1630 mot importerade utdrag. Ingående balans mot
     fjolårets utgående.
   - Bokslut: avskrivningar enligt K2, skatteberäkningen, utdelning mot fritt eget kapital
     (ABL 17 kap. 3 §).
6. **Bevis.** Varje anmärkning ska bygga på något du har läst. Hänvisa till verifikationerna i
   `voucher_ids` när det går. Räkna inte fram summor i huvudet. Hämta dem från rapportrutterna och
   ange var de kommer ifrån.
7. **Allvarlighet.** `material` påverkar årsredovisningen, deklarationen eller lagefterlevnaden.
   `should_fix` är ett fel som bör rättas. `observation` är en iakttagelse. "Inga anmärkningar"
   är ett giltigt utfall.
8. **Begränsningar att nämna i sammanfattningen:** inga lager, inga fysiska tillgångar, inga
   externa bekräftelser. Avsiktligt fusk med förfalskat underlag kan missas.
9. **Rapporten.** Ladda upp med `POST /api/v1/review/reports` enligt `report_schema`. Ange din
   agent och din modell ärligt.

---

## 7. Frontend (`frontend-v3`)

En vy, **Granskning**, under Bokslut, per räkenskapsår:

- Den fasta texten från avsnitt 1 står överst.
- Listan över rapporter visar granskare, modell, datum, antal anmärkningar per allvarlighet och
  "äldre instruktion" när hashen inte stämmer.
- En rapport visar sammanfattningen som markdown. Anmärkningarna sorteras efter allvarlighet, och
  varje verifikations-id länkar till verifikationen.
- **Täckning** visar verifikationerna som minst en rapport anmärkte på. Kolumnerna är
  verifikationen, hur många rapporter som prövade den och vilka granskare som anmärkte. En
  anmärkning som flera modeller har gjort oberoende av varandra väger tyngre än en som bara en
  modell har gjort.
- Vyn ska inte innehålla orden "revision", "revisor" eller "revisionsberättelse" utom i den fasta
  texten. Ett vitest-test söker igenom vyns strängar.

Det finns inga svar, kvitteringar eller PDF:er per anmärkning. Rättelser görs i bokföringen.

---

## 8. Tester

| Fil | Vad |
|---|---|
| `tests/test_review_api.py` | Granskningsnyckelns gränser (avsnitt 3); den publika ingången; `invalid_voucher_id`; samma `id` två gånger ger en rapport; listan och täckningen |
| `tests/test_review_append_only.py` | UPDATE och DELETE vägras på alla fyra tabellerna |
| `tests/test_review_instructions.py` | Instruktionen finns, hashen är stabil, bokföringsagentens instruktion innehåller den inte |
| `tests/test_review_flow.py` | Med granskningsnyckeln: entrypoint → instruktion → läs SIE4 och en verifikation → ladda upp → rapporten listas. Ledgerns radantal är oförändrat. |

---

## 9. Byggordning

1. Granskningsnyckeln i `config.py` och `api/deps.py`, med testerna i avsnitt 3.
2. Migration 055, `ReviewService`, `POST`/`GET /review/reports` och täckningen.
3. `docs/to_reviewer/`, `GET /review/entrypoint` och `GET /review/instructions`.
4. Vyn Granskning i frontend.
5. `BOKFOERING_REVIEW_KEY` i `deploy/hubbabubba` (`bok.env`) och i README:n.

## 10. Öppna frågor

Flyttade till `docs/oppna-beslut.md`, avsnittet Granskning.
