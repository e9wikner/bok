# Spec: `oversikt`

Modul-id `oversikt` i kapabilitetskartan (`ANALYS.md` §8). Beror på ingenting. `skal` beror på
den här — headern kan inte ritas förrän sidräknarna finns i ett anrop.

Status: **Fas 1 — skriven 2026-09-21.** Uppgifterna ligger i `tasks/oversikt/plan.md` och
`tasks/oversikt/todo.md` (O1–O5). Modulen är **klar** 2026-09-21: O1–O5 avbockade,
avvikelserna och besluten står sist i `todo.md`.

---

## Antaganden

1. **Enbolag.** Räknarna gäller installationen, inte ett bolag i en lista. Samma antagande som
   `ANALYS.md` §1.4 och samma beslut som `view_key` i `tradar`.
2. **Ingen migration.** Allt modulen levererar är härlett ur tabeller som redan finns. Se §3 —
   det är inte en bekvämlighet utan den enda formen som inte bryter append-only.
3. **Formen låses nu, siffrorna växer in.** Två av fem räknare hör egentligen hemma i moduler som
   inte är byggda (`beslut`, och lönens fyra spår). De får en ärlig approximation i dag och byts
   ut inifrån utan att payloaden ändras. Se §5.
4. **Läsvägar bara.** Modulen skriver ingenting, låser ingenting och rör inte huvudboken.

---

## 1. Objektiv

### Problemet, konkret

`design_handoff_bokai/datakontrakt.md` §8:

> Sidtabbarna visar en prick där något väntar, och sidans metarad visar vad. Utan ett aggregat
> blinkar headern medan fyra anrop landar.

Så ser det ut i dag. `frontend-v3/app/page.tsx` — dagens Översikt — avfyrar **åtta** parallella
hookar (`useHealth`, `useFiscalYears`, `useVouchers` två gånger, `useInvoiceDrafts`,
`useInvoices`, `useComplianceIssues`, `useAccountingCorrections`) plus en nionde som är kedjad på
räkenskapsårssvaret. Den räknar dessutom fakturautkast **i klienten**, genom att filtrera på
`status in ("draft", "needs_review")` och summera två källor. Det är precis den logik
datakontraktets regel 2 säger hör hemma på servern: *agenten räknar, klienten formaterar.*

Och underlagsflödet (flöde 4) börjar i en lista som inte går att fråga efter:

> ```
> GET /vouchers?missing_attachment=true&sort_by=age
> ```
> Verifikationen behöver ett fält för kompletteringsflaggan (satt när den postas utan underlag,
> borta när ett underlag kopplas) och en ålder i dagar, som driver färgen i vyn.

### Vad vi bygger

Tre saker, i den ordningen:

1. En lagning: `services/compliance.py::_check_missing_attachments` har aldrig fungerat (§2).
2. `missing_attachment` och `age_days` som **härledda** fält på verifikationen, plus filtret och
   sorteringen som flöde 4 börjar i.
3. `GET /api/v1/overview` — ett anrop som ger alla tre sidornas räknare.

### Vad vi inte bygger här

`GET /decisions` (modulen `beslut`), lönens fyra spår (`payment_file`, `agi` — ur scope enligt
`ANALYS.md`, beslutspunkt 2), någon frontend, och någon persistent flagga på verifikationen.

### Framgång

1. `GET /api/v1/overview` svarar med alla tre sidornas räknare i ett anrop, utan att någon räknare
   beräknas i klienten.
2. `GET /api/v1/vouchers?missing_attachment=true&sort_by=age` returnerar postade verifikationer
   utan bilaga, äldst först.
3. Kompletteringskontrollen i `compliance` producerar issues mot riktiga data.
4. Ingen ny tabell, ingen ny kolumn, ingen ny trigger.
5. Listvyn gör inte fler SQL-anrop per rad än i dag.

---

## 2. Fyndet som ändrar modulen: kontrollen är död kod

`ANALYS.md` §5 rad 6 säger *"Billigare än det låter — logiken finns redan i
`services/compliance.py:359` (`_check_missing_attachments`)."*

Det stämmer inte. `services/compliance.py:399`:

```sql
LEFT JOIN voucher_attachments va ON va.voucher_id = v.id
```

`voucher_attachments` finns inte. `grep -rn "voucher_attachments" --include="*.py" --include="*.sql"`
över hela repot ger **den här enda raden**. Tabellen heter `attachments`
(`db/migrations/001_initial_schema.sql:97`). Frågan kastar `no such table`, och funktionen
avslutas med:

