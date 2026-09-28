# Plan: modul `flode-underlag`

Bygger `docs/redesign/SPEC-flode-underlag.md` (fas 1, godkänd 2026-09-28, besluten D1–D10 i §12).
Uppgiftslistan ligger i `tasks/flode-underlag/todo.md`. Beror på `flode-verifikationer` och
`underlagstolkning`, som båda är klara. Den sista modulen i kartan; ersättningen av ett
felkopplat underlag är nästa modul, `underlag-ersatt` (D10).

Modulen har fyra spår som möts i tråden:

- **Schemat och predikatet** (FU1–FU2): två append-only-tabeller, och "saknar underlag" som
  undantar rättelser och räknar hänvisningen.
- **Kopplingen** (FU3–FU7, FU9–FU10): servicen med kontrollerna och beläggen, verktyget, routen,
  stoppet i postningen, kvittot och hänvisningen i postningens transaktion.
- **Tråden och agenten** (FU8, FU11–FU18): jämförelseinlägget, passet, agentens läsning,
  instruktionen, meddelande utan text, `existing_id`, `referenced_by`, sidantalet.
- **Klienten** (FU19–FU23): uppladdningen, `drop`-varianten, sektionen `Saknar underlag`, `note`
  i kvittot, kvittot från verifikationen.

FU24 stänger med regressionen och framgångskriterierna.

## Beroendegraf

```
FU1 migration 032: intake_link_basis + voucher_source_references, domän, repositories  (gate 1)
      │
      ├──► FU2 predikatet: D3 + hänvisningen (voucher_repo)                            (gate 2)
      │          │
      │          └──► FU16 referenced_by + source-context via hänvisningen ◄── FU14 (api/schemas.py)
      │
      ├──► FU3 IntakeLinkService: kontroller 1–8, exact_match, transaktion, uppspelning
      │          │
      │          ▼
      │     FU4 beslutsbelägget (kontroll 9, D1)
      │          │
      │          ├──► FU5 koppla_underlag sist i verktygslistan ──► FU12 las_verifikationer
      │          │          │
      │          ├──► FU6 POST /intake/{id}/link ──► FU15 existing_id i 409
      │          │          │
      │          └──► FU7 stoppet (voucher_posting, draft_service, agent-routen)
      │                     │
      │                     ├──► FU13 instruktionen (kräver FU5)
      │                     │
      │                     └──► FU10 hänvisningen i on_posting (kräver FU2)
      │
      ├──► FU8 jämförelseinlägget (interpretation_service) ──► FU9 kvittot + view.changed (kräver FU7)
      │
      ├──► FU11 passet hoppar över trådens filer (D4)
      │
      └──► FU14 D8: meddelande utan text ──► FU17 pages för pdf i user_file
                                                     │
FU5, FU9, FU10, FU11, FU13, FU14 ───────────────────►FU18 skriptade flöden 39–42

Klienten (kontrakten ur specen; verifieras mot backend när den landat):
FU19 uppladdning.ts + api (kontrakt: FU15)
      │
      ▼
FU20 ChattFalt drop (kräver FU14 för tom text)
      │
      ▼
FU21 sektionen Saknar underlag, Nyss kopplad, fot (kräver FU9, FU16)
      │
      ▼
FU23 kvittot från verifikationen (kräver FU16)

FU22 receipt.note + FilInlagg-länk (kontrakt: FU8) ── parallellt med FU19–FU21

Alla ──► FU24 regression, modulen stängd
```

## Ordning och varför

**FU1 först, och FU1 är modulens första gate.** Allt som skriver ett belägg eller en hänvisning
står på de två tabellerna, och båda är append-only i tre lager (§15). Triggrarna ska vara bevisade
(testfall 17, 42c) innan en rad kod skriver i dem, samma resonemang som `underlagstolkning` U2 och
`flode-verifikationer` F5. Migrationen rör ingen befintlig tabell. 032 är nästa lediga nummer
(`db/migrations/031_add_interpretation_expected.sql` är den senaste).

**FU2 direkt efter FU1, och FU2 är den andra gaten.** Predikatet nämner
`voucher_source_references`, så tabellen måste finnas. D3 ändrar vad "saknar underlag" betyder:
rättelser försvinner ur listan, ur `GET /overview`, ur compliance och ur matchningens kandidater
(`match_candidates` använder samma predikat). Det är en siffra som syns i headern, och den ska
kunna landa och driftsättas ensam, med den sjunkande `missing_attachments` förklarad i
commit-meddelandet (§12 D3), som U1 gjorde. Allt som testar kopplingen mot "saknar underlag" ska
testas mot det lagade predikatet.

