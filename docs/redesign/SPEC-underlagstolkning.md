# Spec: `underlagstolkning`

Modul-id `underlagstolkning` i kapabilitetskartan (`ANALYS.md` §8). Beror på `agentruntime`, som är
klar (A1–A14). `flode-underlag` beror på den här.

Status: **Klar 2026-09-28 (U1–U10).** Skriven 2026-09-24, godkänd 2026-09-28. Fem beslut tagna av beställaren
(§12.1–§12.5): tolkningen är ett verktyg och en läsväg, inte en endpoint med eget LLM-anrop;
predikatet för "saknar underlag" lagas först, i den här modulen, och undantar
`created_by = 'sie4_import'`; `hypothesis` sätts bara när en rad på underlaget bär den; ett hårt
stopp i postningen skjuts till `flode-underlag`. §13:s två frågor är besvarade, se §12.4–§12.5.
Efter U1–U10 besvarades modulens öppna frågor (§12.6); U11–U15 bygger det som kräver kod.

---

## Antaganden

1. **Agenten läser redan filen.** `hamta_underlagsfil` (`services/agent_tools.py:643`) ger
   modellen underlaget enligt `SPEC-agentruntime.md` §6.3: textlager först, dokumentblock sedan,
   annars avstående. Den här modulen bygger ingen andra läsväg och gör inget eget LLM-anrop.
2. **Det modellen läser är ett påstående och det servern räknar är ett faktum.** Leverantör,
   datum, belopp, moms och rader kommer från modellen. Kontrollen, matchningen, differensen,
   säkerheten och hypotesen räknas i kod ur det modellen påstod och ur huvudboken. Ingen siffra i
   svaret är modellens egen slutsats.
3. **Tolkning skriver aldrig i böckerna.** Den kopplar inget underlag, postar inget, ändrar inte
   källans status och rör inte `vouchers`, `voucher_intake_sources` eller `attachments`. Allt det
   hör till `flode-underlag`.
4. **Enbolag, SEK.** Ett underlag i annan valuta tolkas, men matchas inte (§7.1).
5. **Ett underlag, ett köp.** Designens *"Ett kvitto kan innehålla flera köp och då behöver det
   delas upp"* är inte budgeterad här (§1, "Vad vi inte bygger").

→ Punkt 2 bär modulen. Om den ger vika blir `confidence` och `hypothesis` agentens ord i ett fält
som ser ut som data, vilket är just det `ANALYS.md` §7 varnar för.

---

## 1. Objektiv

### Problemet, konkret

`datakontrakt.md` §6:

> Flöde 4 steg 3 visar utläst leverantör, datum, belopp och moms mot bankhändelsen.
> ```
> POST /intake/{id}/interpret → { vendor, date, amount, vat, confidence,
>                                 match: { voucher_id, diff, hypothesis } }
> ```
> `hypothesis` är agentens förklaring till skillnaden och visas som en hypotes, inte som ett faktum.

Det som finns i dag: agenten kan läsa en fil men har ingenstans att lägga det den läste. Det
finns ingen matchning mot huvudboken och inget sparat spår av vad agenten såg i underlaget. Men
luckan är större än flöde 4:s jämförelserader, eftersom tre saker i dagens kod är fel eller
farliga (§2).

### Vad vi bygger

I den här ordningen:

1. **En lagning.** "Saknar underlag" räknar även underlag som kopplats via `voucher_intake_sources`
   (§2.1).
2. **Tabellen `intake_interpretations`**, append-only: en rad per tolkning (§5).
3. **Matchningen:** deterministisk, mot postade verifikationer som saknar underlag, med differens,
   momsjämförelse och en radbelagd hypotes (§7).
4. **Verktyget `tolka_underlag`**, sist i verktygslistan (§6).
5. **`GET /api/v1/intake/{id}/interpretation`**, som läser den senaste tolkningen (§8).
6. **Agentinstruktionen:** tolka före postning, och avstå när underlaget matchar något som redan
   är bokfört (§9).

### Vad vi inte bygger här

- Att **koppla** underlag till en verifikation, bokföra differensen, ersätta ett felkopplat
  underlag eller koppla ett intake-id via `POST /vouchers/{id}/attachments`. Det är
  `flode-underlag`.
- Någon **frontend**: `JamforelseRader` för flöde 4, filsläpp i `ChattFalt`, kompletteringslistan.
  Också `flode-underlag`.
- Att **dela upp** ett underlag med flera köp.
- **Valutaomräkning.**
- Ett eget **LLM-anrop** på servern (§12.1).

### Användare

- **Agenten**, i trådturen och i intagspasset: den får veta om underlaget redan har en
  verifikation, med vilken differens och varför.
- **`flode-underlag`**: den bygger jämförelseraderna och alternativen på tolkningen och läser den
  över `GET`.
- **Människan**, indirekt: räknaren "saknar underlag" slutar räkna verifikationer som har underlag.

### Framgång

1. En verifikation som agenten postade med ett kvitto räknas inte som "saknar underlag", varken i
   `GET /vouchers`, i `GET /overview` eller i `compliance`.
2. `tolka_underlag` på flöde 4:s kvitto (4 600 kr, 896 kr moms, en rad "Pant 120,00") mot A-118
   (4 480 kr) ger `diff_ore = 12000`, lika moms och en hypotes som pekar på raden "Pant".
3. Exakt match ger `match.kind = "exact"` och `hypothesis = null`.
4. Två lika goda kandidater ger `match = null` och båda i `candidates`. Servern väljer aldrig
   godtyckligt.
