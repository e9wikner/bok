# Plan: modul `flode-verifikationer`

Bygger `docs/redesign/SPEC-flode-verifikationer.md` (fas 1, godkänd 2026-09-23, besluten i §12
och §4.4). Uppgiftslistan ligger i `tasks/flode-verifikationer/todo.md`. Beror på `chattyta`,
och genom den på alla tidigare moduler, som alla är klara. `flode-underlag` beror på den här.
Modulen stänger första leveransen.

Modulen har tre spår som möts i postningsroutens två krokar:

- **Numreringen** (F1–F4): utkast utan nummer, och numret sätts vid postning.
- **Förslaget och kvittot** (F5–F10): verktyget, kopplingen, kvittot, felen och räknaren.
- **Korrigeringen** (F11–F12): samma förslag med `correction_of`.

Klienten (F13–F14) kommer sist, eftersom den bara läser det de tre spåren skriver.

## Beroendegraf

```
F1 migration 027: vouchers byggs om, number nullbar        (gate 1: schemat före koden)
      │
      ▼
F2 numret sätts vid postning                                (gate 2: numreringen före förslagen)
      │
      ├──► F3 number: Optional i backenden + luckkontrollen per år
      │          │
      │          ▼
      │     F4 klienten: ett utkast utan nummer
      │
      ▼
F5 migration 028: thread_drafts + repository
      │
      ▼
F6 foresla_verifikation (vanligt förslag) ──► F7 verktygslistan + docs/to_agent
      │
      ├──► F8 postningens krokar: on_posting i transaktionen, kvittot efter
      │          │
      │          ├──► F9 felen: error-inlägget, ett per utkast och kod
      │          │
      │          └──► F10 GET /drafts + count_waiting + overview
      │
      └──► F11 korrigeringsförslaget (correction_of, målperiod, kontroller)
                 │
                 ▼  (kräver F8)
            F12 rättelsens postning: historik och notering i transaktionen
                 │
F10 ────────────►├──► F13 förslagskortets lägen ur GET /drafts
                 │
                 └──► F14 vyn: sektionerna, optimistiska raden, rättad av/rättar
                            │
                            ▼
                       F15 hela flödet, regression, omstart med SIE4, modulen stängd
```

## Ordning och varför

**F1 först, och F1 är modulens första gate.** Allt i modulen står på att ett utkast kan sakna
nummer, och schemat säger i dag att det inte kan det. Migrationen är också det enda i modulen som
rör tabellen som append-only vilar på. Den ska vara bevisad (testfall 1–4) innan en rad kod
räknar med den. Att beställaren kan börja om och importera SIE4-filerna igen (spec §4.4) gör en
misslyckad driftsättning billig. Det gör inte en felaktig migration mindre fel: triggrarna måste
fortfarande stå kvar efteråt, och det är testerna som visar det, inte en omimport.

**F2 före allt som skapar utkast, och F2 är den andra gaten.** Byggs `foresla_verifikation`
innan numret flyttats, får varje förslag ett nummer. Testerna för F6 skulle då skrivas mot fel
beteende och skrivas om i F2. Numreringen är dessutom den ändring som rör flest befintliga vägar
(importen, korrigeringarna, IB, fakturornas och lönernas bokning). Den ska vara grön mot hela
`pytest tests/` innan något nytt läggs ovanpå.

**F3 och F4 direkt efter F2**, eftersom `number: None` annars ger `TypeError` och tomma rubriker
i de gamla sidorna. F3 lagar också luckkontrollen. Den kontrollen är det som ska bekräfta att
omstarten i F15 gav en obruten serie, och den kan inte bekräfta något så länge den missar luckor
över räkenskapsår.

**F5 före F6.** Förslaget skrivs i en transaktion tillsammans med sin rad i `thread_drafts`
(spec §5.1). Tabellen och repositoryt måste finnas och vara testade först.

**F6 före F11.** Korrigeringen är samma verktyg med ett fält till. Byggs det vanliga förslaget
först, blir F11 en gren i en funktion som redan fungerar, och inte två vägar som byggs samtidigt.

**F7 direkt efter F6**, som egen uppgift. `docs/to_agent/` är runtime-innehåll med egna tester
(`test_agent_entrypoint.py`), och verktygslistans ordning är en del av det cachade prefixet. Båda
är lätta att bryta i förbifarten och ska bytas i en commit som bara gör det.

