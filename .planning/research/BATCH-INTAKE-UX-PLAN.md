# Batch Intake UX Plan

**Status:** Draft proposal — candidate scope for the next milestone
**Created:** 2026-09-04
**Scope:** Frontend intake surfaces + a synced-folder ingest path
**Not in scope of this document:** implementation; this describes the outcome only

**Decided 2026-09-04:** sync tool is **Syncthing** (resolves open questions 1 and 4).

**Ticketed:** the folder (§3) is specced in `DROPZONE-SPEC.md`; the HEIC gap in
`HEIC-SUPPORT-SPEC.md`. The frontend surfaces in §4 (batch drop, batches, triage
queue, completeness view) remain plan-level and are not yet ticketed.

---

## 1. The problem

The owner books roughly every two months. That means each session starts with a
pile of 50–200 documents: receipts, supplier invoices, customer invoices and
bank/skattekonto printouts. The current intake surface is built for one document
at a time, so the pile has to be fed through a form one item per interaction.

Concrete friction in today's code:

| # | Friction | Where |
|---|----------|-------|
| 1 | File picker is strictly single-file — reads `event.target.files?.[0]`, no `multiple`, no drag-and-drop | `frontend-v3/app/vouchers/intake/page.tsx:552-559` |
| 2 | Each upload asks for type + `Kort förklaring` + `Meddelande till agent`, then resets the whole form | `page.tsx:118-140`, `page.tsx:224-262` |
| 3 | Bank files are a second card needing a `bank_connection_id` chosen per file | `page.tsx:284-358` |
| 4 | Every failure collapses into one generic Swedish sentence covering filetype, bank account *and* duplicate | `page.tsx:47-48` |
| 5 | Re-uploading a file already in the system is a hard `409` | `services/intake.py:88-90` |
| 6 | Status list is a flat table, 15 rows per page, no grouping — 100 files is 7 pages | `page.tsx:37` |
| 7 | MIME allow-list is jpeg/png/gif/webp/pdf with a 10 MB cap — no HEIC, no ZIP | `services/intake.py:60-66` |

Cost per session at 100 files: roughly 500 discrete UI interactions, each with a
network round trip, and no way to see which of them landed.

---

## 2. Target outcome

Two doors into **one** queue:

- **Door 1 — the folder (primary).** Files are left in a synced folder on the
  shared drive. The agent picks them up. No browser involved.
- **Door 2 — the browser.** Drag 100 files (or a folder) onto the intake page at
  once, no required fields.

Both doors write to the same `intake_sources` / `bank_inputs` tables and surface
in the same `GET /api/v1/agent/intake/pending` queue. No second bookkeeping path
— this keeps the PROJECT.md "automation first" and "traceability" constraints
intact.

Once upload stops being the bottleneck, the frontend's job changes: it stops
being an **upload form** and becomes a **batch status board plus a triage
queue**.

---

## 3. Part A — The synced folder

### 3.1 Folder shape

```
Bokföring/                        ← Syncthing shared folder
  Kvitton/
  Leverantörsfakturor/
  Kundfakturor/
  Utlägg/
  Kontoutdrag/
    1930 Företagskonto/
    1630 Skattekonto/
  _Inläst/                        ← app moves ingested files here
    2026-09/
  _Problem/                       ← app moves rejects here + a .txt saying why
```

The folder name carries the metadata that the form asks for today:

- Top-level folder → `source_type` (`Kvitton` → `receipt`, `Leverantörsfakturor`
  → `supplier_invoice`, …). Both per-file dropdowns disappear.
- `Kontoutdrag/<kontokod> <etikett>/` → `bank_connection_id`, resolved from the
  leading account code. Covers bank, skattekonto, card and payment-provider
  statements — not only banks, hence the general name.
- Optional `_meddelande.txt` in a folder → `agent_guidance` for everything in it.
- Optional `<filnamn>.txt` beside a file → that file's `explanation`.

Anything dropped at the root with no folder gets no `source_type` at all — the
backend already accepts `source_type: None` (`api/routes/intake.py:39`) and the
agent classifies it. Unclassified is a valid, cheap default.

### 3.2 How pickup works

- A `DROPZONE_DIR` setting sits alongside the existing `INTAKE_DIR` /
  `BANK_INPUT_DIR` in `config.py`; the host folder is bind-mounted into the API
  container the same way `bokfoering-data` is today.
- A scanner runs on an interval. For each file it reuses
  `IntakeService.create_source_from_upload_content()` — the exact path the HTTP
  upload uses — so validation, storage and audit behaviour stay identical.
- **Stability check before reading:** skip files whose mtime changed since the
  previous scan, and skip partial-write names (`.part`, `.tmp`, `.crdownload`,
  `~$*`). Sync clients write partials; reading one produces a corrupt intake
  source with a real sha256, which the dedupe index will then happily keep
  forever.