5. `confidence` beror bara på kontroller i kod. Modellen kan inte sätta den.
6. Intagspasset postar inte en ny verifikation för ett underlag som matchar en redan postad
   verifikation. Det avstår i stället, med matchningen som motivering.
7. Ingen `UPDATE` eller `DELETE` på `intake_interpretations`, och ingen ny kolumn på `vouchers`.

---

## 2. Fynden som formar modulen

### 2.1 "Saknar underlag" räknar för högt

`repositories/voucher_repo.py:15`:

```python
MISSING_ATTACHMENT_SQL = (
    "NOT EXISTS (SELECT 1 FROM attachments a WHERE a.voucher_id = vouchers.id)"
)
```

Systemet har två sätt att förse en verifikation med underlag, och predikatet känner bara till
det ena:

| Väg | Skriver i |
|---|---|
| `POST /vouchers/{id}/attachments` (`api/routes/attachments.py:90`) | `attachments` |
| Agentens postning (`services/voucher_posting.py:103`) | `voucher_intake_sources` |
| Ett trådförslag som postas (`services/draft_service.py:788`) | `voucher_intake_sources` |

Varje verifikation som agenten postar från ett kvitto, alltså normalfallet i agent-first, räknas
som "saknar underlag". Räknaren i headern, kompletteringslistan i flöde 4 och kandidaterna för
matchningen (§7) påverkas alla. Det är samma sorts fynd som `SPEC-oversikt.md` §2: en siffra som
ser rimlig ut för att ingen jämfört den med vad den påstår sig räkna.

`services/compliance.py:417` har en **egen kopia** av samma SQL, alltså SQL i en service, i strid
med lagerregeln. Den byter till det delade predikatet.

Lagningen, med §13.2:s undantag för SIE4-import (§12.5) inräknat:

```python
MISSING_ATTACHMENT_SQL = (
    "NOT EXISTS (SELECT 1 FROM attachments a WHERE a.voucher_id = vouchers.id)"
    " AND NOT EXISTS (SELECT 1 FROM voucher_intake_sources vis"
    " WHERE vis.voucher_id = vouchers.id)"
    " AND vouchers.created_by != 'sie4_import'"
)
```

Fortfarande härlett, fortfarande ingen migration och ingen trigger. Resonemanget i
`SPEC-oversikt.md` §3 står sig, predikatet var bara ofullständigt.

**Varför undantaget.** Efter omstarten (`SPEC-flode-verifikationer.md` §4.4) saknar varje
SIE4-importerad verifikation (`created_by = 'sie4_import'`) både `attachments` och
`voucher_intake_sources` — deras underlag finns i det gamla systemet, inte i Bok. Utan undantaget
fylls kompletteringslistan och matchningens kandidater (§7.2) av hundratals historiska rader.
Predikatet ska mäta det det påstår sig mäta, inte historik det aldrig kan koppla underlag till.

**Konsekvens vid driftsättning:** `missing_attachments` i `GET /overview` sjunker, både av
`voucher_intake_sources`-lagningen och av SIE4-undantaget. Det är rätt siffra, inte en regression,
och det ska stå i commit-meddelandet.

### 2.2 Ett underlag för något redan bokfört blir en dubbelpost

Köpet i flöde 4 (A-118) bokfördes från bankhändelsen, och kvittot kommer efteråt. I dag går det
kvittot vidare så här:

1. Människan släpper det i tråden → `POST /intake` → `intake_sources.status = 'pending'`.
2. `_attachment_posts` (`api/routes/threads.py:230`) skriver ett `user_file`-inlägg. Källan
   står kvar som `pending`.
3. Nästa intagspass (`services/agent_runtime.py:396`) läser `list_pending` och får kvittot som
   ett nytt underlag.
4. Ingenting i verktygen eller instruktionen jämför med postade verifikationer. Agenten postar en
   ny verifikation, och köpet är bokfört två gånger.

Passet körs bara manuellt (`SPEC-agentruntime.md` §12.3), så risken är inte akut, men den är
verklig. Matchningen är den första kod som kan se att det är samma köp. §9 använder den för att
göra steg 4 till ett avstående. Ett hårt stopp i postningen är en öppen fråga (§13.1).

### 2.3 Läsningen finns, platsen för det lästa saknas

`hamta_underlagsfil` ger modellen filen. `reconciliation_result`
(`services/agent_documents.py:297`) kan redan läsa netto, moms och totalt ur ett textlager och
stämma av dem. Men det modellen sedan tror att underlaget säger finns bara i dess eget
resonemang och i den text den skriver i tråden. Det finns inget att matcha mot, inget att visa
som jämförelserad och inget att granska i efterhand.

---

## 3. Tech stack och kommandon

Inget nytt beroende. Python 3.11, FastAPI, SQLite (WAL, trådlokala anslutningar enligt
`db/database.py`), `pypdf` för textlagret som i dag.

```bash
pytest tests/test_underlagstolkning.py -v
pytest tests/ -v
black . && isort . && flake8
mypy .                               # 61 fel är baslinjen; inga nya
python main.py --init-db             # tillämpar migration 030
```

---

## 4. Projektstruktur