**F8 före F9, F10 och F12.** Postningsroutens två krokar (`on_posting` i transaktionen,
`on_posted` efter commit) är stället där kvitto, fel, räknare och korrigeringshistorik hänger.
Krokarna byggs en gång, med kvittot som första användare. De andra hakar på.

**F11 kan byggas parallellt med F8–F10**, men **F12 kräver F8**, eftersom rättelsens historik
skrivs i `on_posting`.

**F13 och F14 sist.** Klienten läser bara det backenden redan skriver: `GET /drafts`, nummer som
kan vara `null`, `rättad av`. Byggs klienten först, byggs den mot fixturer som kan glida.

**F15 stänger**, och omstarten med SIE4-filerna hör dit. Det är den enda verifieringen mot
riktiga data som finns för numreringen.

## Parallellt vs sekventiellt

- Sekventiellt: F1 → F2 → F5 → F6 → F8, och F11 → F12.
- Efter F2: `F3 ‖ F5`. F4 efter F3.
- Efter F6: `F7 ‖ F8 ‖ F11`.
- Efter F8: `F9 ‖ F10`, och F12 när F11 är klar.
- Efter F10 och F12: `F13 ‖ F14`.
- F15 avslutar alltid.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| Migrationen tappar en trigger | Postade verifikationer kan ändras tyst, och det märks inte förrän någon gör det | Triggrarna återskapas ordagrant ur 014; testfall 4 försöker ändra och radera postat, och postade rader, efter migrationen |
| `DROP TABLE vouchers` stoppas av `prevent_delete_posted_vouchers` | Migrationen går inte att köra | Testfall 3 visar beteendet i stället för att anta det. Faller det: droppa triggrarna först, i samma transaktion, och återskapa dem |
| Kolumnlistan i `vouchers_new` följer 001 i stället för det faktiska schemat | Kolumner från senare migrationer försvinner | F1 börjar med `PRAGMA table_info(vouchers)` och `grep "ALTER TABLE vouchers"`; testfall 1 jämför varje kolumn |
| `number=None` når kod som formaterar `f"{number:06d}"` | `TypeError` i en rapport, en export eller en gammal sida | F3 greppar varje `.number` i backenden; F4 varje `number` i klienten. `sie4_export` läser bara postade, men testas ändå |
| Numret sätts utanför postningens transaktion | Två samtidiga postningar får samma nummer, eller ett nummer förbrukas av en postning som rullas tillbaka | `UPDATE … SET status, posted_at, number … WHERE status='draft'` i ett uttryck; `UNIQUE` som sista skydd; testfall 28 och 38 kräver att inget nummer förbrukas vid fel |
| SIE4-importen tappar filens nummer | Omstarten i F15 ger en annan serie än filerna | Testfall 10 i F2; F15 jämför importerade nummer mot filen |
| Kvittot skrivs i postningens transaktion "för enkelhetens skull" | Ett fel i trådlagret rullar tillbaka en verifikation | Spec §8.1 och §15; testfall 25 får kvittot att fallera och kräver att postningen står kvar |
| Korrigeringshistoriken skrivs efter commit "för symmetrins skull" | En postad rättelse utan historik | Testfall 38 får historiken att fallera och kräver att hela postningen rullas tillbaka |
| Agenten räknar återföringen själv | En rättelse som inte återför originalet exakt | Verktyget tar bara de rättade raderna; servern bygger återföringen (spec §7.1); testfall 32 |
| Verktygslistan ändrar ordning | Det cachade prefixet slutar träffa, och kostnaden stiger tyst | F7 lägger till sist och ändrar ingenting annat; testfall 22 |
| `las_korrigeringar` får ett nytt argument | Verktygsschemat ändras och prefixet slutar träffa | F12 utökar bara *svaret* med öppna noteringar när `voucher_id` ges. Argumenten rörs inte |
| `count_waiting` räknar ett beslut och dess förslag två gånger | Headern säger 2 när vyn visar 1 | Testfall 31, med beslut + förslag + ersatt förslag + rättelse i samma databas |
| Ett trådutkast visas både under Väntar och under Utkast | Samma händelse två gånger i vyn | Testfall 45 |

## Vad som inte byggs här

Faktura- och löneförslag. Banderollens text. `Agenten postar` i headern vid en knapptryckning.
Korrigering över ett räkenskapsårsskifte. Äldre räkenskapsårs trådar. Modellväljaren. Borttagning
av de gamla sidorna för korrigeringsnoteringar, som tas bort vy för vy enligt `SPEC-skal.md` §3.
