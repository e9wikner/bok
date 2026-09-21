# Uppgifter: modul `skal`

Spec: `docs/redesign/SPEC-skal.md` · Plan: `tasks/skal/plan.md`
Testerna skrivs **före** implementationen (§12). Ingen uppgift rör mer än 5 filer.
Testfallsnumren nedan syftar på tabellen i §12.

Allt ligger under `frontend-v3/`. Ingen uppgift rör backend.

---

- [x] **S1 — tokens och typografi (gate)**
  - Acceptans: designens palett, radier, spacing, skuggor och fasta mått som CSS-variabler med
    prefixet `--bok-` i `app/globals.css`, exponerade i `tailwind.config.ts`. **Ingen befintlig
    shadcn-variabel omdefinieras.** Geist Mono registreras som `--font-geist-mono` i
    `app/layout.tsx` — filen finns i repot men laddas inte i dag. `lib/skal/format.ts` får
    `formatBelopp` med mellanslag som tusentalsavgränsare och `−` (U+2212). Kommentar i tokenfilen
    om att gult och grönt bär betydelse och inte får dekorera.
  - Verifiera: testfall 6, 7. `npm run build` grön.
  - Filer: `app/globals.css`, `tailwind.config.ts`, `app/layout.tsx`, `lib/skal/format.ts`,
    `lib/skal/__tests__/format.test.ts`
  - Obs: `lib/utils.ts::formatCurrency` rörs **inte** — 24 sidor anropar den. Testfall 7 är
    vakten.

- [x] **S2 — testnätet (gate)**
  - Acceptans: `vitest` + `@testing-library/react` + `jsdom` installerade, `npm test` kör, och
    minst ett test som faktiskt kan gå sönder. Inte Playwright (spec §15.5); den befintliga
    `playwright`-devDependencyn lämnas orörd.
  - Verifiera: `npm test` grön, `npm run lint` ren.
  - Filer: `package.json`, `vitest.config.ts`, `vitest.setup.ts`, `.github/workflows/tests.yml`
  - Obs: CI-jobbet ska läsas, inte bockas — hela `tests.yml` är `continue-on-error: true`
    (AGENTS.md), så en grön bock betyder ingenting.

- [x] **S3 — sid- och vykartan som data**
  - Acceptans: `lib/skal/vyer.ts` bär tre sidor och sju vyer i designens ordning, frysta. Varje vy
    har `view_key` ur spec §5, och nycklarna jämförs i test mot en hårdkodad kopia av
    `SPEC-tradar.md` §5. `forstaVyn(sida)`, `vyAt(sida, index)` och `viewKeyOf(...)` är rena
    funktioner. Sidnycklarna är `bocker`, `betala`, `bokslut` — samma som `GET /overview`.
  - Verifiera: testfall 1, 2, 3.
  - Filer: `lib/skal/vyer.ts`, `lib/skal/__tests__/vyer.test.ts`
  - Obs: listan är sluten. En åttonde vy kräver att `SPEC-tradar.md` §5 ändras först — servern
    validerar mot sin egen lista och svarar `404` på allt annat.

- [x] **S4 — rutten `/v4` och flaggan**
  - Acceptans: `/v4` finns, `notFound()` utan `NEXT_PUBLIC_SKAL=1`. Läser `?sida=&vy=`, faller
    tillbaka på `bocker` + sidans första vy vid okänt värde. Vyposition skrivs med
    `history.replaceState`, sidbyte går genom routern. `AppShellClient` renderar `/v4` utan
    sidomeny — **den enda ändringen utanför skalets egen katalog**.
  - Verifiera: testfall 4, 5.
  - Filer: `app/v4/page.tsx`, `app/v4/layout.tsx`, `components/AppShellClient.tsx`,
    `lib/skal/rutt.ts`, `lib/skal/__tests__/rutt.test.ts`
  - Obs: `AuthGuard` rörs inte — skalet är en skyddad rutt som alla andra.

- [x] **S5 — headern och `GET /api/v1/overview`**
  - Acceptans: desktopheader 62, `border-bottom 1px #e5e7eb`, vit, padding 0/20. Vänster:
    `SidVaeljare`-knappen och bolagsraden. Höger: vyns status (mono 13), räkenskapsår och
    periodläge (mono 13 `#52525b`), `AgentStatus` (prick 7×7 + text 13, tre lägen). `useOverview()`
    är **enda** källan till `waiting` och `meta`; skalet summerar ingenting. `AgentStatus` visar
    ingenting alls när statusanropet fallerar — aldrig "pausad".
  - Verifiera: testfall 8, 9.
  - Filer: `components/skal/Header.tsx`, `components/skal/AgentStatus.tsx`, `lib/skal/api.ts`,
    `hooks/useSkal.ts`, `components/skal/__tests__/Header.test.tsx`
  - Obs: bolagsnamnet är öppen fråga 1 — headern visar `BokAi` tills någon säger var namnet
    kommer ifrån. Hårdkoda inte `Wikner Teknik AB` ur skärmbilden.

