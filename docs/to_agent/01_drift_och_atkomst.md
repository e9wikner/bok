# Drift och åtkomst

Detta dokument beskriver BokAi-miljön i generella termer. Den faktiska
serveradressen och API-nyckeln ska ges till agenten vid uppstart och ska inte
skrivas in i detta dokument.

## Miljö

BokAi körs på en server i företagets lokala nätverk. Miljön består av:

- en backend med REST API
- en frontend för mänsklig granskning
- en SQLite-databas i en Docker-volym

Servern ska inte exponeras mot internet. Använd endast adresser som uttryckligen
har lämnats vid uppstart, till exempel:

```text
Backend: <BACKEND_BASE_URL>
Frontend: <FRONTEND_URL>
```

## Autentisering

Alla API-anrop ska använda bearer-token:

```http
Authorization: Bearer <BOKFOERING_API_KEY>
```

`BOKFOERING_API_KEY` är en hemlighet. Den får inte skrivas i Git, chattloggar,
instruktioner, verifikationstexter, `reasoning_summary` eller andra permanenta
fält.

Agentnyckel-endpoints under `/api/v1/agent/keys/*` är endast platshållare tills
separat persistent agentnyckelhantering finns. Använd den API-nyckel som lämnas
vid uppstart.

### Wrappern `scripts/bok-curl`

I repot finns `scripts/bok-curl`, som sätter bearer-headern åt agenten så att
nyckelvärdet aldrig behöver läsas in eller skrivas ut:

```text
scripts/bok-curl <METOD> <SÖKVÄG> [json-fil]
```

Wrappern löser adressen från `BOK_API_URL` och faller tillbaka på
`http://localhost:8000`. Nyckeln hämtas från `BOKFOERING_API_KEY` i miljön, och
i andra hand ur env-filen `BOK_ENV_FILE`. Standardvärdet
`/srv/appdata/bok/bok.env` är serverns placering, inte ett krav — med nyckeln i
miljön fungerar wrappern även utanför servern. Saknas båda källorna avbryter
wrappern utan att skriva ut något nyckelvärde.

## Hälsokontroll

Kontrollera först att backend svarar:

```http
GET /health
```

Ett friskt svar innehåller normalt tjänstenamn, version och commit.

Kontrollera därefter bearer-token mot agentens ping-endpoint:

```http
POST /api/v1/agent/test/ping
Authorization: Bearer <BOKFOERING_API_KEY>
```

Om ping returnerar `401` är headern fel, token saknas eller tokenvärdet är fel.
Fortsätt inte till bokföringsendpoints förrän ping returnerar `200`.

## API-upptäckt

Använd dessa endpoints för schema och verktygsdefinitioner:

```http
GET /openapi.json
```

`/openapi.json` är hela FastAPI-schemat. Särskilda endpoints för genererad
tool-schema-discovery, till exempel `/api/v1/agent/spec/openapi` och
`/api/v1/agent/spec/tools`, finns inte i aktuell version.

## Bankunderlag och bankhändelser

Bankunderlag hämtas via intagskön:

```http
GET /api/v1/agent/intake/pending
Authorization: Bearer <BOKFOERING_API_KEY>
```

Poster med `kind: bank_input` innehåller `transaction_ids`, `transaction_count`
och `match_signals`. Använd dessa fält när du postar verifikation med
`bank_input_ids` och `bank_transaction_ids`.

Det finns ingen separat agent-route `GET /api/v1/bank-transactions`. Om den
returnerar `404`, gå tillbaka till `/api/v1/agent/intake/pending` och använd
bankhändelse-id:n därifrån.

## Frontend

Frontend används av människor för att granska verifikationer, rapporter,
instruktioner, fakturor och korrigeringar. Agenten ska normalt arbeta mot
backend direkt, men kan hänvisa en människa till frontend när granskning eller
beslut krävs.

## Databas och säkerhet

Databasen ligger i serverns Docker-volym. Postade verifikationer ska betraktas
som varaktiga räkenskapsuppgifter. Radera aldrig data, volymer eller containrar
som del av agentens bokföringsarbete.

Om API:t returnerar fel:

- läs felmeddelandet
- kontrollera period, konto, belopp och schema
- gör inte antaganden om saknade uppgifter
- be om kompletterande underlag när bokföringsbeslutet är oklart