```python
except Exception:
    pass  # attachments table might not exist
```

Kontrollen har alltså aldrig producerat en enda issue sedan den skrevs. Den räknas i
`run_all_checks` och ser grön ut just därför att den är tyst.

Två följder för specen:

- Lagningen är en egen uppgift (O1) och landar **före** allt annat, så att resten av modulen
  byggs mot data som finns.
- Den nakna `except Exception: pass` tas bort. Ett trasigt schema ska synas. Det finns en
  svälj till, på `services/compliance.py:381` i `_check_unbooked_bank_transactions` — den rörs
  **inte** här. En svälj i taget, och den andra hör inte till den här modulen.

Tröskeln `> 50000` är öre, alltså 500 kr, och matchar titeln `"… verifikationer >500 SEK saknar
underlag"`. Den är rätt och lämnas.

---

## 3. Kompletteringsflaggan är härledd, inte lagrad

Datakontraktet säger "Verifikationen behöver **ett fält** för kompletteringsflaggan (satt när den
postas utan underlag, borta när ett underlag kopplas)". Läst som en kolumn är det omöjligt:

`db/migrations/014_add_posted_voucher_immutability_triggers.sql`:

```sql
CREATE TRIGGER IF NOT EXISTS prevent_update_posted_vouchers
BEFORE UPDATE ON vouchers
WHEN OLD.status = 'posted'
BEGIN
    SELECT RAISE(ABORT, 'posted vouchers are immutable');
END;
```

*Varje* `UPDATE` på en postad verifikation avbryts. Att sätta eller ta bort en flagga på en
postad verifikation är per definition en `UPDATE` på en postad verifikation. Vägarna vore att
undanta kolumnen i triggerns `WHEN`-villkor — vilket gör append-only till en fråga om vilken
kolumn någon råkar röra — eller att lägga flaggan i en sidotabell som måste hållas i synk.

Båda är fel. Beskrivningen i datakontraktet är ordagrant definitionen av ett **härlett** värde:

```sql
NOT EXISTS (SELECT 1 FROM attachments a WHERE a.voucher_id = vouchers.id)
```

Satt när den postas utan underlag: sant, eftersom ingen rad finns. Borta när ett underlag
kopplas: sant, eftersom raden finns. Ingen synkronisering kan gå sönder, ingen trigger behöver
mjukas upp, och ingen migration behövs.

`age_days` på samma sätt: `julianday('now') - julianday(vouchers.date)`, avrundat nedåt. Åldern
räknas från verifikationens datum, inte från `posted_at` — det är affärshändelsens ålder som
driver färgen i vyn, inte bokföringstillfällets.

**Prestandakravet:** `repositories/voucher_repo.py::list_all` hämtar i dag bara `id` och anropar
sedan `VoucherRepository.get(id)` per rad (`voucher_repo.py:224-229`), som i sin tur gör två
frågor till. Det är N+1 redan innan den här modulen. De två härledda fälten ska joinas in i
**sidfrågan**, aldrig hämtas per rad. Blir det naturligt att laga N+1 i samma svep är det
välkommet; blir det inte det, får det inte bli värre.

---

## 4. `GET /api/v1/vouchers` — filtret och sorteringen

Två nya queryparametrar, i mönstret som redan finns (`voucher_repo.py:165-230` bygger
`where_clauses`/`params`):

| Parameter | Värden | Betydelse |
|---|---|---|
| `missing_attachment` | `true` \| `false` \| utelämnad | `true` → bara postade utan bilaga. `false` → bara med. Utelämnad → filtrera inte |
| `sort_by` | `date` \| `number` \| `age` | `age` sorterar på verifikationens datum med `sort_order=asc` som standard, alltså äldst först. `age` och `date` sorterar på samma kolumn; skillnaden är standardriktningen och att `age` är namnet datakontraktet använder |

`sort_by` är vitlistat till `{"date", "number"}` på `voucher_repo.py:208`. `age` läggs till där.
Vitlistan är säkerhetsgränsen mot SQL-injektion i `ORDER BY` — den ska förbli en vitlista.

Två nya fält i `VoucherResponse` (`api/schemas.py:126`): `missing_attachment: bool` och
`age_days: int`. Båda beräknade, aldrig inskickade.

### Den tysta grenen

`api/routes/vouchers.py:682` har två helt skilda kodvägar:

- med `period_id` → `ledger.vouchers.list_for_period(...)`, sedan filtrering **i Python**;
  `limit`, `offset`, `search` och `sort_*` ignoreras **tyst**.
- utan `period_id` → `VoucherRepository.list_all(...)`, SQL-filtrering och riktig `total`.

Det är en befintlig fälla och den här modulen får inte fördjupa den. `missing_attachment` ska
antingen fungera likadant i båda grenarna, eller avvisas med `400` i den gren som inte kan
hedra det. **Tyst ignorering är inte ett alternativ** — en vy som ber om "saknar underlag" och
får allt tillbaka visar fel bokföring för en människa som ska fatta beslut.

---

## 5. `GET /api/v1/overview`

### Formen

Tre sidor, namngivna som i informationsarkitekturen (`design_handoff_bokai/README.md`):

| Sidnyckel | Titel | Vyer |
|---|---|---|
| `bocker` | Böcker | Balansräkning, Resultaträkning, Verifikationer |
| `betala` | Fakturering och löner | Fakturering, Löner |
| `bokslut` | Bokslut | Rapporter, Åtgärder och nyckeltal |

```jsonc
{
  "fiscal_year": { "id": "…", "label": "2026", "start": "2026-01-01", "end": "2026-12-31" },
  "period_state": { "current_period_id": "…", "label": "2026-03", "locked": false },
  "pages": [
    {
      "key": "bocker",
      "title": "Böcker",
      "waiting": true,
      "meta": "3 väntar på dig",
      "counters": {
        "open_decisions": 3,
        "overdue_invoices": 0,
        "payroll_waiting": 0,
        "missing_attachments": 7
      }
    },
    { "key": "betala",  "title": "Fakturering och löner", "waiting": false, "meta": "…", "counters": { … } },
    { "key": "bokslut", "title": "Bokslut",               "waiting": false, "meta": "…", "counters": { … } }
  ]
}
```

En lista, inte ett objekt med tre nycklar, därför att sidordningen är designens och inte
klientens att bestämma. Samma fyra räknare på varje sida, så att en räknare kan flytta hemvist
utan att formen ändras.

`waiting` och `meta` finns därför att headern faktiskt bara behöver två saker per sida: en prick
6×6 i `#f59e0b` när något väntar, och en metarad. `waiting` är sant när någon av sidans räknare
är nollskild — men **servern bestämmer vilken**, inte klienten (datakontraktets regel 1 och 2).
`meta` är serverns formulering, på svenska, i produkttonen.

`period_state` ligger på toppen och inte per sida: det finns en aktuell period, och headern visar
räkenskapsår och periodläge en gång.

### Var siffrorna kommer ifrån i dag

| Räknare | Sida | Källa i dag | Slutlig hemvist |
|---|---|---|---|
| `open_decisions` | `bocker` | `intake_sources` med `status IN ('failed','needs_attention')` + `correction_notes` med `status IN ('pending','suggested')` | `beslut` (`GET /decisions?status=open`) |
| `overdue_invoices` | `betala` | Samma predikat som `api/routes/invoices.py:182`: `status == "overdue" or is_overdue()` | oförändrad |
| `payroll_waiting` | `betala` | `payroll_runs` med `status IN ('draft','generated')`, alltså inte bokförda | lönens fyra spår, ur scope |
| `missing_attachments` | `bocker` | §3:s härledda predikat | oförändrad |

**`open_decisions` är en approximation och ska stå som en approximation i koden.** Ett
dokumenterat avstående landar i dag som ett `failed`-försök på `intake_sources`, via
`IntakeService.record_failed`, som är det `registrera_avstaende`-verktyget anropar
(`services/agent_tools.py:493`). Det är närmast "fallen där agenten avstod" som finns innan
`beslut` byggs. När `beslut` kommer byter den ut uträkningen bakom fältet — inte fältet.

`payroll_waiting` på samma sätt: `draft`/`generated` är "inte färdigbehandlad", vilket är sant men
grövre än designens fyra spår.

### Auth och placering

Ny router `api/routes/overview.py`, prefix `/api/v1/overview`, `Depends(get_current_actor)` som
övriga. Minsta befintliga mall är `api/routes/compliance.py` (80 rader, modulnivå-service,
registrerad med en rad i `api/main.py`). Uträkningen bor i `services/overview.py`; ingen SQL i
rutten, ingen SQL i servicen som inte går via ett repository.

---

## 6. Gränser

