# Plan: modul `skal`

Bygger `docs/redesign/SPEC-skal.md` (fas 1, skriven 2026-09-21). Uppgiftslistan ligger i
`tasks/skal/todo.md`. Beror på `oversikt` (klar). `chattyta` beror på den här.

## Beroendegraf

```
S1 tokens och typografi ──┐
                          ├─► S3 sid- och vykartan ──► S4 rutt och flagga
S2 testnätet ─────────────┘                                │
                                                           ▼
                                         S5 header ──► S6 SidVaeljare
                                                           │
                                         S7 vyraden ◄──────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                    S8 PrickNav         S9 vyskalet        S11 chattkolumnen
                          │                   │                   │
                          └─────────► S10 mobilen ◄───────────────┘
                                              │
                                     S12 läsvyerna
                                              │
                                   S13 regression och lint
```

## Ordning och varför

**S1 och S2 först, och de är gates.** Tokens före komponenter, annars skrivs sju komponenter mot
hårdkodade hexvärden och tokenfilen blir en efterhandskonstruktion som ingen använder. Testnätet
före första komponenten, annars upprepar modulen exakt det fel `ANALYS.md` §5 pekar ut: 12 700
rader TSX utan ett enda test. De två går parallellt — de rör inte samma filer.

**S3 före S4.** Kartan innan rutten. `view_key`, sidordning och "byte av sida landar på första
vyn" är rena funktioner som går att testa utan DOM. När de är låsta är rutten bara en läsning av
sökparametrar mot kartan. Omvänd ordning betyder att fallback-logiken skrivs mot en karta som
fortfarande flyttar sig.

**S5 före S6.** Headern innan väljaren. Väljaren renderar sidornas metarader, och de kommer från
`GET /overview`. Byggs väljaren först får den mockad data som sedan ska bytas ut — precis det
specens §8 säger att modulen inte ska göra.

**S7 är navet.** Vyraden (`scroll-snap`, position → aktiv vy) är det enda som både `PrickNav`,
vyskalet och mobilen hänger på. Den ska vara på plats och testad innan tre uppgifter börjar
konsumera dess tillstånd.

**S8, S9 och S11 går parallellt.** Prickarna, vyskalet och chattkolumnen rör skilda filer och
delar bara vyradens tillstånd. Det är modulens andra riktiga parallellisering.

**S10 efter alla tre.** Mobilen är inte en egen layout utan samma delar i en annan ordning, plus
`ChattList`. Byggs den tidigare byggs delarna två gånger.

**S12 näst sist, och den är en regel snarare än en yta.** Fakturering och Löner ska vara läsvyer
utan skrivflöde (spec §11). Det är lätt att göra rätt när de andra fem vyerna redan finns och
svårt att göra rätt om de byggs först — då blir de tomma vyer med en avstängd knapp.

## Parallellt vs sekventiellt

Två snitt går parallellt: `S1 ‖ S2` och `S8 ‖ S9 ‖ S11`. Resten är kedja. Vill man dela upp
arbetet mellan två personer är den naturliga gränsen "ram" (S3–S8) mot "innehållsskal" (S9, S11,
S12), med S7 som synkpunkt.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| Skalet börjar rendera trådinlägg | `chattyta` ärver en halvfärdig `BeslutKort` som redan ser rätt ut men inte bär kontraktet (ingen förvald rekommendation, alltid en väg ut, båda talen) | Spec §13 och S11:s acceptans: tråden är två mockade typer, renderaren är utbytbar, inget kort byggs |
| Tokens läggs ovanpå de gamla | En omdefinierad `--background` ändrar 24 sidor på en gång, i en modul vars hela poäng är att inte röra dem | `--bok-`-prefix, ingen gammal variabel omdefinieras. Testfall 7 och 18 |
| `scroll-snap` kopplas till routern | Varje svep blir en navigering; historiken fylls av sju poster per minut och bakåtknappen blir oanvändbar | `history.replaceState` för vy, routern bara för sida. Spec §4 |
| Klienten börjar räkna `waiting` | Datakontraktets regel 2 bryts i den första komponent som har siffrorna nära till hands, och headern blinkar igen | Testfall 8: headern får en `meta` servern hittat på och ska visa exakt den |
| Mobilmönstret byggs som egen layout | Två uppsättningar komponenter som glider isär vid första ändringen | S10 ordnar om befintliga delar och får bara lägga till `ChattList` |
| Testnätet blir sant men tomt | `npm test` är grönt och testar ingenting som kan gå sönder | Testfallen i spec §12 är namngivna per uppgift, och S13 kräver alla 18 |
| `notFound()` glöms i produktion | Ett halvfärdigt skal blir nåbart på driftmaskinen innan det är i bruk | Testfall 5, och flaggan är en byggtidsvariabel utan växel i gränssnittet |

## Vad som inte byggs här

Trådens inlägg och kort (`chattyta`), SSE (`tradar` + `chattyta`), skrivflöden
(`flode-verifikationer`), filsläpp i `ChattFalt` (`flode-underlag`), `SidTabbar` (spec §2.2), och
borttagning eller flytt av någon av de 24 befintliga sidorna (spec §3). Ingen rad Python.
