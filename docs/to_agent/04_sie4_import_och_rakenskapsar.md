# SIE4-import och räkenskapsår

Detta dokument beskriver hur systemet hanterar import av SIE4-filer och
räkenskapsår. Informationen är systemkritisk och används för att förstå hur
verifikationer placeras vid import.

## SIE4-formatet

SIE4 (Standardiserad Import/Export) är ett svenskt filformat för
redovisningsdata. Varje fil innehåller transaktioner för ett specifikt
räkenskapsår.

## Räkenskapsårsidentifiering (`#RAR`)

SIE4-filer använder taggen `#RAR` för att ange räkenskapsår:

```
#RAR <årindex> <startdatum> <slutdatum>
```

Exempel:
```
#RAR 0 20250101 20251231    ; Aktuellt räkenskapsår 2025
#RAR -1 20240101 20241231   ; Föregående räkenskapsår 2024
```

- `#RAR 0` anger filens aktuella räkenskapsår.
- Systemet tolkar datum för att placera verifikationer i rätt period.
- Verifikationer placeras i period baserat på verifikationsdatum inom rätt
  räkenskapsår.

## Ingående balans (`#IB`)

Taggen `#IB` anger ingående balans för konton:

```
#IB <årindex> <kontonummer> <belopp>
```

- `#IB 0` = Ingående balans för filens aktuella räkenskapsår.
- Ingående balans är ingen verifikation. Importen sparar filens `#IB 0` som
  räkenskapsårets angivna ingående balans.
- Beloppen måste balansera (debet = kredit) för att vara giltiga.

Exempel från verklig data:
```
#IB 0 1920 166166177        ; Ingående balans konto 1920: 1 661 661,77 kr
```

## Utgående balans (`#UB`)

Taggen `#UB` anger utgående balans:

```
#UB <årindex> <kontonummer> <belopp>
```

- `#UB -1` = Ingående balans för aktuellt år (föregående års ingående).
- `#UB 0` = Utgående balans för filens räkenskapsår.

**Viktigt:** Föregående års utgående balans (`#UB 0` för år N) blir nästa års
ingående balans (`#IB 0` för år N+1).

Systemet importerar normalt inte `#UB`-värden som verifikationer, men de är
viktiga för att förstå sambandet mellan år.

## Multi-period import

Systemet stödjer import av flera SIE4-filer med olika räkenskapsår:

1. Varje fil behandlas separat baserat på sin `#RAR`-tagg.
2. Verifikationer placeras i rätt period baserat på verifikationsdatum.
3. Verifikationsnummer fortsätter i serie inom varje räkenskapsår.

### Exempel från produktionsdata

**SIE4 2025** (155 verifikationer: A1-A155):
```
#RAR 0 20250101 20251231
#UB -1 1920 166166177       ; IB 2025 = 1 661 661,77 kr
#UB 0 1920 119113902        ; UB 2025 = 1 191 139,02 kr
                              ; Skillnad = -470 522 kr (resultatet för 2025)
```

**SIE4 2026** (31 verifikationer: A156-A186):
```
#RAR 0 20260101 20261231
#IB 0 1920 119113902        ; IB 2026 = samma som UB 2025
```

Verifikationerna fortsätter i A-serien från föregående import.

## Ingående balans i Bok

Ingående balans bokförs inte som verifikation, och det finns ingen IB-serie att
bokföra i (`opening_balance_not_a_voucher`).

- **Första räkenskapsåret i böckerna:** ingående balansen är angiven — ur
  SIE4-filens `#IB 0` eller via `PUT /api/v1/fiscal-years/{id}/opening-balances`.
  Den går att ändra tills året låses.
- **Senare räkenskapsår:** ingående balansen räknas fram ur föregående års
  utgående balans. Resultatet som inte förts till eget kapital hamnar på 2099.
  Den följer varje ändring i föregående år tills det året låses, så inget
  behöver bokas om när ett bokslut blir klart.
- Vid import av ett senare år jämförs filens `#IB` mot den framräknade. En
  avvikelse blir en varning i importsvaret, inget fel.
- `GET /api/v1/fiscal-years/{id}/opening-balances` visar årets ingående balans,
  varifrån den kommer (`source`) och eventuella avvikelser mot filen.

## Nytt räkenskapsår

Ett räkenskapsår skapas med `POST /api/v1/fiscal-years` och
`{"start_date": "2027-01-01", "end_date": "2027-12-31"}`, med en period per
kalendermånad. Åren följer varandra utan glapp och utan överlapp, och ett år är
högst 18 månader. Servern svarar `409 fiscal_year_overlap` och `400
fiscal_year_not_adjacent` eller `fiscal_year_too_long` annars.