1. **Modulen skriver aldrig.** Inget `POST`, ingen `UPDATE`, ingen låsning. `GET /overview` är en
   ren läsning och får inte, till skillnad från `POST /compliance/check`, persistera något som en
   bieffekt av att bli läst.
2. **Ingen räknare beräknas i klienten.** Om en siffra är svår att få fram på servern är svaret
   att göra den svår på servern, inte att skicka råmaterial till klienten.
3. **Ingen kolumn på `vouchers`.** Se §3. Den som vill lägga till en flagga där måste först
   ändra en trigger, och det är inte den här modulens beslut att ta.
4. **`missing_attachment` gäller postade verifikationer.** Ett utkast utan bilaga är inte en
   komplettering — det är ett utkast.

**Fråga först:** en persistent flagga, en ändring i `014`:s triggers, en fjärde sida, eller en
femte räknare.

---

## 7. Teststrategi

Ny fil `tests/test_oversikt.py`. Mönstret är `tests/test_api.py`: lokal `client`-fixtur som beror
på `test_db`, importerar `api.main.app` **inuti** fixturen så appen binds efter db-bytet, och
`auth_headers` från `tests/conftest.py`.

| # | Testfall | Uppgift |
|---|---|---|
| 1 | En postad verifikation över 500 kr utan bilaga ger ett `missing_attachments`-issue | O1 |
| 2 | Samma verifikation med bilaga ger inget issue | O1 |
| 3 | Ett saknat `attachments`-schema kastar, det sväljs inte | O1 |
| 4 | `missing_attachment` är `true` på postad utan bilaga, `false` med | O2 |
| 5 | `age_days` räknas från verifikationens datum | O2 |
| 6 | `?missing_attachment=true` ger bara de utan bilaga; `false` bara de med | O3 |
| 7 | `?sort_by=age` ger äldst först | O3 |
| 8 | `?missing_attachment=true` tillsammans med `period_id` beter sig som utan, eller ger `400` | O3 |
| 9 | Ett utkast utan bilaga kommer aldrig med i `missing_attachment=true` | O3 |
| 10 | `GET /overview` ger tre sidor i ordningen `bocker`, `betala`, `bokslut` | O4 |
| 11 | `waiting` är sant precis när någon av sidans räknare är nollskild | O4 |
| 12 | `overdue_invoices` matchar `GET /invoices`-summeringens `overdue_count` | O4 |
| 13 | `GET /overview` utan bearer ger `401` | O4 |
| 14 | `GET /overview` skriver ingenting — samma räkning två gånger ger samma svar och inga nya rader | O4 |
| 15 | En listning av N verifikationer gör inte fler SQL-anrop per rad än före O2 | O2 |

Testfall 15 mäts genom att räkna anrop på `db.execute`, inte på klockan.

---

## 8. Framgångskriterier

1. `_check_missing_attachments` joinar mot `attachments` och producerar issues mot riktiga data.
2. Ingen naken `except Exception: pass` kvar i den funktionen.
3. `missing_attachment` och `age_days` finns på `VoucherResponse`, härledda, aldrig lagrade.
4. `GET /vouchers?missing_attachment=true&sort_by=age` fungerar och ignorerar inte tyst något.
5. `GET /api/v1/overview` svarar med tre sidor och fyra räknare per sida i ett anrop.
6. `open_decisions` och `payroll_waiting` är dokumenterade approximationer i koden, med den
   slutliga hemvisten namngiven i en kommentar.
7. Ingen migration, ingen ny tabell, ingen ny kolumn, ingen ändrad trigger.
8. Antalet SQL-anrop per listad verifikation är oförändrat eller lägre.
9. `pytest tests/ -v` grön; `black`, `isort`, `flake8` rena; inga nya `mypy`-fel.

---

## 9. Öppna frågor

1. **`meta`-strängens ton.** Servern formulerar ("3 väntar på dig"). Ska den följa samma
   svenska produktton som `docs/to_agent/`, eller finns det en egen copy-källa för gränssnittet?
   Tills något annat sägs: samma ton, och strängen är serverns.
2. **`bokslut`-sidans räknare.** Alla fyra är noll på den sidan i dag. Finns det något som
   *borde* räknas där — en oavstämd period, en osänd momsdeklaration — eller är en tyst sida
   rätt svar tills `flode-verifikationer` är byggt?
3. **Åldern på en komplettering.** `age_days` räknas från verifikationens datum. Designen låter
   åldern driva färgen; var går trösklarna gult och rött? Det är ett designbeslut som inte är
   taget, och tills det är taget skickar servern bara talet.
