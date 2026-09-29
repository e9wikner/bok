# Uppgifter: modul `lasbarhet`

Spec: `docs/redesign/SPEC-lasbarhet.md`. Varje uppgift går till en egen subagent. **Filer** är vad
uppgiften äger (§5); en uppgift som behöver röra något annat stannar och säger till. Testerna
skrivs före implementationen. Subagenterna committar inte och rör inte den här filen — huvudagenten
bockar av och committar per uppgift.

- [x] **L1 — Bara slutsvaret sparas; mellantexten nollställs i klienten** (§4.1, M1, M2)
  - Filer: `services/thread_stream.py`, `services/thread_service.py` (`_render`),
    `services/thread_session.py`, `frontend-v3/lib/chattyta/trad.ts`
  - Gjort 2026-09-29: sista stycket sparas (`thread_stream.py`); `posted`/`abstained` tappar ledtexten i `thread_session._final_paragraph_only`; postningens fallback namnger verifikationen; inflight-ögonblicksbilden töms också vid activity. `test_flode_verifikationer.py`s falska `run_tool_loop` returnerar nu ett outcome.
  - Beror på: —
- [x] **L2 — Instruktionen: att skriva i en tråd** (§4.2, M3)
  - Filer: `docs/to_agent/03_bokforingsinstruktion.md`, `tests/test_agent_entrypoint.py`
  - Gjort 2026-09-29: stycket "Att skriva i en tråd"; regel 1 (en mening), 2 ("säg att du läser den" bort), 5 och 9 justerade. Rapporterat: "människan" i `agent_tools.py` och `02_bokforingsprocess.md` → L6.
  - Beror på: —
- [x] **L3 — Spår-chippen bort; presensetiketter för alla verktyg** (§4.3, M4)
  - Filer: `frontend-v3/components/chattyta/{TradInlagg,TradRenderare,FelKort}.tsx`,
    `frontend-v3/lib/chattyta/etiketter.ts`, `services/thread_service.py` (`_TRACE_LABELS`)
  - Gjort 2026-09-29: chippen och "Visa vad som hände" borta; 13 verktyg i båda etikettabellerna, testade mot verktygslistan. Avvikelse: kvittots "{n} kvar" och "kompletteringsflagga satt" syns inte längre (kom bara som spår).
  - Beror på: —
- [ ] **L4 — Agentens text som markdown** (§4.4, M5)
  - Filer: `frontend-v3/components/chattyta/TradInlagg.tsx`, `frontend-v3/package.json`,
    `frontend-v3/package-lock.json`
  - Beror på: L3
- [x] **L5 — Postade verifikationer sida för sida vid skroll** (§4.5, M6)
  - Filer: `frontend-v3/hooks/useVyer.ts`, `frontend-v3/lib/skal/bocker.ts`,
    `frontend-v3/lib/skal/vydata.ts`, `frontend-v3/components/skal/VyInnehall.tsx`
  - Gjort 2026-09-29: `useInfiniteQuery`, vakt i `VyInnehall`, `slaSamman`/`nastaSida` i `bocker.ts`. Obs: `utkastIVyn`/`verifikationIVyn` hoppar över den sidade cachen — ofarligt, utkast och saknar ligger i egna frågor.
  - Beror på: —
- [ ] **L6 — "användaren" i stället för "människan" i det agenten läser; fältlängder i `be_om_beslut`** (§4.2, M3)
  - Filer: `services/agent_tools.py` (beskrivningar och docstrings), `docs/to_agent/02_bokforingsprocess.md`
  - Beror på: L2