- [x] **S6 — `SidVaeljare`**
  - Acceptans: knappen är sidtiteln (15/500) + metarad mono 11 i sidans statusfärg + `▼`. Listan
    fälls ut direkt under headern: desktop `width 430`, radius 12, skugga
    `0 14px 36px rgba(10,15,26,0.16)`; mobil `left 8 right 8`, radius `0 0 14 14`, med överlägg
    `rgba(10,15,26,0.28)`. Rader min-height 44 (mobil 52) med titel, metarad och bock på aktiv
    sida. Stängs med `Escape` och med klick utanför. `SidTabbar` byggs inte (spec §2.2).
  - Verifiera: testfall 10.
  - Filer: `components/skal/SidVaeljare.tsx`, `components/skal/__tests__/SidVaeljare.test.tsx`
  - Obs: sidbyte landar på sidans **första** vy (S3:s `forstaVyn`), aldrig på den senast besökta.

- [x] **S7 — vyraden (`scroll-snap`)**
  - Acceptans: sidans vyer ligger i en horisontell `scroll-snap`-rad, `flex 0 0 100%` per vy,
    `scroll-snap-type: x mandatory`, dolda skrollisterna. Positionen **läses av** för att markera
    aktiv vy — den härleds inte ur ett klick. Inget karusellbibliotek. `scroll-behavior: smooth`
    respekterar `prefers-reduced-motion`. Desktop: två kolumner per vy, chatt `flex 1` med
    `border-right`, vy fast 470. Under 1000 px byter layouten till mobilmönstret (spec §6).
  - Verifiera: aktiv vy följer skrollpositionen; URL:en uppdateras utan navigering.
  - Filer: `components/skal/VyRad.tsx` *(raden, inte `VyRad`-komponenten — se obs)*,
    `components/skal/__tests__/vyrad.test.tsx`, `lib/skal/rutt.ts`
  - Obs: namnkrock. `komponenter.md`:s `VyRad` är **en rad i vyn** (S9). Raden av vyer heter
    `VySvep` i koden för att undvika två `VyRad`. Mappningen står i spec §6.

- [x] **S8 — `PrickNav` och tangentbordet**
  - Acceptans: prickar 7 px, aktiv 20×7, radius 999, aktiv `#0a0f1a`, inaktiv `#d4d4d8`, `gap 9`,
    i en pillerram `border 1px #e5e7eb`. Riktiga `<button>` med vyns namn som `aria-label`.
    Träffyta ≥ 44 via padding, inte via större prick. `←`/`→` byter vy inom sidan och stannar vid
    kanterna. Desktopfoten är 48 px och bär **bara** prickarna — `dra i sidled` och lägesräknaren
    är krom (spec §2.3).
  - Verifiera: testfall 11, 12.
  - Filer: `components/skal/PrickNav.tsx`, `components/skal/__tests__/PrickNav.test.tsx`,
    `components/skal/VySvep.tsx`

- [x] **S9 — vyskalet och de sex lägena**
  - Acceptans: `VyHeaderStatus` (titel 17/500, status mono 12 i lägets färg, `border-bottom`,
    padding 20/24/14), `VyBanner` (fyra toner, **en åt gången**), `VySektion` (rubrik mono 10
    versalt; **tom sektion renderar `null`**), `VyRad` (padding 9/8, `border-bottom 1px #f4f4f5`,
    titel 14 + metarad mono 11, höger mono 14 tabular) med sex varianter: `normal`, `saknar`,
    `pagaende`, `ny`, `fel`, `paverkad`. `ny`-markeringen är kortvarig, med varaktigheten på ett
    ställe. Laddning är skelettrader i `#f4f4f5` med samma radhöjd — aldrig en spinner.
  - Verifiera: testfall 13, 14, 15.
  - Filer: `components/skal/VyHeaderStatus.tsx`, `components/skal/VyBanner.tsx`,
    `components/skal/VySektion.tsx`, `components/skal/VyRad.tsx`,
    `components/skal/__tests__/vyskal.test.tsx`
  - Obs: vyns rader är mockade i den här modulen. Mocken ligger i `lib/skal/mock.ts`, märkt med
    vilken modul som ersätter den — aldrig inline i en komponent, aldrig som en `if (mock)`-gren.

