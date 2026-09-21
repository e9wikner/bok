# Uppgiftslistor per modul

En katalog per modul i kapabilitetskartan (`docs/redesign/ANALYS.md` §8), med samma två filer:

- `plan.md` — beroendegraf, ordning och varför, risker.
- `todo.md` — uppgifterna, avbockade allteftersom, med vad som faktiskt gjordes och vad som
  avvek från specen.

| Modul | Spec | Läge |
|---|---|---|
| `idempotens` | `docs/redesign/SPEC-idempotens.md` | **Klar** 2026-09-14 (T1–T11) |
| `agentruntime` | `docs/redesign/SPEC-agentruntime.md` | **Klar** (A1–A14) |
| `oversikt` | `docs/redesign/SPEC-oversikt.md` | Fas 1, O1–O5 skrivna 2026-09-21, ingen kod |
| `tradar` | `docs/redesign/SPEC-tradar.md` | Fas 1, T1–T14 skrivna 2026-09-21, ingen kod |

Listorna sparas när en modul är klar. De bär besluten och avvikelserna — varför en uppgift rörde
en fil till än den skulle, vad som lämnades kvar — och det är det enda stället den historiken
finns utanför commit-meddelandena.
