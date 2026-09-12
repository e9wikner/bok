# Spec: `idempotens`

Modul-id `idempotens` i kapabilitetskartan (`ANALYS.md` §8). Rotberoende — inget skrivflöde
kopplas till en knapp innan den här modulen är klar.

Status: **Fas 1 godkänd 2026-09-12.** Alla fyra öppna frågor är besvarade (se §12). Plan och
uppgifter ligger i `tasks/plan.md` och `tasks/todo.md`.

---

## Antaganden

1. Modulen rör **bara verifikationer** i den här omgången. Fakturasändning och löne­godkännande
   är ur scope (flöde 2 och 3 utgår), men mekanismen byggs generisk så de kan hänga på senare
   utan schemaändring.
2. Enbolag. Nyckeln behöver inte bära bolag.
3. `Idempotency-Key` genereras av klienten (UUIDv4) och hör till *avsikten*, inte till försöket.
   Samma avsikt → samma nyckel vid varje omförsök.
4. Idempotensnycklar är **inte** bokföringsmaterial. De omfattas inte av BFL:s bevarandekrav
   och *får* raderas. Verifikationerna de skyddar får det aldrig.

→ Punkt 4 är bekräftad som princip men **utnyttjas inte i den här modulen**: ingen radering byggs
(beslut 2, §12). Raden är ~200 byte per postning, så tabellen kostar inget att behålla, och varje
raderad nyckel återöppnar hålet för ett sent omförsök.

---

## 1. Objektiv

### Problemet, konkret

`POST /api/v1/agent/vouchers` (`api/routes/agent.py:60`) skapar **och** postar en verifikation i
samma transaktion. Ett omförsök — nätverkstimeout, dubbeltryck, agent som kör om ett pass — skapar
en **andra verifikation med ett nytt nummer**. Båda är postade. Båda är immutabla: SQL-triggers
(migration 014), `VoucherValidator` och avsaknaden av DELETE ser till att ingen av dem kan tas bort.

Den enda vägen ut ur en dubblett är en korrigeringsverifikation i B-serien. Det betyder att ett
tappat TCP-paket permanent förorenar huvudboken med två poster och en rättelse där det skulle
ha stått en.

`POST /api/v1/vouchers/{id}/post` (`api/routes/vouchers.py:424`) har inte samma hål — verifikationens
id är i praktiken nyckeln, och ett andra anrop ger `already_posted`. Men det returneras som **400
Bad Request**, vilket får klienten att visa ett fel för något som faktiskt lyckades. Designen kräver
motsatsen: *"Vid konflikt: `409` med den befintliga postens id, så klienten kan visa klart-läget
i stället för ett fel."*

### Vad vi bygger

En idempotensmekanism som gör varje skrivning som skapar ett oåterkalleligt bokföringsfaktum
säker att göra om, plus två felsvar som designen bygger på.

### Användare

Två, med olika behov:

- **Agenten** (worker, modul `agentruntime`) postar utan människa i loopen och måste kunna köra
  om ett avbrutet pass utan att gissa vad som hann bli gjort.
- **Människan** trycker på `Postera`-knappen i ett `VerifikationsForslag`. Trycker hon två gånger,
  eller tappar uppkopplingen efter trycket, ska hon se **klart-läget** — inte ett fel och inte
  två rader.

### Framgång

En postning kan göras om godtyckligt många gånger och ger exakt en verifikation, och klienten kan
alltid skilja "det gick igenom" från "det gick fel" utan att fråga en människa.

---

## 2. Tech stack

Inget nytt. FastAPI, SQLite med WAL och trådlokala anslutningar (`db/database.py`), plain-SQL-migrationer.

---

## 3. Kommandon

```bash
source venv/bin/activate

python main.py --init-db                 # applicerar migration 023
pytest tests/test_idempotency.py -v
pytest tests/ -v                         # hela sviten måste vara grön
black . && isort . && flake8 && mypy .
```

CI (`.github/workflows/tests.yml`) kör allt med `continue-on-error: true` — **en grön bock betyder
inte att stegen gick igenom.** Läs jobboutputen.

---

## 4. Projektstruktur

Modulen följer repots lagerindelning och lägger inget nytt lager till:

