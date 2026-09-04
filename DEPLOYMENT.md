# Deployment av Bok

Den rekommenderade driftsformen i den här milstolpen är en egen Docker-server på
LAN/lokalt nätverk. Det här är self-hosted Docker, inte managed hosting.
Publik domän med HTTPS är ett separat, valfritt spår längre ned.

Terraform/Hetzner-instruktionerna är inte den validerade vägen i den här
milstolpen. Använd `DEPLOYMENT.md` som den kanoniska driftguiden.

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

`git bundle` över SSH är ett avancerat, sekundärt spår för installationer där
servern inte ska hämta direkt från GitHub. Det är inte normalvägen för
LAN-uppdateringar.

### 3. Skapa `.env.production`

```bash
cp .env.production.example .env.production
```

Öppna `.env.production` i en editor och ersätt alla hemligheter innan du startar
tjänsten.

Obligatoriskt att byta:

- `BOKFOERING_API_KEY` - används av agent/API-klienter mot backendens skyddade
  endpoints.
- `JWT_SECRET` - används av backend för att signera och verifiera
  inloggningstokens.
- `AUTH_PASSWORD` - används för första admininloggningen i webbgränssnittet.

Exempel på säkra värden:

```bash
openssl rand -hex 32    # BOKFOERING_API_KEY
openssl rand -hex 32    # JWT_SECRET
openssl rand -base64 24 # AUTH_PASSWORD
```

Sätt sedan in resultatet i `.env.production`, till exempel:

```env
BOKFOERING_API_KEY=klistra-in-slumpat-varde-har
JWT_SECRET=klistra-in-slumpat-varde-har
AUTH_PASSWORD=klistra-in-starkt-losenord-har
```

Spara värdena i en lösenordshanterare så att du kan återställa installationen
senare. Kör inte med exempelvärden.

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

Använd inte `docker compose down -v` för normal deployment, uppdatering eller
återställning. `-v`, borttagning av Docker-volymer eller radering av
`bokfoering-data` kan radera bokföringsdata.

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

### 10. Koppla OpenClaw eller annan HTTP-agent

Bok har ett publikt API-entrypoint för externa agenter. Efter att du har loggat
in kan du koppla en HTTP-agent (t.ex. OpenClaw) som skickar
bearer-autentiserade anrop till backend.

**Människor använder frontend:**
```text
http://SERVER_IP_OR_HOSTNAME:3000/login
```

**Agenter använder backend-API:**
```text
http://SERVER_IP_OR_HOSTNAME:8000
```

`BACKEND_URL=http://api:8000` är Docker-intern och ska aldrig ges till en agent
utanför Docker-nätverket.

**Kontrollera innan du kopplar agenten:**

Sätt shell-variabler:

```bash
BOK_API_URL="http://SERVER_IP_OR_HOSTNAME:8000"
API_KEY="ditt-värde-från-BOKFOERING_API_KEY"
```

Kontrollera backend-hälsa:

```bash
curl -fsS "${BOK_API_URL}/health"
```

Kontrollera att entrypoint är publikt:

```bash
curl -fsS "${BOK_API_URL}/api/v1/agent-instructions/entrypoint"
```

Kontrollera att agent-auth fungerar:

```bash
curl -fsS -X POST "${BOK_API_URL}/api/v1/agent/test/ping" \
  -H "Authorization: Bearer ${API_KEY}"
```

**Ge agenten entrypoint och nyckel:**

1. Kopiera backend-entrypoint-URL:en:
   ```text
   ${BOK_API_URL}/api/v1/agent-instructions/entrypoint
   ```
2. Kopiera API-nyckeln från `BOKFOERING_API_KEY` i `.env.production`.
3. Ge båda till agenten. Agenten hämtar själv startup-instruktioner,
   auth-check och workflow-länkar från entrypoint.

**Första instruktion till agenten (verifiering):**

Klistra in följande i agenten. Detta är enbart en verifieringsprompt — agenten
ska inte börja bokföra eller behandla pending intake än:

```text
Du är en HTTP-agent som ska börja bokföra i Bok. Gör följande:
1. Läs startup-instruktionerna från ${BOK_API_URL}/api/v1/agent-instructions/entrypoint
2. Verifiera att du kan anropa API:t med POST ${BOK_API_URL}/api/v1/agent/test/ping och Authorization: Bearer <BOKFOERING_API_KEY>
3. Rapportera att du är redo och beskriv exakt vilken fråga eller åtgärd ägaren behöver göra härnäst för att starta bokföringen
4. Be ägaren om tillstånd innan du påbörjar den första bokföringskörningen
5. Behandla inte pending intake och starta inte bokföringen nu — detta är enbart en verifieringsprompt
```

## Uppdatera säkert på LAN

