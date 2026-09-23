# Uppgifter: modul `chattyta`

Spec: `docs/redesign/SPEC-chattyta.md` · Plan: `tasks/chattyta/plan.md`
Testerna skrivs **före** implementationen (§13). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §13. Alla sökvägar är under `frontend-v3/`.
Ingen uppgift rör Python.

---

- [x] **C1 — Kontraktet: typer, `parseInlagg`, fixturer (gate)**
  - Gjort 2026-09-23: 31 tester. Driftskyddet läser `SPEC-chattyta.md` §4.3:s `jsonc`-block och
    jämför med fixturen; bevisat genom att ändra ett öre i fixturen (testet föll, ändringen
    återställd). Avvikelse: `parseInlagg` vägrar fler brott än §4.1:s fyra rader — saknade fält,
    debet-och-kredit på samma rad, fel antal `labels`, `decision_id` som saknas. Tabellen i §4.1
    utökad i samma ändring. Fixturerna fick två hjälpare (`kropp`, `kroppUtan`) för testernas
    kontraktsbrott.
  - Acceptans: en diskriminerad union över de åtta `type`-värdena med kroppen typad per typ,
    exakt §2:s tabell och §4.3:s `draft`/`receipt`. `parseInlagg(raw)` ger en typad variant,
    `okant_kontrakt` för de fyra brotten i §4.1, eller `null` för okänd typ (en konsolrad per typ,
    inte per inlägg). En fixtur per typ; `draft` och `receipt` är ordagrant §4.3:s JSON.
  - Verifiera: testfall 1, 2, 3, 4.
  - Filer: `lib/chattyta/typer.ts`, `lib/chattyta/parse.ts`, `lib/chattyta/__fixtures__/inlagg.ts`,
    `lib/chattyta/__tests__/parse.test.ts`
  - Obs: **landas före alla renderare.** Kontraktet är ett ställe, inte åtta `body.x ?? ""`.

- [x] **C2 — SSE-läsaren**
  - Gjort 2026-09-23: 22 tester (testfall 5, 6, 9 plus avbrott och headers), sedda röda först.
    Basadressen ur `apiClient.defaults.baseURL`, token ur `localStorage` som interceptorn gör —
    `fetch` går inte genom axios. Avvikelser: det finns ingen 401-utloggning i `lib/api.ts` att
    återanvända (bara en request-interceptor); `oppnaStrom` tar därför `onObehorig`, och C3:s
    `useTrad` skickar `useAuth().logout`. Bara `401` avslutar; `404`, `5xx` och nätverksfel
    återansluts med backoff — att inte öppna strömmen mot en tråd som inte finns är C3:s jobb.
    En ram med trasig JSON hoppas över med en varning, strömmen lever vidare. Node 26:s globala
    `localStorage` skuggar jsdom:s i vitest; testerna stubbar den med `vi.stubGlobal` (gäller även
    C3 och C12). `prettier --check` klagar på både C1 och C2 — prettier är inte en gate i repot.
  - Acceptans: `lasHandelser(stream: ReadableStream<Uint8Array>)` ger `{event, data}` i ordning;
    ramar delade över chunk-gränser, flerradig `data:`, kommentarsramar ignorerade.
    `oppnaStrom({viewKey, since, signal, onHandelse})` via `fetch` med bearer-headern ur samma
    källa som `lib/api.ts`; återansluter med `since` = högsta sedda `seq`, backoff 1→2→4… tak 30 s;
    `401` avslutar utan återanslutning.
  - Verifiera: testfall 5, 6, 9.
  - Filer: `lib/chattyta/strom.ts`, `lib/chattyta/__tests__/strom.test.ts`
  - Obs: inte `EventSource` (§6.1). Inga nya beroenden.