- **Idempotency is free.** sha256 dedupe already exists, so re-scanning, re-
  dropping, or restoring a backup into the folder costs nothing.
- **On success:** move the file to `_Inläst/YYYY-MM/`.
- **On reject:** move to `_Problem/` and write a sidecar `.txt` in Swedish
  naming the actual reason (too large, wrong format, unreadable).

### 3.3 Why the move matters

The move is what makes this design worth having: **the folder becomes the status
display.** An empty `Kvitton/` means everything is in the system. The owner gets
an answer to "did it take?" without opening a browser. A file still sitting there
after a scan interval is a file the system did not accept, and `_Problem/` says
why.

### 3.4 Decisions and hazards

- **A move inside a synced tree propagates.** Files will vanish from the laptop's
  `Kvitton/` and reappear under `_Inläst/`. That is the desired self-emptying
  inbox, but it must be stated plainly in the docs: nothing is deleted, only
  relocated. The durable accounting copy is the one already stored under
  `intake_dir`; `_Inläst/` is a convenience mirror, not the legal record.
- **Ignore list** is mandatory: `.stfolder`, `.stversions`, `.stignore`,
  `~syncthing~*.tmp`, plus OS noise — `.DS_Store`, `._*`, `Thumbs.db`,
  `desktop.ini`.
- **Sync tool is Syncthing** (decided). The app watches a directory and does not
  care how bytes get there. Syncthing fits the LAN-first posture in
  `DEPLOYMENT.md`: no third-party server, no cloud account, and every device
  holds a real copy. Two consequences follow from choosing it:
  - **No placeholder-file problem.** Syncthing materialises real bytes on disk,
    so unlike OneDrive/Dropbox there are no zero-byte "online-only" stubs the
    scanner would have to recognise. A zero-byte file can be treated as a
    genuine reject rather than "not ready yet".
  - **Its own junk to ignore:** `.stfolder`, `.stversions`, `.stignore`, and
    `~syncthing~*.tmp` partial writes. The `~syncthing~*.tmp` pattern is the
    important one — it is how Syncthing names in-flight transfers, so it is the
    primary signal for the stability check above.
- **Syncthing setup belongs in the deployment docs**, not in the app: one shared
  folder between the server and each device, with the server as an
  "introducer" so the phone and laptop pair once. Set the server's copy to
  *Send & Receive* — the scanner's move into `_Inläst/` must propagate back out.
- **Phone capture.** Paper receipts are photographed. Syncthing's Android client
  can auto-upload a camera album straight into `Kvitton/`, so the phone never
  touches the app at all. On iOS there is no first-party Syncthing client — the
  practical path is a shared folder on the laptop that the phone's photo library
  exports into, or a third-party client. **This makes HEIC support a hard
  prerequisite** rather than a nice-to-have: the iPhone camera default is HEIC
  and intake rejects it today. See `HEIC-SUPPORT-SPEC.md`.

---

## 4. Part B — Frontend changes

### B1. Batch drop replaces the single-file form

The whole `Verifikationsunderlag` card becomes one drop target.

- Accepts a multi-file selection, a **dragged folder** (`webkitdirectory`), or a
  click-to-browse multi-select.
- **No required fields.** Type is inferred from the dropped folder name where
  present, otherwise omitted for the agent to classify.
- A row per file appears immediately — thumbnail, name, size, status chip —
  with 3–4 uploads in flight and one batch progress bar.
- Per-row outcomes, never a blanket message:
  - *Uppladdad*
  - *Fanns redan* — the `409` becomes a benign, non-red state linked to the
    existing intake item. This is essential: re-dropping a half-processed folder
    is the normal case, not an error case.
  - *Avvisad* — with the real reason.
- Metadata becomes opt-in and **post-hoc**: select rows → set type, or attach one
  `Meddelande till agent` to the whole selection. The 5 % of files that need a
  note get one; the other 95 % cost zero interactions.

### B2. Batches become a first-class object

A pile needs one row, not 100.

- An `intake_batches` concept (id, label, `created_at`, `origin` =
  `upload | dropzone`, counts) groups items ingested together. Dropzone scans
  create batches too.
- The intake page leads with batch cards:
  `4 sep 2026 · 84 underlag · 71 bokförda · 9 väntar · 4 behöver dig`
  and drills into the file list from there. This retires the 15-row flat table
  as the primary view.

### B3. "Behöver dig" triage queue

Once upload is free, **this becomes the actual bottleneck.** 100 files with 10 %
needing a human is 10 decisions, and each one today is a navigate-to-detail,
read, go-back trip through `intake/[kind]/[id]`.

