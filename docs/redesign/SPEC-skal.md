# Spec: `skal`

Modul-id `skal` i kapabilitetskartan (`ANALYS.md` §8). Beror på `oversikt` (klar 2026-09-21).
`chattyta` beror på den här. Byggs parallellt med `agentruntime`/`tradar` mot mockad tråd — det
är den enda meningsfulla parallelliseringen i hela planen (`ANALYS.md` §8).

Status: **Fas 1 — skriven 2026-09-21.** Uppgifterna ligger i `tasks/skal/plan.md` och
`tasks/skal/todo.md` (S1–S13). Modulen är **klar** 2026-09-21: S1–S13 avbockade, avvikelserna
och besluten står sist i `todo.md`.

De två öppna frågor som blockerade den här specen (`ANALYS.md` §9.1 och §9.3) är besvarade av
beställaren 2026-09-21 och skrivna i §3 respektive §2.1.

---

## Antaganden

1. **Skalet, inte innehållet.** Modulen bygger ramen: sidor, vyer, header, navigering, tokens,
   de sex lägena och den tomma chattkolumnen. Trådens inlägg (`TradInlagg`, `BeslutKort`,
   `AlternativLista`, `VerifikationsForslag`, `FelKort`, `JamforelseRader`) är `chattyta`.
   Skalet visar dem som mockad data och får inte rendera dem "nästan rätt" — se §13.
2. **Bredvid, inte i stället för.** De 24 befintliga sidorna står orörda. Skalet ligger på en egen
   rutt bakom en flagga (§4). Det är `ANALYS.md` §7:s motdrag mot big-bang-rewrite, skrivet i kod.
3. **Enbolag.** En `view_key` bär vyn och ingenting annat (`SPEC-tradar.md` §12.2). Headern visar
   bolagsnamnet som text, inte som väljare.
4. **Servern räknar, klienten formaterar.** Datakontraktets regel 2. `waiting` och `meta` kommer
   färdiga från `GET /api/v1/overview` (`SPEC-oversikt.md` §5); skalet summerar ingenting.
5. **Hi-fi.** Färger, mått, typografi och copy i handoffen är avsedda värden, inte förslag.
   Svensk produkttext, inte platshållare.

---

## 1. Objektiv

### Problemet, konkret

`design_handoff_bokai/README.md`:

> Tre sidor, sju vyer. **Vyer inom en sida** byts på plats: horisontell `scroll-snap`-rad, svep
> eller prickar. Inget karusellbibliotek. **Chatten hör till vyn**, inte till appen.

`frontend-v3` i dag är det motsatta: 24 sidor, ~12 700 rader TSX, en sidomeny och noll
frontendtester (`ANALYS.md` §5). Det finns ingen yta att hänga en tråd på, ingen `view_key`, inga
designtokens — `tailwind.config.ts` bär shadcn-standardpaletten i HSL, och `app/fonts/GeistMonoVF.woff`
ligger i repot utan att någonsin laddas, trots att hela designen vilar på mono för belopp, datum
och verifikationsnummer.

Utan skalet har `chattyta` ingenstans att landa, och `tradar`s sju `view_key` har ingen klient som
skickar dem.

### Vad vi bygger

Fem saker, i den ordningen:

1. **Tokens och typografi** — designens färger, mått, radier och skuggor som CSS-variabler, och
   Geist Mono faktiskt laddad.
2. **Ett testnät** — det finns inget i dag. Ingen skalkomponent landar utan test (§12).
3. **Ramen** — 3 sidor / 7 vyer, `SidVaeljare`, `PrickNav`, `scroll-snap`-raden, `AgentStatus`,
   headerns räkenskapsår och periodläge, allt matat av `GET /api/v1/overview`.
4. **Vyskalet** — `VyHeaderStatus`, `VyBanner`, `VySektion`, `VyRad` i alla sex lägen, med
   skelettladdning i stället för spinner.
5. **Mobilen** — header 56, vy överst, `ChattList` nederst, tråden 260 px, chatten följer samma
   svep som vyn.

### Vad vi inte bygger här

Trådens inlägg och kort (`chattyta`), något skrivflöde (`flode-verifikationer`), SSE-anslutningen
(`tradar` levererar strömmen, `chattyta` konsumerar den), och borttagning av någon av de 24
befintliga sidorna. Se §13.

