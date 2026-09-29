# Uppgifter: modul `lasbarhet`

Spec: `docs/redesign/SPEC-lasbarhet.md`. Varje uppgift går till en egen subagent. **Filer** är vad
uppgiften äger (§5); en uppgift som behöver röra något annat stannar och säger till. Testerna
skrivs före implementationen. Subagenterna committar inte och rör inte den här filen — huvudagenten
bockar av och committar per uppgift.

- [ ] **L1 — Bara slutsvaret sparas; mellantexten nollställs i klienten** (§4.1, M1, M2)
  - Filer: `services/thread_stream.py`, `services/thread_service.py` (`_render`),
    `services/thread_session.py`, `frontend-v3/lib/chattyta/trad.ts`
  - Beror på: —
- [ ] **L2 — Instruktionen: att skriva i en tråd** (§4.2, M3)
  - Filer: `docs/to_agent/03_bokforingsinstruktion.md`, `tests/test_agent_entrypoint.py`
  - Beror på: —
- [ ] **L3 — Spår-chippen bort; presensetiketter för alla verktyg** (§4.3, M4)
  - Filer: `frontend-v3/components/chattyta/{TradInlagg,TradRenderare,FelKort}.tsx`,
    `frontend-v3/lib/chattyta/etiketter.ts`, `services/thread_service.py` (`_TRACE_LABELS`)
  - Beror på: —
- [ ] **L4 — Agentens text som markdown** (§4.4, M5)
  - Filer: `frontend-v3/components/chattyta/TradInlagg.tsx`, `frontend-v3/package.json`,
    `frontend-v3/package-lock.json`
  - Beror på: L3
- [ ] **L5 — Postade verifikationer sida för sida vid skroll** (§4.5, M6)
  - Filer: `frontend-v3/hooks/useVyer.ts`, `frontend-v3/lib/skal/bocker.ts`,
    `frontend-v3/lib/skal/vydata.ts`, `frontend-v3/components/skal/VyInnehall.tsx`
  - Beror på: —
