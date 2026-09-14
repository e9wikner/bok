# Uppgifter: modul `idempotens`

Spec: `docs/redesign/SPEC-idempotens.md` · Plan: `tasks/plan.md`
Testerna skrivs **före** implementationen (§9). Ingen uppgift rör mer än 5 filer.

---

- [x] **T1 — Migration 023: nyckeltabell och `periods.locked_by`**
  - Acceptans: `idempotency_keys` finns med `PRIMARY KEY (key, endpoint)` och
    `CHECK (state IN ('in_flight','completed'))`. `periods.locked_by` finns och är backfillad från
    `audit_log` (`entity_type='period' AND action='locked'`); saknas raden blir värdet `NULL`.
  - Verifiera: `python main.py --init-db` mot ny DB **och** mot en kopia av en befintlig DB.
    `sqlite3 bok.db ".schema idempotency_keys"`.
  - Filer: `db/migrations/023_add_idempotency_and_lock_actor.sql`
  - Obs: ny fil. Redigera aldrig 001–022.

- [x] **T2 — `IdempotencyRepository`**
  - Acceptans: `reserve` (commitar direkt, returnerar `False` vid `IntegrityError`), `get`,
    `complete` (`_commit`-flagga, default `True`). All SQL här, ingen någon annanstans.
  - Verifiera: `pytest tests/test_idempotency.py -v` — reservation, dubbelreservation, complete.
  - Filer: `repositories/idempotency_repo.py`, `tests/test_idempotency.py`

- [x] **T3 — `IdempotencyService`: fingerprint och uppspelning**
  - Acceptans: sha256 över kanoniserad JSON (sorterade nycklar, inga blanksteg, UTF-8); `actor`
    ingår inte. Beslutslogiken i §6 steg 2 returnerar *domänutfall*, inte HTTP — inga
    HTTP-begrepp i `services/`.
  - Verifiera: testfall 2, 4 och 5 (ändrad body, olika nycklar, annan endpoint) gröna.
  - Filer: `services/idempotency.py`, `tests/test_idempotency.py`
  - Obs: testfall 4 ska ge **två** verifikationer. Det är inte en bugg — idempotens är inte
    dubblettdetektering.

- [x] **T4 — Header-dependency**
  - Acceptans: `Idempotency-Key` läses som valfri header och valideras som UUID; saknas den
    returneras `None` och loggas `idempotency_key_missing`. Ingen rutt ändrar beteende ännu.
  - Verifiera: `pytest tests/test_idempotency.py -v` grön; `pytest tests/ -v` oförändrad.
  - Filer: `api/deps.py`, `tests/test_idempotency.py`

- [x] **T5 — `POST /agent/vouchers` kopplas på  ← hålet stängs här**
  - Acceptans: reservationen commitas före arbetet; `complete` körs med `_commit=False` inuti det
    befintliga `with db.transaction():` (`api/routes/agent.py:87`). Uppspelat svar bär
    `Idempotent-Replay: true`. Utan header: gammal väg (beslut §12.1(c)).
  - Verifiera: testfall 1, 3 och 6. Tio trådar med samma nyckel → **en** rad i `vouchers`.
    Testfall 6: låt transaktionen kasta efter postning, verifiera att *både* verifikation och
    nyckelrad är borta.
  - Filer: `api/routes/agent.py`, `tests/test_idempotency.py`
  - Obs: trådtestet får inte dela en connection mellan trådarna.

- [x] **T6 — `POST /vouchers/{id}/post`: `already_posted` 400 → 409**
  - Acceptans: 409 med `detail.code = "already_posted"` och hela verifikationen i `detail.voucher`.
    `domain/validation.py` orört — bara mappningen i rutten.
  - Verifiera: testfall 7.
  - Filer: `api/routes/vouchers.py`, `tests/test_idempotency.py`
  - Obs: verifierat i §12.3 att ingen konsument läser 400 här.
  - Utfört: mappningen ligger i `_posting_http_error`, som tar båda konfliktkoderna (T6 och T7)
    och lämnar allt annat på 400. Ett extra test håller `voucher_not_found` kvar på 400, så
    statusbytet inte tyst breddas till nästa felkod.

- [ ] **T7 — `period_locked`: 409 med vem och när**
  - Acceptans: 409 med `locked_at`, `locked_by` och `period_id`. Saknas `locked_by` svarar API:t
    `"okänd"` — ingen gissning, ingen krasch. Låsningen skriver `locked_by` framåt.
  - Verifiera: testfall 8 och 9.
  - Filer: `api/routes/periods.py`, `api/routes/vouchers.py`, `repositories/period_repo.py`,
    `tests/test_idempotency.py`

