# Plan: modul `idempotens`

Bygger `docs/redesign/SPEC-idempotens.md` (fas 1 godkänd 2026-09-12, alla beslut i §12).
Uppgiftslistan ligger i `tasks/todo.md`.

## Beroendegraf

```
T1 migration 023
      │
T2 IdempotencyRepository ──┐
      │                    │
T3 IdempotencyService      │   (ren logik: fingerprint, reservera, spela upp)
      │                    │
T4 api/deps.py: header ────┘
      │
      ├──→ T5 POST /agent/vouchers kopplas på        ← hålet stängs här
      │
      ├──→ T6 POST /vouchers/{id}/post: 400 → 409
      │
      ├──→ T7 periods: period_locked 409 + locked_by  (behöver T1)
      │
      └──→ T8 _commit genom korrigeringskedjan
                   │
              T9 POST /vouchers/{id}/correct kopplas på
                   │
              T10 docs/to_agent + entrypoint-test     (kräver T5)
                   │
              T11 regression + lint
```

## Ordning och varför

**T1 först** därför att allt annat skriver mot tabellen. Migrationen bär både `idempotency_keys`
och `periods.locked_by` — samma fil, för att T7 annars behöver en egen migration för en kolumn.

**T2–T4 är mekanismen utan konsument.** De kan byggas och testas isolerat; ingen rutt ändrar
beteende förrän T5. Det gör T5 till den enda uppgift där hålet faktiskt stängs, och den enda
som måste verifieras med trådtest.

**T5 före T6–T7** därför att `/agent/vouchers` är hålet. `/post` och `period_locked` är
statusmappningar som förbättrar klientupplevelsen men inte förorenar huvudboken om de dröjer.

**T8 är en gate för T9.** Korrigeringskedjan går inte att köra i en transaktion i dag (§12.4).
Den ändringen rör en kodväg fem testfiler använder, så den landar och verifieras *ensam* innan
nyckeln hängs på i T9.

**T10 sist av funktionaliteten** därför att `docs/to_agent/` är runtime-innehåll. Det ska inte
ändras förrän rutten faktiskt accepterar headern det beskriver — annars beskriver systemets egna
instruktioner något som inte finns.

## Parallellt vs sekventiellt

- Sekventiellt: T1 → T2 → T3 → T4 → T5, och T8 → T9.
- Parallellt efter T4: T6, T7 och T8 rör olika filer och kan tas i vilken ordning som helst.
- T11 avslutar alltid.

## Risker

| Risk | Utfall om den slår in | Motmedel |
|---|---|---|
| Reservationen commitas i samma transaktion som verifikationen | Parallella anrop ser inte varandra; hålet står öppet trots modulen | Reservationen commitas direkt (§6), T5 verifieras med 10 trådar |
| Nyckelraden commitas *efter* verifikationen | Exakt det fönster modulen ska stänga | Testfall 6: transaktionen kastar efter postning, båda raderna ska vara borta |
| `_commit`-genomtrådningen i T8 bryter befintlig korrigering | `test_correction_notes.py`, `test_ledger.py` m.fl. faller | Default `_commit=True` överallt, full svit körs i T8 innan T9 påbörjas |
| `docs/to_agent/`-ändringen bryter `test_agent_entrypoint.py` | Systemets instruktionsinnehåll och dess test glider isär | T10 uppdaterar testet medvetet i samma commit, aldrig genom att lätta assertionen |
| Trådtest delar en SQLite-connection | Falskt grönt eller sporadiskt rött | Anslutningarna är trådlokala (`db/database.py:31`); testet får inte skicka en connection mellan trådar |

## Verifieringspunkter

- Efter T4: `pytest tests/test_idempotency.py -v` grön på fingerprint- och uppspelningstesterna,
  utan att någon rutt ändrats.
- Efter T5: testfall 1–6 gröna. **Hålet är stängt här** — allt efter detta är förbättringar.
- Efter T8: hela `tests/` grön *utan* nya funktioner. Ren regressionsgate.
- Efter T11: `black . && isort . && flake8 && mypy .`, och jobboutputen läst — inte bocken
  (CI kör allt med `continue-on-error: true`).