I en tråd och i ett underlagspass skapar agenten aldrig året själv. Ett
underlag daterat utanför alla räkenskapsår föreslår året med
`foresla_rakenskapsar`, och användaren skapar det med ett tryck på kortet. Se
regel 11 under "Tolka underlaget innan du bokför" i
`03_bokforingsinstruktion.md`.

## Viktiga principer

1. **Datum är avgörande:** Verifikationer placeras alltid i den period som
   motsvarar verifikationsdatumet.
2. **Räkenskapsår från `#RAR`:** Filens `#RAR 0` bestämmer vilket räkenskapsår
   verifikationerna tillhör.
3. **Seriefortsättning:** Verifikationsnummer fortsätter automatiskt när flera
   filer importeras för samma räkenskapsår.
4. **Inga dubbletter:** Systemet hanterar import så att samma verifikation inte
   skapas flera gånger.

## Filhantering

SIE4-filer kan innehålla:
- Verifikationer med fullständiga konteringsrader
- Ingående balanser (`#IB`)
- Utgående balanser (`#UB`)
- Kontoplan (`#KONTO`)
- Dimensionsinformation (`#DIM`, `#OBJ`)

Systemet importerar främst verifikationer och balanser. Kontoplan och
dimensioner används som referens vid import men påverkar inte systemets egen
kontoplan.

## SRU-mappning mellan år

SRU-mappningen styr vilket INK2-fält varje konto hamnar i. Ett räkenskapsår
utan sparad mappning använder BAS-kopplingstabellen (standarden). Har året en
sparad mappning, oftast från en SIE4-import med `#SRU`, används den **ensam**:
ett konto som saknas i den kommer inte med i deklarationen. Ett nytt
räkenskapsår får en kopia av föregående års sparade mappning när det skapas.

Fältkoder och kopplingar kan ha ändrats sedan fjolåret. Gå igenom arvet så här
när användaren ber om det, eller innan en INK2 tas fram:

1. `GET /api/v1/fiscal-years/{id}/sru-mappings/diff` visar en rad per konto
   med `current_field` (i år), `previous_field` (föregående år),
   `standard_field` (BAS nu) och `status`.
2. `POST /api/v1/fiscal-years/{id}/sru-mappings/inherit-previous?dry_run=true`
   skriver inget. Svaret har `source_fiscal_year_id`, `copied` och
   `needs_review`: raderna som vore granskningsfall efter arvet.
3. Fråga användaren om varje rad i `needs_review`, en i taget, med konto och
   båda koderna, till exempel: "Behåll fjolårets 7369 eller ta standarden 7368
   för konto 2510 (Skatteskulder)?" Gissa aldrig.
4. `POST .../sru-mappings/inherit-previous` utan `dry_run` skriver arvet. Det
   ersätter årets sparade mappning helt.
5. `POST /api/v1/fiscal-years/{id}/sru-mappings` med `{"account_code": "2510",
   "sru_field": "7368"}` för varje konto där användaren valde standarden eller
   en annan kod. Giltiga koder: `GET /api/v1/sru-fields`.
6. Slutkontroll: `GET .../sru-mappings/diff` igen ska inte ha några rader med
   `missing` eller `unknown_field`, och `GET /api/v1/bokslut/{id}` ska inte ha
   någon `ink2`-kontroll om konton med saldo som saknar SRU-fält.

`status` är den första som stämmer:

- `missing` – kontot har saldo men exporten hittar inget fält: årets sparade
  mappning saknar kontot, eller, om året inte har någon, standarden saknar
  det. Beloppet faller ur deklarationen. Konto 8990–8999 räknas aldrig hit.
- `unknown_field` – fjolårets eller årets kod finns inte i fälttabellen
  (utgången eller felstavad).
- `differs_from_standard` – fjolårets kod hamnar på en annan INK2-rad än
  standarden. Ett aktivt val som användaren ska bekräfta.
- `ok` – ingen fjolårskod, eller samma rad som standarden. En enskild kod som
  är ena halvan av en teckenstyrd standard (7411 mot `7411/7510`) räknas som
  samma rad.

`POST .../sru-mappings/reset-default` tar bort årets sparade mappning, så att
standarden gäller för alla konton.

## Källa

- SIE4-standard: https://www.sie.se/
- BAS-kontoplanen: https://www.bas.se/