```
db/migrations/030_add_intake_interpretations.sql   # tabellen + triggrar (§5)
domain/interpretation.py                           # Interpretation, Match, Candidate, Confidence
repositories/interpretation_repo.py                # insert, latest_for_source; ingen update/delete
repositories/voucher_repo.py                       # MISSING_ATTACHMENT_SQL (§2.1), match_candidates (§7.2)
services/interpretation.py                         # kontroller, säkerhet, matchning, hypotes
services/agent_tools.py                            # tolka_underlag, sist i _TOOL_SPECS
services/compliance.py                             # delat predikat i stället för egen SQL
api/routes/intake.py                               # GET /intake/{id}/interpretation
docs/to_agent/03_bokforingsinstruktion.md          # tolka före postning (§9) -- körtidsinnehåll
tests/test_underlagstolkning.py
```

`services/interpretation.py` innehåller ingen SQL och inga HTTP-begrepp.
Kandidatfrågan ligger i `voucher_repo`. Servicen gör kontrollerna och rankningen, som är ren
logik och testas utan databas.

**§12.5:** matchningens kandidater (§7) körs mot samma lagade predikat, alltså undantar även
kandidatfrågan `created_by = 'sie4_import'` — ingen egen SQL för det i `services/interpretation.py`.

---

## 5. Datamodell — migration 030

```sql
CREATE TABLE intake_interpretations (
    id                TEXT PRIMARY KEY,
    intake_source_id  TEXT NOT NULL REFERENCES intake_sources(id),
    -- Vad modellen läste (påståenden)
    vendor            TEXT,
    document_date     DATE,
    currency          TEXT NOT NULL DEFAULT 'SEK',
    total_ore         INTEGER NOT NULL,
    vat_ore           INTEGER,
    lines_json        TEXT NOT NULL DEFAULT '[]',   -- [{text, amount_ore, vat_rate}]
    -- Vad servern räknade (fakta, i tolkningsögonblicket)
    checks_json       TEXT NOT NULL,                -- §6.3
    confidence        TEXT NOT NULL,
    match_json        TEXT,                         -- §7.4, NULL = ingen entydig match
    candidates_json   TEXT NOT NULL DEFAULT '[]',
    expected_voucher_id TEXT REFERENCES vouchers(id),
    -- Vem och var
    actor             TEXT NOT NULL,
    agent_run_id      TEXT REFERENCES agent_runs(id),
    thread_id         TEXT REFERENCES threads(id),
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (confidence IN ('high', 'medium', 'low')),
    CHECK (total_ore >= 0),
    CHECK (vat_ore IS NULL OR vat_ore >= 0)
);
CREATE INDEX idx_interpretations_source ON intake_interpretations(intake_source_id, created_at);

CREATE TRIGGER prevent_update_intake_interpretations
BEFORE UPDATE ON intake_interpretations
BEGIN SELECT RAISE(ABORT, 'intake interpretations are append-only'); END;

CREATE TRIGGER prevent_delete_intake_interpretations
BEFORE DELETE ON intake_interpretations
BEGIN SELECT RAISE(ABORT, 'intake interpretations are append-only'); END;
```

**Varför append-only, och varför triggrar.** En tolkning är det agenten såg när den gjorde det
den gjorde. Den är underlaget för ett avstående i passet (§9) och, i `flode-underlag`, för en
koppling och kanske en korrigering. Om den gick att skriva över skulle spåret efter den kopplingen
kunna ändras i efterhand. Samma tre lager som för verifikationer (`AGENTS.md`): triggrar,
repository utan `update`/`delete`, och ingen endpoint som skriver. En ny tolkning av samma
underlag blir en ny rad, och den **senaste** är den som gäller.

**Varför matchningen sparas som ögonblicksbild.** Kandidaterna beror på huvudboken, och
huvudboken ändras: när kvittot kopplats saknar A-118 inte längre underlag och skulle försvinna
ur en omräknad matchning. Det agenten jämförde med ska gå att läsa i efterhand, så det sparas. Att
matchningen inte längre är aktuell räknas ut vid läsning (§8, `still_open`), aldrig genom att
raden ändras.

---

## 6. `tolka_underlag`

### 6.1 Vad det gör

Tar emot det modellen läste ur ett underlag, kontrollerar det, matchar det mot huvudboken, sparar
en tolkning och returnerar den. Verktyget är skrivskyddat mot böckerna men skriver en rad i
`intake_interpretations`. Det är **inte terminalt**: turen eller passet fortsätter efter svaret.

Verktyget finns på båda vägarna. I trådturen är det steg 3 i flöde 4. I intagspasset är det
kontrollen före `posta_verifikation` (§9).

### 6.2 Argumenten

```python
class TolkaUnderlagLine(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    amount_ore: int                      # rad inkl. moms; negativ för rabatt
    vat_rate: Optional[Literal[25, 12, 6, 0]] = None

class TolkaUnderlagArgs(BaseModel):
    source_id: str
    vendor: Optional[str] = Field(None, max_length=200)
    document_date: Optional[date] = None
    currency: str = Field("SEK", pattern="^[A-Z]{3}$")
    total_ore: int = Field(..., ge=0)
    vat_ore: Optional[int] = Field(None, ge=0)
    lines: list[TolkaUnderlagLine] = Field(default_factory=list, max_length=100)
    expected_voucher_id: Optional[str] = None
```

- **Belopp i öre**, som i resten av systemet. Modellen läser "4 600,00 kr" och skickar `460000`.
- **`lines` är valfri.** Utan rader går det inte att belägga en hypotes (§7.5), och det är det
  enda som saknas.