- [x] **S10 — mobilen och `ChattList`**
  - Acceptans: header 56 (sidtiteln är väljaren, prickarna till höger), vyn överst, chatten
    nederst, båda synliga. `ChattList`: knapp min-height 50, padding 11/16, `Chatt` 14/500 + vyns
    namn 14 `#9ca3af` + märke + `▼`/`▲`. Uppfälld tråd 260 px med egen skroll. **Märket för
    väntande beslut syns även när chatten är minimerad.** `box-shadow 0 -8px 20px rgba(10,15,26,0.06)`
    skiljer listen från vyn. Chatten följer med i samma horisontella svep som vyn.
  - Verifiera: testfall 16.
  - Filer: `components/skal/ChattList.tsx`, `components/skal/VySvep.tsx`,
    `components/skal/Header.tsx`, `components/skal/__tests__/ChattList.test.tsx`
  - Obs: ingen egen mobil-layout. Samma delar i en annan ordning plus `ChattList` — annars glider
    två uppsättningar isär vid första ändringen.

- [x] **S11 — chattkolumnen och `ChattFalt`**
  - Acceptans: tråden padding 26/38, `gap 24`, **bottenankrad** (`justify-content: flex-end`),
    textrader max 54ch, kort max-bredd 560. `ChattFalt` nederst: padding 16/38/20,
    `border-top 1px #e5e7eb`, fältet radius 12 med streckad kant `#c7c7cc` på `#fbfbfc`, text 15
    `#71717a`, `↵` mono 12 till höger. **Ren text — inga förslagschips** (spec §2.1).
    `aria-live="polite"` på trådens nedre region.
  - Verifiera: inga chips i DOM; fältet är en riktig `<textarea>`/`<input>` med etikett.
  - Filer: `components/skal/ChattKolumn.tsx`, `components/skal/ChattFalt.tsx`, `lib/skal/mock.ts`,
    `components/skal/__tests__/ChattKolumn.test.tsx`
  - Obs: tråden renderas som **två** mockade typer (agenttext, egen replik) genom en utbytbar
    renderare. Bygg inget kort — `BeslutKort`, `AlternativLista`, `VerifikationsForslag`,
    `FelKort` och `JamforelseRader` är `chattyta` och bär kontrakt som skalet inte äger.

- [x] **S12 — Fakturering och Löner som läsvyer utan skrivflöde**
  - Acceptans: båda vyerna visar rader, status och tråd som de andra fem. **Ingen primärknapp i
    vyns fot, inget `GodkannKort`, ingen `VerifikationsForslag`.** Ingen avstängd knapp och ingen
    `kommer snart`-text — en yta som lovar en funktion som inte finns är sämre än en som inte
    lovar den. Vyns fottext säger vad agenten gör härnäst, inget mer.
  - Verifiera: testfall 17.
  - Filer: `lib/skal/mock.ts`, `components/skal/VyInnehall.tsx`,
    `components/skal/__tests__/lasvyer.test.tsx`
  - Obs: spec §11 finns därför att `ANALYS.md` §8 uttryckligen kräver att det här står skrivet
    någonstans. Skrivning sker tills vidare via `/invoices` och `/payroll`, som står kvar.

- [x] **S13 — regression, tillgänglighet och lint**
  - Acceptans: alla tio framgångskriterier i §14 uppfyllda. Kontrast ≥ 4.5:1 utom för metadata;
    `#9ca3af` bär aldrig en konsekvens. `aria-live="polite"` finns och annonserar vybyte.
    Träffytor ≥ 44. Ingen fil under `app/` utanför skalet ändrad utom `AppShellClient.tsx`.
  - Verifiera: testfall 18, samt hela `npm test`, `npm run build` och `npm run lint`.
    `git diff main -- frontend-v3/app` ska bara visa `app/v4/` och `app/globals.css` +
    `app/layout.tsx` (S1:s tokens och mono-fonten).
  - Filer: inga nya.

---

**Utanför scope:** trådens inlägg och kort (`chattyta`), SSE (`tradar`), skrivflöden
(`flode-verifikationer`), filsläpp i `ChattFalt` (`flode-underlag`), `SidTabbar`, och borttagning
eller flytt av någon av de 24 befintliga sidorna.

**Fråga först** (§13): en fjärde sida, en åttonde vy, ett fält som inte finns i `GET /overview`,
en ändring i `formatCurrency` eller i någon shadcn-token, eller en flytt av en gammal sida.