**FU3 före FU4.** Kontrollerna 1–8, transaktionen och uppspelningen är samma oavsett belägg, och
`exact_match` är det enklare belägget. Byggs `decision` först blir FU3 en gren i något som redan
är testat, inte två vägar samtidigt. FU3 är också där den enda ändringen i en befintlig service
görs: `link_existing_voucher` kör i dag alltid `_ensure_can_record_outcome`, och kopplingen
behöver sin egen källkontroll (D9, avvikelse 1 nedan).

**FU5, FU6 och FU7 efter FU4, parallellt.** Verktyget och routen är två tunna ytor på samma
service, och de ska båda ha hela regelverket när de öppnas — en route som bara kan `exact_match`
är en route som ändrar beteende i nästa commit. Stoppet behöver serviceklassen men inte ytorna.

**FU5 som egen commit.** Verktygslistan är det cachade prefixet (`SPEC-agentruntime.md` §6.6), och
fyra befintliga tester låser dess form. Tillägget sist ska vara det enda som ändras.

**FU8 kan byggas när som helst efter FU1.** Jämförelseinlägget ändrar bara tolkningsvägen och
skriver ett `receipt`-inlägg. Radbyggaren som FU8 skriver återanvänds av kvittot i FU9 (§9.3:
"samma som jämförelseinlägget, ur samma tolkning"), så FU9 kommer efter.

**FU9 efter FU7 och FU8.** Kvittot skrivs av `IntakeLinkService` efter commit, och FU7 är den
senaste uppgiften som rör `services/intake_link.py` före den. Kvittot kräver radbyggaren ur FU8.

**FU10 efter FU7 och FU2.** Hänvisningen skrivs i `DraftService.on_posting`, och FU7 rör samma
fil (`_check_traceability`). Att A-121 inte står i `Saknar underlag` är FU2:s predikat.

**FU11 när som helst efter FU1.** Passets fråga rör bara `IntakeRepository`. Den ska vara på plats
före de skriptade flödena i FU18.

**FU12 efter FU5, FU13 efter FU5 och FU7.** `las_verifikationer`s svar och verktygslistan bor i
samma fil. Instruktionen hänvisar till ett verktyg modellen måste kunna se, och till stoppet.

**FU14 före FU17 och FU20.** Både D8 och sidantalet rör `api/routes/threads.py`. Klientens
tomma meddelande kräver att servern tar emot det.

**FU15 efter FU6.** Samma fil, `api/routes/intake.py`.

**FU16 efter FU2 och FU14.** `referenced_by` joinas i `VOUCHER_SELECT_SQL` (samma fil som
predikatet) och läggs i `VoucherResponse` (samma fil som D8:s schemaändring).

**FU18 stänger backenden.** De skriptade flödena (39–42) prövar att instruktionens väg håller hela
vägen: fil, tolkning, beslut, svar, koppling, kvitto, förslag, postning, hänvisning.

**Klienten sist, men den kan börja tidigt.** Kontrakten står i specen (§7, §9, §10), så FU19 och
FU22 kan byggas mot fixturer medan backenden byggs. Risken är att fixturerna glider; därför
verifieras varje klientuppgift mot den riktiga backenden när dess backendberoende landat, och FU24
kör flödet i `/v4`.

## Parallellt vs sekventiellt

Implementationen fördelas på flera subagenter. Två uppgifter får köras samtidigt bara om deras
filer (under **Filer** i `todo.md`) är disjunkta. Tabellen nedan är ägarskapet; en uppgift som
behöver röra en fil utanför sin lista stannar och säger till i stället för att ta den.

- Sekventiellt: FU1 → FU3 → FU4 → FU7 → FU9 → FU18 → FU24.
- Efter FU1: `FU2 ‖ FU3 ‖ FU8 ‖ FU11 ‖ FU14`, och klientens `FU19 ‖ FU22`.
- Efter FU4: `FU5 ‖ FU6 ‖ FU7`.
- Efter FU5: `FU12`. Efter FU5 och FU7: `FU13`.
- Efter FU6: `FU15`. Efter FU7 och FU2: `FU10`. Efter FU7 och FU8: `FU9`.
- Efter FU2 och FU14: `FU16`. Efter FU14: `FU17`.
- Klienten: FU19 → FU20 → FU21 → FU23; FU22 parallellt med alla fyra.
- FU24 avslutar alltid.

