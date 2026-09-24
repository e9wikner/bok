# Plan: modul `chattyta`

Bygger `docs/redesign/SPEC-chattyta.md` (fas 1, skriven 2026-09-23, besluten i §12).
Uppgiftslistan ligger i `tasks/chattyta/todo.md`. Beror på `skal`, `tradar` och `beslut`, alla
klara. `flode-verifikationer` beror på den här.

Modulen är **bara frontend**. Ingen uppgift rör Python; gör en det har specen fel (antagande 1).

## Beroendegraf

```
C1 kontraktet: typer, parseInlagg, fixturer        (gate: formen före renderarna)
      │
      ├──► C2 SSE-läsaren (ramparser + återanslutning)
      │          │
      │          ▼
      │     C3 trådens tillstånd: reducer + useTrad + api
      │          │
      ├──► C4 textinläggen: TradInlagg, SparChip, FilInlagg, SkriverIndikator, RadLista
      │          │
      │          ▼
      │     C5 renderaren byts i skalet + ChattFalt skickar    ◄── första riktiga tråden
      │          │
      │          ├──► C6 BeslutKort / GodkannKort + beslutsstatus
      │          │          │
      │          │          ▼
      │          │     C7 AlternativLista + svar
      │          │
      │          └──► C8 märket + age_days-tröskeln
      │
      ├──► C9  JamforelseRader (receipt)
      │
      └──► C10 VerifikationsForslag (utan knapp)
                 │
                 ▼
            C11 idempotensnyckeln                            (gate: nyckeln före knappen)
                 │
                 ▼
            C12 postningsknappen och dess sju utfall
                 │
                 ▼
            C13 FelKort
                 │
            C14 tillgänglighet, regression, lint, visuell kontroll, modulen stängd
```

## Ordning och varför

**C1 först, och C1 är modulens första gate.** Allt annat är renderare av en typ, och typen är
kontraktet. `parseInlagg()` är det enda stället ett råinlägg blir en typad sak, och det är där
`okant_kontrakt` avgörs (§4.4). Byggs renderarna först läser var och en `body` på sitt eget sätt,
och det finns ingen plats där regeln "hellre inget kort än ett halvt" håller. Fixturerna i C1 är
**samma JSON som specen visar** för `draft` och `receipt` (§4.3) — det är det kontrakt
`flode-verifikationer` ska skriva mot, och en fixtur som glidit från specen är ett tyst kontraktsbrott.

**C2 före C3, som rena funktioner.** Ramparsern tar en `ReadableStream` och ger händelser; den
vet inget om React, auth eller vyer. Då går chunk-gränser, hjärtslag och flerradig `data:` att
testa utan nätverk (testfall 5). Samma skäl som `thread_stream.format_sse` är en fri funktion på
serversidan.

**C3 är en reducer först, en hook sedan.** Tillståndet (§6.3) har åtta händelser och tre sätt att
få en dubblett — återuppspelning, optimistiskt inlägg, strömmande platshållare. En ren reducer
testas händelse för händelse; en hook med `useEffect` och en ström testas bara som helhet.

**C4 → C5: en vertikal skiva tidigt.** Efter C5 visar `/v4` riktiga trådar med text, och
`ChattFalt` skickar. Allt efter C5 är ett kort till i en tråd som redan fungerar. Det gör också
att tidiga fel i C2/C3 syns mot riktig backend innan korten byggs ovanpå. Typer som ännu saknar
renderare under C5–C13 renderas som `okant_kontrakt` — ärligt, inte tomt.

**C6 före C7.** Beslutets status (§7) är en fråga per vy som både `BeslutKort` och
`AlternativLista` läser. C6 bygger frågan och de tre lägena; C7 skriver svaret och invaliderar
den. Omvänd ordning ger ett svar som inte syns.

**C8 efter C5**, eftersom märket ersätter `mockVantandeBeslut` i samma `Skal.tsx` som C5 rör.
`age_days`-regeln är en ren funktion och kunde gå när som helst; den ligger här för att den och
märket båda stänger ärvda frågor från `beslut` och `skal`.

