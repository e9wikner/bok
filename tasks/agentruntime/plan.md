# Plan: modul `agentruntime`

Bygger `docs/redesign/SPEC-agentruntime.md` (fas 1 godkänd 2026-09-14, alla sex besluten i §12).
Uppgiftslistan ligger i `tasks/agentruntime/todo.md`. Beror på `idempotens`, som är klar.

## Beroendegraf

```
A1 voucher_posting (gate: flytt, inget nytt)
      │
A2 migration 024: agent_runs + agent_run_events
      │
A3 AgentRunRepository ─────────────┐
      │                            │
A4 services/llm/: protokoll,       │   (ren logik, ingen nätverkstrafik)
   modellregister, prislista,      │
   config                          │
      │                            │
      ├──→ A5 Messages-adapter     │
      │                            │
      └──→ A6 underlagsläsning     │   (pypdf, textlager, eskaleringsregeln)
              │                    │
           A7 verktygsytan ────────┘
              │
           A8 sessionen (systemprompt, verktygsloop, avståenden)
              │
              ├──→ A9 budget, kostnad, tak
              │
           A10 workern (tråd, flock, övergivna körningar, manuell start)
              │
              ├──→ A11 GET /agent/status ersätter operations/log
              │
              └──→ A12 Chat-adapter + protokollskillnaderna
                      │
                   A13 agentinstruktionerna (runtime-innehåll)
                      │
                   A14 regression och lint
```

## Ordning och varför

**A1 först, och ensam.** `api/routes/agent.py::_create_and_post_voucher` är i dag enda vägen in i
huvudboken för en agent. A1 flyttar den till `services/voucher_posting.py` utan att ändra en rad i
logiken, så att verktyget i A7 och rutten delar exakt samma kod. Samma form som T8 i `idempotens`:
en gate-uppgift utan ny funktionalitet, verifierad med hela sviten grön. Den landar för sig.

**A2–A3 är lagringen utan konsument.** Tabellerna och repositoryt kan byggas och testas isolerat.
`protocol`-kolumnen finns från början — den går inte att lägga till senare utan migration, och
utan den är `cache_read_tokens = 0` oläsbart (§5).

**A4 före båda adaptrarna.** `LLMClient`, `LLMTurn` och modellregistret är gränsen hela modulen
vilar på. Prislistan hör hit därför att §2 säger att en modell utan prisrad inte får köra — den
regeln ska finnas innan något kan köra.

**A5 före A12.** Messages-vägen är standard (§2) och den enda som har cache, dokumentblock och
egen vägrankod. Chat-vägen byggs när sessionen fungerar på den rika vägen, annars byggs sessionen
mot minsta gemensamma nämnare av misstag.

**A6 före A7.** Verktyget `hamta_underlagsfil` returnerar det A6 producerar. Eskaleringsregeln
(text → dokumentblock → avstående) är en bokföringsregel, inte en optimering, och den ska vara
testad innan ett verktyg lämnar ut innehållet.

**A7 före A8.** Sessionen anropar verktygen. Testfall 17 — att inget verktyg kan ändra eller
radera postad bokföring — hör till A7 och är den enda automatiska kontrollen av append-only genom
agentens yta.

**A9 efter A8.** Taken kontrolleras mellan underlag och mellan verktygsvarv (§6.5). Det går inte
att placera dem förrän loopen finns, och de får aldrig hamna inuti `with db.transaction():`.

**A13 sent, av samma skäl som T10.** `docs/to_agent/` är runtime-innehåll och blir bokstavligen
agentens systemprompt. Det ändras först när runtimen faktiskt gör det texten beskriver.

## Parallellt vs sekventiellt

- Sekventiellt: A1 → A2 → A3, och A4 → A5 → A6 → A7 → A8.
- Parallellt efter A8: A9 och A11 rör olika filer.
- A12 kan påbörjas när A8 är klar, men landar efter A9 så att kostnadsberäkningen finns för båda
  protokollen samtidigt.
- A14 avslutar alltid.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| A1 ändrar beteende i smyg | Postningsvägen är den som skapar oåterkalleliga fakta. En tyst ändring där syns först i huvudboken | Ren flytt, noll logikändring, hela sviten grön innan A2 påbörjas |
| Sessionen läcker protokoll | En `if provider ==` i affärslogiken gör en tredje leverantör till en omskrivning | `anthropic`/`openai` importeras bara i `services/llm/`, verifierat i test (kriterium 10) |
| Tyst cacheinvaliderare | Kostnaden tiodubblas utan att något går sönder | Testfall 14 och 15: identisk systemprompt byte för byte, `cache_read_input_tokens > 0` från underlag två |
| Textextraktion kastar om kolumner | Nettobelopp och moms byter plats → felaktig kontering som bara går att rätta med B-verifikation | Avstämningsregeln i §6.3: beloppen ordagrant i texten, netto + moms = totalen, annars eskalering. Testfall 23 |
| Modell utan prisrad | Dygnstaket kan inte räkna → säkringen är ur funktion | Passet vägrar starta. Testfall 19 |
| Två workers | Dubbelbokföring i en bok som inte kan städas | `flock`, testfall 13 — och idempotensnyckeln som andra lager |
| Budgettak mitt i en postning | Halv verifikation | Taken kontrolleras mellan underlag och varv, aldrig inuti transaktionen |

## Vad som inte byggs här

Schemaläggning (§12.3 — manuell start tills ett pass är mätt), Gemini-protokollet, trådar och SSE
(`tradar`), och den modellväljare människan klickar i (`tradar`). Runtimen tar modellen som
argument; platsen för valet kommer i nästa modul.