```
db/migrations/023_add_idempotency_and_lock_actor.sql   → tabell + periods.locked_by
repositories/idempotency_repo.py                       → all SQL för nycklar
services/idempotency.py                                → reservera / fullborda / spela upp
api/deps.py                                            → dependency som läser headern
api/routes/agent.py                                    → POST /agent/vouchers kopplas på
api/routes/vouchers.py                                 → POST /vouchers/{id}/post: 409-svar
                                                         POST /vouchers/{id}/correct: nyckel
services/ledger.py                                     → _commit genom korrigeringskedjan
repositories/voucher_repo.py                           → create_correction får _commit
docs/to_agent/02_bokforingsprocess.md                  → nyckelkravet (RUNTIME-INNEHÅLL)
api/routes/periods.py                                  → period_locked: 409 med vem/när
domain/validation.py                                   → befintliga felkoder, oförändrade
tests/test_idempotency.py                              → modulens tester
```

Ingen SQL utanför `repositories/`. Inga HTTP-begrepp i `services/`.

---

## 5. Datamodell

Ny migration — **ny fil, ingen redigering av redan applicerad migration.**

```sql
-- 023_add_idempotency_and_lock_actor.sql

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key                  TEXT NOT NULL,
    endpoint             TEXT NOT NULL,      -- "POST /api/v1/agent/vouchers"
    request_fingerprint  TEXT NOT NULL,      -- sha256 av kanoniserad body
    state                TEXT NOT NULL,      -- in_flight | completed
    response_status      INTEGER,            -- satt när completed
    response_body        TEXT,               -- JSON, satt när completed
    entity_type          TEXT,               -- "voucher"
    entity_id            TEXT,               -- verifikationens id
    actor                TEXT NOT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at         TIMESTAMP,
    PRIMARY KEY (key, endpoint),
    CHECK (state IN ('in_flight', 'completed'))
);

CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);

-- Låsningen ska kunna svara på vem, inte bara när.
ALTER TABLE periods ADD COLUMN locked_by TEXT;
```

`locked_at` finns redan (`001_initial_schema.sql:26`); `locked_by` saknas. Befintliga låsta perioder
backfillas från `audit_log` där `entity_type='period' AND action='locked'` i samma migration. Saknas
raden blir `locked_by` `NULL` och API:t svarar `"okänd"` — en historisk lucka ska synas som en lucka,
inte gissas.

**Nyckeln är (key, endpoint), inte key ensam.** Samma klientgenererade nyckel som återanvänds mot
en annan endpoint är en annan avsikt och ska inte spela upp fel svar.

---

## 6. Beteende

### Postningsvägen, steg för steg

```
1. Header saknas                → kör som i dag (se §8, övergångsregeln)
2. Slå upp (key, endpoint)
   ├─ finns inte               → reservera raden state=in_flight, gå vidare
   ├─ state=completed
   │   ├─ fingerprint lika     → spela upp response_status + response_body,
   │   │                         lägg till "Idempotent-Replay: true"
   │   └─ fingerprint olika    → 422 idempotency_key_reuse
   └─ state=in_flight          → 409 request_in_flight, klienten får försöka igen
3. Utför arbetet
4. Skriv response i SAMMA transaktion som verifikationen, state=completed
```

**Steg 4 är hela poängen.** Nyckelraden måste commitas i samma `db.transaction()` som
verifikationen. Skrivs den i en egen transaktion efteråt finns ett fönster där verifikationen är
postad men nyckeln saknas — och just det fönstret är hålet vi bygger för att stänga. Mönstret finns
redan i repot: `api/routes/agent.py:87` kör `create_voucher(_commit=False)` och
`post_voucher(_commit=False)` inuti ett `with db.transaction():`. Nyckelskrivningen läggs in där,
med samma `_commit=False`-konvention.

Reservationen i steg 2 commitas däremot direkt — annars är den osynlig för ett parallellt anrop
och skyddar ingenting. `PRIMARY KEY (key, endpoint)` gör att exakt en samtidig reservation vinner;
förloraren får `IntegrityError` och behandlas som `in_flight`.

### Fingerprint

sha256 över den kanoniserade requestbodyn: JSON med sorterade nycklar, inga blanksteg, UTF-8.
`actor` ingår **inte** — samma avsikt från samma klient är samma avsikt oavsett hur aktören
råkar formuleras.

### Felsvar

Tre former, alla med samma `detail`-form som repot redan använder
(`{"error", "code", "details"}`, se `api/routes/vouchers.py:440`):

