# Plan: modul `oversikt`

Bygger `docs/redesign/SPEC-oversikt.md` (fas 1, skriven 2026-09-21). Uppgiftslistan ligger i
`tasks/oversikt/todo.md`. Beror på ingenting. `skal` beror på den här.

## Beroendegraf

```
O1 laga _check_missing_attachments (gate: buggfix, ingen ny yta)
      │
O2 missing_attachment + age_days, härledda, joinade i sidfrågan
      │
O3 ?missing_attachment=true&sort_by=age
      │
O4 GET /api/v1/overview
      │
O5 regression och lint
```

Rak kedja. Ingenting går parallellt — modulen är fem uppgifter lång.

## Ordning och varför

**O1 först, och ensam.** `_check_missing_attachments` joinar mot `voucher_attachments`, en tabell
som inte finns, och sväljer felet med `except Exception: pass`. Kontrollen har aldrig producerat
en issue. Allt annat i modulen handlar om samma predikat — det ska vara lagat och testat innan
något byggs ovanpå det. `ANALYS.md` §5 rad 6 ("logiken finns redan") rättas i samma svep.

**O2 före O3.** Fältet innan filtret. `missing_attachment` och `age_days` är härledda värden på
verifikationen; när de finns och är testade är filtret ett `WHERE`-villkor och sorteringen en rad
i en vitlista. Tvärtom ordning betyder att filtret testas mot ett fält som inte finns än.

**Härlett, inte lagrat — och det är inte en genväg.** Migration 014 avbryter varje `UPDATE` på en
postad verifikation. Datakontraktets "satt när den postas utan underlag, borta när ett underlag
kopplas" är ordagrant definitionen av `NOT EXISTS (SELECT 1 FROM attachments …)`. En kolumn hade
krävt att triggern mjukades upp. Det är därför modulen inte har någon migration alls.

**O4 sist av de byggande.** `/overview` konsumerar `missing_attachments` från O2/O3. Den låser
också payloadformen som `beslut` senare ska fylla `open_decisions` i, utan att ändra formen.

## Parallellt vs sekventiellt

Sekventiellt hela vägen. Vill man dela upp arbetet är den enda meningsfulla snittet O1–O3
(verifikationen) mot O4 (aggregatet), och då måste O4 ändå vänta på O2.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| N+1 fördjupas | `list_all` hämtar redan bara `id` och gör `get()` per rad. Två härledda fält hämtade per rad gör en listvy långsammare för varje verifikation bolaget bokför | Joinat i sidfrågan. Testfall 15 räknar `db.execute`-anrop, inte sekunder |
| `missing_attachment` ignoreras tyst i `period_id`-grenen | En vy som ber om "saknar underlag" får allt tillbaka, och en människa fattar beslut på fel lista | Samma beteende i båda grenarna, eller `400`. Testfall 8 |
| Kolumn i stället för härlett värde | Någon undantar kolumnen i triggerns `WHEN` — append-only blir en fråga om vilken kolumn man råkar röra | Spec §3 och kriterium 7: ingen migration i modulen. En kolumn kräver att frågan ställs först |
| `open_decisions` tas för en riktig siffra | `beslut` byggs mot en approximation och ärver den | Approximationen står som approximation i koden, med den slutliga hemvisten namngiven i kommentaren |
| O1 avslöjar hundratals issues | Kontrollen har varit tyst sedan den skrevs; första riktiga körningen kan ge en vägg av varningar | Det är rätt utfall, inte ett fel. Men det ska nämnas för beställaren innan det syns i gränssnittet |

## Vad som inte byggs här

`GET /decisions` (`beslut`), lönens fyra spår (ur scope), någon frontend, någon persistent flagga,
och trösklarna som gör `age_days` gult eller rött (designbeslut som inte är taget — servern
skickar bara talet).
