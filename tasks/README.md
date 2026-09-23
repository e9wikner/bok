# Uppgiftslistor per modul

En katalog per modul i kapabilitetskartan (`docs/redesign/ANALYS.md` §8), med samma två filer:

- `plan.md` — beroendegraf, ordning och varför, risker.
- `todo.md` — uppgifterna, avbockade allteftersom, med vad som faktiskt gjordes och vad som
  avvek från specen.

| Modul | Spec | Läge |
|---|---|---|
| `idempotens` | `docs/redesign/SPEC-idempotens.md` | **Klar** 2026-09-14 (T1–T11) |
| `agentruntime` | `docs/redesign/SPEC-agentruntime.md` | **Klar** (A1–A14) |
| `oversikt` | `docs/redesign/SPEC-oversikt.md` | **Klar** 2026-09-21 (O1–O5) |
| `tradar` | `docs/redesign/SPEC-tradar.md` | **Klar** 2026-09-21 (T1–T14) |
| `skal` | `docs/redesign/SPEC-skal.md` | **Klar** 2026-09-21 (S1–S13) |
| `beslut` | `docs/redesign/SPEC-beslut.md` | **Klar** 2026-09-22 (B1–B12) |
| `chattyta` | `docs/redesign/SPEC-chattyta.md` | Specad 2026-09-23 (C1–C14), ej påbörjad |

Listorna sparas när en modul är klar. De bär besluten och avvikelserna — varför en uppgift rörde
en fil till än den skulle, vad som lämnades kvar — och det är det enda stället den historiken
finns utanför commit-meddelandena.
