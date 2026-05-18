---
status: resolved
trigger: "Agentinstruktioner är tomma i frontend. I Översikt så visas 5 verifikationsutkast, men när man klickar på länken så ser man inga utkast. Periodens läge har en formattering som gör att texten inte är läsbar. Intag har inga konton i Bankfil. Knappar för att välja fil har fel språk och ser inte ut att gå att klicka på med den konstiga färgen. Räkenskapsår som löper över fler än ett kalenderår visar bara det första kalenderåret, exempelvis 2010 syns endast för 2010-2011."
created: 2026-05-18
updated: 2026-05-18
---

# Symptoms

- Expected behavior: Agentinstruktioner ska visa instruktionstext, verifikationsutkast i översikten ska leda till motsvarande lista, periodkort ska vara läsbara, bankfilsuppladdning ska ha valbara konton, filväljare ska vara svenska och tydligt klickbara, och räkenskapsår ska visas som hela intervall.
- Actual behavior: Instruktionssidan blir tom, verifikationsutkast visar antal men ingen lista efter klick, periodkortens siffror flyter ihop, bankkonto-dropdown är tom, native file input visar "Choose File", och räkenskapsår visas bara som första året.
- Error messages: Inga explicita felmeddelanden rapporterade.
- Timeline: Rapporterat i nuvarande frontend.
- Reproduction: Öppna `Översikt`, `Intag`, `Agentinstruktioner` och sidor med räkenskapsårsval.

# Current Focus

- hypothesis: Frontend antar fel API-form på agentinstruktioner, översikten räknar/filtrerar verifikationsutkast inkonsekvent, native filinputs och räkenskapsårslabeler är ofärdiga, och bankfilsvyn kräver bank_connections utan fallback för lokala konton.
- test: Läs frontend/API-kontrakt, patcha rendering och fallback-beteenden, kör riktade tester och frontend-build.
- expecting: UI visar rätt data, navigering/filter matchar dashboarden, bankfil får valbara alternativ, och räkenskapsår renderas som intervall.
- next_action: resolved and archived after frontend build plus targeted backend/frontend regression tests