---

## Avvikelse från specen: `VySvep` i stället för ett andra `VyRad`

Specens §6 förutsåg namnkrocken; koden löser den som planerat. Raden **av vyer** heter `VySvep`,
raden **i vyn** heter `VyRad`, och mappningen mot `komponenter.md` står i båda filernas
docstring. Ingen fil heter `VyRad` två gånger.

## Avvikelse från specen: testfall 18 blev två vakter, inte en

Specen beskrev ett test. Det blev två, därför att det ena inte kan köras överallt:

- **Statisk vakt** — ingen fil under `app/` utanför `app/v4/` importerar från
  `@/components/skal`, `@/lib/skal` eller `@/hooks/skal`, och `AppShellClient.tsx` är den enda
  filen under `components/` utanför `components/skal/` som gör det. Körs alltid.
- **Git-vakt** — `git diff --name-only main -- app` får bara innehålla `app/v4/`,
  `app/globals.css` och `app/layout.tsx`. Hoppas över när `main` inte finns i checkouten, vilket
  den inte gör i CI:s grunda klon.

Bara den statiska vakten hade varit svagare än specens löfte; bara git-vakten hade varit tyst i
CI. Tillsammans är de det specen ber om.

## Avvikelse från designen: `AgentStatus` på mobilen

v10:s mobilram (`BokAi redesign v10.dc.html` rad 217–231) har ingen plats för `AgentStatus` —
headern är sidtiteln plus prickarna, och det är allt. Men `komponenter.md` är uttrycklig om att
pausad *"ska visas så länge den är pausad, inte bara i felinlägget"*.

Löst så att den enda regeln designen faktiskt uttalar hålls: mobilheadern visar `AgentStatus`
**bara i läget `pausad`**. `arbetar` och `postar` syns inte på mobilen, eftersom designen inte
säger att de ska och att rita in dem hade varit att hitta på krom. Det här är en
designfråga att bekräfta — se "Kvar att nämna för beställaren".

## Avvikelse från repots CI-vana: frontendjobbet får fälla bygget

Varje steg i `.github/workflows/tests.yml` är `continue-on-error: true`, så en grön bock betyder
ingenting (AGENTS.md säger det rakt ut). Det nya `frontend`-jobbets `npm test` är **inte**
undantaget: ett testnät som inte kan fälla ett bygge är inte ett testnät, och det här nätet är
nytt och har inga ärvda fel att svälja. `npm run lint` i samma jobb är däremot
`continue-on-error`, eftersom lintreglerna är de gamla.

Det ändrar inte beteendet för något befintligt jobb.

## Avvikelse från planen: versionsval i verktygskedjan

Två nedgraderingar mot senaste, båda tvingade av repots egna pinnar:

- **`vitest@^3`, inte `^5`.** Vitest 5 kräver `@types/node` `^22 || >=24`; repot står på `^20`.
  Att flytta `@types/node` hade rört Next-byggets typkontroll i en modul som lovar att inte röra
  de gamla sidorna.
- **`@vitejs/plugin-react@^4`, inte `^6`.** v6 drar in en egen Vite/Rolldown och `tsc --noEmit`
  faller på två oförenliga `Plugin`-typer. Testerna kördes, men typkontrollen gjorde det inte —
  och en grön testkörning bredvid en röd typkontroll är sämre än ingen av delarna.

Den befintliga oanvända `playwright`-devDependencyn är orörd (spec §15.5).

## Två fel som bara syntes i webbläsaren

Båda hittades vid visuell kontroll mot `next dev` med riktig backend, inte av testerna, och båda
har fått ett test efteråt (`components/skal/__tests__/VySvep.test.tsx`):

1. **En länk till `?vy=verifikationer` landade på sidans första vy.** Svepraden mäts upp innan
   barnen fått bredd; `scrollLeft` klamrades då till 0, och `scroll`-händelsen därifrån
   rapporterade vy 0 tillbaka och skrev över startpositionen. Åtgärd: `vidScroll` ignorerar
   händelser medan `scrollWidth <= clientWidth`, och startpositionen läggs om en gång efter
   första målningen.
2. **Rätt vy var markerad men fel vy syntes.** `scroll-behavior: smooth` gäller även
   programmatisk skrollning, och den animerade startpositionen hann avbrytas av
   snap-ankringen. Åtgärd: startpositionen sätts med `scroll-behavior: auto` och återställer
   stilen direkt — ett svep användaren inte har gjort ska inte se ut som ett svep.

## Beslut som inte stod i specen