- **`expected_voucher_id`** är vad agenten tror att underlaget hör till, till exempel för att
  den själv bett om kvittot till A-118 i tråden. Det styr inte matchningen (§7.3). Servern
  räknar differensen mot den verifikationen och säger om en annan kandidat är bättre.
- **Det finns inget fält för `confidence` och inget för `hypothesis`.** Det är avsiktligt (§12.3).

Beskrivning i verktygslistan:

> Lämna det du läst ur ett underlag (leverantör, datum, belopp, moms, rader) för kontroll och
> matchning mot huvudboken. Servern stämmer av momsen och textlagret, letar efter en postad
> verifikation som saknar underlag och räknar differensen. Sparar tolkningen men kopplar
> ingenting och ändrar ingenting i bokföringen. Anropa efter hamta_underlagsfil och före
> posta_verifikation eller foresla_verifikation för samma underlag.

### 6.3 Kontrollerna

Alla körs, och ingen avvisar anropet utom de hårda felen längst ned. Resultatet sparas i
`checks_json`:

| Nyckel | Värden | Regel |
|---|---|---|
| `lines_sum` | `ok` · `mismatch` · `not_applicable` | Σ`lines.amount_ore` = `total_ore`, ±1 öre per rad; `not_applicable` utan rader |
| `vat_rate` | `ok` · `mismatch` · `not_applicable` | Varje rad med `vat_rate`: momsen ur raden räknad baklänges; Σ = `vat_ore` ±1 öre per rad |
| `vat_share` | `ok` · `implausible` · `not_applicable` | Utan rader: `vat_ore / (total_ore − vat_ore)` ligger nära 25, 12 eller 6 %, ±0,5 procentenheter, eller är 0 |
| `text_layer` | `agrees` · `disagrees` · `not_available` | PDF med textlager där `reconciliation_result` hittar ett trippel som går ihop: dess `total_ore` och `vat_ore` jämförs med modellens, och en läsning utan `vat_ore` mot en text med moms är `disagrees`. Bild, skannad PDF, inget trippel eller ett trippel som inte går ihop: `not_available` (§12.6) |
| `date` | `ok` · `future` · `missing` | `document_date` efter i dag → `future` |
| `currency` | `sek` · `not_sek` | `not_sek` stänger av matchningen (§7.1) men sänker inte säkerheten |

`text_layer` återanvänder `extract_pdf_text` och `reconciliation_result`. Filen läses igen på
servern, vilket kostar millisekunder och inga token. Det är den enda kontroll där servern har en
egen källa att jämföra modellen med. Därför är det den som skiljer `high` från `medium`.

Hårda fel: okänd `source_id` → `IntakeError("source_not_found")`. En källa med status `deleted`
→ `IntakeError("source_deleted")`. `las_underlag` ger andra koder (`intake_not_found`) och
avvisar inte en raderad källa; den ändras inte här (§12.6).

### 6.4 Säkerheten

Räknas ur kontrollerna, aldrig ur modellen:

| `confidence` | Villkor |
|---|---|
| `high` | `text_layer = agrees`, och ingen kontroll är `mismatch`/`implausible`/`disagrees`/`future` |
| `medium` | `text_layer = not_available`, och ingen kontroll är `mismatch`/`implausible`/`future` |
| `low` | Allt annat, inklusive `text_layer = disagrees` |

Tre nivåer, inte ett tal. Ett tal mellan 0 och 1 skulle se mer exakt ut än underlaget det räknas
ur. `low` betyder att underlaget ska läsas om eller att människan ska tillfrågas. Designens
*"Oläsbar bild: agenten ber om en ny i stället för att gissa fram belopp"* står i instruktionen
(§9), inte i koden.

### 6.5 Svaret

```json
{
  "interpretation_id": "…",
  "source_id": "…",
  "read": { "vendor": "Elektronikhuset", "document_date": "2026-06-03",
            "currency": "SEK", "total_ore": 460000, "vat_ore": 89600,
            "lines": [ { "text": "USB-C docka", "amount_ore": 448000, "vat_rate": 25 },
                       { "text": "Pant", "amount_ore": 12000, "vat_rate": 0 } ] },
  "checks": { "lines_sum": "ok", "vat_rate": "ok", "vat_share": "not_applicable",
              "text_layer": "agrees", "date": "ok" },
  "confidence": "high",
  "match": { "kind": "amount_diff", "voucher_id": "…", "voucher_number": "A-118", "…": "§7.4" },
  "candidates": [ "…" ],
  "expected": null
}
```

`read` är det modellen skickade, oförändrat, så att det som sparades och det som visas är samma
sak. `expected` fylls när `expected_voucher_id` gavs (§7.3).

### 6.6 Placering i verktygslistan

Sist i `_TOOL_SPECS`, efter `foresla_verifikation`. Listan är en del av det cachade prefixet
(`SPEC-agentruntime.md` §6.6), och ett tillägg sist kostar en cache-miss en gång. Ett tillägg i
mitten gör samma sak men flyttar varje senare verktyg. Det blir det tolfte verktyget.
`agentruntime`s testfall 17 körs mot den utökade listan, som i `beslut` och `flode-verifikationer`.

`tool_context` öppnas bara för spårbarheten: `thread` → `thread_id`, och turens `agent_run_id`
om det finns. Verktyget fungerar utan båda: då är det ett anrop från intagspasset eller ett
testanrop.

---

## 7. Matchningen

### 7.1 Vad som matchas mot vad

