# Plan: modul `beslut`

Bygger `docs/redesign/SPEC-beslut.md` (fas 1, skriven 2026-09-21, besluten i §11).
Uppgiftslistan ligger i `tasks/beslut/todo.md`. Beror på `tradar`, som är klar.
`chattyta` och `flode-verifikationer` beror på den här.

## Beroendegraf

```
B1 migration 026: decisions + decision_options
      │
B2 DecisionRepository + domänmodeller
      │
B3 DecisionService: livscykeln
      │
      ├──► B4 eskaleringsinvarianten   (gate: regeln före verktyget som kan bryta den)
      │          │
      │          ▼
      │     B5 be_om_beslut            (tionde verktyget, sist i _TOOL_SPECS)
      │
      ├──► B6 avståendet i tråden blir ett spårat beslut
      │
      └──► B7 GET /decisions + /decisions/{id}   (unionen av de tre källorna)
                 │
                 ▼
            B8 POST /decisions/{id}/answer
                 │
         ┌───────┼────────────┐
         ▼       ▼            ▼
        B9      B10          B11
   open_decisions  påminnelsen   agentinstruktionerna
                                  (runtime-innehåll — fråga först)
                 │
            B12 regression och lint
```

## Ordning och varför

**B1–B3 är livscykel utan konsument.** Tabellerna, repositoryt och servicen går att bygga och
testa isolerat, precis som T1–T2 i `tradar`. De fyra `CHECK`-villkoren finns från början och kan
inte läggas till senare utan migration: `kind`, `status`, och de två som säger att ett besvarat
beslut måste ha en tidpunkt och ett faktiskt svar. `UNIQUE (post_id)` hör till samma uppgift —
utan den kan ett kort i tråden svara mot två rader med olika status, och gränssnittet visar ett
kort vars knappar gör olika saker beroende på vilken rad som lästes.

**B4 före B5, och B4 är modulens gate.** Eskaleringsinvarianten (§6.3) är det beslutet i §11.1
skrivet som kod: en `options`-lista som ändrar resultat, moms eller period utan att ligga under
ett öppet `decision` avvisas. Landar verktyget först skrivs den första alternativlistan utan
validering, och invarianten blir en efterhandskonstruktion runt data som redan finns — samma fel
som `ANALYS.md` §5 pekar ut på annat håll. Regeln ska dessutom vara grön mot alla fyra fall
designen ritar innan något kan producera en lista alls.

**B5 är den enda uppgiften som rör `services/agent_tools.py`.** Verktyget läggs **sist** i
`_TOOL_SPECS`. Ordningen är en del av det cachade systempromptprefixet
(`SPEC-agentruntime.md` §6.6), och en insättning i mitten är en tyst cache-brytare som inte syns
i något test som inte letar efter den. `registrera_avstaende` står orört: det är dokumentvägens
verktyg och `tests/test_agent_runtime.py` står på det.

**B6 efter B3.** Ett avstående som agenten registrerar i en tråd ger redan i dag ett
`decision`-inlägg via `ThreadService._render`. Efter B1 är ett sådant inlägg utan rad i
`decisions` ett föräldralöst kort: det syns i tråden, men det går inte att lista, åldras eller
besvara. B6 stänger det hålet. `_decision_body` flyttas inte och skriver inte om agentens text —
den får en `decision_id` att bära.

**B7 före B8.** Läsvägen först, skrivvägen sedan — samma skäl som T8 före T9 i `tradar`: ett
beslut ska gå att lista och läsa innan det går att svara på, annars går svarsvägen inte att
felsöka mot något känt. B7 bär också hela unionen (§5), som är den del av modulen med flest
sätt att bli subtilt fel: tre id-rymder, två av dem syntetiska.

**B9 efter B7**, eftersom `open_decisions` ska läsa samma service som listan. Kriteriet är att
talet är **oförändrat** dagen uträkningen byts (testfall 33). Byggs den före unionen finns det
inget att jämföra mot.