### Framgång

Sju vyer går att nå med svep, prickar, piltangenter och sidväljare; headern blinkar inte;
belopp är mono och tabulära; ingen av de 24 gamla sidorna har ändrat beteende; och det finns
för första gången ett `npm test` som går att lita på.

---

## 2. Tre motsägelser i handoffen, avgjorda

Handoffen är i huvudsak entydig. Tre punkter är det inte, och alla tre är skalets. De avgörs här
så att de inte avgörs en gång till i varje komponent.

### 2.1 Förslagschips — **BESLUTAT: nej, ren text**

`README.md` och `komponenter.md` säger båda ordagrant om `ChattFalt`: *"Ren text, inga
förslagschips."* `BokAi redesign v10.dc.html` rad 154 har ändå en `sc-if value="{{ visaForslag }}"`
med två chips, och `skarmbilder/v10-desktop-01-bocker-balansrakning.png` visar dem renderade.

Beslutat av beställaren 2026-09-21: **inga chips.** Två dokument som säger samma sak uttryckligen
väger tyngre än en påslagen växel i en prototyp. `ChattFalt` är ren textinmatning.

Skälet håller även utan omröstningen: ett chip är ett förvalt yttrande. Designens egen regel för
`AlternativRad` är att ingenting förväljs — ringen är tom, och sista alternativet är alltid en väg
ut. Chips under fältet hade varit samma sak i andra kläder, och de hade dessutom behövt ett
kontrakt om **vem** som formulerar dem, vilket datakontraktet inte ger.

Det här stänger `ANALYS.md` §9.3.

### 2.2 `SidTabbar` eller `SidVaeljare` på bred skärm — **BESLUTAT: väljaren, båda breddarna**

`README.md` §Skärmar beskriver sidtabbar från ungefär 900 px, och `komponenter.md` listar
`SidTabbar` som egen komponent. Men omgång 10 — den senaste, och den som `v10-desktop-*` är tagna
ur — har väljarknappen (`SIDA` / `Böcker` / `▼`) i headern **också** på 1180 px breda ramen.
Skärmbilden bekräftar den.

Avgjort mot v10: **`SidVaeljare` på båda breddarna, `SidTabbar` byggs inte.** Tre skäl:

1. `ANALYS.md` §8 räknar upp modulens innehåll som *"header, `PrickNav`, `SidVaeljare`, mobil
   `ChattList`, tokens"*. `SidTabbar` står inte där. Kapabilitetskartan är godkänd; README:s
   skärmsektion är det inte.
2. Prototypen är senare än prosan. `README.md`:s desktopsektion beskriver en tidigare omgång.
3. En komponent mindre att hålla i synk, och sidprickens betydelse (gult = väntar) finns redan i
   väljarens metarad.

Det som **inte** faller bort är tabbens informationsinnehåll: väntar-pricken och sidans metarad.
Båda bor i väljaren i stället, i samma färger.

### 2.3 Desktopfotens `dra i sidled` och lägesräknare — **krom, byggs inte**

Ramens fot i v10 (höjd 48) innehåller tre saker: texten `dra i sidled`, `PrickNav`, och en
lägesräknare (`{{ deskLage }}`, t.ex. `1 av 3`). `README.md` listar *"raden 'Flöde på sidan' i
ramens fot och stegräknaren"* som dokumentationskrom som inte ska byggas.

Foten byggs, men bara som bärare av `PrickNav`: 48 px, `border-top 1px #e5e7eb`, vit, prickarna
centrerade. Instruktionstexten och räknaren är krom och utgår. `PrickNav` självt är inte krom —
`komponenter.md` specificerar det som riktiga knappar med `aria-label`, och README kräver en
tangentbordsekvivalent till svepet.

---

## 3. Sidorna som designen inte ritar (`ANALYS.md` §8b)

Beslutat av beställaren 2026-09-21: **bakom flagga, gamla kvar.** Väg (b) av de tre.

- Det nya skalet får en egen rutt bakom en flagga. Headern har **exakt** tre sidor och sju vyer.
- De 24 befintliga rutterna finns kvar oförändrade, med sin sidomeny, utanför skalet.
- De tas bort **vy för vy** när motsvarigheten i skalet är klar och i bruk.

