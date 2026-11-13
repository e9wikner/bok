# Öppna beslut efter redesignen (v4)

Redesignen (`/v4`, bakom `NEXT_PUBLIC_SKAL`) är byggd: idempotens, översikt,
agentruntime, trådar, beslut, skal, chattyta, flöde 1 (verifikationer), underlagstolkning,
flöde 4 (underlag), läsbarhet, underlag-ersatt och fakturering F0–F1. Modulspecarna och uppgiftslistorna är
borttagna och används inte längre.

Här står bara det som fortfarande väntar på ett beslut eller en kontroll. Stryk en punkt när
den är avgjord och skriv beslutet i koden eller i commit-meddelandet, inte här.

## Före och vid driftsättning

Det här är kontroller, inte beslut. De kräver en människa, och den första en riktig LLM.

1. **Kvitton med riktig LLM:**
   - Ett kvitto för en verifikation som redan är bokförd från banken ger ett avstående i
     underlagspasset.
   - I en tråd ger samma kvitto en koppling, aldrig en ny verifikation.
   - Säg "fel verifikation" om en koppling. Agenten ska då lägga fram ett beslut, koppla bort
     och koppla rätt (instruktionen punkt 10).
2. **Fakturering F0:**
   - Fyll i `company_info`: säte (`seat`), momsnummer, bankgiro och F-skatt (`f_skatt`).
     Utan dem vägrar utfärdandet (`company_info_incomplete`).
   - Fakturor med `status = 'draft'` eller `voucher_id IS NULL` behöver ett eget beslut.
     `/send` och `/book` finns inte längre, så inget bokför dem.
   - Utfärda en riktig faktura. Kontrollera PDF:en mot förlagan och verifikationen
     (1510 mot 30xx/26xx).
3. **Fakturering F1 med riktig LLM:** en faktura genom Fakturerings tråd, från meddelandet via
   `foresla_faktura` och en ändring till `Utfärda` och kvittot. Kontrollera PDF:en mot
   förlagan.

## Produktbeslut

1. **Tröskeln för beslutskort kontra val.** I dag hamnar varje alternativ som ändrar böckerna
   under ett beslutskort, oavsett belopp. En differens på 2 kr blir alltså ett beslutskort.
   Ändra det om det blir för tungt i praktiken.
2. **Årsskiftet.** Nästa meddelande efter ett årsskifte hamnar i en ny tråd. Det avslutande
   inlägget i den gamla tråden, som säger vart samtalet tog vägen, är inte byggt. Det är inte
   heller bestämt vad som händer med ett öppet beslut eller ett väntande förslag i förra årets
   tråd. I dag ligger de kvar där och syns ändå i `GET /decisions`.
3. **`superseded` sätts aldrig automatiskt.** En inloggad människa sätter det med `Avfärda` på
   beslutskortet (`POST /decisions/{id}/dismiss`). Ett underlag som beslutet gäller blir då
   `skipped`. Agenten kan inte avfärda. Automatiska utlösare saknas fortfarande. Möjliga sådana är
   ett raderat underlag, en låst period eller en rättad verifikation.
4. **Intagspasset körs bara manuellt.** Schemaläggning (t.ex. var femtonde minut med
   tomkö-kontroll) ska läggas på när ett pass kostnad och träffsäkerhet är mätta.
   `agent_runs.trigger` har redan `'schedule'`.
5. **Påminnelse om gamla kompletteringar.** Designen vill ha en. Det hör ihop med punkt 4.
6. **Fritextsvar på ett kopplingsbeslut.** Servern släpper igenom fritext, så ett "nej, inte samma"
   i fritext kopplas om agenten läser det fel. Alternativet är att ett kopplingsbeslut bara kan
   besvaras med ett alternativ.
7. **Ett kvitto med flera köp** stöds inte.
8. **Kursdifferens mot företagets eget kort.** Ett belopp i utländsk valuta räknas nu om med
   Riksbankens dagliga mittkurs för köpdatumet (`hamta_valutakurs`, `valuta` på
   `posta_verifikation`/`foresla_verifikation`, migration 045). Servern skriver kursen, datumet
   och källan i verifikationens kommentar. Kvar är fallet där företagets eget kort drogs med
   bankens kurs: skillnaden mot kortdragningen ska bokföras som kursdifferens när
   banktransaktionen matchas, 3960 vid vinst och 7960 vid förlust (7960 finns inte i
   kontoplanen ännu). Ett utlägg berörs inte, eftersom skulden på 2820 är det omräknade beloppet.
9. **`thinking`-block över flera turer.** Frågan är om `LLMTurn` ska bära dem, så att långa
   trådar går fram och tillbaka korrekt. Det ändrar agentruntimens gränsyta.
10. **Små designfrågor:**
    - Varaktigheten på `ny` är gissad (6 s).
    - Headern visar `BokAi` i stället för bolagsnamnet.
    - Bokslut-sidan säger alltid `Inget väntar`.
    - `AgentStatus` syns bara som `pausad` på mobilen.
