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

## Hälsokontroll

Kontrollera först att backend svarar:

```http
GET /health
Authorization: Bearer <BOKFOERING_API_KEY>
```

Ett friskt svar innehåller normalt tjänstenamn, version och commit.

## API-upptäckt

Använd dessa endpoints för schema och verktygsdefinitioner:

```http
GET /openapi.json
GET /api/v1/agent/spec/openapi
POST /api/v1/agent/spec/tools
```

`/openapi.json` är hela FastAPI-schemat. `/api/v1/agent/spec/openapi` och
`/api/v1/agent/spec/tools` är mindre hjälpresurser för agentintegration.

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