- [ ] **T8 — `_commit` genom korrigeringskedjan (gate för T9)**
  - Acceptans: `VoucherRepository.create_correction` får `_commit: bool = True`;
    `services/ledger.create_correction` och `create_posted_correction` trådar flaggan vidare till
    `add_row`, `post`, `audit.log` och `AccountingCorrectionRepository.create`. Beteendet vid
    default är bit för bit oförändrat.
  - Verifiera: **hela** `pytest tests/ -v` grön utan ny funktionalitet. Särskilt
    `test_ledger.py`, `test_correction_notes.py`, `test_agent_accounting_workflow.py`.
  - Filer: `repositories/voucher_repo.py`, `services/ledger.py`
  - Obs: ingen annan ändring i korrigeringskedjan (§10 "fråga först"). Landas ensam.

- [ ] **T9 — `POST /vouchers/{id}/correct` kopplas på**
  - Acceptans: rutten tar `Idempotency-Key`; B-verifikation, `accounting_corrections`-rad och
    nyckelrad commitas i ett enda `with db.transaction():`.
  - Verifiera: testfall 10 och 11 — samma nyckel två gånger ger en B-verifikation; avbrott
    mitt i lämnar ingen av de tre raderna kvar.
  - Filer: `api/routes/vouchers.py`, `services/ledger.py`, `tests/test_idempotency.py`

- [x] **T10 — Nyckelkravet i agentinstruktionerna**
  - Acceptans: `docs/to_agent/02_bokforingsprocess.md` beskriver `Idempotency-Key` som krav vid
    postning, med samma nyckel vid omförsök. `tests/test_agent_entrypoint.py` uppdateras medvetet.
  - Verifiera: testfall 12, `pytest tests/test_agent_entrypoint.py -v`.
  - Filer: `docs/to_agent/02_bokforingsprocess.md`, `tests/test_agent_entrypoint.py`,
    `api/routes/agent_instructions.py`
  - Obs: **runtime-innehåll**, inte dokumentation — serveras av
    `repositories/system_instructions.py`. Assertionen ska uppdateras, aldrig lättas.
  - Utfört: doc fick avsnittet "Idempotensnyckel" (en händelse–en nyckel, omförsök med samma
    nyckel, tabell över `201` / uppspelning / `422 idempotency_key_reuse` /
    `409 request_in_flight` / `400 invalid_idempotency_key`).
    **Tredje filen tillkom med avsikt:** entrypointen (`/agent-instructions/entrypoint`) påstod
    `"Durable idempotency for agent operations is not implemented."` — nu falskt och serverat till
    agenten vid varje start. Den raden är omskriven till att namnge vad som faktiskt saknas
    (allt utom `/api/v1/agent/vouchers`), och ett `idempotency_contract`-block har lagts till
    bredvid `bank_input_contract`, plus en guardrail. Assertionen `"durable idempotency"` är
    skärpt till hela den nya, smalare meningen — inte borttagen.

- [ ] **T11 — Regression och lint**
  - Acceptans: alla tio framgångskriterier i §11 uppfyllda.
  - Verifiera: `pytest tests/ -v` och `black . && isort . && flake8 && mypy .`. Läs jobboutputen
    i CI — bocken betyder inget (`continue-on-error: true`).
  - Filer: inga nya.

---

**Utanför scope:** fakturasändning och lönegodkännande (flöde 2 och 3), radering av nycklar
(beslut §12.2), frontendtester (finns inte i repot), att göra headern obligatorisk (§10).

---

## Avvikelse från specen: `release`

`IdempotencyRepository.release(key, endpoint)` finns inte i specens §7 men krävs av testfall 6
och framgångskriterium 4: reservationen commitas före arbetet, så ett avbrott mitt i skulle annars
lämna en `in_flight`-rad kvar och låsa ute varje omförsök med `request_in_flight` för alltid.
`release` raderar **bara** `in_flight`-rader — en `completed` nyckel skyddar en verklig postning
och måste överleva. Det rör inte beslut §12.2, som gäller retention/städning.

Kvarstående, medvetet: kraschar processen mellan reservation och commit ligger raden kvar som
`in_flight` tills någon ger nycklarna en livslängd. Det är samma beslut som §12.2 sköt på framtiden.