- [x] **C3 — Trådens tillstånd: reducer, `useTrad`, api**
  - Gjort 2026-09-23: 40 tester (21 reducer, 19 hook), sedda röda först och mutationsprövade
    (tre avsiktliga fel gav sex röda). Beslut: ett misslyckat `POST` **tar bort** det optimistiska
    inlägget — ett kvarlämnat skulle påstå att servern lagrat något den inte lagrat; `skicka`
    ger `Promise<boolean>`, `fel` sätts, och C5 låter texten stå kvar i fältet. Optimistiska
    inlägg känns igen på id-prefixet `lokal-`, `seq: -1`. Frågenycklar: `OVERVIEW_NYCKEL =
    ["overview"]` (kopia av `hooks/useSkal.ts`, ett test håller dem lika), `BESLUT_NYCKEL =
    ["decisions"]` som rot — C6/C8 lägger sina nycklar under den. Utloggning: `useAuth().logout`
    som `onObehorig`. Avvikelser: `message.completed` av typen `decision`/`options`/`user_text`
    invaliderar också beslutsfrågan (§7) här, eftersom C6 inte rör `useTrad.ts`. Ett
    `message.delta` utan föregående `created` startar ändå platshållaren: turen startar inuti
    `POST`, klienten prenumererar efteråt, så `created` kan missas på första meddelandet i en tom
    tråd. Det färdiga inlägget går inte förlorat — det spelas upp via `since` — men de första
    deltana kan göra det. Serverns lopp lämnas orört (antagande 1).
  - Acceptans: `tradReducer` enligt §6.3:s tabell, sorterad på `seq`, optimistiska sist,
    idempotent på `id`. `useTrad(viewKey)`: `GET /threads/{vk}`; ingen ström när `thread_id` är
    `null`; ström från `cursor` annars; `skicka(text)` gör optimistiskt `user_text` → `POST
    …/messages` → öppnar strömmen om den inte var öppen. Vybyte stänger strömmen.
    `view.changed` invaliderar `overview` och beslutsfrågan.
  - Verifiera: testfall 7, 8, 10, 11, 12.
  - Filer: `lib/chattyta/trad.ts`, `lib/chattyta/api.ts`, `hooks/useTrad.ts`,
    `lib/chattyta/__tests__/trad.test.ts`
  - Obs: det lagrade inlägget vinner över den ihopsamlade deltatexten vid `completed` (testfall 10) —
    servern lagrar det människan såg, men det lagrade är sanningen.

- [x] **C4 — Textinläggen**
  - Gjort 2026-09-23: 43 tester, skrivna före komponenterna. Avvikelser: `SparChip` bor i
    `TradInlagg.tsx` (exporterad) i stället för egen fil — med `lib/chattyta/etiketter.ts` hade
    uppgiften annars rört sex filer, och chippet har ingen egen inläggstyp. `TradInlagg` har en
    `radLista`-slot som C5 fyller med C9:s `RadLista`. **Indikatorn talar i presens**
    (`Postar verifikation…`), inte med chippens perfekt (`verifikation postad`): `activity` sänds
    när verktyget *anropas*, och perfekt vore ett påstående om huvudboken som inte har hänt än.
    Två tabeller i `etiketter.ts`, testade att täcka samma verktyg; perfekttabellen är fastlåst
    ordagrant mot serverns `_TRACE_LABELS`. `FilInlagg`s valfria textbubbla ritas inte —
    `user_file` har inget textfält.
  - Acceptans: `TradInlagg` (agent/du), `SparChip`, `FilInlagg`, `SkriverIndikator`,
    `RadLista` med `komponenter.md`s mått. Metarad `agenten · HH:MM` ur `created_at`.
    `SkriverIndikator` säger aldrig tomt: `activity` via svenska etiketter, annars `Läser…`.
  - Verifiera: testfall 11, 13. Mått mot `komponenter.md` i testet där de är klasser.
  - Filer: `components/chattyta/TradInlagg.tsx`, `components/chattyta/SparChip.tsx`,
    `components/chattyta/FilInlagg.tsx`, `components/chattyta/SkriverIndikator.tsx`,
    `components/chattyta/__tests__/text.test.tsx`
  - Obs: `RadLista` läggs i `JamforelseRader.tsx` (C9) som en enkolumnsvariant — samma radkomponent,
    en fil. Byggs här om C9 inte landat, flyttas då i C9.