### Filägarskap

Filer som mer än en uppgift rör, och i vilken ordning:

| Fil | Uppgifter, i ordning |
|---|---|
| `repositories/voucher_repo.py` | FU2 → FU16 |
| `services/intake_link.py` | FU3 → FU4 → FU7 → FU9 |
| `repositories/intake_link_repo.py` | FU1 → FU10 |
| `services/agent_tools.py` | FU5 → FU12 |
| `services/draft_service.py` | FU7 → FU10 |
| `api/routes/intake.py` | FU6 → FU15 |
| `api/routes/threads.py` | FU14 → FU17 |
| `api/schemas.py` | FU14 → FU16 |
| `domain/intake_link.py` | FU1 → FU3 |
| `docs/to_agent/03_bokforingsinstruktion.md` | FU13 |
| `frontend-v3/hooks/useTrad.ts` | FU20 → FU21 |
| `frontend-v3/lib/chattyta/api.ts` | FU19 |
| `frontend-v3/lib/skal/bocker.ts` | FU21 → FU23 |

**Testfilerna.** Specen §4 nämner en testfil. För att parallella subagenter inte ska krocka i
den, äger varje spår en egen fil, och alla importerar hjälparna (databas, verifikation, källa,
tolkning, tråd, besvarat beslut) ur `tests/test_flode_underlag.py`, som FU1 skriver — samma sätt
som U10 importerade `FakeLLMClient` ur `tests/test_agent_runtime.py`:

| Testfil | Uppgifter |
|---|---|
| `tests/test_flode_underlag.py` | FU1 (hjälparna), FU3, FU4 |
| `tests/test_flode_underlag_predikat.py` | FU2, FU16 |
| `tests/test_flode_underlag_verktyg.py` | FU5, FU12 |
| `tests/test_flode_underlag_http.py` | FU6, FU15 |
| `tests/test_flode_underlag_stopp.py` | FU7 |
| `tests/test_flode_underlag_trad.py` | FU8, FU9 |
| `tests/test_flode_underlag_hanvisning.py` | FU10 |
| `tests/test_flode_underlag_pass.py` | FU11, FU18 |
| `tests/test_flode_underlag_meddelande.py` | FU14, FU17 |

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| En koppling rullas inte tillbaka hel | Länk utan belägg, eller källa `processed` utan länk | En transaktion för länk, försök, status och belägg; testfall 16 får belägget att fallera och kräver att inget av de fyra står kvar |
| `link_existing_voucher` ändras så att postningen släpper igenom `failed` | Ett avstått underlag postas som ny verifikation | `_ensure_can_record_outcome` rörs inte (§3.3, D9); FU3 lägger till en väg förbi den som bara `IntakeLinkService` använder, och ett test kräver att `posta_verifikation` fortfarande vägrar en `failed` källa |
| Kopplingen skriver i `vouchers` | Append-only bryts i förbifarten | Testfall 18 jämför `vouchers` och `voucher_rows` före och efter, rad för rad |
| Kvittot skrivs i kopplingens transaktion | Ett fel i trådlagret rullar tillbaka en koppling | §9.3; testfall 30 får kvittot att fallera och kräver att kopplingen står |
| Hänvisningen skrivs efter commit | A-121 postad utan hänvisning, och står i `Saknar underlag` för alltid | Skrivs i `on_posting`, i postningens transaktion; FU10 får insättningen att fallera och kräver att postningen rullas tillbaka |
| D3 sänker `missing_attachments` vid driftsättning och läses som en regression | Någon "lagar" tillbaka det | Commit-meddelandet och `tasks/README.md` säger att det är rätt siffra (§12 D3) |
| Predikatet får hänvisningen men `referenced_by` blir en fråga per rad | Långsam lista | Joinas i `VOUCHER_SELECT_SQL` som `corrected_by`; testfall 49e räknar SQL-anropen |
| Verktygslistan ändrar ordning | Det cachade prefixet slutar träffa | FU5 lägger till sist; testfall 36 jämför de tolv första byte för byte (sha256 tagen på commiten före) |
| `las_verifikationer`s argument eller beskrivning ändras | Prefixet slutar träffa | FU12 ändrar bara `_voucher_dict`; testfall 37 jämför schemat och beskrivningen byte för byte |
| Stoppet reserverar en nyckel | Ett stoppat anrop blockerar ett senare med samma nyckel | Kontrollen körs före `idempotency.begin` i båda anroparna, eller släpps av deras `release`; testfall 20 kräver att nyckeln inte finns efteråt (avvikelse 2) |
| Fritextsvar på ett kopplingsbeslut läses fel av agenten | Ett "nej" i fritext kopplas | Accepterat pris (§13.4); testfall 6 visar beteendet, visuell kontroll i FU24 |
| Passet och tråden tar samma fil | Källan avstås mitt i ett samtal | D4 i FU11; testfall 38 |
| D4:s filter når fler läsare än passet | `las_underlag`, `GET /agent/intake/pending` och `queue_depth` tappar trådens filer | Avsett (tråden äger dem), men det ska stå i commit-meddelandet och prövas; intagssidan (`/intake/workspace`) läser `list_by_status` och påverkas inte (avvikelse 3) |
| `view.changed` på `bocker.verifikationer` skickas till fel ström | Vyn tappar inte raden | Brokern är per `thread_id`; FU9 slår upp vyns tråd för det aktuella räkenskapsåret och publicerar bara om den finns (avvikelse 5) |
| Klientens fixturer glider från serverns form | Grönt i vitest, trasigt i `/v4` | Fixturerna byggs ur specens exempel och jämförs med ett riktigt svar i FU24 |
| Filen öppnas med en vanlig länk | `401`: `GET /intake/{id}/file` kräver bearer | Hämtas som blob genom `apiClient`, som `api.getIntakeFile` gör i dag (avvikelse 6) |

