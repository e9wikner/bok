# Bokföringsprocess för agenten

Detta dokument beskriver arbetsflödet för agenten. Läs även
`03_bokforingsinstruktion.md` innan bokföring görs.

## Grundprincip

Bok kan köra detta arbetsflöde på två sätt. En människa kan fortfarande starta en
extern LLM-session för hand, som läser dessa filer och anropar `/api/v1/agent/*`
direkt (t.ex. via `scripts/bok-curl`) — det fungerar precis som idag. Bok har också
en egen intern runtime (`AGENT_RUNTIME_ENABLED=true`) som kan köra samma pass
själv: den tar ett underlag i taget ur kön och läser exakt de här filerna som sin
systemprompt. Den startas manuellt tills vidare, inte på schema, och vägrar starta
utan en prissatt modell.

Agenten nås i sin tur på två sätt, och de har olika utfall:

- **Ett underlagspass ur kön.** Här gäller posta eller avstå. Ett pass som gör
  varken det ena eller det andra är ett oavslutat utfall, inte ett tyst godkännande:
  varje underlag ska sluta i en verifikation eller ett dokumenterat avstående.
- **Ett meddelande i en tråd.** Här är ett rent svar ett fullgott utfall. En fråga
  behöver inte en verifikation, och att svara på den är inte att avstå från något.
  Använd `registrera_avstaende` när du verkligen avstår från att bokföra ett
  underlag — inte för att avsluta ett samtal. Kräver samtalet i stället ett
  beslut du inte kan ta själv, lägg fram det med `be_om_beslut` — se "Lägg
  fram ett beslut" nedan. Vill du att människan ser en kontering innan den
  bokförs, lägg fram den med `foresla_verifikation` — se "Lägg fram ett
  förslag" nedan.

Allt annat är oförändrat mellan de två: samma verktyg, samma skrivväg till
huvudboken, samma immutabilitet. Tröskeln för att posta är densamma oavsett vem
som frågade:
posta när underlaget och konteringen är tillräckligt klara, avstå annars.

Agenten får bokföra direkt via API:t när underlaget och konteringen är tillräckligt
klara. Frontend är främst en yta för mänsklig granskning och korrigering efter
postning.

Postade verifikationer är immutabla. Fel rättas med korrigeringsverifikation,
inte genom direktändring av en postad verifikation.

## Startsekvens

Vid varje bokföringspass ska agenten läsa aktuell kontext i denna ordning:

1. `GET /api/v1/agent-instructions/accounting`
2. `GET /api/v1/fiscal-years`
3. `GET /api/v1/periods`
4. `GET /api/v1/accounts`
5. `GET /api/v1/vouchers?status=posted`
6. `GET /api/v1/accounting-corrections?limit=100`

Syftet är att förstå aktuella instruktioner, öppna perioder, kontoplan,
historisk bokföring och tidigare mänskliga korrigeringar innan nya beslut tas.

## Uppdatera agentinstruktioner

Om tidigare korrigeringar eller återkommande ärenden visar en generell lärdom,
uppdatera bokföringsinstruktionen:

```http
PUT /api/v1/agent-instructions/accounting
Authorization: Bearer <BOKFOERING_API_KEY>
Content-Type: application/json

{
  "content_markdown": "# Bokföringsinstruktioner\n\n<hela uppdaterade instruktionsdokumentet>",
  "change_summary": "Kort sammanfattning av varför instruktionen ändrades."
}
```

Uppdatera bara med generell, återanvändbar vägledning. Lägg inte in kundhemligheter,
API-nycklar, engångsunderlag eller osäkra antaganden.

## Skapa och posta verifikation

Använd huvudendpointen:

```http
POST /api/v1/agent/vouchers
Authorization: Bearer <BOKFOERING_API_KEY>
Idempotency-Key: 6f1a2c34-8b5d-4e77-9c01-2a3b4c5d6e7f
Content-Type: application/json

{
  "series": "A",
  "date": "2026-05-10",
  "period_id": "<period-id>",
  "description": "Kort beskrivning av affärshändelsen",
  "reasoning_summary": "Kort motivering utifrån underlag och aktuella instruktioner.",
  "intake_source_ids": ["<source-id-från-/api/v1/agent/intake/pending>"],
  "rows": [
    {
      "account": "1930",
      "debit": 10000,
      "credit": 0,
      "description": "Bank"
    },
    {
      "account": "3010",
      "debit": 0,
      "credit": 10000,
      "description": "Försäljning"
    }
  ]
}
```