§8b besvaras alltså inte nu — den besvaras per sida, av den modul som ersätter den. Det betyder
att kontoplan, inställningar, learning, SRU-mappningar, **revisionsspåret**, fakturaformulären och
`vouchers/new` + `vouchers/intake` varken flyttas, döps om eller tappas i den här modulen.

Revisionsspåret är skälet att beslutet är rätt även om det låter som ett uppskjutande: `audit` är
ett BFL-krav, inte en bekvämlighet (`ANALYS.md` §8b), och en rewrite som tar bort det innan
ersättaren finns är precis den sortens fel append-only-reglerna finns för att förhindra.

**Konsekvens som ska stå i koden:** ingen fil under `app/` utanför skalets egen katalog får ändras
av den här modulen, med **ett** undantag — `components/AppShellClient.tsx`, som måste veta att
skalets rutt inte ska ha sidomeny. Undantaget är en rad. Se §4.

---

## 4. Rutt, flagga och samexistens

| | Gamla | Skalet |
|---|---|---|
| Rutt | `/`, `/vouchers`, `/invoices`, … (24 st) | `/v4` |
| Ram | `AppShellClient` + `Sidebar` | ingen sidomeny, egen header |
| Flagga | — | `NEXT_PUBLIC_SKAL=1`, annars `notFound()` |
| Auth | `AuthGuard` | `AuthGuard`, oförändrad |

**Rutten heter `/v4`** och inte `/skal`: `skal` är vårt modul-id, inte ett ord en människa ska se i
adressfältet. `/v4` är ärligt temporärt — när de gamla sidorna är borta blir skalet `/` och
rutten försvinner.

**Flaggan är en miljövariabel, inte en användarväxel.** `NEXT_PUBLIC_SKAL` läses vid bygget.
Saknas den svarar `/v4` med `notFound()`. Det finns ingen växel i gränssnittet, ingen cookie och
inget läge att hamna i av misstag — ANALYS §7 ber om en flagga för att kunna bygga vidare utan att
störa drift, inte om en A/B-mekanism.

**Sidan är en rutt, inte sju.** Hela skalet är `/v4` med två sökparametrar: `?sida=bocker&vy=balans`.
Skälet är `scroll-snap`: vyerna ligger i en rad som skrollas, och ett svep får inte kosta en
navigering. Positionen skrivs tillbaka med `history.replaceState` så att en omladdning landar rätt,
men den går aldrig genom Next-routern. Sidbytet går genom routern, för det är ett riktigt byte.

Okänd `sida` eller `vy` i URL:en faller tillbaka på `bocker` respektive sidans första vy — till
skillnad från servern, som ger `404` på en okänd `view_key` (`SPEC-tradar.md` §5). Asymmetrin är
avsiktlig: en trasig länk ska landa någonstans, en trasig klient ska inte tysta skapa en tråd.

---

## 5. Sid- och vykartan

Tabellen är skalets enda sanning om vad som finns, och den är samma sju nycklar som
`SPEC-tradar.md` §5 validerar mot.

| Sida | Sidnyckel | Vy | `view_key` |
|---|---|---|---|
| Böcker | `bocker` | Balansräkning | `bocker.balans` |
| Böcker | `bocker` | Resultaträkning | `bocker.resultat` |
| Böcker | `bocker` | Verifikationer | `bocker.verifikationer` |
| Fakturering och löner | `betala` | Fakturering | `betala.fakturering` |
| Fakturering och löner | `betala` | Löner | `betala.loner` |
| Bokslut | `bokslut` | Rapporter | `bokslut.rapporter` |
| Bokslut | `bokslut` | Åtgärder och nyckeltal | `bokslut.atgarder` |

Kartan ligger som **data i en modul**, inte utspridd i JSX: `lib/skal/vyer.ts`, en fryst lista i
designens ordning. Sidnycklarna är samma tre som `GET /api/v1/overview` svarar med, i samma
ordning, så att headern kan zippa svaret mot kartan utan att leta.

Tre regler som hör till kartan och testas som kartans regler (§12):

1. **Byte av sida landar alltid på sidans första vy** (`README.md`). Aldrig på "den vy du var på
   sist i den sidan" — det gör navigeringen oförutsägbar och står inte i designen.
2. **`view_key` härleds ur kartan**, aldrig ur en sträng som klistras ihop i en komponent. Ett
   stavfel ska vara ett typfel, inte en tom tråd.