| Läge | Status | `code` | Extra fält |
|---|---|---|---|
| Nyckel återanvänd med annan body | 422 | `idempotency_key_reuse` | `original_fingerprint` |
| Samtidigt anrop pågår | 409 | `request_in_flight` | `retry_after_ms` |
| Verifikationen redan postad | 409 | `already_posted` | `voucher` (hela objektet) |
| Perioden låst | 409 | `period_locked` | `locked_at`, `locked_by`, `period_id` |

De två sista är **statusbyten från 400 till 409** på befintliga felkoder. Koderna `already_posted`
och `period_locked` finns redan i `domain/validation.py:86` respektive `:69` — domänen ändras inte,
bara hur `api/routes/` mappar dem. Det är precis den uppdelning `CLAUDE.md` föreskriver: rutter
mappar domänfel till statuskoder.

### Retention

**Ingen radering i den här modulen** (beslut 2, §12). Ingen städfunktion, inget retentionstest,
ingen schemaläggare. Nycklarna ligger kvar tills någon ger dem en livslängd, och tills dess kan
inget omförsök bli för sent. `idx_idempotency_created` finns i schemat så att en framtida städning
kan hänga på utan migration.

---

## 7. Kodstil

Som repot i övrigt: black, isort, flake8 (ignorerar E203, E266, E501, W503), mypy. Statiska
repository-metoder, `_commit`-flagga genom hela kedjan, domänfel som `ValidationError`.

```python
class IdempotencyRepository:
    """Manage idempotency key persistence."""

    @staticmethod
    def reserve(
        key: str,
        endpoint: str,
        fingerprint: str,
        actor: str,
    ) -> bool:
        """Claim the key. Returns False if another request already holds it."""
        try:
            db.execute(
                """
                INSERT INTO idempotency_keys
                (key, endpoint, request_fingerprint, state, actor, created_at)
                VALUES (?, ?, ?, 'in_flight', ?, ?)
                """,
                (key, endpoint, fingerprint, actor, datetime.now()),
            )
            db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def complete(
        key: str,
        endpoint: str,
        response_status: int,
        response_body: str,
        entity_type: str,
        entity_id: str,
        _commit: bool = True,
    ) -> None:
        """Record the outcome. Call inside the same transaction as the write."""
        db.execute(
            """
            UPDATE idempotency_keys
            SET state = 'completed', response_status = ?, response_body = ?,
                entity_type = ?, entity_id = ?, completed_at = ?
            WHERE key = ? AND endpoint = ?
            """,
            (response_status, response_body, entity_type, entity_id,
             datetime.now(), key, endpoint),
        )
        if _commit:
            db.commit()
```

---

## 8. Övergång: är nyckeln obligatorisk?

`POST /agent/vouchers` har en befintlig konsument — dagens `bok-curl`-agent, som inte skickar någon
nyckel. Tre vägar:

- **(a) Obligatorisk direkt.** 400 utan header. Stänger hålet helt, men bryter dagens agent samma dag.
- **(b) Frivillig tills vidare.** Utan header körs den gamla vägen. Bryter inget — och stänger
  ingenting, eftersom exakt den konsument som oftast kör om ett pass är den som saknar nyckeln.
- **(c) Frivillig med varning i en release, sedan obligatorisk.** Anrop utan header loggas som
  `idempotency_key_missing` och `docs/to_agent/02_bokforingsprocess.md` uppdateras med kravet.

**Beslut: (c)** (beslut 1, §12), och `docs/to_agent/` uppdateras i samma omgång. Notera att den katalogen är
**runtime-innehåll, inte dokumentation** — den serveras av `repositories/system_instructions.py`
och testas av `tests/test_agent_entrypoint.py`. En ändring där ändrar systemets beteende och kräver
att testet uppdateras medvetet.

För nya klienter (`chattyta`, `flode-verifikationer`) är nyckeln obligatorisk från dag ett.

---

## 9. Teststrategi

pytest, `tests/test_idempotency.py`, fixtures från `tests/conftest.py` (`test_db`, `ledger_service`,
`fiscal_year`, `test_period`, `auth_headers`).

Testerna skrivs **före** implementationen. Modulen är liten nog att bära full TDD, och dess hela
existensberättigande är ett fall som är svårt att återskapa i efterhand.