- [x] **C5 — Renderaren byts i skalet; `ChattFalt` skickar**
  - Gjort 2026-09-23: 24 nya tester i `renderare.test.tsx`, skalets tre trådtester uppdaterade
    (mockar `useTrad`), 279 gröna totalt. Lint, `tsc` och `NEXT_PUBLIC_SKAL=1 npm run build`
    gröna. `decision`, `options`, `error` renderas som `OkantKontrakt`-raden tills C6/C7/C13 byter
    sina grenar. Avvikelser: **tio filer**, inte fem — `ChattFalt.tsx` och fyra testfiler
    tillkom. **Bara den aktiva vyn läser sin tråd** (`aktiv`-prop, `Skal` skickar
    `i === vyIndex`): svepraden renderar en sidas alla vyer, och utan det öppnade varje sida tre
    `GET` och tre strömmar (§6.2 punkt 5). Priset: grannvyns tråd är tom under ett svep.
    `ChattKolumn` tappade `variant="mobil"`; `ChattList` anropar `useTrad` en gång för både
    märke och tråd via den exporterade `TradYta` — två anrop hade gett två strömmar.
    `ChattFalt`: ett andra tryck under pågående sändning ignoreras, och fältet töms bara om
    texten fortfarande är den som skickades. **Visuell kontroll mot backend gjordes inte** —
    ingen backend svarade på `127.0.0.1:8000`; den görs i C14.
  - Acceptans: `TradRenderare` väljer komponent per `type`; typer utan renderare än blir
    `okant_kontrakt`. `ChattKolumn` och `ChattList` tar `useTrad` i stället för `inlagg`-propen.
    `ChattFalt.onSkicka` kopplas till `skicka`. `mockTrad` och `TradInlaggData` borta ur
    `lib/skal/mock.ts`. Skalets tester uppdaterade, inte borttagna.
  - Verifiera: testfall 12, 19, 32 (trådens halva). Visuellt i `next dev` mot riktig backend:
    fråga i en vy, svaret strömmar in.
  - Filer: `components/chattyta/TradRenderare.tsx`, `components/skal/ChattKolumn.tsx`,
    `components/skal/ChattList.tsx`, `components/skal/Skal.tsx`, `lib/skal/mock.ts`
  - Obs: skalets kommentar om att `chattyta` byter renderaren tas bort när det är gjort. Rör
    `grans.test.tsx` bara om den pekar på den borttagna mocken.

- [x] **C6 — `BeslutKort`, `GodkannKort` och beslutsstatus**
  - Gjort 2026-09-23: 26 tester (testfall 17, 18, 20, 22), 323 gröna totalt. `useBeslut`
    anropas per kort men TanStack slår ihop dem till **ett** `GET` per vy; en tråd utan
    beslutsinlägg frågar inte alls. **Avvikelse från spec §5, kräver serverändring:**
    `DecisionResponse` saknar `answered_at`, `answer_option_id` och `answer_text` (bara
    `409`-kroppen bär dem), så besvarat läge säger bara `Besvarat` — utan tid och svar.
    Människans svar syns ändå i tråden som hennes `user_text`. Tas upp som öppen fråga i C14.
    Okänd status (laddar, fel, id utanför de 200): öppet läge med neutral rubrik
    `Behöver ditt beslut`, eftersom `kind` bara finns i listan, inte i inlägget. Ersatt: grå,
    inte gul — gult betyder "väntar på dig". Konsekvensen i mono 12 `text-bok-text-dampad`, som
    förslagskortets. Filer: **åtta** — `viewKey` fick trädas Skal → ChattKolumn/ChattList →
    TradYta → TradRenderare, och två befintliga tester asserterade det gamla `decision`-beteendet.
    `ChattKolumn.test` använder nu `FIXTUR_OPTIONS` som orenderad typ; C7 byter till
    `FIXTUR_ERROR`.
  - Acceptans: `useBeslut(viewKey)` = ett `GET /decisions?view_key&status=all&limit=200` per vy,
    uppslag på `decision_id`, invalideras enligt §7. `BeslutKort` i tre lägen (öppen, besvarad,
    ersatt); knappar bara i öppen. `kind="approval"` → `GodkannKort`-rubriken. Källraden färgas
    med `aldersTon` (C8) när den finns, annars väntar-tonen.
  - Verifiera: testfall 17, 18, 20.
  - Filer: `components/chattyta/BeslutKort.tsx`, `hooks/useBeslut.ts`, `lib/chattyta/api.ts`,
    `components/chattyta/__tests__/beslut.test.tsx`
  - Obs: `BeslutKort` har ingen egen svarsknapp för alternativen — de bor i `AlternativLista`, som
    är ett eget inlägg. Primär/sekundär i `BeslutKort` finns bara när kroppen säger vad de gör;
    i dag gör den inte det, så öppet läge är text + källrad och vägen är fritexten eller listan.