- **Rutten är `/v4`, inte `/skal`.** `skal` är modul-id, inte ett ord en människa ska se i
  adressfältet. Rutten är avsiktligt temporär.
- **Flaggan accepterar `1` och `true`.** Allt annat, inklusive tom sträng, är av.
- **`ny`-markeringen varar 6000 ms** (`NY_MARKERING_MS` i `components/skal/VyRad.tsx`). Talet är
  satt på känsla — designen säger bara "kortvarig". Det står på ett ställe och är öppen fråga 3.
- **Brytpunkten 1000 px sitter i `hooks/useBredSkarm.ts`**, byggd på `useSyncExternalStore` så
  att servern ser bred skärm och klienten sin riktiga bredd utan hydreringsvarning.
- **Inaktiva vyer i svepraden är `aria-hidden`.** De ligger utanför skärmen; utan det läser en
  skärmläsare upp tre vyers innehåll i följd som om de vore en sida.
- **Bolagsnamnet är `BokAi`**, inte skärmbildens `Wikner Teknik AB`. `GET /overview` bär inget
  bolagsnamn (öppen fråga 1); att hårdkoda exempeldata hade sett färdigt ut och varit fel.
- **Tokens ligger i `app/globals.css` under `--bok-`**, exponerade som `bok-*` i Tailwind.
  Ingen shadcn-variabel är omdefinierad, och det står som kommentar i båda filerna.

## Modulen är klar

S1–S13 avbockade 2026-09-21. De tio framgångskriterierna i spec §14, verifierade:

1. Sju vyer, tre sidor, i designens ordning, nåbara med svep, prickar, piltangenter och väljare —
   ✅ (testfall 1, 2, 11, 12; visuellt kontrollerat i `next dev`).
2. Sidbyte landar på sidans första vy; positionen överlever en omladdning via URL:en — ✅
   (testfall 3, 4, plus `Skal.test.tsx` och `VySvep.test.tsx`).
3. Headern får `waiting`, `meta`, räkenskapsår och periodläge från ett anrop och räknar inget —
   ✅ (testfall 8). Mot riktig backend: `6 saknar underlag`, `1 förfallen faktura`,
   `Inget väntar` — serverns tre strängar, renderade ordagrant.
4. Geist Mono laddad; belopp mono, tabulära, med mellanslag och `−` — ✅ (testfall 6).
5. Alla sex lägen går att visa, och tomt läge tar bort sektionen — ✅ (testfall 13).
6. Laddning är skelettrader, aldrig en spinner — ✅ (testfall 14).
7. `PrickNav` är riktiga knappar med `aria-label`; `←`/`→` fungerar; träffytor ≥ 44 — ✅
   (testfall 11, 12).
8. Fakturering och Löner är läsvyer utan primärknapp, utan avstängd knapp, utan `kommer snart` —
   ✅ (testfall 17).
9. `/v4` oåtkomlig utan flaggan; de 24 gamla sidorna oförändrade — ✅ (testfall 5, 18).
   `git diff main -- frontend-v3/app` rör bara `globals.css` och `layout.tsx`, båda tillägg.
10. `npm test`: **89 gröna i 13 filer** (0 före modulen). `npm run lint` och `npx tsc --noEmit`
    rena. `NEXT_PUBLIC_SKAL=1 npm run build` bygger 24 rutter plus `/v4`.
    `pytest tests/ -q`: **794 gröna** — modulen rör ingen Python.

Nästa modul i byggordningen är `chattyta` (`ANALYS.md` §8), som beror på `skal`, `tradar` och
`beslut`. `beslut` är inte byggd än.

## Kvar att nämna för beställaren

- **`AgentStatus` syns bara som `pausad` på mobilen.** v10 ritar ingen plats för den i
  mobilheadern. Vill du ha `arbetar`/`postar` där också behöver mobilheadern ritas om — det är en
  designfråga, inte en bugg.
- **Bokslut-sidans metarad säger alltid `Inget väntar`.** Det följer av `oversikt`s beslut att
  sidan räknar noll tills `flode-verifikationer` ger den något att räkna. Ärligt, men det ser
  tomt ut bredvid två sidor med siffror.
- **`ny`-markeringens varaktighet är gissad** (6 s). Sätt ett tal om du har ett.
- **`age_days`-trösklarna är fortfarande inte satta** (öppen fråga från `oversikt`).
  `VyRad`-varianten `saknar` finns; vad som gör den gul eller röd gör inte.
- **De 24 gamla sidorna står kvar och kostar underhåll tills de tas bort vy för vy.** Det var
  beslutet, men det betyder att två frontends lever parallellt under hela redesignen.
