# Plan: modul `underlagstolkning`

Bygger `docs/redesign/SPEC-underlagstolkning.md` (fas 1, godkänd 2026-09-28, besluten i §12).
Uppgiftslistan ligger i `tasks/underlagstolkning/todo.md`. Beror på `agentruntime`, som är klar.
`flode-underlag` beror på den här.

Modulen har tre spår som möts i verktyget:

- **Predikatet** (U1): "saknar underlag" räknar `voucher_intake_sources` och undantar SIE4-importen.
  Det är en lagning av befintlig kod och modulens gate.
- **Tolkningen** (U2–U5): tabellen, kontrollerna och säkerheten, kandidatfrågan, rankningen och
  hypotesen. Kontrollerna, rankningen och hypotesen är ren logik utan databas.
- **Ytan** (U6–U9): verktyget, verktygslistan, läsvägen och agentinstruktionen.

U10 stänger med det skriptade passet och regressionen.

## Beroendegraf

```
U1 predikatet: voucher_intake_sources + sie4_import, compliance på det delade   (gate)
      │
      ├──────────────────────────────────┐
      ▼                                  ▼
U2 migration 030 + domän + repository   U4 kandidatfrågan (voucher_repo.match_candidates)
      │                                  │
      │   U3 kontroller + säkerhet ──┐   │
      │   (ren logik)                │   │
      │   U5 rankning + match +  ────┤   │
      │   hypotes (ren logik)        │   │
      │                              ▼   ▼
      └────────────────────────► U6 tolka_underlag: argument, hanterare, orkestrering
                                         │
                                         ├──► U7 verktygslistan: tolka_underlag sist
                                         │          │
                                         │          ▼
                                         │     U9 agentinstruktionen (03_bokforingsinstruktion.md)
                                         │          │
                                         └──► U8 GET /intake/{id}/interpretation
                                                    │
                                                    ▼
                                    U10 skriptat pass, regression, modulen stängd
```

## Ordning och varför

**U1 först, och U1 är modulens gate.** Matchningens kandidater är "postade verifikationer som
saknar underlag" (spec §7.1). Med dagens predikat är varje agentpostad verifikation en kandidat
för det kvitto den redan har, och varje SIE4-importerad verifikation en kandidat för vad som helst
(spec §2.1, §12.2, §12.5). Byggs kandidatfrågan före lagningen, testas den mot fel mängd. U1 är
också en fristående buggrättning av en siffra som syns i headern i dag, så den ska kunna landa och
driftsättas ensam, med den sjunkande `missing_attachments` förklarad i commit-meddelandet.

**U2 efter U1, men oberoende av den.** Tabellen och repositoryt rör ingenting befintligt. Den
kommer före verktyget eftersom append-only-triggrarna (testfall 30) ska vara bevisade innan något
skriver i tabellen, samma resonemang som `flode-verifikationer` F1.

**U3 och U5 är ren logik och kan byggas när som helst.** De tar det modellen påstod (och för
U5 en lista kandidater) och ger ett resultat. Att de inte behöver databasen är specens avsikt
(§4, sista stycket): servicen innehåller ingen SQL, och det är lättast att hålla om logiken
byggs och testas innan servicen får en databasberoende orkestrering runt sig.

**U4 kräver U1.** Kandidatfrågan använder det lagade predikatet, och testfall 20 (kandidat med
`voucher_intake_sources`) är just det U1 lagar. Frågan joinar in debetsumma, `VAT_IN`-moms och
kopplad bankhändelse i ett anrop (testfall 29).

**U6 samlar U2–U5.** Verktygets hanterare hämtar källan, läser filen för `text_layer`, kör
kontrollerna, hämtar kandidaterna, rankar, räknar `expected` och sparar. Hanteraren byggs utan
att läggas i `_TOOL_SPECS`, som `foresla_verifikation` i F6.