11. **Avstående i intagspasset som riktiga beslut med alternativ.** I dag blir ett avstående
    `failed` och syns som ett syntetiskt `intake:`-beslut utan alternativ. Raden tas upp i
    chatten (`BeslutFokus`) med `Försök igen` och `Svara agenten`, men människan formulerar
    själv svaret. Nästa steg är att passet skapar ett `decisions`-kort med 2–3 alternativ i
    Verifikationers tråd, så att svaret blir ett klick (`POST /decisions/{id}/answer`), och att
    likartade avstånden kan grupperas. Formuleringen av alternativen ska först stå i
    instruktionen.
12. **Moms på tjänster köpta utanför EU** är löst framåt (migration 045). Instruktionen har
    ett beslutsträd för köp från säljare utanför Sverige. En tjänst enligt huvudregeln bokförs
    med omvänd skattskyldighet: 2645/2614 för momsen och 4535 (EU) eller 4531 (utanför EU) mot
    4598 för underlaget. `services/vat_report.py` fyller ruta 21, 22, 30 och 48. Kvar är:
    - Bokfört 2026 är inkonsekvent (A5, A6 utan moms; A8 bara ingående moms; A20 mot 2650;
      övriga 2610/2640) och rättas med B-verifikationer.
    - Företagets egna agentinstruktioner kan fortfarande säga "utan moms" (v5, regel D2/D3)
      och måste i så fall skrivas om.
    - eSKD-taggarna för ruta 21, 22 och 30 (`InkopTjanstAnnatEg`, `InkopTjanstUtomEg`,
      `MomsInkopUtgHog`) är inte kontrollerade mot Skatteverkets DTD.
    - Import av varor (ruta 50/60) och varor från EU (ruta 20) stöds inte.

## underlag-ersatt: val som gjordes i bygget, att bekräfta

1. **Grunden för en frånkoppling** är en inloggad människa (`POST /intake/{id}/unlink` med JWT)
   eller ett besvarat beslut om underlaget. Beslutet ska vara fattat efter kopplingen och får
   inte vara kopplingens eget. Agenten kan aldrig koppla bort på eget initiativ, och
   underlagspasset kan det inte alls.
2. **Varje gällande koppling kan kopplas bort,** också en som gjordes när verifikationen postades
   ur underlaget. Då är en rättelse ofta den riktiga vägen. Frånkopplingen gör bara att
   verifikationen står som "saknar underlag".
3. **Ett bortkopplat underlag blir `needs_attention`.** Det kan kopplas igen, men det kan inte
   postas som en ny verifikation. Det gäller i dag också ett underlag som passet avstått från.
   Utvägen "Det är ett annat köp" kräver alltså att underlaget raderas och laddas upp igen.
   Beslut: ska posten släppa igenom `failed`/`needs_attention`?
4. **En hänvisning står kvar.** A-121, som bokfördes på kvittot via A-118, räknas fortfarande som
   att den har underlag. Svaret (`orphaned_references`) och kvittot i tråden namnger den, och
   agenten frågar om den ska rättas.
5. **Frånkoppling tillåts i en låst period,** precis som koppling. Ingen verifikation rörs.
6. **Ingen knapp i gränssnittet.** Vägen tillbaka går genom tråden, som vägen fram. En inloggad
   människa kan också använda routen direkt. Frånkopplade underlag visas i
   `source-context.unlinked_source_material`, men `/v4` ritar dem inte ännu.

## Delat underlag (migration 044): val som gjordes i bygget, att bekräfta

1. **Ett nytt underlag kopplas fortfarande automatiskt till högst en verifikation.** En exakt
   matchning gäller bara ett underlag som inte styrker någon verifikation än. Ett redan kopplat
   underlag kopplas till en till bara efter en människas tryck.
2. **Människans tryck finns på två ställen.** Det ena är `foresla_delat_underlag`-kortet, som
   kopplar till en redan postad verifikation. Det andra är ett `foresla_verifikation`-kort med ett
   redan kopplat underlag: fotnoten säger vilka verifikationer underlaget redan styrker, och
   trycket på Posta kopplar det. Ett vanligt beslut från `be_om_beslut` räcker inte, eftersom det
   inte visar för människan att underlaget redan är bokfört.
3. **"Godkänn för kommande verifikationer" finns bara på `foresla_delat_underlag`-kortet.**
   Verifikationskortet har en knapp, Posta, och den kopplar en gång. Ska valet finnas där också
   behövs en andra knapp i `/v4`.
4. **Ett godkännande gäller verifikationens räkenskapsår**, alltså året för verifikationen på
   kortet, inte året då kortet besvarades. Ett nytt år kräver ett nytt kort.
5. **Ett godkännande kan återkallas** av en inloggad människa:
   `POST /api/v1/intake/{id}/reuse-approvals/{approval_id}/revoke`. Kopplingar som redan gjorts
   står kvar. Det finns ingen knapp i `/v4` än. Godkännandena syns i
   `GET /intake/workspace/voucher_source/{id}` som `reuse_approvals`.
6. **En koppling i efterhand till en ytterligare verifikation kräver en tolkning av underlaget**,
   eftersom kopplingens grund pekar ut en tolkning. Verifikationen behöver däremot inte finnas
   i tolkningen: kortet pekar ut den, och ett låneavtals belopp matchar ingen enskild amortering.