Underlaget matchas mot **postade verifikationer som saknar underlag** (§2.1:s lagade predikat),
utom serie `IB`. Det är de som kan få underlaget kopplat. En verifikation som redan har underlag
är ingen kandidat. Ett andra underlag till samma köp, eller ett felkopplat underlag som ska
ersättas, är ett annat fall än flöde 4 och hör till `flode-underlag`.

Underlag i annan valuta än SEK matchas inte: `match = null`, `candidates = []`,
`checks.currency = "not_sek"`. Att räkna om med en kurs vore att hitta på ett belopp.

**Verifikationens belopp** är summan av debetraderna, alltså bruttobeloppet för ett köp. Är
verifikationen kopplad till en bankhändelse (`voucher_bank_transactions`) visas den som
jämförelserad med sitt eget belopp och datum. Det är designens *"bankhändelse"*, men differensen
räknas mot verifikationen, eftersom det är den som ska få underlaget.

**Verifikationens moms** är summan av raderna på konton av typ `VAT_IN`. Den jämförs med
`vat_ore` om båda finns (`match.vat.equal`). Designens *"Momsen på 896 kr stämmer i båda
underlagen"* är det fältet.

### 7.2 Kandidaterna

En fråga i `voucher_repo.match_candidates(document_date, total_ore, window)`, med de härledda
beloppen joinade in i frågan. Aldrig en fråga per kandidat, samma krav som i
`SPEC-oversikt.md` §3.

- **Datumfönster:** verifikationens datum i `[document_date − 3, document_date + 7]` dagar.
  Kortköp dras oftast 0–3 bankdagar efter köpet. Fönstret är asymmetriskt för att bankdatumet
  nästan aldrig ligger före kvittots datum, men kan göra det över en helg.
- **Beloppsfönster:** `|diff| ≤ max(5 000 öre, 10 % av total_ore)`. Ett kvitto som skiljer mer än
  så är inte samma köp med en pantavgift utan ett annat köp.
- Saknas `document_date`: inget datumfönster, bara exakt belopp. Utan datum är en ungefärlig
  matchning bara en gissning.

Konstanterna står i `services/interpretation.py`, inte i `config.py`. De är en del av
matchningens definition och inget att driftsätta olika.

### 7.3 Rankningen och entydigheten

Kandidaterna sorteras på, i den här ordningen:

1. `|diff_ore|` stigande
2. `|date_diff_days|` stigande
3. Leverantörsträff: `vendor` finns, skiftlägesokänsligt, i verifikationens `description` eller
   i den kopplade bankhändelsens `counterpart_name`/`description`

`match` sätts till den första **bara om den är entydig**: ingen annan kandidat är lika på alla
tre nycklarna. Är två lika väljer servern inte. `match = null` och båda står i `candidates`,
eftersom designens *"Filer kan komma utan sammanhang. Då måste agenten fråga vilken verifikation
det gäller"* ska vara agentens fråga, inte serverns gissning. `candidates` bär högst fem.

`expected_voucher_id` ändrar inte rankningen. Om den ges räknas `expected` fullt ut (differens,
moms, hypotes) mot just den verifikationen, även om den ligger utanför fönstren, och med
`expected.is_best_match: bool`. Då kan agenten säga *"du bad om kvittot till A-118, men det här
ser ut att höra till A-109"*, och servern har inte i tysthet bytt verifikation.

### 7.4 `match`

```json
{
  "kind": "exact",
  "voucher_id": "…", "voucher_number": "A-118", "voucher_date": "2026-06-03",
  "voucher_description": "Förbrukningsinventarier",
  "amounts": { "document_ore": 460000, "voucher_ore": 448000 },
  "diff_ore": 12000,
  "date_diff_days": 0,
  "vat": { "document_ore": 89600, "voucher_ore": 89600, "equal": true },
  "bank_transaction": { "id": "…", "date": "2026-06-03", "amount_ore": -448000,
                        "counterpart_name": "ELEKTRONIKHUSET" },
  "hypothesis": { "text": "…", "basis": "line_items", "lines": [1] }
}
```

`kind` är `exact` när `diff_ore = 0` och `date_diff_days ≤ 3`, annars `amount_diff`. Designens
*"Exakt match ska hoppa över det här steget"* läser `kind`. Klienten räknar aldrig själv på
`diff_ore`.

`diff_ore` är `document − voucher`. Positivt betyder att underlaget är större än det som
bokförts.

### 7.5 `hypothesis`

Sätts **bara** när rader på underlaget förklarar differensen (§12.3):

1. En rad vars `amount_ore` = `diff_ore`, ±1 öre.
2. Annars den minsta mängden av högst tre rader vars summa = `diff_ore`, ±1 öre per rad. Tre rader
   av högst hundra ger under 170 000 kombinationer, och sökningen avbryts vid första träff per
   storlek.
3. Flera lika små mängder → ingen hypotes. Tvetydighet är inte en förklaring.

Texten formuleras av servern, som en hypotes:

> Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.

Med `basis: "line_items"` och radernas index. Förklarar ingen rad differensen är `hypothesis =
null`. Agenten får gissa fritt i sin text i tråden, där gissningen står som agentens ord, men
gissningen kommer aldrig in i ett fält som `flode-underlag` visar som jämförelse.

Designens *"Skillnaden ser ut att vara en pantavgift på en separat rad"* är agentens formulering i
tråden. Serverns hypotes är beläggningen för den.

---

## 8. `GET /api/v1/intake/{id}/interpretation`

Bearer-autentiserad som resten av `/intake`. Returnerar den **senaste** tolkningen av källan, i
samma form som verktygets svar (§6.5), plus:

- `created_at`, `actor`, `thread_id`, och `superseded_count` (hur många äldre tolkningar som
  finns). Historiken listas inte här, eftersom ingen vy behöver den ännu.
- `match.still_open: bool`, härlett vid läsning: verifikationen saknar fortfarande underlag
  **och** källan är inte kopplad. Ögonblicksbilden ändras aldrig.

`404 interpretation_not_found` om källan finns men aldrig tolkats. `404 source_not_found` om
källan inte finns.

Varför `GET` och inte datakontraktets `POST /intake/{id}/interpret`: tolkningen görs av agenten i
en tur, med turens modell och budget (§12.1). En `POST` som människan kunde anropa skulle behöva
ett eget LLM-anrop för att göra något. `flode-underlag` läser resultatet, den startar det inte.
Avvikelsen från datakontraktet står i §12.1.

---

## 9. Agentinstruktionen

`docs/to_agent/03_bokforingsinstruktion.md` är körtidsinnehåll (`AGENTS.md`). Ändringen är en
beteendeändring och testas som en: `tests/test_agent_entrypoint.py` får nya påståenden.

Tillägget, i sak:

1. **Innan du postar eller föreslår en verifikation för ett underlag:** läs filen och anropa
   `tolka_underlag`.
2. **`match.kind = "exact"`** eller **`amount_diff` med hypotes:** underlaget hör sannolikt till
   en redan postad verifikation. I passet: **posta inte**. Avstå med `registrera_avstaende`, och
   skriv verifikationsnumret och differensen i motiveringen. I tråden: säg vad du hittat, med
   båda beloppen. Kopplingen görs i `flode-underlag`.
3. **`match = null` med kandidater:** fråga vilken verifikation det gäller. Välj inte själv.
4. **`confidence = "low"`:** gissa inte fram ett belopp. Be om ett nytt underlag eller säg vad som
   inte stämmer.
5. **Hypotesen:** återge den som en hypotes. Förklarar ingen rad differensen, säg det, och gissa
   bara om du uttryckligen säger att det är en gissning.

Punkt 2 i passet är vad §2.2:s dubbelpost stoppas med i den här modulen: en instruktion, inte en
spärr. Om den räcker är §13.1.

---

## 10. Teststrategi

`pytest`, i `tests/test_underlagstolkning.py`. Kontrollerna, säkerheten, rankningen och hypotesen
är ren logik och testas utan databas. Kandidatfrågan och verktyget testas mot testdatabasen som i
`tests/test_flode_verifikationer.py`. Inget test gör ett LLM-anrop: verktyget anropas direkt
med `execute_tool`, och sessionsfallen använder den skriptade klienten från `agentruntime`.

### 10.1 Predikatet

| # | Fall | Förväntat |
|---|---|---|
| 1 | Postad, rad i `attachments` | `missing_attachment = false` |
| 2 | Postad, rad i `voucher_intake_sources`, ingen i `attachments` | `false` (i dag: `true`) |
| 3 | Postad, ingetdera | `true` |
| 4 | `GET /overview`, `GET /vouchers?missing_attachment=true` och `compliance` på samma data | Samma tal |
| 5 | `services/compliance.py` | Ingen egen SQL för predikatet (grep-test) |
| 5b | Postad, `created_by = 'sie4_import'`, ingetdera av `attachments`/`voucher_intake_sources` | `missing_attachment = false` (§12.5) |

Fall 5b är lettrat för att inte rubba numreringen på 6–40, som andra avsnitt hänvisar till.

### 10.2 Kontrollerna och säkerheten

| # | Fall | Förväntat |
|---|---|---|
| 6 | Rader summerar till totalen | `lines_sum = ok` |
| 7 | Rader summerar fel med 2 öre över tre rader | `ok` (±1 per rad) |
| 8 | Rader summerar fel med 100 öre | `mismatch`, `confidence = low` |
| 9 | 25 %-rad, moms stämmer | `vat_rate = ok` |
| 10 | Utan rader, moms 20 % av netto | `vat_share = implausible`, `low` |
| 11 | PDF med textlager, samma totalt och moms | `text_layer = agrees`, `high` |
| 12 | PDF med textlager, modellen läste 4 600 där texten säger 4 060 | `disagrees`, `low` |
| 13 | Bild | `text_layer = not_available`, bäst `medium` |
| 14 | Datum i morgon | `date = future`, `low` |
| 15 | `confidence` i argumenten | `422`-motsvarighet: `invalid_tool_arguments` (fältet finns inte) |

### 10.3 Matchningen

| # | Fall | Förväntat |
|---|---|---|
| 16 | Flöde 4: kvitto 4 600 / A-118 4 480, samma dag, rad "Pant 120" | `amount_diff`, `diff_ore = 12000`, hypotes på raden, `vat.equal` |
| 17 | Exakt belopp, bankdatum två dagar senare | `kind = exact`, `hypothesis = null` |
| 18 | Två kandidater med samma belopp och datum, ingen leverantörsträff | `match = null`, båda i `candidates` |
| 19 | Samma som 18, men leverantören finns i den enas bankhändelse | `match` = den |
| 20 | Kandidat med underlag (via `voucher_intake_sources`) | Ingen kandidat |
| 21 | Kandidat i serie `IB` | Ingen kandidat |
| 22 | Utanför datumfönstret | Ingen kandidat |
| 23 | Diff 6 000 öre på 20 000 | Utanför beloppsfönstret, ingen kandidat |
| 24 | `document_date` saknas | Bara exakt belopp matchar |
| 25 | `currency = EUR` | `match = null`, `candidates = []`, `checks.currency = not_sek` |
| 26 | `expected_voucher_id` = en sämre kandidat | `expected` räknat mot den, `is_best_match = false`, `match` oförändrad |
| 27 | Differens förklaras av två rader tillsammans | Hypotes med båda raderna |
| 28 | Differens förklaras av två olika enskilda rader | `hypothesis = null` |
| 29 | Kandidatfrågan | Ett SQL-anrop oavsett antal kandidater |

