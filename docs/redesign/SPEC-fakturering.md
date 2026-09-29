# SPEC-fakturering

Kundfakturor i Bok: agenten föreslår, människan utfärdar, Bok bokför och skapar
PDF:en, och användaren skickar PDF:en själv. Specen täcker F0 i detalj. F1–F4 står
som ramar och specas när F0 är byggd.

Källa för fakturans innehåll: verksamt.se, "Fakturanummer" och följande avsnitt,
samt momslagen 17 kap. 24 §.

## 1. Beslut (2026-09-29)

1. **Faktureringsmetoden.** Kundfordran bokförs när fakturan utfärdas: debet
   1510, kredit 30xx och 26xx. Betalningen bokförs som debet 1930, kredit 1510.
2. **Leverans är PDF som användaren laddar ner och skickar själv.** Bok skickar
   ingenting till kunden. Designens "bokföring lyckas men sändning fallerar"
   utgår. I stället finns ett enda steg, *utfärda*, som antingen blir helt gjort
   eller inte alls.
3. **Agenten utfärdar aldrig.** Den läser, föreslår och ändrar utkast. Utfärdandet
   kräver en inloggad människa (JWT). API-nyckeln får `403 human_only`.
4. **Agenten föreslår fakturanumret. Servern kräver bara att det är unikt.** Bok
   håller ingen egen serie och räknar inte fram något nummer. Agenten föreslår
   numret i utkastet och följer serien i de senast utfärdade fakturorna (till
   exempel `2026-13` → `2026-14`). Människan ser numret och kan ändra det innan
   hon utfärdar. Befintliga fakturor behåller sina nummer.

   Verksamt.se beskriver en obruten serie per räkenskapsår. Kärnan i lagtexten
   är att numret identifierar fakturan unikt. Servern upprätthåller det, och
   agentinstruktionen sköter serien (§8). Ett nummer bestäms först vid
   utfärdandet, så ett förkastat utkast lämnar ingen lucka.

## 2. Begrepp

- **Utkast** (`invoice_drafts`): redigerbart och med ett *föreslaget* nummer.
- **Utfärdad faktura** (`invoices`): numret är fast, fakturan är bokförd och har
  en sparad PDF. Den är append-only. Bara betalstatusen ändras (§4.4).
- **Utfärda**: från utkast till faktura, verifikation och PDF i en transaktion.

## 3. Mål för F0

Efter F0 gäller följande:

1. En faktura kan bara uppstå genom att ett utkast utfärdas.
2. Ett utfärdande ger antingen alla fyra sakerna (faktura, postad verifikation,
   sparad PDF och utkastet märkt utfärdat) eller ingen av dem.
3. Två utfärdanden av samma utkast ger en faktura. Det andra anropet får `409`
   med den befintliga fakturans id.
4. Två fakturor kan aldrig få samma nummer.
5. En utfärdad faktura kan inte ändras eller raderas i databasen.
6. PDF:en har allt som §6 kräver. Den är byte för byte samma vid varje
   nedladdning.

F0 bygger inget nytt gränssnitt. De gamla sidorna byter bara anrop och får
fälten som behövs (§7).

## 4. Datamodell (migration 036)

### 4.1 Nummer

- `invoice_drafts.invoice_number TEXT`: föreslaget, kan vara NULL och är inte
  unikt. Två utkast kan föreslå samma nummer. Det som utfärdas sist får
  `number_taken`.
- `invoices.invoice_number` är redan `UNIQUE`. Det är servern hela
  nummerregel.
- Numret är fritext med begränsningen `^[A-Za-z0-9-]{1,32}$`. Ett nummer som
  bara är ett datum (`^\d{8}$` eller `^\d{4}-\d{2}-\d{2}$`) avvisas med
  `number_is_date`.
- Nummerrymden ska senare delas med kreditfakturor och påminnelsefakturor
  (F4). Då kontrollerar servern unikheten över båda tabellerna.

### 4.2 Rader: antal och enhet

- `invoice_draft_rows` och `invoice_rows` får `unit TEXT NOT NULL DEFAULT 'st'`
  och `quantity_centi INTEGER`, antalet gånger 100, så 7,5 h lagras som 750.
- Belopp ex moms beräknas som `round_half_even(quantity_centi * unit_price /
  100)` i öre.
- Den gamla heltalskolumnen `quantity` fylls kvar för gamla läsare men räknas
  inte på.