3. **Listan är sluten.** Sju vyer. En åttonde kräver att `SPEC-tradar.md` §5 ändras först, och den
   listan är validerad i servern.

---

## 6. Komponenterna

Namnen är `komponenter.md`:s. Mappningen görs **en gång** här och hålls fast (handoffens egen
instruktion).

| Designnamn | Fil | Vad skalet levererar |
|---|---|---|
| `SidVaeljare` | `components/skal/SidVaeljare.tsx` | knapp + utfälld lista, desktop `width 430`, mobil `left 8 right 8` med överlägg |
| `PrickNav` | `components/skal/PrickNav.tsx` | prickar 7 px, aktiv 20×7, pillerram, riktiga knappar |
| `AgentStatus` | `components/skal/AgentStatus.tsx` | prick 7×7 + text, tre lägen |
| `VyHeaderStatus` | `components/skal/VyHeaderStatus.tsx` | vytitel 17/500 + status mono 12 i lägets färg |
| `VyBanner` | `components/skal/VyBanner.tsx` | fyra toner, en åt gången |
| `VySektion` | `components/skal/VySektion.tsx` | rubrik mono 10 versalt; tom sektion renderas inte |
| `VyRad` | `components/skal/VyRad.tsx` | sex varianter, mono tabular till höger |
| `ChattFalt` | `components/skal/ChattFalt.tsx` | streckad kant, ren text, `↵` |
| `ChattList` | `components/skal/ChattList.tsx` | mobil list min-height 50, märke, tråd 260 |
| — | `components/skal/Header.tsx` | desktopheader 62 / mobil 56 |
| — | `components/skal/VyRad.skeleton` | skelettrader `#f4f4f5`, samma radhöjd |

`TradInlagg`, `FilInlagg`, `SkriverIndikator`, `SparChip`, `RadLista/i-tråd`, `BeslutKort`,
`GodkannKort`, `AlternativLista`, `VerifikationsForslag`, `FelKort` och `JamforelseRader` byggs
**inte** här. De är `chattyta`. Skalet renderar tråden som en mockad lista av två enkla typer
(agenttext och egen replik) och markerar i koden att `chattyta` byter ut renderaren.

### Mått som inte får glida

Fasta värden ur `README.md` §Mått, och de enda som är fasta:

- desktopheader **62**, vykolumn **470**, desktopfot **48**
- mobilheader **56**, mobil chattråd **260**, mobilram radius **28**
- träffytor minst **44**, i mobila kort **46**, chattlisten **50**
- brytpunkten mellan desktop och mobilmönster: **1000 px** (`README.md`: *"Under ungefär 1000 px
  ska vyn läggas över chatten enligt mobilmönstret i stället för att pressas smalare"*)

Vykolumnen är fast 470; chattkolumnen krymper. Det är den enda kolumnen som har ett fast tal.

---

## 7. Tokens

Designens palett, skala och mått blir CSS-variabler under `:root` i `app/globals.css`, med
prefixet `--bok-`, och exponeras i `tailwind.config.ts` som namngivna färger och mått.

**De befintliga shadcn-variablerna (`--background`, `--foreground`, `--primary`, …) rörs inte.**
De 24 gamla sidorna står på dem. Skalets tokens läggs **bredvid**; ingen gammal variabel omdefinieras.
Det är hela skälet att prefixet finns.

Tre saker som är mer än färgvärden:

1. **Två toner bär betydelse.** Gult = väntar på människan. Grönt = postat och låst. De får inte
   användas dekorativt, och det ska stå som kommentar i tokenfilen — inte bara i den här specen.
2. **Geist Mono laddas.** `app/fonts/GeistMonoVF.woff` finns i repot men registreras inte i
   `app/layout.tsx`. Utan den faller varje belopp, datum och verifikationsnummer tillbaka på
   systemets monofont och designen är sönder på första raden. Registreras som `--font-geist-mono`
   bredvid `--font-geist-sans`.
3. **Vikt 500 är den tyngsta.** Ingen fet text någonstans i skalet. Tokenfilen definierar
   `--bok-vikt-medel: 500` och skalet använder inte `font-bold`.

**Belopp** renderas med `font-variant-numeric: tabular-nums`, mellanslag som tusentalsavgränsare
och `−` (U+2212) som minustecken. `lib/utils.ts::formatCurrency` ger i dag `Intl` med
`style: "currency"`, alltså `−400 720,00 kr` med valutasuffix — designen visar `400 720` utan
suffix i vyraderna. Skalet får en egen `formatBelopp` i `lib/skal/format.ts` och **ändrar inte**
`formatCurrency`, som 24 sidor anropar.

---

## 8. Data

| Vad | Var det kommer ifrån | Läge |
|---|---|---|
| Sidornas `waiting` + `meta` | `GET /api/v1/overview` (`SPEC-oversikt.md` §5) | finns |
| Räkenskapsår, periodläge | samma anrop, `fiscal_year` + `period_state` | finns |
| Agentläge | `GET /api/v1/agent/status` (`SPEC-tradar.md` §7) | finns, tre lägen |
| Vyns rader | vyns egna endpoints, via `hooks/useVyer.ts` (`lib/skal/bocker.ts`, `betala.ts`, `bokslut.ts`) | finns |
| Tråden | `GET /api/v1/threads/{view_key}` | finns (`chattyta`) |

**Ett anrop för headern.** `useOverview()` är en `useQuery` med nyckeln `["overview"]`, och den är
den **enda** källan till sidornas prickar och metarader. Skalet räknar aldrig `waiting` själv, inte
ens när det vore en rad — datakontraktets regel 2, och `SPEC-oversikt.md` §5 säger uttryckligen att
servern bestämmer.

**Ingen påhittad data.** `lib/skal/mock.ts` är borttagen (2026-09-23). Vyernas innehåll byggs av
rena avbildningar från API-svar till `VyData` (`lib/skal/vydata.ts`); komponenterna tar data som
props. En vy utan data visar sitt tomma läge, aldrig exempelrader.

**`agent_status` faller mjukt.** Går anropet inte fram visar `AgentStatus` ingenting alls, inte
"Agenten pausad". Pausad är ett riktigt läge med en orsak (`SPEC-tradar.md` §7); att gissa det ur
ett nätverksfel vore en lögn i produkttonen.

---

## 9. De sex lägena

`README.md` §Tillstånd. Varje vy ska kunna visa alla sex, och skalet ska kunna visa dem innan det
finns riktig data — därför är lägena en prop, inte en härledning.

| Läge | Vyn | Chatten | Header |
|---|---|---|---|
| Normal | rader, ingen banner | tråd med historik | status `#6b7280` |
| Väntar på dig | banner varning, rad med gul metatext | beslutskort sist | status `#b45309` |
| Pågår | rad grå med `postas…`, banner neutral | skriver-indikator | `Agenten postar`, prick `#2563d9` |
| Klart | ny rad kortvarigt `#f0fdf4` | kvittering | status `#15803d` |
| Fel | rad med röd metatext, banner röd | felkort | `Agenten pausad`, prick `#dc2626` |
| Tomt | **sektionen utgår helt**, inte tom rubrik | agenten säger att perioden är avstämd | status neutral |

Två av raderna är regler, inte utseende, och de testas som regler:

- **Tomt läge tar bort sektionen.** En rubrik utan rader är en lögn om att något saknas. `VySektion`
  renderar `null` när radlistan är tom.
- **`ny`-markeringen är kortvarig.** Annars färgas listan grön över tiden och grönt slutar betyda
  "postat och låst". Skalet har en timer och en varaktighet på ett ställe.

**Laddning är skelettrader, aldrig en spinner över hela ytan** — `#f4f4f5`, samma radhöjd som en
riktig rad, så att listan inte hoppar när data landar. Chatten visar tråden så fort den finns.

---

## 10. Tillgänglighet

`README.md` §Tillgänglighet är krav, inte ambition:

1. **Svepet har en tangentbordsekvivalent.** `←`/`→` byter vy inom sidan när fokus ligger i
   vyraden. `PrickNav`:s knappar är riktiga `<button>` med `aria-label` som är vyns namn.
2. **`aria-live="polite"`** på det som strömmar och på postningar. Skalet lägger regionen och
   annonserar vybyte och laddningsutfall; `chattyta` fyller den med agentens text.
3. **Kontrast minst 4.5:1.** `#9ca3af` är tillåtet för metadata och kolumnrubriker, **aldrig** för
   text som bär en konsekvens. Konsekvensnotisen (`låses vid postning`) är mono 12 `#52525b`, inte
   metatextgrå — den hör till `chattyta` men tokenens roll sätts här.
4. **Träffytor aldrig under 44.** Prickarna är 7 px höga *visuellt* men får en träffyta på 44 via
   padding, inte via en större prick.
5. **Reducerad rörelse.** `scroll-behavior: smooth` på vyraden respekterar
   `prefers-reduced-motion`.

---

## 11. Fakturering och Löner är läsvyer utan skrivflöde

`ANALYS.md` §8 kräver uttryckligen att det här står i den här specen, *"annars byggs två tomma
vyer eller två vyer som lovar mer än de gör"*.

Flöde 2 (löneunderlag) och flöde 3 (kundfaktura) är ur scope. Vyerna finns ändå i
informationsarkitekturen, och de byggs som **läsvyer med tråd men utan skrivflöde**:

- De visar rader och status som de andra fem vyerna.
- De har sin egen tråd och `view_key`; agenten kan svara på frågor om dem.
- De har **ingen** primärknapp i vyns fot, inget `GodkannKort`, ingen `VerifikationsForslag`.
- Skrivning sker tills vidare via de befintliga sidorna (`/invoices`, `/payroll`), som står kvar
  enligt §3.

Vad de **inte** får göra: visa en avstängd knapp, en `kommer snart`-text eller ett tomt kort.
En yta som lovar en funktion som inte finns är sämre än en yta som inte lovar den.

---

## 12. Teststrategi

Det finns **noll** frontendtester i dag (`ANALYS.md` §5). Att bygga skalet utan att lägga nätet
först vore att upprepa felet i större skala — 7 vyer utan regressionsskydd.

**Verktyg:** `vitest` + `@testing-library/react` + `jsdom`, körda med `npm test`. Inte Playwright:
`playwright` finns som oanvänd devDependency, men en webbläsarstart per körning är fel växel för
komponenter vars regler är rena funktioner och DOM-påståenden. Den dagen ett flöde ska testas
hela vägen (det är `flode-verifikationer`, inte skalet) är Playwright rätt verktyg och finns kvar.

**Testerna skrivs före implementationen**, som i de tre färdiga backendmodulerna.

| # | Fall | Uppgift |
|---|---|---|
| 1 | Kartan har exakt 7 vyer och 3 sidor, i designens ordning | S3 |
| 2 | Varje vy ger den `view_key` `SPEC-tradar.md` §5 listar — jämfört mot en hårdkodad lista | S3 |
| 3 | Sidbyte landar på sidans första vy, aldrig på den senast besökta | S3 |
| 4 | Okänd `sida`/`vy` i URL faller tillbaka på `bocker` + första vyn | S4 |
| 5 | `/v4` utan `NEXT_PUBLIC_SKAL` ger `notFound()` | S4 |
| 6 | `formatBelopp` ger mellanslag som avgränsare och `−` (U+2212), inte `-` | S1 |
| 7 | `formatCurrency` är oförändrad — samma utdata som före modulen | S1 |
| 8 | Headern läser `waiting`/`meta` från svaret och räknar inte själv | S5 |
| 9 | `AgentStatus` visar ingenting när statusanropet fallerar, inte "pausad" | S5 |
| 10 | `SidVaeljare` fälls ut, stängs med `Escape` och med klick utanför | S6 |
| 11 | `PrickNav` har en `<button>` per vy med vyns namn som `aria-label` | S8 |
| 12 | `←`/`→` byter vy inom sidan och stannar vid kanterna | S8 |
| 13 | `VySektion` med tom radlista renderar `null`, inte en rubrik | S9 |
| 14 | Laddning ger skelettrader med samma radhöjd, ingen spinner | S9 |
| 15 | `ny`-markeringen försvinner efter sin varaktighet | S9 |
| 16 | `ChattList` visar märket för väntande beslut även minimerad | S10 |
| 17 | Fakturering och Löner har ingen primärknapp i vyns fot | S12 |
| 18 | Ingen fil under `app/` utanför skalet har ändrats utom `AppShellClient.tsx` (undantag: de fem sidor `flode-verifikationer` F4 måste röra, se `SPEC-flode-verifikationer.md` §4.3) | S13 |

Testfall 7 och 18 är regressionsvakter mot §3:s löfte: de gamla sidorna ska inte märka att
modulen har funnits.

---

## 13. Gränser

**Byggs inte här:** trådens inlägg och kort (`chattyta`), SSE-anslutning (`tradar` + `chattyta`),
något skrivflöde eller någon postning (`flode-verifikationer`), filuppladdning i `ChattFalt`
(`drop`-varianten är ritad men hör till `flode-underlag`), borttagning eller flytt av någon av de
24 befintliga sidorna (§3), och `SidTabbar` (§2.2).

**Rörs inte:** backend överhuvudtaget. Modulen lägger ingen endpoint, ingen migration och ingen
rad Python. Om headern saknar ett fält är det `oversikt` eller `tradar` som ska ändras, inte en
uträkning i klienten.

**Fråga först** om något av det här visar sig behövas: en fjärde sida, en åttonde vy, ett fält som
inte finns i `GET /overview`, en ändring i `formatCurrency` eller i någon av de befintliga
shadcn-tokensen, eller en flytt av en gammal sida.

---

## 14. Framgångskriterier

1. Sju vyer, tre sidor, i designens ordning, nåbara med svep, prickar, piltangenter och väljare.
2. Byte av sida landar på sidans första vy; positionen överlever en omladdning via URL:en.
3. Headern får `waiting`, `meta`, räkenskapsår och periodläge från **ett** anrop och räknar inget.
4. Geist Mono är laddad; alla belopp är mono, tabulära, med mellanslag och `−`.
5. Alla sex lägen går att visa i varje vy, och tomt läge tar bort sektionen.
6. Laddning är skelettrader, aldrig en spinner över hela ytan.
7. `PrickNav` är riktiga knappar med `aria-label`; `←`/`→` fungerar; träffytor ≥ 44.
8. Fakturering och Löner är läsvyer utan primärknapp, utan avstängd knapp och utan `kommer snart`.
9. `/v4` är oåtkomlig utan flaggan; de 24 gamla sidorna beter sig exakt som före modulen.
10. `npm test` finns, är grönt och täcker de 18 fallen i §12. `npm run build` och `npm run lint`
    är rena.

---

## 15. Beslut

### 15.1 Förslagschips — **BESLUTAT: nej** (§2.1). Stänger `ANALYS.md` §9.3.

### 15.2 Sidorna utan hemvist — **BESLUTAT: bakom flagga, gamla kvar** (§3)

Skjuter `ANALYS.md` §9.1 från "blockerar `skal`" till "besvaras per sida av den modul som ersätter
sidan". Frågan är inte död, men den blockerar ingen längre.

### 15.3 `SidTabbar` utgår — **BESLUTAT** (§2.2)

Avgjort mot v10 och mot kapabilitetskartans uppräkning. `komponenter.md`:s `SidTabbar`-post är
därmed historik. Om beställaren vill ha tabbarna tillbaka är det en egen uppgift, inte en variant.

### 15.4 En rutt, inte sju — **BESLUTAT** (§4)

`scroll-snap` och Next-routern drar åt olika håll. Vyn är ett skrolläge, sidan är en navigering.

### 15.5 `vitest`, inte Playwright — **BESLUTAT** (§12)

Rätt växel för skalets regler. Playwright står kvar för det flöde som ska gå hela vägen.

---

## 16. Öppna frågor

1. **Vad står i headern som bolagsnamn?** v10 visar `BokAi · Wikner Teknik AB` hårdkodat.
   `GET /overview` bär inget bolagsnamn, och enbolagsantagandet gör en väljare fel. Skalet visar
   `BokAi` tills någon säger var namnet ska komma ifrån.
2. **Vad visar `Bokslut`-sidans metarad?** `oversikt` beslutade att `bokslut` räknar noll med
   skälet skrivet i koden (`tasks/oversikt/todo.md`). Sidan får alltså `Inget väntar` i väljaren
   tills `flode-verifikationer` ger den något att räkna. Ärligt, men ser trasigt ut bredvid två
   sidor med siffror.
3. **Varaktigheten på `ny`-markeringen.** Designen säger "kortvarig" och inget tal. Skalet sätter
   ett värde på ett ställe (§9); vilket tal det ska vara är ett designbeslut som inte är taget.
4. **Tröskeln som gör `age_days` gul eller röd** står kvar från `oversikt` (öppen fråga 3 där).
   `VyRad`-varianten `saknar`/`vantar` finns; vad som utlöser den gör inte.