**U7 direkt efter U6, som egen commit.** Verktygslistan är en del av det cachade prefixet
(`SPEC-agentruntime.md` §6.6), och två befintliga tester (`agentruntime` 17, `flode-verifikationer`
22) låser dess form. Tillägget sist ska vara det enda som ändras.

**U8 kan byggas parallellt med U7.** Läsvägen läser bara det U6 sparar, plus `still_open` räknat
vid läsning.

**U9 efter U7.** Instruktionen hänvisar till ett verktyg som modellen måste kunna se.
`docs/to_agent/` är körtidsinnehåll, och ändringen testas som beteende (testfall 38).

**U10 stänger.** Det skriptade passet (testfall 39) prövar att instruktionens väg håller hela
vägen till `registrera_avstaende` utan ny verifikation.

## Parallellt vs sekventiellt

- Sekventiellt: U1 → U4 → U6 → U7 → U9 → U10.
- Efter U1: `U2 ‖ U4`. `U3` och `U5` när som helst före U6.
- Efter U6: `U7 ‖ U8`.
- U10 avslutar alltid.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| `compliance` byter till predikatet men behåller aliaset `v` | Predikatet nämner `vouchers.id`; frågan faller eller, värre, korrelerar fel | U1 flyttar hela frågan (med 500 kr-tröskeln) till `VoucherRepository`, så predikatet står i samma fil som sitt alias; testfall 4 jämför talen och testfall 5 greppar |
| SIE4-undantaget fångar mer än importen | Agentpostade verifikationer försvinner ur "saknar underlag" | `created_by` är `NOT NULL DEFAULT 'system'` (027), så `!=` ger aldrig `NULL`; testfall 3 och 5b står bredvid varandra |
| `missing_attachments` sjunker vid driftsättning och läses som en regression | Någon "lagar" tillbaka det | Commit-meddelandet och `tasks/README.md` säger att det är rätt siffra (spec §2.1) |
| Kandidatfrågan blir en fråga per kandidat | Långsam tolkning när många verifikationer saknar underlag | Testfall 29 räknar SQL-anropen; belopp och moms joinas i frågan |
| Verifikationens belopp räknas på fel sida | Diff mot nettot i stället för bruttot; pantexemplet ger 1 016 i stället för 120 | Spec §7.1: summan av debetraderna; testfall 16 kräver exakt `12000` |
| Rankningen väljer den första av två lika | Servern gissar vilken verifikation kvittot hör till | Entydigheten prövas på alla tre nycklarna (§7.3); testfall 18 |
| Hypotessökningen exploderar | Långsamt verktygsanrop vid 100 rader | Högst tre rader, avbrott vid första storlek med träff (§7.5); ett test med 100 rader och tidsgräns |
| `confidence`/`hypothesis` smyger in som argument | Modellens ord i ett fält som ser ut som data | Pydantic-modellen med `extra="forbid"`; testfall 15 |
| `text_layer` läser filen fel eller långsamt | Fel säkerhetsnivå | Återanvänder `extract_pdf_text` och `reconciliation_result` oförändrade; bild och skannad PDF ger `not_available` (testfall 13) |
| Verktygslistan ändrar ordning | Det cachade prefixet slutar träffa | U7 lägger till sist; testfall 34 jämför de elva första byte för byte |
| Verktyget skriver i böckerna | Tolkningen kopplar eller ändrar status i förbifarten | Testfall 33 jämför `vouchers`, `voucher_intake_sources`, `attachments` och `intake_sources.status` före och efter |
| `still_open` räknas genom att skriva | Ögonblicksbilden ändras | Härleds vid läsning i U8; triggrarna (testfall 30) och testfall 32 |

## Vad som inte byggs här

Koppling av underlag, differensbokföring och ersättning av felkopplat underlag. Ett hårt stopp i
postningen (§12.4). All frontend: `JamforelseRader` för flöde 4, filsläpp, kompletteringslistan.
Uppdelning av ett underlag med flera köp. Valutaomräkning. Ett LLM-anrop på servern. Historiken
av äldre tolkningar i läsvägen. Allt det hör till `flode-underlag` eller senare.
