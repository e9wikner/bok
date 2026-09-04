# Spec: Syncthing dropzone — folder-based intake

**Status:** Ready for implementation
**Created:** 2026-09-04
**Related:** `.planning/research/BATCH-INTAKE-UX-PLAN.md` §3 (the folder)
**Depends on:** HEIC support (`HEIC-SUPPORT-SPEC.md`) — see §12
**Scope:** Backend scanner + config + Docker mount + status endpoint + deployment docs
**Estimated shape:** 1 new service, 1 new route, 0 migrations, ~6 touched files

---

## 1. Goal

Files left in a synced folder are picked up and enter intake on their own. The
owner drops a receipt into `Kvitton/` from any device and does nothing else —
no browser, no form, no upload button.

The folder becomes the status display: an empty `Kvitton/` means everything is in
the system. That property is the whole point of the design, and §5 is built
around preserving it.

**Non-goal:** replacing the browser upload. It stays as the second door.

---

## 2. Folder contract

```
Bokföring/                     ← the Syncthing shared folder
  Kvitton/                     → source_type = receipt
  Leverantörsfakturor/         → source_type = supplier_invoice
  Kundfakturor/                → source_type = customer_invoice
  Utlägg/                      → source_type = reimbursement
  Övrigt/                      → source_type = other
  Bank/
    1930/                      → bank input on account 1930
    1630/                      → bank input on account 1630 (skattekonto)
  _Inläst/2026-09/             ← app moves ingested files here
  _Problem/                    ← app moves rejects here, with a .txt saying why
```

**Mapping rules**

- Folder name → `source_type`, matched **case-insensitively and
  Unicode-normalised** (§9 — this is a real trap, not a formality).
- `Bank/<kontokod>/` → a bank input. The account code is passed as
  `account:<kontokod>`, which the existing
  `_resolve_bank_connection_reference()` (`api/routes/bank_inputs.py:206-229`)
  already resolves to a real connection, creating a manual one from the chart of
  accounts if none exists. **No new bank-account concept is invented.**
- A file directly in the root, or in an unrecognised folder, is ingested with
  **`source_type = None`** and the agent classifies it. Unknown folders are not
  an error — the backend already accepts a null source type
  (`api/routes/intake.py:39`).
- `_Inläst/` and `_Problem/` are never scanned.

**Sidecar metadata** (both optional)

- `_meddelande.txt` in a folder → `agent_guidance` for every file ingested from
  that folder.
- `<filnamn>.txt` beside a file → that file's `explanation`
  (`kvitto-taxi.pdf` + `kvitto-taxi.txt`).

`.txt` files are **sidecars, never sources.** They must be excluded from
ingestion explicitly — `text/plain` is not in `ALLOWED_MIME_TYPES`, so without
the exclusion every sidecar would be rejected and moved to `_Problem/`, which is
both wrong and noisy. A consumed sidecar moves to `_Inläst/` alongside its file.

---

## 3. Configuration

New settings in `config.py`, alongside the existing `INTAKE_DIR` /
`BANK_INPUT_DIR`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `DROPZONE_ENABLED` | `False` | Opt-in. Off means the scanner never starts |
| `DROPZONE_DIR` | `/app/data/dropzone` | Root of the watched tree |
| `DROPZONE_SCAN_INTERVAL_SECONDS` | `60` | Seconds between ticks |
| `DROPZONE_QUIET_SECONDS` | `10` | A file must be unmodified this long before it is read (§5) |
| `DROPZONE_MAX_FILES_PER_SCAN` | `25` | Bounds one tick's work (§4) |

Default-off matters: an existing deployment upgrading to this version must not
suddenly start walking a directory nobody configured.

---

## 4. Where the scanner runs

**A background thread inside the API process,** started from a FastAPI lifespan
hook in `api/main.py` when `DROPZONE_ENABLED` is true.

Rationale: `db.Database` already uses thread-local SQLite connections
(`db/database.py:29-40`) precisely so non-request threads work, and WAL mode is
already on — so a worker thread gets a correct connection with no new
infrastructure. A separate container would mean a second image, a second set of
secrets, and a second thing to keep running, for one user's every-two-months
workload.

Two constraints follow, and both must be implemented:

- **Single instance.** `uvicorn.run()` currently starts one process
  (`main.py:76-82`, no `workers` argument). If workers are ever added, N scanners
  would race on the same files. Take an `O_EXCL` lock file in `DROPZONE_DIR` at
  thread start and exit if it is held; stale-lock recovery by PID check.
- **Bounded work per tick.** Conversion and hashing are CPU-bound and hold the
  GIL, so an unbounded tick would make the API sluggish while a large batch is
  ingested. Process at most `DROPZONE_MAX_FILES_PER_SCAN` files per tick and
  yield briefly between files. 200 files then take ~8 ticks — invisible at this
  cadence, and the UI stays responsive throughout.

The thread must catch and log every exception per file. **One bad file must
never kill the scanner** — a dead scanner is the failure mode §7 exists to make
visible.

---

## 5. Scan algorithm

Per tick:

1. Walk `DROPZONE_DIR`, excluding `_Inläst/` and `_Problem/`.
   **Do not follow symlinks** (§10).
2. Skip ignored names (§9).
3. **Stability gate.** Stat each candidate. Read it only if its `(mtime, size)`
   is unchanged since the previous tick *and* `mtime` is at least
   `DROPZONE_QUIET_SECONDS` old. Otherwise record the observation and move on.
   Syncthing writes in-flight transfers as `~syncthing~*.tmp` and renames on
   completion, but the gate also covers a file being copied in by hand or over
   SMB. Reading a partial file would store corrupt bytes under a *valid* sha256
   — permanently, because dedupe would then reject the good copy.
4. Route by folder (§2) and call the existing service:
   `IntakeService.create_source_from_upload_content()` or
   `BankInputService.create_from_upload_content()`. **No new ingest path** — the
   scanner is a caller, not a parallel implementation, so validation, storage,
   dedupe and audit behave identically to an HTTP upload.
5. Dispose of the file by outcome:

| Outcome | Destination | Note |
|---------|-------------|------|
| Ingested | `_Inläst/YYYY-MM/` | |
| **Duplicate** (`duplicate_intake_source`) | `_Inläst/YYYY-MM/` | **Success, not failure** — the file *is* in the system. This is what makes re-dropping a half-processed folder safe |
| Validation rejection | `_Problem/` | Plus `<namn>.problem.txt` in Swedish naming the reason |
| Unexpected error | left in place | Retried next tick; logged. Do not move what you do not understand |

Name collisions at the destination get a ` (2)`, ` (3)` suffix. **Nothing is ever
deleted** — the scanner only ever moves.

**Stability state lives in memory.** A restart just re-observes each file and
costs one extra tick; persisting it would add a table for no benefit.

---

## 6. Ordering: files before sidecars

Within a folder, resolve `_meddelande.txt` and any `<filnamn>.txt` **before**
ingesting the files they annotate, so guidance and explanation are attached at
creation. Attaching them afterwards would need
`PUT /api/v1/intake/{id}/agent-guidance`, which only accepts pending or
processing sources (`services/intake.py:135-141`) — a race against an agent that
picks the source up first.

---

## 7. Status endpoint — the thing that stops silent failure

**This is not optional polish.** The characteristic failure of any folder-based
system is the scanner dying quietly: files accumulate in `Kvitton/`, the owner
assumes they are queued, and two months later nothing was booked. The folder
looks exactly the same when the scanner is dead as when files were just dropped.

`GET /api/v1/intake/dropzone/status` returns:

```json
{
  "enabled": true,
  "dropzone_dir": "/app/data/dropzone",
  "last_scan_at": "2026-09-04T10:31:00",
  "last_scan_duration_ms": 412,
  "pending_file_count": 3,
  "ingested_total": 84,
  "problem_file_count": 1,
  "last_error": null
}
```

Surfaced on the intake page as one line: when `last_scan_at` is older than
roughly three scan intervals, show a warning that pickup has stopped. That is
the entire frontend change in this issue.

---

## 8. Docker and deployment

`docker-compose.local.yml` and `docker-compose.yml`:

```yaml
    environment:
      DROPZONE_ENABLED: "${DROPZONE_ENABLED:-false}"
    volumes:
      - bokfoering-data:/app/data
      - ${DROPZONE_HOST_DIR:-./dropzone}:/app/data/dropzone
```

The bind mount must be the same host directory Syncthing syncs. The container
runs as root (no `USER` in the `Dockerfile`), so files written by the host's
Syncthing user are readable and movable. **If a non-root `USER` is ever added,
this breaks** — note it in the Dockerfile.

**`DEPLOYMENT.md` gains a Syncthing section** covering: install on the server,
share one folder with the laptop and phone, set the server's copy to
**Send & Receive** (the moves into `_Inläst/` must propagate back out, or the
inbox never empties on the other devices), and the folder skeleton from §2.

Worth documenting as the answer to "should `_Inläst/` be synced?": keep it inside
the shared folder so the server holds a real archive, and let space-constrained
devices exclude it with a `.stignore` entry. Per-device, not per-folder — each
device decides.

---

## 9. Names to ignore

```
.stfolder  .stversions  .stignore  ~syncthing~*.tmp  *.sync-conflict-*
.DS_Store  ._*  Thumbs.db  desktop.ini  *.part  *.tmp  *.crdownload
```

`*.sync-conflict-*` matters: Syncthing creates these when the same file changes
on two devices. Ingesting one produces a near-duplicate that dedupe will *not*
catch, because the bytes differ. Leave them for the owner.

**Unicode normalisation is a real trap.** macOS stores filenames as NFD, Linux as
NFC. A `Leverantörsfakturor/` folder created on a Mac arrives on the Linux server
with `ö` decomposed, and a naive `==` against an NFC constant silently fails —
every file in it would fall through to `source_type = None` with no error
anywhere. Normalise both sides with `unicodedata.normalize("NFC", name)` before
comparing. Same for `Utlägg/` and `Övrigt/`.

---

## 10. Security