Den normala uppdateringsvägen för LAN/lokal server är lokal Git-checkout +
`docker-compose.local.yml`. Använd inte Terraform/Hetzner eller `git bundle`
som standardrutin för vanliga uppdateringar.

### Uppdateringschecklista

1. Skapa eller bekräfta en aktuell säkerhetskopia innan du rör koden.
2. Kontrollera att arbetskopian är ren så att du vet vad som ändras.
3. Hämta den avsedda versionen med Git.
4. Bygg om och starta tjänsterna igen.
5. Verifiera containerstatus, backend och frontend innan du lämnar servern.

```bash
git status
git pull
docker compose --env-file .env.production -f docker-compose.local.yml up -d --build
docker compose --env-file .env.production -f docker-compose.local.yml ps
curl -fsS http://localhost:8000/health
curl -fsSI http://localhost:3000/login
curl -fsS http://localhost:3000/health
```

Blunt varning: kör inte `docker compose down -v`, ta inte bort Docker-volymer
och radera aldrig `bokfoering-data` som del av en normal uppdatering. Normala
uppdateringar ska använda `up -d --build` följt av verifiering, inte volymradering.

## Valfritt: synkad mapp (Syncthing) som intag

Filer som läggs i en synkad mapp plockas upp av sig själva — ingen webbläsare,
ingen uppladdningsknapp. Mappen blir samtidigt statusvyn: en tom `Kvitton/`
betyder att allt ligger i systemet. Webbläsaruppladdningen finns kvar som andra
väg in.

Funktionen är avstängd som standard. `DROPZONE_ENABLED=false` lämnar nuvarande
beteende helt orört.

### 1. Mappstruktur på servern

Skapa mappen som Syncthing ska dela och lägg upp skelettet:

```bash
mkdir -p /opt/docker/bok/dropzone/{Kvitton,Leverantörsfakturor,Kundfakturor,Utlägg,Övrigt}
mkdir -p "/opt/docker/bok/dropzone/Kontoutdrag/1930 Företagskonto"
```

Mappkontraktet:

```text
Bokföring/                     ← Syncthings delade mapp
  Kvitton/                     → kvitto
  Leverantörsfakturor/         → leverantörsfaktura
  Kundfakturor/                → kundfaktura
  Utlägg/                      → utlägg/ersättning
  Övrigt/                      → annat
  Kontoutdrag/
    1930 Företagskonto/        → kontoutdrag för konto 1930
    1630 Skattekonto/          → kontoutdrag för konto 1630
  _Inläst/2026-09/             ← hit flyttas inlästa filer
  _Problem/                    ← hit flyttas avvisade filer, med .txt som förklarar
```

Mappnamnen matchas oberoende av versaler och av hur `å ä ö` är lagrade, så en
mapp skapad på en Mac fungerar lika bra som en skapad på servern. En fil i
mappens rot eller i en okänd mapp läses in utan typ — agenten klassificerar den.
En `.txt` är alltid sidodata, aldrig underlag.

**Kontoutdrag.** Ledande token i mappnamnet är kontokoden, resten är en etikett
som ignoreras: `Kontoutdrag/1930/`, `Kontoutdrag/1930 Företagskonto/` och
`Kontoutdrag/1930-Företagskonto/` är likvärdiga. `Bank/` accepteras som alias.
Att lägga till `Kontoutdrag/1630 Skattekonto/` kräver ingen kodändring och ingen
konfiguration — bara att konto 1630 finns i kontoplanen och är ett tillgångs-
eller skuldkonto. Saknas kontot säger intagssidan till innan något lagts där.

**Valfri sidodata.** `_meddelande.txt` i en mapp blir meddelande till agenten för
alla filer i mappen och ligger kvar. `<filnamn>.txt` bredvid en fil blir just den
filens förklaring och flyttas med filen.

### 2. Slå på hämtningen

Lägg till i `.env.production`:

```bash
DROPZONE_ENABLED=true
DROPZONE_HOST_DIR=/opt/docker/bok/dropzone
```

Starta om och verifiera:

```bash
docker compose -f docker-compose.local.yml up -d --build
curl -fsS -H "Authorization: Bearer ${API_KEY}" \
  http://localhost:8000/api/v1/intake/dropzone/status
```

Scannern är en tråd i API-processen och tar ett låsfil-lås i mappen, så bara en
scanner går även om fler startas. Den raderar aldrig någon fil — den flyttar.
Filer som fortfarande skrivs läses inte förrän de lagt sig.

Containern kör som root med flit: filerna i bind-mounten skrivs av värdens
Syncthing-användare och måste kunna läsas och flyttas. Lägg inte till en
`USER`-rad i `Dockerfile` — då slutar mapphämtningen fungera.

### 3. Syncthing