| # | Fall | Förväntat |
|---|---|---|
| 1 | Samma nyckel, samma body, två anrop | En verifikation i `vouchers`. Identiska svarskroppar. Andra svaret bär `Idempotent-Replay: true`. |
| 2 | Samma nyckel, ändrad body | 422 `idempotency_key_reuse`. Ingen andra verifikation. |
| 3 | Två trådar, samma nyckel, samtidigt | Exakt en verifikation. Förloraren får 409 `request_in_flight` eller uppspelning — aldrig en andra post. |
| 4 | Olika nycklar, identisk body | **Två** verifikationer. Idempotens är inte dubblettdetektering — två likadana köp får finnas. |
| 5 | Samma nyckel, olika endpoint | Ingen uppspelning. Behandlas som ny avsikt. |
| 6 | Avbrott mitt i transaktionen | Varken verifikation eller nyckelrad finns kvar. Omförsök lyckas rent. |
| 7 | `POST /vouchers/{id}/post` på redan postad | 409 `already_posted` med hela verifikationen i `detail.voucher`. Inte 400. |
| 8 | Postning mot låst period | 409 `period_locked` med `locked_at` och `locked_by`. |
| 9 | Låst period utan `locked_by` i `audit_log` | `locked_by` är `null`, svaret säger `"okänd"`. Inget krasch, ingen gissning. |
| 10 | `POST /vouchers/{id}/correct`, samma nyckel två gånger | **En** B-serieverifikation. Andra svaret uppspelat med `Idempotent-Replay: true`. |
| 11 | Avbrott i korrigeringskedjan | Varken B-verifikation, `accounting_corrections`-rad eller nyckelrad finns kvar. |
| 12 | Anrop utan header | Går igenom som i dag, och `idempotency_key_missing` hamnar i loggen. |
| 13 | Regression | Hela `tests/` grön. Särskilt `test_ledger.py`, `test_agent_accounting_workflow.py`, `test_correction_notes.py` och `test_agent_entrypoint.py`. |

Test 3 kräver äkta trådar mot samma SQLite-fil. Anslutningarna är trådlokala med WAL
(`db/database.py:31`), så det fungerar — men testet får inte dela en connection mellan trådarna.

Test 11 är nytt för att korrigeringsvägen inte har något transaktionsmönster i dag — se §12.4.

Test 6 är modulens svåraste och viktigaste. Det skrivs genom att låta en `db.transaction()` kasta
efter postningen men före commit, och sedan verifiera att **båda** raderna är borta.

Frontendtester finns inte i repot och byggs inte här.

---

## 10. Gränser

**Alltid**

- Ny migrationsfil för schemaändringar. Aldrig redigera en applicerad.
- Nyckelraden commitas i samma transaktion som verifikationen.
- All SQL i `repositories/`. Statusmappning bara i `api/routes/`.
- Hela `tests/` körs före commit, och jobboutputen läses — inte bocken.
- `black . && isort . && flake8 && mypy .` innan commit.

**Fråga först**

- Att gå från (c) till hårt krav, dvs. släppa releasen som gör headern obligatorisk. Beslut 1 täcker
  varningssteget, inte avstängningen.
- Varje ytterligare ändring i `docs/to_agent/*.md` utöver nyckelkravet. Katalogen är runtime-innehåll:
  den serveras av `repositories/system_instructions.py` och asserteras på av `tests/test_agent_entrypoint.py`.
- Att ge nycklarna en livslängd. Beslut 2 är "ingen radering"; en städning är ett nytt beslut.
- Att röra något annat i korrigeringskedjan än `_commit`-genomtrådningen (§12.4).

**Aldrig**

- Lätta på en trigger, lägga till en väg att ändra postad verifikation, eller radera en verifikation
  för att städa en dubblett. Dubbletter som redan finns rättas med B-serieverifikation.
- Låta klienten konstruera en postning utan utkast-id.
- Spela upp ett svar när fingerprint inte stämmer.
- Använda idempotenstabellen som revisionsspår. `audit_log` är revisionsspåret.

---

## 11. Framgångskriterier

Modulen är klar när allt nedan är sant:

1. Två identiska `POST /api/v1/agent/vouchers` med samma `Idempotency-Key` ger **en** rad i
   `vouchers`, och båda svaren är identiska så när som på `Idempotent-Replay: true` på det andra.