- [x] **C7 — `AlternativLista` och svaret**
  - Gjort 2026-09-23: 22 tester (testfall 14, 15, 16 m.fl.), sedda röda först och
    mutationsprövade; 345 gröna totalt. Sex filer, som planerat. Låst = `aria-disabled` plus
    klickvakt, inte `disabled` — en avstängd knapp kan inte ta fokus, och §11 flyttar fokus till
    den valda raden i samma ögonblick. Efter omladdning markeras **ingen** rad (samma lucka som
    C6: `GET /decisions` saknar `answer_option_id`); inom sessionen markeras det klickade
    alternativet, eller `answer_option_id` ur `409`-kroppen. `Besvarat · HH:MM` bara när tiden
    kom ur en `409`. Nätverksfel: `Svaret kom inte fram. Ingenting är besvarat.`, mono 12, raderna
    låses upp, inget automatiskt omförsök. `decision_not_answerable` kastas vidare — kan inte
    uppstå från ett inlägg i tråden. **Att notera:** väg-ut-alternativet (`is_exit`) skickar sitt
    `option_id` som vilket annat som helst; vad agenten gör efter `Annat konto` är agentens.
  - Acceptans: `AlternativRad` med tom ring, `RekMarke` vid `recommended`, fotnot med
    `aria-describedby`. Tryck → `POST /decisions/{id}/answer {option_id}`; övriga rader låsta i
    flykt; `202` och `409 decision_already_answered` ger båda besvarat läge (svaret ur kroppen vid
    `409`). Fokus till den besvarade raden. Ingen radiogrupp.
  - Verifiera: testfall **14**, 15, 16.
  - Filer: `components/chattyta/AlternativLista.tsx`, `lib/chattyta/api.ts`,
    `components/chattyta/TradRenderare.tsx`, `components/chattyta/__tests__/alternativ.test.tsx`
  - Obs: testfall 14 kontrollerar tre saker — inget valt, inget fokuserat, ingen annan stil än
    `RekMarke`. En rekommendation som får en mörkare kant är också ett förval.