## Fakturering

F0 och F1 är byggda.

### F1: frågor som står öppna

1. **Nya kunder.** Verktygen skapar ingen kund, så en ny kunds uppgifter står bara på fakturan.
   Ska utfärdandet lägga till kunden i registret, eller behövs ett eget verktyg? Det kan vänta
   tills det blir ett problem i praktiken.
2. **Årsskiftet.** Ett förslag i förra årets tråd som utfärdas efter årsskiftet får sitt kvitto
   i förslagets tråd. Hör ihop med produktbeslut 2.
3. **Headerns tal räknas utan `view_key`** och tar därför med fakturaförslagen även på Böcker.
   Det är konsekvent med verifikationsförslagen, men kanske inte önskvärt när fler sidor väntar.
4. **Leveransdatum per rad** sätts av agenten (`foresla_faktura`) eller via API:t. De gamla
   sidorna redigerar bara leveransen för hela utkastet.

### Senare faser

F2–F4 är ramar och specas en i taget innan de byggs.

- **F2 Utskickad.** Människan markerar fakturan som skickad, med datum, för påminnelser. Ingen
  e-post från Bok. Triggern i migration 038 låser `sent_at` på en utfärdad faktura, och
  `sent_at` lämnas `NULL` vid utfärdandet. F2 lägger därför markeringen i en egen
  append-only-tabell, där en felaktig markering ångras med en ny rad, som
  `voucher_intake_unlinks`.
- **F3 Inbetalningar.** Bankhändelser matchas mot öppna fakturor. En säker träff bokförs som
  1930/1510, annars blir det ett beslutskort.
- **F4 Kreditfaktura, påminnelse och dröjsmålsränta.** Kreditfakturor och påminnelsefakturor
  får egna unika nummer i samma nummerrymd, föreslagna av agenten. Kreditfakturan hänvisar
  till originalet. Dröjsmålsräntan är referensräntan plus 8 procentenheter på beloppet
  inklusive moms, utan moms på räntan. Påminnelser väntar på schemaläggningen
  (produktbeslut 4).

## Observerat beteende att ta ställning till

Beteendet är inte ändrat. Det här är iakttagelser.

- Ett underlagspass som kopplar och sedan slutar räknas som `abstained: agent_no_outcome`, trots
  att källan blir `processed`.
- `POST /vouchers/{id}/post` svarar `missing_attachment: true` för en differensverifikation
  (A-121). Svaret byggs före efterarbetet. En ny läsning ger `false`.
- "kvitto kopplat" syns bara för kopplingar gjorda medan sidan är öppen. `VoucherResponse` säger
  inte att en verifikation har ett kopplat kvitto.
- Ett meddelande med bara blanktecken och utan bilagor ger `422`.
- **SIE4-importen hoppar över helt strukna verifikationer.** En verifikation vars rader alla är
  `#BTRANS` (strukna i det tidigare systemet) blir tom och importeras inte. Saldona stämmer,
  men numret saknas: 21 verifikationer i filerna 2010–2025, som ger 18 `voucher_sequence`-ärenden
  i compliance-kontrollen. Ska importen spara dem som tomma eller makulerade verifikationer så
  att serien är obruten, eller räcker det att kontrollen förklarar luckan?

## Städning och skuld

- **De gamla sidorna** i `frontend-v3` tas bort en i taget när skalet har en vy för dem.
  Kontoplanen och revisionsloggen (behandlingshistoriken, ett BFL-krav) är vyer i Böcker sedan
  november 2026, företagets uppgifter är Företaget i Fakturering och löner, och SIE4-filen
  laddas ner per år i Bokslut, där SRU-kopplingen också ställs in. `/accounts`, `/audit` och
  `/settings` (med SRU-mappningarna) är borta.
- **Fakturering** är skrivvy sedan F1. En faktura skrivs genom att en inloggad människa utfärdar
  ett utkast (`POST /invoice-drafts/{id}/issue`). **Löner** skriver i `/v4` på samma sätt. De
  sätts upp under Anställda eller i samtalet med agenten, som har `registrera_anstalld`, `satt_lon`
  och `skapa_lonekorning` (bara i en tråd). Agenten lägger fram bokföringen av ett lönebesked
  som ett beslutskort (`foresla_lonebokforing`), och en inloggad människa bokför med ett tryck.
  En AGI bokför agenten själv när kvittensen kommer in (`bokfor_agi`). Lönebeskeden skickas,
  markeras och en obokförd lönekörning tas bort under Lönebesked, där också AGI:ns fält står;
  `/payroll` är borta.
- **`mypy .`** ger 58 fel i 22 filer. Alla fanns före redesignen.
- **CI** har `continue-on-error: true` på backendens steg (pytest, black, isort, flake8, mypy)
  och Docker-bygget, liksom på frontendens lint. Bara `npm test` fäller bygget. En grön bock
  betyder alltså lite förrän det tas bort.
- **`BokAI App Redesign.zip`** är designunderlaget (v10, flödespanelerna) och ligger kvar som
  referens för de vyer som återstår.
