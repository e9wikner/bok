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

- [ ] **C2 — SSE-läsaren**
  - Acceptans: `lasHandelser(stream: ReadableStream<Uint8Array>)` ger `{event, data}` i ordning;
    ramar delade över chunk-gränser, flerradig `data:`, kommentarsramar ignorerade.
    `oppnaStrom({viewKey, since, signal, onHandelse})` via `fetch` med bearer-headern ur samma
    källa som `lib/api.ts`; återansluter med `since` = högsta sedda `seq`, backoff 1→2→4… tak 30 s;
    `401` avslutar utan återanslutning.
  - Verifiera: testfall 5, 6, 9.
  - Filer: `lib/chattyta/strom.ts`, `lib/chattyta/__tests__/strom.test.ts`
  - Obs: inte `EventSource` (§6.1). Inga nya beroenden.

- [ ] **C3 — Trådens tillstånd: reducer, `useTrad`, api**
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

- [ ] **C4 — Textinläggen**
  - Acceptans: `TradInlagg` (agent/du), `SparChip`, `FilInlagg`, `SkriverIndikator`,
    `RadLista` med `komponenter.md`s mått. Metarad `agenten · HH:MM` ur `created_at`.
    `SkriverIndikator` säger aldrig tomt: `activity` via svenska etiketter, annars `Läser…`.
  - Verifiera: testfall 11, 13. Mått mot `komponenter.md` i testet där de är klasser.
  - Filer: `components/chattyta/TradInlagg.tsx`, `components/chattyta/SparChip.tsx`,
    `components/chattyta/FilInlagg.tsx`, `components/chattyta/SkriverIndikator.tsx`,
    `components/chattyta/__tests__/text.test.tsx`
  - Obs: `RadLista` läggs i `JamforelseRader.tsx` (C9) som en enkolumnsvariant — samma radkomponent,
    en fil. Byggs här om C9 inte landat, flyttas då i C9.

- [ ] **C5 — Renderaren byts i skalet; `ChattFalt` skickar**
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

- [ ] **C6 — `BeslutKort`, `GodkannKort` och beslutsstatus**
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

- [ ] **C7 — `AlternativLista` och svaret**
  - Acceptans: `AlternativRad` med tom ring, `RekMarke` vid `recommended`, fotnot med
    `aria-describedby`. Tryck → `POST /decisions/{id}/answer {option_id}`; övriga rader låsta i
    flykt; `202` och `409 decision_already_answered` ger båda besvarat läge (svaret ur kroppen vid
    `409`). Fokus till den besvarade raden. Ingen radiogrupp.
  - Verifiera: testfall **14**, 15, 16.
  - Filer: `components/chattyta/AlternativLista.tsx`, `lib/chattyta/api.ts`,
    `components/chattyta/TradRenderare.tsx`, `components/chattyta/__tests__/alternativ.test.tsx`
  - Obs: testfall 14 kontrollerar tre saker — inget valt, inget fokuserat, ingen annan stil än
    `RekMarke`. En rekommendation som får en mörkare kant är också ett förval.

- [ ] **C8 — Märket och `age_days`-tröskeln**
  - Acceptans: `aldersTon(ageDays)` med `ROD_FRAN_DAGAR = 7` på ett ställe. Mobilens
    `ChattList`-märke = `total` ur `GET /decisions?view_key&status=open&limit=1`.
    `mockVantandeBeslut` borta. `VyRad`s `saknar`/`vantar` tar en valfri `ageDays` och färgas
    med regeln.
  - Verifiera: testfall 21, 22, 32 (beslutshalvan).
  - Filer: `lib/chattyta/alder.ts`, `components/skal/VyRad.tsx`, `components/skal/Skal.tsx`,
    `lib/skal/mock.ts`, `lib/chattyta/__tests__/alder.test.ts`
  - Obs: stänger `SPEC-beslut.md` öppen fråga 1 och den ärvda frågan i `tasks/skal/todo.md` —
    notera det i båda filerna när C14 stänger modulen, inte här.

- [ ] **C9 — `JamforelseRader` (`receipt`) och `RadLista`**
  - Acceptans: båda talen i varje rad, etiketterna ur `labels`, belopp via `formatBelopp`,
    mono tabulärt. `RadLista` = samma radkomponent med en kolumn tal.
  - Verifiera: testfall 23. Fixtur ur C1.
  - Filer: `components/chattyta/JamforelseRader.tsx`, `components/chattyta/TradRenderare.tsx`,
    `components/chattyta/__tests__/jamforelse.test.tsx`

- [ ] **C10 — `VerifikationsForslag` utan knapp**
  - Acceptans: rubrikrad, kolumnrubriker Konto / Debet / Kredit (högra två 92 px högerställda),
    `KonteringsRad`, fot, konsekvensnotis i mono 12 `#52525b`. `kind` ≠ `voucher` →
    `okant_kontrakt` (redan i C1). Knappraden finns som slot, tom.
  - Verifiera: testfall 24.
  - Filer: `components/chattyta/VerifikationsForslag.tsx`, `components/chattyta/TradRenderare.tsx`,
    `components/chattyta/__tests__/forslag.test.tsx`
  - Obs: konsekvensnotisen är inte metatext. `text-bok-meta` på den är ett fel, inte en stilfråga.

- [ ] **C11 — Idempotensnyckeln (gate)**
  - Acceptans: `nyckelForUtkast(draftId)` = UUIDv5 under en fast `BOK_KLIENT_NS`, via
    `crypto.subtle` (SHA-1). Deterministisk, giltig v5 (version- och variantbitar), skild från
    serverns namnrymd.
  - Verifiera: testfall 26, plus en känd testvektor räknad med Pythons `uuid.uuid5` så att klient
    och server kan jämföras om de någon gång behöver det.
  - Filer: `lib/chattyta/idempotens.ts`, `lib/chattyta/__tests__/idempotens.test.ts`
  - Obs: **landas före C12.** Idempotens före något skrivflöde kopplas till en knapp
    (`ANALYS.md` §7).

- [ ] **C12 — Postningsknappen och dess sju utfall**
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

- [ ] **C13 — `FelKort`**
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