### 10.4 Lagring, verktyget och läsvägen

| # | Fall | Förväntat |
|---|---|---|
| 30 | `UPDATE`/`DELETE` på `intake_interpretations` | Triggern avbryter |
| 31 | Två tolkningar av samma källa | Två rader; `GET` ger den senare, `superseded_count = 1` |
| 32 | Tolkning, sedan koppling av källan | `GET`: ögonblicksbilden oförändrad, `still_open = false` |
| 33 | `tolka_underlag` | Inga ändringar i `vouchers`, `voucher_intake_sources`, `attachments` eller `intake_sources.status` |
| 34 | `AGENT_TOOL_DEFINITIONS` | `tolka_underlag` sist; de elva före oförändrade byte för byte |
| 35 | Verktyget från trådturen | `thread_id` och `agent_run_id` satta |
| 36 | Okänd källa / raderad källa | `source_not_found` / `source_deleted` |
| 37 | `GET` utan tolkning | `404 interpretation_not_found` |

### 10.5 Instruktionen och passet

| # | Fall | Förväntat |
|---|---|---|
| 38 | `tests/test_agent_entrypoint.py` | Instruktionen nämner `tolka_underlag` före postning och avstående vid match |
| 39 | Skriptat pass: kvitto som matchar A-118 exakt | `registrera_avstaende` med `A-118` i motiveringen; ingen ny verifikation |
| 40 | Regression | `pytest tests/` grönt; `black`, `isort`, `flake8` rena; `mypy` ≤ 61 |

Fall 39 är skriptat: det testar att vägen fungerar när modellen följer instruktionen, inte att en
riktig modell gör det. Det senare är §11:s kriterium 6 och kräver en körning med riktig LLM.

---

## 11. Framgångskriterier

Modulen är klar när:

1. Predikatet räknar `voucher_intake_sources` och används på alla fyra ställen (fall 1–5).
2. `tolka_underlag` finns sist i listan, sparar en tolkning och ändrar ingenting i böckerna
   (33, 34).
3. Flöde 4:s exempel ger designens siffror: 4 600 mot 4 480, differens 120, lika moms, hypotes på
   pantraden (16).
4. Servern väljer aldrig mellan lika kandidater (18) och byter aldrig i tysthet bort den
   verifikation agenten förväntade sig (26).
5. `confidence` och `hypothesis` kan inte sättas av modellen (15, 28).
6. Skriptat pass avstår i stället för att dubbelposta (39). Med riktig LLM: ett kvitto för en
   bankbokförd verifikation ger ett avstående, inte en ny verifikation. Det kontrolleras av
   beställaren tillsammans med `flode-verifikationer`s visuella kontroll.
7. `intake_interpretations` är append-only i tre lager (30, repository utan `update`/`delete`,
   ingen skrivande endpoint).
8. `pytest tests/ -v`, `black`, `isort`, `flake8` rena; `mypy .` inte över baslinjen 61.

---

## 12. Beslut

### 12.1 Verktyg och läsväg, inte en endpoint med eget LLM-anrop — **BESLUTAT 2026-09-24**

Datakontraktet ritar `POST /intake/{id}/interpret`. Det skulle kräva ett andra LLM-anrop från
servern, utanför trådturen: eget modellval, egen budgetredovisning i `agent_runs`, och 5–30
sekunders synkront väntande i en HTTP-förfrågan. Agenten läser redan filen i turen. Det som
saknades var platsen för det den läste och en matchning i kod. `flode-underlag` läser resultatet
med `GET`.

### 12.2 Predikatet lagas här, först — **BESLUTAT 2026-09-24**

Matchningens kandidater är "postade verifikationer som saknar underlag". Med dagens predikat är
varje agentpostad verifikation en kandidat för ett kvitto den redan har. Lagningen är första
uppgiften, och siffran i headern sjunker vid driftsättning.

### 12.3 `hypothesis` bara när en rad bär den — **BESLUTAT 2026-09-24**

Servern skriver hypotesen, och bara när rader på underlaget summerar till differensen. Agentens
egna förklaringar står i tråden som agentens text. Alternativet, ett fritextfält i verktyget, hade
placerat modellens formulering i något som `flode-underlag` visar bredvid två belopp, alltså i
något som ser ut som data.

### 12.4 Hårt stopp i postningen skjuts till `flode-underlag` — **BESLUTAT 2026-09-28**

Svar på §13.1. Ett stopp i `posta_verifikation`/`foresla_verifikation`
(`source_matches_posted_voucher`) utan en kopplingsväg att peka på i felet blir bara ett nytt
avstående utan utväg. Instruktionen i §9 är spärren för fas 1, och skriptat testfall 39 visar att
den håller när modellen följer den. En riktig spärr väntar till `flode-underlag`, som ger en väg
att koppla underlaget — då kan felet hänvisa dit. Ingen kodändring i den här modulen av detta.

