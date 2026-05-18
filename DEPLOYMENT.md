# Deployment av Bok

Den rekommenderade driftsformen i den här milstolpen är en egen Docker-server på
LAN/lokalt nätverk. Det här är self-hosted Docker, inte managed hosting.
Publik domän med HTTPS är ett separat, valfritt spår längre ned.

Terraform/Hetzner-instruktionerna är inte den validerade vägen i den här
milstolpen.

## Filerna du använder

- `.env.production` - dina lokala hemligheter och driftinställningar. Skapas från
  `.env.production.example` och ska inte commitas.
- `docker-compose.local.yml` - rekommenderad Compose-fil för LAN/lokal server.
- `docker-compose.prod.yml` - valfri publik domän/HTTPS med Traefik och Let's
  Encrypt.
- `DEPLOYMENT.md` - den här guiden, den kanoniska driftsinstruktionen.

## LAN/lokal server: checklista

### 1. Förutsättningar

Servern behöver:

- Linux-server på ditt lokala nätverk.
- Docker Engine och Docker Compose v2.
- Git.
- En fast IP-adress eller ett stabilt lokalt hostnamn.
- Tillgång till terminalen på servern.

Kontrollera:

```bash
docker --version
docker compose version
git --version
```

### 2. Hämta koden

GitHub är normalvägen för första installation och senare uppdateringar:

```bash
git clone https://github.com/e9wikner/bok.git
cd bok
```

Vid senare uppdatering:

```bash
git pull
```

### 3. Skapa `.env.production`

```bash
cp .env.production.example .env.production
```

Öppna `.env.production` i en editor och ersätt alla hemligheter innan du startar
tjänsten.

Obligatoriskt att byta:

- `BOKFOERING_API_KEY` - API-nyckel för agenten.
- `JWT_SECRET` - signeringshemlighet för inloggning.
- `AUTH_PASSWORD` - adminlösenordet för första inloggning.

Använd en lösenordshanterare eller annan betrodd slumpgenerator. Spara värdena
så att du kan återställa installationen senare. Kör inte med exempelvärden.

Osäkra fallbacks/placeholders som inte får användas i verklig drift:

- `dev-key-change-in-production`
- `dev-jwt-secret-change-in-production`
- `admin`

### 4. LAN-standard för frontend och backend

Behåll dessa värden för LAN/lokal server:

```env
NEXT_PUBLIC_API_URL=
BACKEND_URL=http://api:8000
```

`NEXT_PUBLIC_API_URL=` ska vara tom. Då anropar webbläsaren samma origin via
`/api`, och Next.js-proxyn skickar vidare till `BACKEND_URL`.

`BACKEND_URL=http://api:8000` är den interna backend-adressen inne i Docker
Compose-nätverket. Ändra inte den för LAN-drift.

### 5. Starta

```bash
docker compose --env-file .env.production -f docker-compose.local.yml up -d --build
```

Använd inte `docker compose down -v` för normal deployment eller uppdatering.
`-v` tar bort volymer och kan radera SQLite-data.

### 6. Verifiera containrar

```bash
docker compose --env-file .env.production -f docker-compose.local.yml ps
```

Backend ska vara igång och frontend ska vara igång.

### 7. Verifiera backend

```bash
curl -fsS http://localhost:8000/health
```

Kommandot ska skriva ett lyckat hälsosvar.

### 8. Verifiera frontend

```bash
curl -fsSI http://localhost:3000/login
curl -fsS http://localhost:3000/health
```

### 9. Första inloggning

Öppna från en annan dator på samma LAN:

```text
http://SERVER_IP_OR_HOSTNAME:3000/login
```

Logga in med användarnamnet från `AUTH_USERNAME` och lösenordet du satte i
`AUTH_PASSWORD`.

## Avancerat: git bundle över SSH

Använd bara det här om servern ska få kod från en lokal repository-kopia i stället
för GitHub.

Skapa bundle lokalt:

```bash
commit="$(git rev-parse --short HEAD)"
git bundle create "/tmp/bok-deploy-${commit}.bundle" HEAD
```

Skicka till servern:

```bash
scp "/tmp/bok-deploy-${commit}.bundle" user@SERVER_IP_OR_HOSTNAME:/tmp/
```

Hämta in på servern:

```bash
ssh user@SERVER_IP_OR_HOSTNAME
cd ~/bok
git fetch "/tmp/bok-deploy-${commit}.bundle" HEAD:refs/heads/deploy-local
git checkout deploy-local
git reset --hard deploy-local
```

Behåll serverns befintliga `.env.production`. Den ska inte komma från Git.

## Valfritt: publik domän och HTTPS

Det här spåret är bara för en server som ska exponeras publikt och där du redan
har DNS och en e-postadress för Let's Encrypt. Blanda inte ihop detta med
LAN-checklistan ovan.

Använd `docker-compose.prod.yml` och sätt minst:

```env
APP_DOMAIN=app.example.com
API_DOMAIN=api.example.com
LETSENCRYPT_EMAIL=admin@example.com
```

DNS ska peka `APP_DOMAIN` och `API_DOMAIN` till serverns publika IP-adress innan
du startar.

Starta det publika spåret med:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

Kontrollera därefter:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl -fsS "https://${API_DOMAIN}/health"
curl -fsSI "https://${APP_DOMAIN}/login"
```

## Felsökning

Visa status:

```bash
docker compose --env-file .env.production -f docker-compose.local.yml ps
```

Visa loggar:

```bash
docker compose --env-file .env.production -f docker-compose.local.yml logs -f
```

Starta om efter ändring i `.env.production`:

```bash
docker compose --env-file .env.production -f docker-compose.local.yml up -d
```

Kontrollera att `.env.production` finns och inte innehåller placeholders:

```bash
test -f .env.production
rg "dev-key-change-in-production|dev-jwt-secret-change-in-production|AUTH_PASSWORD=admin" .env.production
```

Om `rg` hittar något av dessa värden ska filen ändras innan tjänsten används.