The scanner reads arbitrary bytes from a directory that syncs from other
machines, so it is a genuine trust boundary.

- **Do not follow symlinks.** `os.walk(followlinks=False)`, and `lstat` each
  candidate. A symlink in the dropzone pointing at `/etc/passwd` or at the
  SQLite file would otherwise be read and stored as an intake source.
- **Confirm containment.** Resolve every path and verify it stays under
  `DROPZONE_DIR` before reading or moving, mirroring `resolve_source_file()`
  (`services/intake.py:149-165`). PROJECT.md flags this class of bug explicitly.
- **Actor.** Ingested sources record `uploaded_by`. Use a distinct
  `dropzone` actor rather than a human username, so the audit trail
  distinguishes machine pickup from a person's upload.
- The existing 10 MB cap and MIME allow-list apply unchanged — the scanner calls
  the same validators.

---

## 11. Test plan

New `tests/test_dropzone.py`, using `tmp_path` and the existing `test_db` /
`intake_dir` fixtures. No running Syncthing is needed anywhere.

| # | Test | Asserts |
|---|------|---------|
| 1 | PDF in `Kvitton/` | source created with `source_type == "receipt"`; file moved to `_Inläst/YYYY-MM/` |
| 2 | File in an unknown folder | ingested with `source_type is None`, not rejected |
| 3 | CSV in `Bank/1930/` | bank input created against the resolved connection for account 1930 |
| 4 | File modified during the tick | **not** ingested; ingested on a later tick once stable (§5.3) |
| 5 | Same file dropped twice | second is a duplicate, still moved to `_Inläst/`, no second source |
| 6 | Oversized / disallowed file | moved to `_Problem/` with a `.problem.txt` naming the reason |
| 7 | `_meddelande.txt` in a folder | `agent_guidance` set on sources from that folder; the `.txt` is not itself a source |
| 8 | `<filnamn>.txt` sidecar | `explanation` set on that file's source only |
| 9 | Ignored names (§9) | skipped, left in place, not moved |
| 10 | `Leverantörsfakturor/` as **NFD** | maps to `supplier_invoice` (§9) |
| 11 | Symlink to a file outside the root | not read, not ingested |
| 12 | Destination name collision | second file becomes `namn (2).pdf`, neither is lost |
| 13 | A file that raises unexpectedly | stays in place, scanner survives, next file still processed |
| 14 | `_Inläst/` and `_Problem/` contents | never re-scanned |
| 15 | Status endpoint after a scan | `last_scan_at` set, counts correct |
| 16 | `DROPZONE_ENABLED=false` | thread never starts; endpoint reports `enabled: false` |

---

## 12. Relationship to HEIC (#36)

Independent, one-directional: **HEIC ships on its own; the dropzone is much less
useful without it.**

If the dropzone lands first, every iPhone photo syncing in from `Kvitton/` is
rejected and moved to `_Problem/` — the exact silent pile-up §7 is designed to
prevent, on the single most common file type. Ship HEIC first, or accept that
phone capture does not work until it lands.

No code dependency exists in either direction: the scanner calls
`create_source_from_upload_content()`, which is where HEIC handling is added.

---

## 13. Acceptance criteria

1. A PDF dropped into `Kvitton/` appears in the intake workspace within one scan
   interval, typed as a receipt, with no browser interaction.
2. A CSV dropped into `Bank/1930/` becomes a bank input on that account.
3. Ingested files are moved to `_Inläst/YYYY-MM/`; the inbox folder empties.
4. Re-dropping an already-ingested file creates nothing and still tidies away.
5. A rejected file lands in `_Problem/` with a readable Swedish explanation.
6. A file still being written is not read until it settles.
7. Nothing the scanner does deletes a file, ever.
8. The intake page shows when pickup last ran, and warns when it has stopped.
9. `DROPZONE_ENABLED=false` (the default) leaves current behaviour untouched.

---

## 14. Task breakdown

| # | Task | Files |
|---|------|-------|
| 1 | Config settings | `config.py` |
| 2 | Folder→type mapping with NFC normalisation and the ignore list | new `services/dropzone.py` |
| 3 | Scan loop: stability gate, routing, sidecars, move/disposal | `services/dropzone.py` |
| 4 | Lifespan thread + single-instance lock | `api/main.py`, `services/dropzone.py` |
| 5 | Move `_resolve_bank_connection_reference()` from the route into a service so both callers share it | `api/routes/bank_inputs.py`, `services/bank_inputs.py` |
| 6 | Status endpoint | `api/routes/intake.py` |
| 7 | Status line on the intake page | `frontend-v3/app/vouchers/intake/page.tsx`, `frontend-v3/lib/api.ts` |
| 8 | Docker mount + env wiring | `docker-compose.yml`, `docker-compose.local.yml`, `.env.example` |
| 9 | Syncthing setup section + folder skeleton | `DEPLOYMENT.md` |
| 10 | Tests §11 | `tests/test_dropzone.py` |

Tasks 2–4 are the substance. Task 5 is a small refactor that avoids duplicating
bank-account resolution logic — worth doing properly rather than copying.