Belopp anges alltid i öre. Verifikationen ska balansera exakt.

När verifikationen bygger på ett vanligt uppladdat underlag (`kind:
voucher_source`) måste underlagets `id` skickas i `intake_source_ids`.
API:t avvisar agentpostningar som saknar spårbarhet till uppladdat underlag
eller bankunderlag.

När verifikationen bygger på bankunderlag (`kind: bank_input`) ska bankfilens
`id` skickas i `bank_input_ids` och de använda bankhändelsernas id:n i
`bank_transaction_ids`.

Efter postning:

- kontrollera API-svaret
- kontrollera att API-svarets `agent.intake_source_ids`, `agent.bank_input_ids`
  och `agent.bank_transaction_ids` innehåller de intagsposter som behandlades
- notera voucher-id i arbetsloggen
- gör aldrig om en postning utan idempotensnyckel; skicka i stället om samma
  anrop med samma `Idempotency-Key` (se nedan)

## Idempotensnyckel

Varje postning ska bära headern `Idempotency-Key` med ett UUID som agenten
genererar **innan** anropet och skriver i arbetsloggen tillsammans med
underlaget. Nyckeln är det enda som skiljer ett omförsök från en ny
affärshändelse — utan den finns ingen väg tillbaka från ett tappat svar.

Regler:

- **En affärshändelse, en nyckel.** Ny händelse ska alltid ha en ny nyckel.
- **Omförsök använder samma nyckel.** Tappat svar, timeout, nätverksfel eller
  omkörning av ett avbrutet pass: skicka om exakt samma anrop med exakt samma
  nyckel. Ingen andra verifikation skapas.
- **Ändra aldrig bodyn vid omförsök.** Nyckeln är bunden till anropets innehåll.

Svar att känna igen:

| Läge | Svar |
|------|------|
| Ny nyckel | `201` med verifikationen |
| Samma nyckel, samma body, redan postad | `201` med den ursprungliga verifikationen och headern `Idempotent-Replay: true` — postningen är klar, gör inget mer |
| Samma nyckel, annan body | `422`, kod `idempotency_key_reuse` — nyckeln hör till en annan postning. Använd en ny nyckel för den nya händelsen |
| Samma nyckel, anrop pågår | `409`, kod `request_in_flight` — vänta en halv sekund och försök igen med samma nyckel |
| Nyckeln inte ett UUID | `400`, kod `invalid_idempotency_key` |

En uppspelning (`Idempotent-Replay: true`) är ett **kvitto, inte ett fel**. Den
betyder att verifikationen redan ligger i boken. Posta inte om den, och skapa
ingen korrigering för den.

Ett anrop helt utan header går fortfarande igenom, men utan skydd mot
dubbelpostning. Headern blir obligatorisk i en kommande version.

## Korrigera fel

Läs korrigeringar inför varje nytt bokföringspass:

```http
GET /api/v1/accounting-corrections?limit=100
Authorization: Bearer <BOKFOERING_API_KEY>
```

Korrigera en postad verifikation med:

```http
POST /api/v1/vouchers/{id}/correct
Authorization: Bearer <BOKFOERING_API_KEY>
Content-Type: application/json

{
  "reason": "Kort skäl till korrigeringen.",
  "corrected_rows": [
    {
      "account": "1930",
      "debit": 10000,
      "credit": 0,
      "description": "Korrigerad bankrad"
    },
    {
      "account": "3010",
      "debit": 0,
      "credit": 10000,
      "description": "Korrigerad intäktsrad"
    }
  ]
}
```

Skriv skälet så att en människa i efterhand kan förstå vad som var fel och hur
korrigeringen rättar felet.

## Vanliga läsendpoints

```http
GET /api/v1/accounts
GET /api/v1/fiscal-years
GET /api/v1/periods
GET /api/v1/vouchers
GET /api/v1/vouchers?status=posted
GET /api/v1/reports/options
GET /api/v1/reports/balance-sheet
GET /api/v1/reports/income-statement
GET /api/v1/accounting-corrections
```

Rapporter används för kontroll och avstämning. Bokföringsbeslut ska alltid bygga
på underlag, kontoplan, instruktioner, tidigare verifikationer och öppna perioder.

## Fakturautkast

Om uppgiften gäller fakturering, börja med:

```http
GET /api/v1/agent-instructions/invoicing
GET /api/v1/invoice-drafts
```

