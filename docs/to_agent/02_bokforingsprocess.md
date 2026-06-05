# Bokföringsprocess för agenten

Detta dokument beskriver arbetsflödet för agenten. Läs även
`03_bokforingsinstruktion.md` innan bokföring görs.

## Grundprincip

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
voucher_source`) måste underlagets `id` skickas i `intake_source_ids`. Annars
ligger underlaget kvar som `pending` i intaget även om agenten har bokfört
affärshändelsen.

När verifikationen bygger på bankunderlag (`kind: bank_input`) ska bankfilens
`id` skickas i `bank_input_ids` och de använda bankhändelsernas id:n i
`bank_transaction_ids`.

Efter postning:

- kontrollera API-svaret
- kontrollera att API-svarets `agent.intake_source_ids`, `agent.bank_input_ids`
  och `agent.bank_transaction_ids` innehåller de intagsposter som behandlades
- notera voucher-id i arbetsloggen
- gör inte om samma postning om svaret är oklart; läs först verifikationslistan
  eller använd idempotensflöde när det är lämpligt

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

Avstå från att posta och be om mänsklig komplettering när:

- underlag saknas eller är motsägelsefullt
- rätt konto, momssats eller period inte kan avgöras
- transaktionen rör lön, skatt, anläggningstillgång, utdelning, lån till närstående,
  representation, bilförmån eller annat område med särskilda regler och underlaget
  inte är tydligt
- perioden är låst eller saknas
- verifikationen inte balanserar
- transaktionen kan ha juridisk eller skattemässig effekt som inte framgår av underlaget