**C11 före C12, och C11 är modulens andra gate.** Nyckeln (§8 steg 1) är det som gör att två tryck
ger en verifikation. Den ska vara härledd, testad och deterministisk **innan** någon knapp kan
anropa `POST /vouchers/{id}/post` — samma regel som `ANALYS.md` §7 satte för hela redesignen:
*idempotens byggs före något skrivflöde kopplas till en knapp.* Låsningen av knappen är
bekvämlighet; testfall 25 trycker två gånger utan att låsningen hinner verka.

**C13 efter C12**, eftersom `FelKort`s `Försök igen` går samma väg som `Posta`, med samma nyckel.
Utan C12 finns det inget att försöka igen med.

**C9 och C10 är fria efter C1.** De är presentation av fixturer och rör inga delade filer.

## Parallellt vs sekventiellt

- Sekventiellt: C1 → C2 → C3, C4 → C5 → C6 → C7, och C10 → C11 → C12 → C13.
- Efter C1: `C2 ‖ C4 ‖ C9 ‖ C10` rör olika filer.
- Efter C5: `C6 ‖ C8`.
- C14 avslutar alltid.

Det meningsfulla snittet är **trådspåret** (C2–C8) mot **förslagsspåret** (C9–C13). De möts bara i
renderarens `switch` på `type`, som är en rad per typ.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| Två tryck på `Posta` ger två verifikationer | En post i en append-only-bok som bara kan rättas med en korrigeringsverifikation | Nyckeln härledd ur `draft_id` (C11), före knappen (C12). Testfall 25, 26 |
| En rekommendation förväljs "för bekvämlighet" | Designens bärande regel bryts; en LLM:s kontering går igenom av bara farten | Ingen state som startar på ett alternativ; testfall 14 kontrollerar val, fokus **och** stil |
| Ett kort renderas halvt när kontraktet bryts | Ett `options` utan väg ut eller ett `receipt` med ett tal ser färdigt ut och ljuger | `parseInlagg` + `okant_kontrakt` (C1). Testfall 3, 4 |
| `draft`-fixturen glider från specen | `flode-verifikationer` skriver mot en form som klienten inte läser | Fixturen **är** §4.3:s JSON; C1:s test läser båda |
| Strömmen tappar eller dubblerar inlägg vid återanslutning | Tråden visar ett svar två gånger, eller inte alls | `since` = högsta sedda `seq`; dedup på `id`. Testfall 6, 7 |
| `EventSource` väljs av vana | Strömmen får `401`; någon lägger token i query-strängen för att få det att fungera | `fetch`-läsare (§6.1), och §6.1 säger varför de två andra vägarna är fel |
| Varje delta annonseras av skärmläsaren | Ett ord i taget, i evighet | Dold live-region som annonserar indikatorbyte och färdigt inlägg (testfall 31) |
| En knapp skickar en färdig mening | Förslagschipsen kommer tillbaka bakvägen | `Ändra` lägger bara fokus (§8 steg 4). Testfall 36 |
| `Försök igen` skickar om senaste meddelandet | En ny tur med kanske ett annat utfall, förklädd till ett omförsök | Ingen primärknapp utan `retry_draft_id` (§9). Testfall 29 |
| En Python-ändring "bara för att" | Modulen slutar vara en klient; en klar modul refaktoreras mitt i en ny | Framgångskriterium 8: `git diff main -- '*.py'` tom |
| Knappen kan inte ses mot riktig data | Den ser färdig ut i test och har aldrig mött ett riktigt `draft` | §12.1 accepterar priset. C14 kör knappen mot ett handskapat utkast i dev-DB, med `POST /vouchers` + ett `draft`-inlägg ur fixturen. Noteras för beställaren |

## Vad som inte byggs här

Producenten av `draft` och `receipt`, kedjan beslut → förslag → postning → kvitto, `view.changed`
som uppdaterar vyns rader, och de optimistiska `pagaende`-raderna — `flode-verifikationer`.
Vyernas riktiga rader. `ChattFalt`s `drop`-variant — `flode-underlag`. Äldre räkenskapsårs
trådar. Modellväljaren. Faktura- och löneförslag (`draft.kind` ≠ `voucher`).