**B11 sent, av samma skäl som T13 i `tradar` och A13 i `agentruntime`.** `docs/to_agent/` är
runtime-innehåll och bokstavligen agentens systemprompt — `repositories/system_instructions.py`
läser och serverar den, `tests/test_agent_entrypoint.py` asserterar på den. Ett tionde verktyg
ändrar vad agenten *kan göra*, så texten behöver troligen ändras. Frågan ställs först (§7).

## Parallellt vs sekventiellt

- Sekventiellt: B1 → B2 → B3, och B4 → B5, och B7 → B8.
- B4/B5 och B6 och B7 rör olika filer och kan gå parallellt när B3 ligger.
- Parallellt efter B8: B9, B10 och B11.
- B12 avslutar alltid.

Det enda meningsfulla snittet är `B5 ‖ B6 ‖ B7` efter B3. Resten är kedja.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| Ett beslut besvaras två gånger | Två repliker på ett kort som har ett svar, och i värsta fall två verifikationer i en bok som inte kan städas | Svarsinlägg och statusändring i **en** transaktion; `409` med det befintliga svaret ur `decisions.status`. Testfall 15, 17, 29 |
| En `options`-lista ändrar böckerna utan öppet beslut | En människa ändrar resultatet i förbifarten, utan att något spårat beslut säger att ett beslut togs — och utan att det kommer tillbaka om hon stänger fliken | Eskaleringsinvarianten, validerad när listan skrivs. Testfall 19, 20, 21 |
| Det tionde verktyget blir en väg förbi append-only | Append-only-regelns enda automatiska kontroll genom agentens yta faller | `be_om_beslut` rör bara `decisions`, `decision_options`, `thread_posts`. Testfall 26 = testfall 17 i `agentruntime`, kört mot den utökade listan |
| Verktyget läggs in i mitten av `_TOOL_SPECS` | Cache-prefixet bryts tyst; kostnaden stiger utan att något går sönder | Sist i listan, pinnat av testfall 25 |
| Status lagras i `thread_posts` | Ett inlägg ändras, vilket bryter `SPEC-tradar.md` §8.4 och gör tråden till något annat än vad människan såg | Statusen bor i `decisions`. Antagande 2, och `UNIQUE (post_id)` som binder ihop dem |
| Unionens id:n kolliderar | Ett svar går till fel beslut | Prefixade id:n per källa (`intake:`, `correction:`). Testfall 7 |
| De syntetiska källorna ser besvarbara ut | Klienten visar en knapp som leder till ett flöde som inte finns | `409 decision_not_answerable` med pekare till den befintliga vägen. Testfall 16 |
| `open_decisions` hoppar vid driftsättning | Räknaren i headern börjar ljuga den dag modulen som ska göra den sann driftsätts | Unionen (§11.2). Testfall 33 jämför talet före och efter bytet |
| Påminnelsen går varje körning | Tråden fylls av samma påminnelse, och designens *"en gång, inte varje körning"* bryts | `reminded_at` som kolumn, inte som beräkning. Testfall 31 |
| Agentens text skrivs om | Kortets hela trovärdighet bygger på att `reason` är agentens ord, inte en omformulering | `reason`, `consequence` och `rationale` lagras ordagrant. Testfall 34, och `_decision_body`s egen kommentar |
| Ett beslut går tillbaka till `open` när turen havererar | Människan ombeds fatta ett beslut hon redan fattat | Svaret gavs; det var turen som föll. `FelKort` bär `Försök igen` med samma utkast-id. Testfall 30 |
| `registrera_avstaende` byggs om "medan vi ändå är här" | En klar modul refaktoreras mitt i en ny, och dokumentvägen postar i huvudboken | Verktyget står orört. Testfall 27: hela sviten grön |

## Vad som inte byggs här

All frontend — `BeslutKort`, `AlternativLista`, `AlternativRad`, `RekMarke` hör till `chattyta`.
`VerifikationsForslag` och kedjan beslut → förslag → postning → låst hör till
`flode-verifikationer`, liksom `draft`- och `receipt`-inläggen. Underlagstolkning och flöde 4:s
matchning hör till `underlagstolkning`. Lönens fyra spår är ur scope (`ANALYS.md` §2).
`age_days`-trösklarna (öppen fråga 1) — servern ger talet, färgen är `chattyta`s.
De 61 mypy-felen.
