# Plan: modul `tradar`

Bygger `docs/redesign/SPEC-tradar.md` (fas 1, skriven 2026-09-21, besluten i §12).
Uppgiftslistan ligger i `tasks/tradar/todo.md`. Beror på `agentruntime`, som är klar.

## Beroendegraf

```
T1 migration 025: threads + thread_posts
      │
T2 ThreadRepository ──────────────┐
      │                           │
T3 since_seq på list_events       │   (liten, oberoende av T1/T2)
                                  │
T4 bryt ut verktygsloopen         │   (gate: ren refaktorering, noll ny funktionalitet)
      │                           │
T5 strömningshook på LLMClient    │   (on_text, on_tool_call — Messages strömmar redan)
      │                           │
T6 trådsessionen ─────────────────┘   (andra ingången: meddelande i stället för underlag)
      │
T7 runtimens händelser → inlägg
      │
T8 GET /threads/{view_key} + POST /messages
      │
T9 GET /threads/{view_key}/stream (SSE)
      │
      ├──→ T10 view.changed
      │
      ├──→ T11 modell per tråd
      │
      └──→ T12 GET /agent/status: state, since, current_task, paused_reason
                  │
               T13 agentinstruktionerna (runtime-innehåll — bara om beteendet ändrats)
                  │
               T14 regression och lint
```

## Ordning och varför

**T1–T3 är lagring utan konsument.** Tabellerna, repositoryt och markören kan byggas och testas
isolerat. `UNIQUE (view_key, fiscal_year_id)` finns från början — det är beslutet "en tråd per
räkenskapsår" (§12.3) skrivet i schemat, och det går inte att lägga till senare utan migration.
`CHECK` på `type` finns av samma skäl: de åtta inläggstyperna är ett kontrakt mot klienten, och
en nionde som smyger in är en renderare som tyst faller igenom.

**T4 är en gate, som A1 i `agentruntime`.** `run_session` är dokumentformad: den kräver
`IntakeSource` + `file_bytes`, och ett blankt `stop == "end"` — vilket är precis vad ett
samtalssvar är — returnerar `agent_no_outcome`. Loopen bryts ut till en generisk form som tar en
**terminalpolicy**; dokumentvägen behåller sin policy byte för byte. Ren refaktorering, noll
logikändring, hela sviten grön innan T5 påbörjas. Dokumentvägen är den som skapar oåterkalleliga
fakta — en tyst ändring där syns först i huvudboken.

**T5 före T6.** Strömningshooken är det `agentruntime` medvetet inte byggde: A10 kunde inte
rapportera verktygsnamn eftersom loopen saknade en hook, och `current_activity` blev grov med
avsikt. Messages-adaptern gör redan `.stream()` och kastar inkrementen i `get_final_message()` —
hooken plockar upp något som finns. Byggs den efter sessionen får sessionen en form som inte kan
strömma, och T9 blir en omskrivning.

**T6 före T7.** Sessionen producerar utfallet; mappningen händelse → inlägg konsumerar det.
`agentruntime` §1:s gräns gäller: runtimen producerar händelser och utfall, `tradar` bestämmer
hur de visas. Ingen `thread_id` går ned i runtimen.

**T8 före T9.** Rutterna först, strömmen sedan. En tråd ska gå att läsa och skriva till innan den
går att lyssna på; annars går det inte att felsöka strömmen mot något känt.

**T13 sent, av samma skäl som A13.** `docs/to_agent/` är runtime-innehåll och bokstavligen
agentens systemprompt. Den ändras bara om trådvägen faktiskt ändrar vad agenten *gör* — och
frågan ställs först (§8).

## Parallellt vs sekventiellt

- Sekventiellt: T1 → T2, och T4 → T5 → T6 → T7 → T8 → T9.
- T3 kan göras när som helst före T9; den är liten och rör en annan fil.
- Parallellt efter T9: T10, T11 och T12 rör olika filer.
- T14 avslutar alltid.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| T4 ändrar beteende i smyg | Dokumentvägen postar i huvudboken. En tyst ändring där upptäcks av en revisor, inte av ett test | Ren utbrytning, noll logikändring, hela sviten grön innan T5. Testfall 7 och 8 |
| Ett bekvämt trådverktyg | Append-only-regelns enda automatiska kontroll genom agentens yta faller | Verktygsytan utökas inte. Testfall 14 = testfall 17 i `agentruntime`, kört mot trådvägen |
| Trådsvar postar dubbelt | Append-only kan inte städas — det kräver en B-verifikation | Egen namnrymd `thread:{thread_id}:{post_id}`, hängd på användarinlägget och inte på tiden. `services/voucher_posting.py` är fortfarande enda skrivvägen. Testfall 15 |
| Två skrivare delar ett `run_id` | `add_event` allokerar `seq` läs-sedan-skriv på en dokumenterad enskrivarpremiss. `UNIQUE (run_id, seq)` fångar brottet — men som ett fel mitt i ett svar | En `agent_runs`-rad per trådkörning, aldrig delad. Testfall 21 |
| SSE delar en SQLite-anslutning över trådgränser | `db/database.py` är trådlokal med WAL. En delad anslutning är ett trasigt läge som inte alltid kraschar | Sessionen kör i sin egen arbetstråd; kön bär bara serialiserade händelser, aldrig en rad eller en anslutning |
| Flocken blockerar tråden | En människa kan inte skriva medan intagspasset kör — fel produkt | Flocken vaktar intag-passet, inte varje LLM-anrop. Testfall 22 |
| Hela tråden in i kontexten | Kostnaden växer obegränsat tills dygnstaket slår i av sig självt, och det ser ut som en bugg | Token-budgeterat fönster inom räkenskapsårets tråd (§6.3). Testfall 13 |
| En sammanfattning blir bokföringsunderlag | En LLM-sammanfattning av tidigare samtal som ligger till grund för en postning är andrahandstext i något som liknar en revisionshistorik | Det som inte ryms **utelämnas**, det sammanfattas aldrig. Testfall 13 |
| Base64 i ett inlägg | Tråden sväller, och dokumentinnehåll hamnar i en tabell som inte är byggd för det | `_compact_tool_result`-precedensen gäller inlägg också. Testfall 17 |
| Deltan lagras per tecken | `thread_posts` blir en teckenlogg i stället för en tråd | Ett `agent_text` skrivs en gång, när turen är klar. Deltan går bara över strömmen |

## Vad som inte byggs här

`GET /decisions` och `POST /decisions/{id}/answer` (`beslut`) — tråden *bär* ett
`decision`-inlägg, men listan och svarsvägen via knapp hör till nästa modul. Tröskeln för
beslutskort kontra val (designens öppna fråga 3). All frontend. `underlagstolkning`.
De 61 mypy-felen.