- [x] **C8 — Märket och `age_days`-tröskeln**
  - Gjort 2026-09-23: 18 nya tester, sedda röda först; 297 gröna totalt. Frågenyckel
    `["decisions", viewKey, "open"]` under `BESLUT_NYCKEL`. `hamtaBeslut` och de fulla
    beslutstyperna (`BeslutSvar` m.fl., exakt `api/schemas.py`) ligger i `lib/chattyta/api.ts`
    för C6. Avvikelser: sex källfiler — hooken `hooks/useVantandeBeslut.ts` och `api.ts` utöver
    listan. Märket hämtas bara för aktiv vy **och bara på mobil**; desktop har inget märke.
    Laddning eller fel ger `0`, så märket faller tillbaka på `N inlägg` i stället för att
    gissa. `staleTime` 60 s som `useOverview`. `ChattList.tsx` orörd. Testfilen för åldern är
    `.tsx`, eftersom den renderar `VyRad`.
  - Acceptans: `aldersTon(ageDays)` med `ROD_FRAN_DAGAR = 7` på ett ställe. Mobilens
    `ChattList`-märke = `total` ur `GET /decisions?view_key&status=open&limit=1`.
    `mockVantandeBeslut` borta. `VyRad`s `saknar`/`vantar` tar en valfri `ageDays` och färgas
    med regeln.
  - Verifiera: testfall 21, 22, 32 (beslutshalvan).
  - Filer: `lib/chattyta/alder.ts`, `components/skal/VyRad.tsx`, `components/skal/Skal.tsx`,
    `lib/skal/mock.ts`, `lib/chattyta/__tests__/alder.test.ts`
  - Obs: stänger `SPEC-beslut.md` öppen fråga 1 och den ärvda frågan i `tasks/skal/todo.md` —
    notera det i båda filerna när C14 stänger modulen, inte här.

- [x] **C9 — `JamforelseRader` (`receipt`) och `RadLista`**
  - Gjort 2026-09-23: 6 tester (4 för testfall 23, 2 för `RadLista`), skrivna före komponenten.
    En radkomponent för båda, som `komponenter.md` säger. Två decimaler, inte hela kronor — en
    avrundad jämförelse kan visa två lika tal för en skillnad i öre. Avvikelser: `TradRenderare`
    rördes inte (C5 registrerar: `JamforelseRader kropp={body}`, `RadLista rader={body.rows}`).
    Designskissen ritar `var`/`blir` som två rader med ett tal var; specen §4.3 följs i stället —
    en rad med `left_ore`/`right_ore`, etiketterna som kolumnrubriker.
  - Acceptans: båda talen i varje rad, etiketterna ur `labels`, belopp via `formatBelopp`,
    mono tabulärt. `RadLista` = samma radkomponent med en kolumn tal.
  - Verifiera: testfall 23. Fixtur ur C1.
  - Filer: `components/chattyta/JamforelseRader.tsx`, `components/chattyta/TradRenderare.tsx`,
    `components/chattyta/__tests__/jamforelse.test.tsx`

- [x] **C10 — `VerifikationsForslag` utan knapp**
  - Gjort 2026-09-23: 9 tester (testfall 24), skrivna före komponenten och sedda röda.
    Avvikelser: `TradRenderare.tsx` rördes inte — C5 skapar den och registrerar kortet. Kortet
    tar hela `DraftInlagg` (för `data-inlagg-id`), inte bara kroppen. Fotens `#78716c` har ingen
    token och står som `text-[#78716c]`. Rubrik-, kolumn- och fotpadding saknas i
    `komponenter.md`; valda kring radens 18 px. `lib/skal/__tests__/grans.test.tsx` undantar nu
    `components/chattyta/` — vakten skyddar de 24 gamla sidorna, och `chattyta` beror på `skal`
    enligt spec §1.
  - Acceptans: rubrikrad, kolumnrubriker Konto / Debet / Kredit (högra två 92 px högerställda),
    `KonteringsRad`, fot, konsekvensnotis i mono 12 `#52525b`. `kind` ≠ `voucher` →
    `okant_kontrakt` (redan i C1). Knappraden finns som slot, tom.
  - Verifiera: testfall 24.
  - Filer: `components/chattyta/VerifikationsForslag.tsx`, `components/chattyta/TradRenderare.tsx`,
    `components/chattyta/__tests__/forslag.test.tsx`
  - Obs: konsekvensnotisen är inte metatext. `text-bok-meta` på den är ett fel, inte en stilfråga.