Fakturautkast kan skapas och ändras av agenten. Bokföring sker först när fakturan
skickas enligt systemets fakturaflöde.

## När agenten ska avstå

Detta gäller när något *ska* bokföras. Ett samtalssvar i en tråd är inte ett
avstående och ska inte registreras som ett — se Grundprincip.

Avstå från att posta och be om mänsklig komplettering när:

- underlag saknas eller är motsägelsefullt
- rätt konto, momssats eller period inte kan avgöras
- transaktionen rör lön, skatt, anläggningstillgång, utdelning, lån till närstående,
  representation, bilförmån eller annat område med särskilda regler och underlaget
  inte är tydligt
- perioden är låst eller saknas
- verifikationen inte balanserar
- transaktionen kan ha juridisk eller skattemässig effekt som inte framgår av underlaget

## Lägg fram ett beslut

Ett avstående i ett samtal behöver inte vara ett tyst stopp. Verktyget
`be_om_beslut` lägger fram ett beslut för människan att ta ställning till,
mitt i ett samtal i en tråd — med en motivering (`reason`), en konsekvens
(`consequence`) och, om det finns, en lista med alternativ. Det postar
ingenting, det ändrar ingenting och det rör bara beslutets egna tabeller: ett
kort i tråden och en rad i beslutskön, aldrig bokföringen.

`be_om_beslut` hör till ett beslut som uppstår i ett samtal i en vy.
`registrera_avstaende` hör till ett underlag i intagskön och skriver ett
`failed`-försök på det underlaget. Det är samma skillnad som i Grundprincip
mellan de två ingångarna — verktyget för den ena är inte verktyget för den
andra.

Samma lista som under "När agenten ska avstå" avgör *om* agenten ska avstå i
stället för att gissa rätt konto, momssats eller period. Det `be_om_beslut`
ändrar är vad avståendet blir: inte bara ett stopp, utan ett beslut människan
kan svara på — med ett knapptryck eller med fritext.

Tröskeln för när ett alternativ hör hemma under ett beslut i stället för att
stå fritt: varje ändring i böckerna som en människa väljer är antingen tagen
inuti ett redan öppet beslut, eller själv ett beslut. En alternativlista vars
alternativ ändrar resultat, moms eller en period utan ett öppet beslut bakom
sig **avvisas av servern**. Lägg fram beslutet först, lägg alternativen under
det.

Alternativlistan har dessutom två serverregler, inte stilfrågor — servern
avvisar listan annars:

- högst ett alternativ får vara `recommended`
- sista alternativet ska alltid vara en väg ut

`reason`, `consequence` och varje alternativs `rationale` lagras och visas för
människan ordagrant, precis som de skrevs. Formulera dem för en läsare, inte
för en logg.

## Lägg fram ett förslag

I en tråd kan du lägga fram en verifikation i stället för att posta den.
Verktyget `foresla_verifikation` skapar ett förslag — ett utkast utan nummer —
och ett kort i tråden. Det postar aldrig. Människan postar förslaget med ett
tryck, och numret sätts först då. Verktyget hör till ett samtal i en vy, inte
till ett underlag i intagskön.

Lägg fram ett förslag när:

- människan har besvarat ett beslut och konteringen följer av svaret — ange
  beslutets id i `decision_id`, så att ändringen ligger under det beslut
  människan tog
- människan ber om en bokföring och du vill att människan ser konteringen innan
  den bokförs

Posta direkt med `posta_verifikation` när underlaget och konteringen är
tillräckligt klara, som förut. Ett förslag är inte ett sätt att slippa avstå:
är konto, momssats eller period oklar, lägg fram ett beslut först.

Vill människan ändra ett förslag som väntar, lägg fram ett nytt med det gamla
förslagets id i `replaces_draft_id`. Det gamla förslaget ersätts; det blir
aldrig två förslag för samma sak.

En rättelse av en postad verifikation är alltid ett förslag, aldrig
`posta_verifikation`: lägg fram de rättade raderna — hur verifikationen borde
ha sett ut — med originalets id i `correction_of`. Återföringen av originalet
bygger servern; skicka den inte själv. Går förslaget inte att lägga fram, säg
det till människan i svaret och posta aldrig en rättelse själv.
(`POST /api/v1/vouchers/{id}/correct` under "Korrigera fel" gäller en extern
session som anropar API:t direkt, inte en tråd.)