## Avvikelser mellan specen och koden

Hittade vid planeringen 2026-09-28. Specen är inte ändrad; uppgifterna nedan bär lösningen, och
den uppgift som löser en avvikelse uppdaterar specen i samma commit, som tidigare moduler gjort.

1. **`link_existing_voucher` kör alltid källkontrollen.** §6.1 säger att kopplingen skriver
   "länken (`IntakeService.link_existing_voucher` utan källkontrollen i §3.3)". Metoden
   (`services/intake.py:254`) anropar `_ensure_can_record_outcome` på rad 266 utan väg förbi, och
   kontrollerar också `voucher_not_found`/`voucher_not_posted` själv. FU3 lägger till en
   nyckelordsparameter (eller bryter ut `persist_link` till en metod) som bara
   `IntakeLinkService` använder; postningens två anrop (`services/voucher_posting.py:103`,
   `services/draft_service.py:789`) är oförändrade.
2. **Idempotensreservationen ligger inte i `voucher_posting`.** §8: "Den körs **före**
   idempotensreservationen i `voucher_posting`". `post_agent_voucher`
   (`services/voucher_posting.py:59`) reserverar ingenting; det gör anroparna, med
   `idempotency.begin` i `api/routes/agent.py:86` och i `services/agent_tools.py` (`_post_voucher`,
   runt rad 755), och båda släpper nyckeln (`release`) när anropet kastar. FU7 lägger kontrollen i
   `post_agent_voucher` bredvid `ensure_source_ready_for_voucher_link` (rad 73–74) och låter
   `release` ta nyckeln, eller kör den före `begin` i båda anroparna; testfall 20:s "ingen nyckel
   reserverad" prövas som att nyckeln inte finns i `idempotency_keys` efteråt. `POST
   /agent/vouchers` mappar `IntakeError` genom `_intake_http_error` (`api/routes/agent.py:293`),
   där `source_matches_posted_voucher` måste läggas till 409-mängden (eller felet får en egen typ).
3. **`list_pending`/`count_pending` har fler läsare än passet.** §11.3 nämner passet och
   intagssidan. Förutom `services/agent_runtime.py:396` läser `IntakeService.get_pending_queue`
   (`services/intake.py:171`) dem för `las_underlag` (`services/agent_tools.py:674`) och `GET
   /agent/intake/pending` (`api/routes/agent.py:170`), och `queue_depth` i agentstatusen läser
   `count_pending` direkt (`api/routes/agent.py:440`). D4:s filter gäller dem alla. Intagssidan
   (`GET /intake/workspace`) läser `list_by_status`/`count_by_status` och påverkas inte, som §11.3
   säger.
4. **`user_file` har redan ett sidfält, `pages`.** §10.4 säger att sidantalet "ingår inte i
   `user_file`-kroppen i dag och läggs till för pdf (`page_count` …)". Kroppen har `pages`
   (`services/thread_service.py`, `record_user_file`), klienten tolkar det
   (`frontend-v3/lib/chattyta/parse.ts:64`) och `FilInlagg` visar redan `218 kB · 1 sida`
   (`components/chattyta/FilInlagg.tsx:26`). Det som saknas är att routen fyller i det:
   `_attachment_posts` (`api/routes/threads.py:230`) skickar aldrig `pages`. FU17 fyller i `pages`
   och inför inget `page_count`; klienten behöver ingen ändring.
5. **`view.changed` publiceras per tråd, inte per vy.** §9.3 säger att händelsen skickas "på
   trådens `view_key`" och "på `bocker.verifikationer`", även utan tråd. Brokern
   (`services/thread_stream.py`, `ThreadBroker.publish(thread_id, …)`) har bara trådar. FU9
   publicerar på den kopplande trådens id och, när den inte är `bocker.verifikationer`s, på den
   vyns tråd för det aktuella räkenskapsåret (`ThreadRepository.find(view_key, fiscal_year_id)`),
   om den finns. Finns ingen sådan tråd finns ingen öppen ström att nå, och ingenting skickas;
   vyn läser rätt nästa gång den hämtas.
6. **`GET /vouchers/{id}` returnerar inte de kopplade källorna, och `/v4` har ingen
   raddetalj.** §10.4 hänvisar till `api/routes/vouchers.py:335`, men den raden ligger i `GET
   /vouchers/{id}/source-context` (routen på rad 316); `GET /vouchers/{id}` (rad 432) svarar med
   `VoucherResponse` utan källor. `/v4`s `VyRad` har ingen detaljvy (`lib/skal/vydata.ts`,
   `VyRadData` har ingen länk eller expansion). FU16 utökar `source-context` med hänvisningens
   källa (`via_voucher_id`), och FU23 bygger det minsta som bär en länk: en länk på raden, inte en
   detaljpanel — växer det bortom det är det ett "fråga först". Filen kräver bearer, så länken
   hämtar en blob genom `apiClient` (som `api.getIntakeFile`, `frontend-v3/lib/api.ts:1016`).
7. **`view.changed` invaliderar redan `vouchers` och `overview`.** §10.4 och testfall 51 kräver
   att `kind: "source_linked"` invaliderar dem. `useTrad` (`frontend-v3/hooks/useTrad.ts:87`)
   invaliderar redan fyra rötter för varje `view.changed`, oavsett `kind`. Testfall 51 blir en
   vakt, inte en ändring; det nya i FU21 är att läsa `kind` för `Nyss kopplad`.
8. **`komponenter.md` finns inte i repot.** §10.1 hänvisar till den för `drop`-variantens mått och
   copy. Den ligger i designpaketet (`BokAI App Redesign.zip`, `ANALYS.md` rad 4), utanför repot.
   FU20 behöver den; en subagent utan tillgång till paketet stannar och frågar i stället för att
   gissa måtten.
9. **Mindre radhänvisningar.** `services/agent_runtime.py:396` är `get_pending_queue`, inte
   `list_pending` direkt (§3.4). `api/routes/threads.py:230` är `_attachment_posts`; själva routen
   är `post_message` på rad 159 (§1). `services/intake.py:29` är `DuplicateIntakeSourceError`,
   som redan har `existing_id` som attribut — FU15 behöver bara lägga det i svaret (§7).
   Övriga hänvisningar i §1, §3, §5, §10 och §11 stämmer mot koden på `5ee0f43`.

## Vad som inte byggs här

Ersättning av ett felkopplat underlag (D10, `underlag-ersatt`). Uppdelning av ett underlag med
flera köp. Valutaomräkning. Påminnelse om gamla kompletteringar (§13.2). Ändringar i `POST
/vouchers/{id}/attachments`. Ändringar i `UNIQUE(intake_source_id)`. Koppling från `processed`
eller `skipped`. En detaljpanel för verifikationer i `/v4` utöver kvittolänken (avvikelse 6).