- [x] **C11 — Idempotensnyckeln (gate)**
  - Gjort 2026-09-23: 12 tester, sedda röda först. `BOK_KLIENT_NS =
    67d43419-c305-4b32-9247-305e346b0398` (skild från serverns `BOK_NAMESPACE` i
    `services/agent_tools.py`; får aldrig bytas — gamla utkast skulle få nya nycklar). Fyra
    vektorer räknade med Pythons `uuid.uuid5`, varav en med `å`, plus DNS-vektorn
    `www.example.com`; kommandona står i testet. `crypto.subtle` finns i jsdom, ingen fallback.
    Avvikelse: `uuidV5` exporteras också, för DNS-vektorn. `SPEC-idempotens.md` antagande 3 säger
    att klienten slumpar v4 — servern kräver bara en UUID (`api/deps.py:78`), så v5 fungerar, men
    antagandet är inaktuellt.
  - Acceptans: `nyckelForUtkast(draftId)` = UUIDv5 under en fast `BOK_KLIENT_NS`, via
    `crypto.subtle` (SHA-1). Deterministisk, giltig v5 (version- och variantbitar), skild från
    serverns namnrymd.
  - Verifiera: testfall 26, plus en känd testvektor räknad med Pythons `uuid.uuid5` så att klient
    och server kan jämföras om de någon gång behöver det.
  - Filer: `lib/chattyta/idempotens.ts`, `lib/chattyta/__tests__/idempotens.test.ts`
  - Obs: **landas före C12.** Idempotens före något skrivflöde kopplas till en knapp
    (`ANALYS.md` §7).

- [x] **C12 — Postningsknappen och dess sju utfall**
  - Gjort 2026-09-23: 27 tester (testfall 25, 27, 28, 34, 35, 36 plus nätverk), mutationsprövade
    (slumpad nyckel gav sex röda, ignorerad `retry_after_ms` gav testfall 34 röd); 372 gröna.
    **Fynd: `POST /vouchers/{id}/post` läser inte `Idempotency-Key`** — bara `/correct` har
    beroendet. `request_in_flight`, `idempotency_key_reuse` och `Idempotent-Replay` kan alltså
    inte uppstå på den vägen i dag; klienten hanterar dem enligt `SPEC-idempotens.md` §6 och
    fixturer. Kontrollerat av koordinatorn: postning skriver **ingen ny rad** — den byter
    `status` på utkastets egen rad (`VoucherRepository.post`), så två tryck kan inte ge två
    verifikationer. Andra trycket får `409 already_posted` (klart läge); i ett exakt samtidigt
    lopp avvisar triggern på postade verifikationer det andra `UPDATE`:t, klienten visar
    nätverksfel, och `Försök igen` landar i `already_posted`. Kvar i ett sådant lopp: möjligen
    en dubbel `POSTED`-rad i `audit_log`. Nyckeln är ofarlig och framtidssäker (spec §15.1);
    att koppla `get_idempotency_key` till `/post` hör till `flode-verifikationer`.
    Avvikelser: **nio filer** — `Ändra` måste nå fältet i kortets egen kolumn, och alla
    kolumners fält har samma `id="skal-chattfalt"`; en fokuskontext i `ChattKolumn` och
    `ChattList` plus `forwardRef` på `ChattFalt`. (Samma id ger en befintlig a11y-bugg:
    `<label for>` i andra kolumnen pekar på första kolumnens fält. Inte rättad här.) Perioden
    nämns inte vid namn — felet bär bara `period_id`, och att läsa månaden ur `meta` vore att
    tolka serverns text; `locked_at` skärs som sträng, inte tolkad med gissad tidszon.
    Nätverksfel säger **inte** `Ingenting är bokfört` — efter ett förlorat svar vet klienten
    inte det. Okända fel (t.ex. `400 voucher_date_outside_period`) visas som
    `Servern nekade postningen · {kod}`, utan omförsök. `Ändra` skriver aldrig i fältet.
  - Acceptans: `Posta` → `postaUtkast(draftId)` → `POST /vouchers/{draftId}/post` med nyckeln ur
    C11. Låst i flykt. Utfallen i §8:s tabell: `200`, replay, `409 already_posted`,
    `409 request_in_flight` (vänta, samma nyckel), `422 idempotency_key_reuse`,
    `409 period_locked` (vem/när, `okänd` vid `null`), nätverk/`5xx` (`Försök igen`). `Ändra`
    lägger fokus i `ChattFalt`, tomt, inget anrop.
  - Verifiera: testfall **25**, 27, 28, 34, 35, 36.
  - Filer: `components/chattyta/VerifikationsForslag.tsx`, `lib/chattyta/api.ts`,
    `hooks/usePostaUtkast.ts`, `components/skal/ChattFalt.tsx`,
    `components/chattyta/__tests__/posta.test.tsx`
  - Obs: testfall 25 trycker två gånger **utan** att låsningen hinner verka och kräver samma
    nyckel i båda anropen. `ChattFalt` får en `ref` för fokus och inget annat.