2. Samma nyckel med ändrad body ger 422 `idempotency_key_reuse` och skapar ingen verifikation.
3. Tio parallella trådar med samma nyckel ger exakt en verifikation.
4. Ett avbrott mellan postning och nyckelskrivning lämnar databasen utan både verifikation och
   nyckel — inga halvvägstillstånd.
5. `POST /vouchers/{id}/post` på en postad verifikation ger 409 med verifikationen i svaret, så
   klienten kan rendera klart-läget direkt.
6. Postning mot låst period ger 409 `period_locked` med `locked_at` och `locked_by`.
7. `POST /vouchers/{id}/correct` med samma nyckel två gånger ger **en** B-serieverifikation, och
   hela korrigeringen — B-verifikation, `accounting_corrections`-rad, nyckelrad — commitas eller
   rullas tillbaka tillsammans.
8. Anrop utan header fungerar som i dag och loggar `idempotency_key_missing`;
   `docs/to_agent/02_bokforingsprocess.md` beskriver kravet och `test_agent_entrypoint.py` är
   uppdaterat medvetet.
9. `tests/` är grön, inklusive de 25 befintliga testfilerna.
10. `black`, `isort`, `flake8`, `mypy` rena — verifierat i jobboutput, inte via bocken.

---

## 12. Beslut

Alla fyra frågorna avgjordes vid fas 1-granskningen 2026-09-12.

### 12.1 Obligatorisk nyckel → **(c)**

Frivillig med varning i en release, sedan obligatorisk. Anrop utan header körs som i dag och loggas
som `idempotency_key_missing`, och `docs/to_agent/02_bokforingsprocess.md` uppdateras med kravet i
samma omgång. För nya klienter (`chattyta`, `flode-verifikationer`) är nyckeln obligatorisk från
dag ett. Avstängningen — att faktiskt svara 400 utan header — är ett eget beslut senare (§10).

### 12.2 Retention → **ingen radering i den här modulen**

Antagande 4 står kvar som princip: nycklarna är inte bokföringsmaterial och *får* raderas. Men de
raderas inte nu. Raden är ~200 byte per postning, så även tusentals verifikationer per år är
försumbart, och varje raderad nyckel återöppnar hålet för ett sent omförsök. Ingen städfunktion,
inget retentionstest, ingen schemaläggare. `idx_idempotency_created` ligger i schemat så att en
framtida städning kan hänga på utan migration.

### 12.3 Bryter 400 → 409 någon konsument? → **nej, verifierat**

`already_posted` och `period_locked` förekommer bara i `domain/validation.py` (`:69`, `:86`, `:130`)
och i `tests/test_ledger.py:105`, och det testet asserterar domänkoden — inte HTTP-statusen.
Ingenting i `frontend-v3` läser någon av koderna, och `scripts/bok-curl:37` skriver bara ut
`%{http_code}` utan att grena på värdet. De 400-assertions som finns i sviten gäller andra koder
(`voucher_not_posted`, obalanserad verifikation). Statusbytet kan göras utan följdändringar.

### 12.4 `POST /vouchers/{id}/correct` → **ja, med i den här modulen**

Endpointen (`api/routes/vouchers.py:451`) skapar en B-serieverifikation och har samma
dubblettproblem — och en korrigering är precis vad man gör om efter ett avbrott.

**Men den kostar en uppgift mer än jag först sa.** `create_posted_correction`
(`services/ledger.py:266`) kör i dag *inte* i en transaktion: den anropar `create_correction`,
`post_voucher` och `_record_correction_history`, som var och en commitar för sig. För att nyckelraden
ska kunna commitas tillsammans med korrigeringen måste kedjan gå att köra med `_commit=False`. Av
hela kedjan saknar exakt **en** metod flaggan:

- `VoucherRepository.create_correction` (`repositories/voucher_repo.py:256`) — commitar internt,
  behöver `_commit`-parameter.
- `add_row` (`:63`), `post` (`:247`), `AuditService.log` och `AccountingCorrectionRepository.create`
  har den redan.
- `services/ledger.create_correction` (`:197`) och `create_posted_correction` (`:266`) behöver
  tråda flaggan vidare.

Det är en avgränsad ändring på befintligt mönster, men den rör en kodväg som fem testfiler
använder — därav en egen uppgift med regressionskörning, inte ett påhäng på rutten.