1. Installera Syncthing på servern och på de enheter som ska lägga filer i
   mappen (laptop, telefon).
2. Dela **en** mapp — den katalog `DROPZONE_HOST_DIR` pekar på.
3. Sätt serverns kopia till **Send & Receive**. Det är nödvändigt: flyttarna in
   i `_Inläst/` måste propagera ut igen, annars töms aldrig inkorgen på de andra
   enheterna.
4. Foton: ställ in kameran på "Mest kompatibla", eller exportera som JPEG. HEIC
   stöds inte — en HEIC-fil hamnar i `_Problem/` med en notering om hur den
   rättas.

**Ska `_Inläst/` synkas?** Behåll den i den delade mappen så att servern har ett
riktigt arkiv, och låt utrymmesbegränsade enheter utesluta den med en rad i sin
`.stignore`. Det är ett val per enhet, inte per mapp — varje enhet bestämmer
själv.

### 4. Kontrollera att hämtningen lever

Det klassiska felläget för mappbaserade system är att scannern dör tyst: filerna
hopar sig i `Kvitton/`, man utgår från att de ligger i kö, och två månader senare
är ingenting bokfört. En stoppad scanner och en nyss släppt fil ser likadana ut i
mappen.

Intagssidan visar därför när hämtningen senast kördes och varnar när den slutat.
Samma uppgifter finns i `GET /api/v1/intake/dropzone/status`, tillsammans med
antal väntande filer, antal filer i `_Problem/` och mappar under `Kontoutdrag/`
vars kontokod är okänd.

## Säkerhetskopiering

Den viktiga bokföringsdatan ligger i `/app/data` i den persistenta Docker-volymen
`bokfoering-data`. Git-checkouten och `.env.production` räcker inte för att
återställa bokföringsdata. Använd `./backups` som lokal katalog för
ägarkontrollerade backupfiler.

### Manuell LAN-backup

Skapa en tidsstämplad arkivfil från `bokfoering-data`:

```bash
mkdir -p backups
timestamp=$(date +%Y%m%d-%H%M%S)
docker run --rm \
  -v bokfoering-data:/source:ro \
  -v "$PWD/backups:/archive" \
  alpine sh -c "cd /source && tar -czf /archive/bokfoering-data-${timestamp}.tar.gz ."
ls -lh backups/
tar -tzf "backups/bokfoering-data-${timestamp}.tar.gz" | head
```

Det här arkivet är den praktiska säkerhetskopian av SQLite-databasen och övriga
filer i `/app/data`.

### Valfritt publikt backupspår

`docker-compose.prod.yml` innehåller den valfria containern
`offen/docker-volume-backup`, som skriver backuparkiv till `./backups`. Det spåret
hör till publik domän/HTTPS-installationer och är inte den rekommenderade
standardrutinen för LAN.

S3-kompatibla variabler i `.env.production.example` är valfria platshållare för
framtida eller separat validerad off-site backup. I den här milstolpen ska de
inte tolkas som en verifierad backupväg.

## Återställ backup

Återställning ersätter aktuell bokföringsdata. Ta en ny backup först om du vill
behålla nuvarande läge innan du återställer en äldre kopia.

Stoppa tjänsterna utan att ta bort volymer:

```bash
docker compose --env-file .env.production -f docker-compose.local.yml stop
```

Återställ vald backup till `bokfoering-data`:

```bash
BACKUP_FILE=backups/bokfoering-data-YYYYMMDD-HHMMSS.tar.gz
docker run --rm \
  -v bokfoering-data:/target \
  -v "$PWD/backups:/archive" \
  alpine sh -c "rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null; tar -xzf /archive/$(basename "$BACKUP_FILE") -C /target"
```

Starta därefter tjänsterna igen:

```bash
docker compose --env-file .env.production -f docker-compose.local.yml up -d
docker compose --env-file .env.production -f docker-compose.local.yml ps
curl -fsS http://localhost:8000/health
curl -fsSI http://localhost:3000/login
curl -fsS http://localhost:3000/health
```

Kontrollera även inloggning i webbläsaren efter återställning. Bevara
`.env.production` om du inte medvetet återställer hemligheter eller annan
konfiguration separat. Återställning får inte använda `docker compose down -v`
och ska inte radera Docker-volymer utanför den kontrollerade återläsningen till
`bokfoering-data`.

## Rollback till tidigare commit

Om en uppdatering går fel kan du köra tillbaka till en tidigare Git-commit utan
att radera volymer eller ersätta `.env.production`.

```bash
git log --oneline -n 10
git checkout <COMMIT_SHA>
docker compose --env-file .env.production -f docker-compose.local.yml up -d --build
docker compose --env-file .env.production -f docker-compose.local.yml ps
curl -fsS http://localhost:8000/health
curl -fsSI http://localhost:3000/login
curl -fsS http://localhost:3000/health
```