- [x] **C13 — `FelKort`**
  - Gjort 2026-09-23: 16 tester (testfall 29, 30 m.fl.), sedda röda först och mutationsprövade;
    388 gröna. Rubriken är `Något gick fel`, inte designens `Postningen misslyckades` — nästan
    varje `error` servern skriver i dag är en tur som tog slut (`agent_turn_limit`,
    `llm_connection_error`), och rubriken skulle påstå något om huvudboken som servern inte sagt.
    Orsakskoden i metaraden bara när den ser ut som en kod. `Visa vad som hände` finns alltid;
    utan spår säger den `Inga spår sparades för den här turen.` `Försök igen` är en egen
    komponent som bara monteras med `retry_draft_id`, så dagens kort varken anropar hooken
    eller kräver en `QueryClientProvider`. Efter C13 ritar ingen känd typ längre
    `OkantKontrakt` — bara verkliga kontraktsbrott. Koordinatorn flyttade utfallstexterna
    (`felText`, `lastTid`) till `hooks/usePostaUtkast.ts`: agenten hade kopierat dem från
    `VerifikationsForslag.tsx`, och nätverksfelets mening får inte kunna glida isär i två kopior.
  - Acceptans: rubrik, orsak **och** konsekvens ur kroppen ordagrant. `Försök igen` bara när
    `retry_draft_id` finns, och då via `usePostaUtkast` med samma nyckel. `Visa vad som hände`
    fäller ut `traces[]` på plats.
  - Verifiera: testfall 29, 30.
  - Filer: `components/chattyta/FelKort.tsx`, `components/chattyta/TradRenderare.tsx`,
    `components/chattyta/__tests__/fel.test.tsx`
  - Obs: i dag är `retry_draft_id` alltid `null` — kortet har alltså ingen primärknapp i drift.
    Det är rätt, inte ofullständigt (§9).

- [ ] **C14 — Tillgänglighet, regression, lint, visuell kontroll; modulen stängd**
  - Acceptans: dold live-region annonserar indikatorbyte och färdigt inlägg, inte varje delta.
    Träffytor ≥ 44/46. Alla 36 testfall namngivna i minst ett test. `npm test`, `npm run lint`,
    `npx tsc --noEmit`, `NEXT_PUBLIC_SKAL=1 npm run build` gröna. `pytest tests/ -q` grön och
    `git diff main -- '*.py'` tom. Visuellt i `next dev` mot riktig backend: fråga + strömmande
    svar, ett beslut via `be_om_beslut` besvarat med knapp och ett med text, och `Posta` två
    gånger mot ett handskapat utkast i en dev-DB.
  - Verifiera: testfall 31, 33; framgångskriterierna i §14 ett och ett.
  - Filer: `components/chattyta/TradRenderare.tsx`, `tasks/chattyta/todo.md`, `tasks/README.md`,
    `docs/redesign/SPEC-chattyta.md`, `docs/redesign/SPEC-beslut.md`
  - Obs: stäng `SPEC-beslut.md` öppen fråga 1 här, och skriv avvikelserna sist i den här filen.