### 12.5 `created_by = 'sie4_import'` undantas i predikatet — **BESLUTAT 2026-09-28**

Svar på §13.2. SIE4-importerade verifikationers underlag finns i det gamla systemet, inte i
`attachments` eller `voucher_intake_sources` — predikatet kan aldrig se dem som annat än "saknar
underlag" om det inte undantar dem uttryckligen. Utan undantaget fylls kompletteringslistan och
matchningens kandidater (§7.2) av historik. §2.1:s predikat utökas med
`AND vouchers.created_by != 'sie4_import'`, vilket ändrar vad "saknar underlag" betyder men gör
predikatet sant mot det det påstår sig mäta. Fall 5b (§10.1).

### 12.6 Efter U1–U10: modulens öppna frågor — **BESLUTAT 2026-09-28**

Frågorna (a)–(h) under "Kvar för beställaren" i `tasks/underlagstolkning/todo.md`. (b) och (g)
är införda i texten ovan; resten är uppgifterna U11–U15.

- **(a) `agent_run_id` förs fram.** Trådturen och intagspasset lägger körningens id i
  `tool_context`, så att `intake_interpretations.agent_run_id` fylls i drift. → U11.
- **(b) Felkoderna står för sig.** `source_not_found`/`source_deleted` enligt §6.3;
  "samma fel som `las_underlag`" struket. `las_underlag` är oförändrad.
- **(c) Beskrivningen skrivs om.** §6.2:s text nämner inte "huvudboken"; regeln att bara
  `posta_verifikation` nämner den gäller igen utan undantag. De elva första verktygen orörda.
  → U12.
- **(d) `kind = "exact_no_date"`.** Exakt belopp utan `document_date` är en egen sort: agenten
  avstår i passet och frågar i tråden med verifikationsnumret, men ett hårt stopp i
  `flode-underlag` (§12.4) slår bara på `exact`. Utan datum skiljer ingenting ett återkommande
  belopp (hyra, abonnemang) från samma köp. → U13.
- **(e) `expected` sparas.** Migration 031 lägger till `expected_json` på
  `intake_interpretations`. Läsvägen visar den sparade jämförelsen; ingenting räknas om mot dagens
  huvudbok. → U14.
- **(f) HTTP-väg.** `POST /api/v1/intake/{id}/interpretation` med samma argument och service som
  verktyget, så att externa sessioner kan följa instruktionens punkt 1. Den skriver bara en ny
  tolkningsrad: append-only gäller (inga PUT/PATCH/DELETE), inget LLM-anrop (§12.1 står). → U15.
- **(g) `text_layer`.** Ett trippel som inte går ihop är ingen källa att jämföra med
  (`not_available`, högst `medium`). En läsning utan moms mot en text med moms är en felläsning
  (`disagrees`, `low`). Infört i §6.3.
- **(h) Raderad källa i läsvägen.** `GET` ger 200 som förut, men svaret bär `source_status`, så
  att klienten ser att källan är raderad. Tolkningen är en del av spåret. → U14.

---

## 13. Öppna frågor — besvarade 2026-09-28

Ingen blockerade starten. Båda är nu beslutade, se §12.4 (§13.1) och §12.5 (§13.2). Texten nedan
står kvar som historik för resonemanget bakom besluten.

1. **Räcker instruktionen mot dubbelposten (§2.2)?** Den här modulen stoppar den med en
   instruktion (§9). Ett hårt stopp vore att `posta_verifikation` och `foresla_verifikation`
   vägrar (`source_matches_posted_voucher`) när källans senaste tolkning har `match.kind = exact`
   och `still_open`. Det ändrar postningens regler och är därför ett "fråga först". Förslag: vänta
   till `flode-underlag`, när det finns en kopplingsväg att hänvisa till i felet. Ett stopp utan
   väg framåt blir ett nytt avstående. → **Ja, vänta.**

2. **Ska SIE4-importerade verifikationer räknas som "saknar underlag"?** Efter omstarten
   (`SPEC-flode-verifikationer.md` §4.4) har varje importerad verifikation (`created_by =
   'sie4_import'`) varken `attachments` eller `voucher_intake_sources`. Deras underlag finns i det
   gamla systemet. Kompletteringslistan och räknaren fylls då av historik, och matchningen får
   hundratals kandidater. Förslag: undanta `created_by = 'sie4_import'` i predikatet. Det är en
   ändring av vad "saknar underlag" betyder och behöver ett ja. → **Ja, undanta.**

---

## 14. Gränser

**Alltid:**
- Tester före implementation, och predikatet (§2.1) först, med sina tester gröna.
- Ny SQL i `repositories/`, aldrig i en service eller route.
- Belopp i öre, heltal, genom hela modulen.
- Varje tolkning är en ny rad, och den senaste gäller.

**Fråga först:**
- Allt som skriver i `vouchers`, `voucher_intake_sources`, `attachments` eller ändrar
  `intake_sources.status`.
- Ett stopp i postningen — avgjort till "vänta" för den här modulen (§12.4), hör till
  `flode-underlag`.
- Att ändra vad "saknar underlag" betyder utöver §2.1 och SIE4-undantaget (§12.5).
- En ändring av matchningens fönster efter att modulen är klar.

**Aldrig:**
- Ett fält där modellen sätter `confidence`, `hypothesis`, `diff` eller `match`.
- Att servern väljer mellan lika kandidater.
- `UPDATE` eller `DELETE` på en tolkning.
- Ett LLM-anrop från den här modulens kod.