När problemet är löst och du vill tillbaka till ordinarie gren:

```bash
git checkout main
git pull
docker compose --env-file .env.production -f docker-compose.local.yml up -d --build
```

Rollback ska inte ta bort Docker-volymer och ska inte ersätta
`.env.production` om du inte uttryckligen också återställer konfiguration.

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
docker compose --env-file .env.production -f docker-compose.local.yml up -d --build
```

Behåll serverns befintliga `.env.production`. Den ska inte komma från Git.

## Valfritt: publik domän och HTTPS

Det här spåret är bara för en server som ska exponeras publikt och där du redan
har DNS och en e-postadress för Let's Encrypt. Blanda inte ihop detta med
LAN-checklistan ovan.

**Om du använder publik domän och HTTPS:** människor loggar in via
`https://${APP_DOMAIN}` och agenten använder `https://${API_DOMAIN}`.

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

### Containerstatus eller unhealthy tjänster

```bash
docker compose --env-file .env.production -f docker-compose.local.yml ps
docker compose --env-file .env.production -f docker-compose.local.yml logs --tail=100
```

Om `api` eller `frontend` inte är `Up` ska du läsa loggarna först och sedan
starta om med:

```bash
docker compose --env-file .env.production -f docker-compose.local.yml up -d
```

### Backend svarar inte

```bash
curl -fsS http://localhost:8000/health
```

Om kommandot fallerar:

- kontrollera `docker compose ... ps`
- läs `docker compose ... logs --tail=100 api`
- bekräfta att `.env.production` finns
- kontrollera att inga placeholders används i hemlighetsfälten

### Frontend eller inloggningssidan svarar inte

```bash
curl -fsSI http://localhost:3000/login
curl -fsS http://localhost:3000/health
```

Om frontend svarar men API-anrop från webben misslyckas, kontrollera dessa värden
i `.env.production`:

```env
NEXT_PUBLIC_API_URL=
BACKEND_URL=http://api:8000
```

För LAN/lokal server ska `NEXT_PUBLIC_API_URL=` vara tom och
`BACKEND_URL=http://api:8000`. Om du sätter ett annat värde här kan frontenden
peka fel eller hoppa över samma-origin-proxyn.

### `.env.production` saknas eller innehåller osäkra värden

```bash
test -f .env.production
rg "dev-key-change-in-production|dev-jwt-secret-change-in-production|AUTH_PASSWORD=admin" .env.production
```

Om `test -f` misslyckas finns filen inte. Om `rg` skriver träffar innehåller
filen osäkra placeholders och måste rättas innan tjänsten används.

### Publik domän, DNS eller HTTPS fungerar inte

Det här avsnittet gäller bara om du använder `docker-compose.prod.yml`.
Kontrollera att följande variabler finns och är riktiga:

```env
APP_DOMAIN=app.example.com
API_DOMAIN=api.example.com
LETSENCRYPT_EMAIL=admin@example.com
```

Verifiera sedan DNS och HTTPS:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl -fsS "https://${API_DOMAIN}/health"
curl -fsSI "https://${APP_DOMAIN}/login"
```

Om detta fallerar, kontrollera att DNS redan pekar rätt, att port 80/443 når
servern och att Let's Encrypt kan utfärda certifikat för `APP_DOMAIN` och
`API_DOMAIN`.

### Agenten får 401 eller svarar inte

Om agenten får `401 Unauthorized` eller inget svar:

- Kontrollera att du använder rätt API-nyckel från `BOKFOERING_API_KEY`.
- Kontrollera att `Authorization: Bearer ${API_KEY}` skickas med i headern.
- Kontrollera att du använder backend-porten `8000`, inte frontend-porten `3000`.
- Kontrollera att du använder den externa backend-URL:en
  (`http://SERVER_IP_OR_HOSTNAME:8000`), inte Docker-interna
  `BACKEND_URL=http://api:8000`.

## Supportklar diagnostik

Skicka diagnostik som visar version, commit, containerstatus, loggutdrag och
hälsokontroller. Skicka inte hela `.env.production`.

```bash
docker --version
docker compose version
git rev-parse --short HEAD
docker compose --env-file .env.production -f docker-compose.local.yml ps
docker compose --env-file .env.production -f docker-compose.local.yml logs --tail=100
curl -fsS http://localhost:8000/health
curl -fsSI http://localhost:3000/login
curl -fsS http://localhost:3000/health
rg "dev-key-change-in-production|dev-jwt-secret-change-in-production|AUTH_PASSWORD=admin" .env.production
```

Berätta gärna vilken URL du testade, vad du förväntade dig och exakt vilket fel
du såg. Men klistra inte in hela `.env.production` i supportkanaler eller issue-
rapporter.