- A dedicated surface handling one item at a time: large document preview on the
  left, the agent's question and proposed booking on the right.
- Two primary actions — **Godkänn** and **Skriv meddelande till agenten** —
  with keyboard movement (`J`/`K` next/previous, `A` approve) so ten decisions
  take a minute.
- **The default filter on the intake page becomes `Behöver dig`, not `Alla`.**
  Work the agent already handled should be collapsed by default; the owner
  should only ever see the exceptions.

### B4. "Är jag klar?" — a completeness view

At a two-month cadence the real anxiety is not upload, it is *completeness*:
did I forget a receipt, did I miss a month of the bank statement.

- Per month in the period, show: bank transactions with no linked voucher, and
  posted vouchers with no source.
- The data already exists — bank inputs carry `transaction_ids` and
  `match_signals` (`api/routes/intake.py:298-319`), and voucher↔source links are
  in `voucher_intake_sources`.
- This is what lets the owner confidently *stop* for another two months.

### B5. Honest per-file errors

The backend already returns typed codes — `duplicate_intake_source`,
`unsupported_mime_type`, `file_too_large`, `invalid_source_type`,
`missing_bank_connection_id`, `bank_input_file_too_large`
(`services/intake.py`, `services/bank_inputs.py`). The frontend currently throws
all of them away in favour of one sentence. Map each code to a Swedish message
plus the fix.

---

## 5. Part C — Format gaps that batch will expose

None of these are UI, but batch drop makes each one bite on day one — a wall of
red rows is worse than the current slow form.

| Gap | Why it bites at 100 files | Proposed outcome |
|-----|---------------------------|------------------|
| **HEIC not in the allow-list** | It is the iPhone default. Every phone photo of a receipt is rejected today. | Accept and convert to JPEG on ingest — specced in `HEIC-SUPPORT-SPEC.md` |
| **10 MB cap** | A scanned stack of receipts as one PDF exceeds it | Raise the cap for PDFs, and downscale oversized images on ingest |
| **Multi-receipt PDF** | One PDF of 30 receipts is one intake source, but needs 30 vouchers. `link_existing_voucher` → `_ensure_can_record_outcome` raises `intake_already_linked` on the second voucher (`services/intake.py:262`, `:324-329`), so this is genuinely blocked today. | Split per page on ingest (preferred — keeps one source per voucher and the traceability model unchanged), or allow one source to link to many vouchers |
| **ZIP archives** | The common shape of a bank/portal bulk export | Expand on ingest; each member becomes its own source |
| **Kontoutdrag as PDF** | `bank_inputs` hard-requires `.csv` (`services/bank_inputs.py:373-378`); banks and Skatteverket hand out PDF by default | Decide explicitly: either accept the PDF as a `voucher_source` for context, or say clearly in the UI and in the folder README that `Kontoutdrag/` needs CSV |

---

## 6. Suggested sequencing

Each step ships on its own and is useful on its own.

1. **Batch drop + per-file outcomes + duplicate-as-benign.** Frontend and error
   mapping only, no schema change. Largest relief per unit of work — this alone
   turns 500 interactions into about 3.
2. **Format gaps** (HEIC, size cap, ZIP). Without this, step 1 just produces a
   faster wall of rejects.
3. **Dropzone scanner + folder convention + ops documentation.** This is the step
   that removes the browser from the loop entirely — the outcome actually asked
   for.
4. **Batches as a first-class object** and the intake page restructure.
5. **Triage queue** for `Behöver dig`.
6. **Completeness view.**

Steps 1–2 likely cut a two-month session from hours to minutes. Step 3 is what
makes the session disappear as an event: files are picked up as they are
dropped, not in a batch at all.

---

## 7. Open questions

1. ~~Which sync tool?~~ **Resolved 2026-09-04: Syncthing.** Folded into §3.4.
2. **Should `_Inläst/` live inside the synced tree** (visible and space-consuming
   on every device, but a reassuring visible archive) **or only on the server**
   (the inbox folder simply empties)?
3. **Is the phone the main capture device for paper receipts?** If yes, camera
   auto-upload into `Kvitton/` should be part of the setup documentation rather
   than an afterthought.
4. ~~Interval scan or filesystem events?~~ **Resolved by the Syncthing choice:
   interval.** Syncthing writes to a real local filesystem, so inotify would
   work — but an interval scan is simpler, has no watch-descriptor limits on
   large trees, and recovers on its own after a restart. A 30–60 s interval is
   invisible at this cadence.

Still open, and newly relevant now that iPhone capture is the main HEIC source:

5. **Is there an iOS device in the loop, or Android only?** Android has a
   first-party Syncthing client and a clean camera-album path; iOS does not, and
   would need the laptop as an intermediate hop.