- Raden får leveransen som ett datum, en period eller en månad:
  `delivery_from DATE` och `delivery_to DATE` (lika för en enda dag) eller
  `delivery_month TEXT` (`YYYY-MM`). En av dem krävs vid utfärdande, antingen på
  raden eller på utkastet (samma kolumner på `invoice_drafts`, som gäller alla
  rader som saknar eget värde).
- Raden får `article_number TEXT`. Det kopieras från artikeln när raden
  bygger på en artikel och får annars vara tomt.

### 4.3 Kunden på fakturan

`invoice_drafts` och `invoices` får `customer_address TEXT`. Den kopieras från
`customers.address` när utkastet skapas och får inte vara tom vid utfärdande
(`customer_address_missing`). Namnet skrivs fullt ut. Förkortningar kontrolleras
inte av servern, men agentinstruktionen säger det.

`invoices` får också `payment_terms_days INTEGER`, som visas bredvid
förfallodagen, och `customer_reference TEXT` (Er referens). Utkastets
befintliga `reference` är Er referens och kopieras dit. `customers` får
`contact_person TEXT`, som förifyller den. Vår referens är
`company_info.contact_person`.

### 4.4 Utfärdande och oföränderlighet

`invoices` får:

- `source_draft_id TEXT UNIQUE`, med FK till `invoice_drafts`. Ett utkast kan
  bara ge en faktura.
- `pdf_sha256 TEXT` och `pdf_path TEXT`.
- `issued_at TIMESTAMP` och `issued_by TEXT`.

`invoice_drafts.status` får värdet `issued`. Befintliga `sent` behålls som
historik.

Triggers när `issued_at IS NOT NULL`:

- UPDATE på `invoices` avvisas om något annat än `status` eller `paid_amount`
  ändras.
- DELETE på `invoices` avvisas.
- UPDATE och DELETE på `invoice_rows` avvisas när fakturan är utfärdad.

Alla nya kolumner läggs till med `ALTER TABLE ADD COLUMN`, så ingen tabell
behöver byggas om.

## 5. Utfärda

```
POST /api/v1/invoice-drafts/{id}/issue          (JWT, inte API-nyckel)
  → 201 { invoice_id, invoice_number, voucher_id, pdf_url }
  → 409 draft_already_issued { invoice_id }
  → 409 number_taken { invoice_number, invoice_id }
  → 409 period_locked { locked_by, locked_at }
  → 422 invoice_number_missing | number_is_date | missing_rows | draft_rejected
        | customer_address_missing | delivery_date_missing
        | company_info_incomplete { missing: [...] }
```

Allt nedan sker i en `with db.transaction():`:

1. Läs utkastet. Om det redan är `issued` svarar anropet 409 med fakturans id.
2. Kontrollera allt i §4 och §6. Varje fel ger sin kod, och inget skrivs.
3. Skapa fakturan och raderna från utkastet med `source_draft_id`. `UNIQUE`
   på numret ger `number_taken`.
4. Skapa och posta verifikationen i A-serien på fakturadatumet. Konteringen är
   den i `create_booking_for_invoice`, och beskrivningen är
   "Faktura {nr} {kund}".
5. Rendera PDF:en, skriv den under datakatalogen, spara sha256 och sökväg och
   koppla den som underlag till verifikationen. Om filen skrivs men
   transaktionen fallerar blir den en föräldralös fil utan betydelse.
6. Märk utkastet `issued` och auditlogga.

**Förutsättning:** fakturarepona och `InvoiceService` får inte själva anropa
`db.commit()` på den här vägen. Commit flyttas ut till anroparna. Det bevisas
med test 3.

## 6. Fakturans innehåll (PDF)

Säljarens uppgifter läses ur `company_info`, inte ur query-parametrar. Vid
utfärdande krävs:

| Uppgift | Källa | Krav |
|---|---|---|
| Fullständigt företagsnamn och adress | `company_info` | krävs |
| Organisationsnummer | `company_info` | krävs |
| Säte (ort) | `company_info.seat`, ny nyckel | krävs för aktiebolag |
| Momsregistreringsnummer | `company_info` | krävs, format `SE` + 10 siffror + `01`, utan bindestreck eller mellanslag |
| Bankgiro eller plusgiro | `company_info` | minst ett krävs |
| "Godkänd för F-skatt" | `company_info.f_skatt` | skrivs när den är sann, och krävs då fakturan säljer tjänster |
| Telefon, e-post, webb | `company_info` | skrivs om de finns |
| Fakturanummer, fakturadatum | fakturan | krävs |
| Kundens fullständiga namn och adress | fakturan | krävs |
| Leveransdatum eller -månad, per rad om de skiljer sig | raderna eller utkastet | krävs |
| Specifikation, antal, enhet och á-pris ex moms | raderna | krävs |
| Momsbelopp per momssats, och momsfri försäljning specificerad | beräknat | krävs |
| Totalbelopp | beräknat | krävs |
| Förfallodatum och betalningsvillkor i dagar | fakturan | krävs |
| Text om dröjsmålsränta | — | skrivs inte. Bolaget fakturerar bara företag (beslut 2026-09-29), och då krävs texten inte. Om privatkunder tillkommer får kunden en kundtyp, och texten skrivs för dem. |

Fält som saknas samlas i `company_info_incomplete.missing`, så agenten kan be om
dem i en fråga.

### 6.1 Utseende

Förlagan är användarens egen faktura (nr 101282, 2026-07-31). Mallen ska se ut
som den, uppifrån och ned:

1. **Rubrik** `FAKTURA`, versaler, uppe till vänster.
2. **Två kolumner.**
   - Vänster: `MOTTAGARE`, kundens namn, Er referens på egen rad och
     adressraderna.
   - Höger: nyckel och värde med prickade ledare (`Fakturanummer ....... 101282`)
     för Fakturanummer, Fakturadatum, Betalningsvillkor (`65 dagar`) och
     Förfallodatum. Efter en tom rad följer Er referens och Vår referens.
3. **`Summa att betala`** med totalbeloppet högerställt, före raderna.
4. **Radtabell** med kolumnerna `ART.NR.`, `BESKRIVNING`, `KOMMENTAR`, `ANTAL`,
   `À PRIS` och `NETTO`, rubrikerna i versaler.
   - Beskrivningen radbryts.
   - KOMMENTAR visar leveransen: en period som `2026-06-29 --> 2026-07-02`
     över två rader, ett enda datum eller en månad (`juli 2026`).
   - ANTAL visar enheten (`28 h`). Förlagan saknar den, men verksamt.se kräver
     den.
5. **Summering längst ned.**
   - Vänster: `Momsgrundande belopp:` per momssats (`25 %: 22 400,00 kr`). En
     rad `Momsfritt:` finns om det förekommer momsfri försäljning.
   - Höger: Netto, Moms och Totalt.
6. **Sidfot.**
   - Företagsnamnet i fetstil.
   - Vänster kolumn: Adress, Telefon, E-post.
   - Höger kolumn: Org.nr., Säte, VAT-nr., Bankgiro.
   - Längst ned: `Godkänd för F-skatt.`

Hela sidan har Courier Prime (SIL OFL, fritt att bädda in), ett skrivmaskinstypsnitt. Det ligger
som fil i `templates/pdf/fonts/` och bäddas in, så utseendet inte beror på vilka
typsnitt containern har. Belopp skrivs med mellanslag som tusentalsavgränsare,
komma som decimaltecken och `kr` efter: `22 400,00 kr`. Datum skrivs
`YYYY-MM-DD`. Sidstorleken är A4.

Två avvikelser från förlagan, båda för att uppfylla §6:

- **Säte** läggs till i sidfoten.
- **ANTAL** får en enhet.

`GET /api/v1/invoices/{id}/pdf` ger den sparade filen, aldrig en ny rendering.
Den gamla `/export/pdf/invoice/{id}` används bara för fakturor som saknar sparad
PDF, alltså de gamla.

## 7. Gamla vägar

| Endpoint | Efter F0 |
|---|---|
| `POST /invoices` | Tas bort. En faktura uppstår bara genom utfärdande. |
| `POST /invoices/{id}/send` | Tas bort. |
| `POST /invoices/{id}/book` | Tas bort. |
| `POST /invoice-drafts/{id}/send` | Ersätts av `/issue`. |
| `POST/PUT /invoice-drafts` | Tar `invoice_number`, `customer_address`, leveransdatum och radernas `unit` och decimala `quantity`. |
| `POST /invoices/preview` | Behålls och räknar med decimalt antal. |
| `/payment`, `/credit-note` | Behålls oförändrade till F3/F4. |

De gamla sidorna:

- `invoices/drafts/[id]` och `invoices/new` får fälten för nummer, adress,
  leveransdatum och enhet och anropar `/issue`.
- `invoices/[id]` tappar knapparna Skicka och Bokför och länkar den sparade
  PDF:en.

**Kontroll före driftsättning:** fakturor med `status = 'draft'` eller
`voucher_id IS NULL` på hubbabubba behöver ett eget beslut.

## 8. Agenten i F0

Inget nytt verktyg. Agenten skapar och ändrar utkast via `invoice-drafts`, som
i dag. `docs/to_agent/` får en instruktion om att:

- läsa de senast utfärdade fakturornas nummer och föreslå nästa i samma serie.
  Om det inte finns någon utfärdad faktura frågar agenten användaren vilket
  nummer den senaste fakturan utanför Bok hade.
- skriva kundens namn fullt ut och ange leveransdatum, eller leveransmånad om
  det exakta datumet inte är känt.
- vid `number_taken` föreslå ett nytt nummer i stället för att försöka igen.

## 9. Tester (skrivs först)

1. Utfärda ett utkast med nummer `2026-1`. Fakturan har det numret,
   verifikationen är postad och balanserad på 1510/3011/2610, och PDF-filen
   finns med rätt sha256.
2. Två utkast med samma nummer: det första utfärdas, det andra får 409
   `number_taken` och ingenting skrivs.
3. Tvinga ett fel efter postningen, till exempel att PDF-renderingen kastar.
   Ingen faktura och ingen verifikation, utkastet är orört och numret är
   fortfarande ledigt.
4. Samma utkast två gånger ger 409 med samma `invoice_id`, och det finns en
   faktura och en verifikation.
5. Låst period ger 409 `period_locked` och ingenting skrivs.
6. Utan nummer ger `invoice_number_missing`. `20260929` ger `number_is_date`.
7. Utan kundadress eller leveransdatum ger respektive 422.
8. SQL-UPDATE av `amount_inc_vat`, `invoice_number` eller en rad på en
   utfärdad faktura avvisas. UPDATE av `paid_amount` går igenom. DELETE avvisas.
9. API-nyckeln mot `/issue` ger 403 `human_only`.
10. Två nedladdningar av PDF:en ger identiska bytes.
11. `company_info` utan momsregistreringsnummer, säte eller bankgiro/plusgiro
    ger 422 `company_info_incomplete` med alla tre i `missing`.
12. 7,5 h à 1 150 kr ger 8 625,00 ex moms och 2 156,25 i moms.
13. PDF:ens text innehåller varje obligatorisk uppgift i §6, inklusive
    "Godkänd för F-skatt" men ingen räntetext. En rad med period visar
    `2026-06-29 --> 2026-07-02`, och beloppen står som `22 400,00 kr`.
14. De gamla fakturorna finns kvar med sina nummer och kan läsas och betalas.
15. Förlagans faktura (28 h à 800 kr, 25 %) återskapad ger Netto 22 400,00,
    Moms 5 600,00 och Totalt 28 000,00. En PNG av första sidan jämförs visuellt
    en gång mot förlagan och sparas inte i repot, eftersom den innehåller
    kunddata.

## 10. Senare faser (ramar)

- **F1 Agenten och tråden.** Verktygen `las_kunder`, `las_fakturor`,
  `foresla_faktura` (utkast som `FakturaForslag` i `betala.fakturering`, med
  föreslaget nummer synligt) och `andra_fakturautkast`. Knappen "Utfärda" i
  kortet. Kvittot länkar PDF:en och verifikationen. Läsvyn blir en skrivvy.
- **F2 Utskickad.** Människan markerar fakturan som skickad, med datum. Det
  används för påminnelser. Ingen e-post från Bok.
- **F3 Inbetalningar.** Bankhändelser matchas mot öppna fakturor. En säker träff
  bokförs som 1930/1510, annars blir det ett beslutskort.
- **F4 Kreditfaktura, påminnelse och dröjsmålsränta.** Kreditfakturor och
  påminnelsefakturor har egna unika nummer i samma nummerrymd, föreslagna av
  agenten på samma sätt. Kreditfakturan hänvisar till originalet. Dröjsmålsränta
  är referensränta plus 8 procentenheter på beloppet inklusive moms, utan moms
  på räntan. Påminnelser väntar på schemaläggningen (öppet beslut 4).

Utanför scope: e-faktura/Peppol, valuta, EU-försäljning och omvänd
skattskyldighet, ROT/RUT, avtal och tidrapporter.
