# Spec: HEIC/HEIF support for intake source material

**Status:** ⛔ **DESCOPED 2026-09-04 — not scheduled.** The owner will save photos
as JPEG before they reach intake, so HEIC support is not needed. This spec is kept
complete and ready in case that changes; see §14 for the trigger to revisit.
Originally: ready for implementation
**Created:** 2026-09-04
**Related:** `.planning/research/BATCH-INTAKE-UX-PLAN.md` §5 (format gaps)
**Scope:** Backend ingest + storage + file serving; small frontend change
**Estimated shape:** 1 migration, 1 new dependency, ~4 touched backend files, 2 touched frontend files

---

## 1. Goal

A photo of a receipt taken with an iPhone must be accepted by intake, and every
downstream consumer — the bookkeeping agent above all — must receive bytes it can
actually decode.

Today `IntakeService.ALLOWED_MIME_TYPES` is jpeg/png/gif/webp/pdf
(`services/intake.py:60-66`, `:67`). HEIC is the iPhone camera default, so **every
unconverted phone photo of a receipt is rejected** with
`unsupported_mime_type`. The owner's workaround is to switch the phone to "Most
Compatible" or convert by hand — both are exactly the kind of per-file manual
step the batch plan exists to remove.

This becomes load-bearing rather than annoying once the Syncthing dropzone
ships: the phone's camera album syncs straight into `Kvitton/`, so HEIC will be
the single most common file type arriving, and a rejected file lands in
`_Problem/` where nobody is watching.

---

## 2. Design decisions

These are the judgement calls. Each is a decision, not a preference — changing
one changes the implementation materially.

### D1 — Detect by magic bytes, never by `content_type`

The upload path currently trusts the client's `content_type`
(`services/intake.py:87`, `api/routes/intake.py:48`). That is unreliable for
HEIC specifically: browsers and OSes that do not know the format send
`application/octet-stream`, so a MIME allow-list alone would reject exactly the
files this ticket is about. The future dropzone scanner has **no**
`content_type` at all — it reads bytes off a disk.

So: classify from the file's own bytes. `content_type` may be used as a hint,
never as the authority.

### D2 — sha256 hashes the ORIGINAL bytes, not the converted JPEG

This is the most important correctness decision here.

Dedupe (`services/intake.py:90-93`, unique index
`idx_intake_sources_sha256_active`) answers "have I already uploaded this
file?". If the hash were taken over the converted JPEG, the answer would depend
on the encoder: a Pillow or libheif upgrade can change JPEG output bytes for
identical input, so the same HEIC re-dropped after an upgrade would hash
differently and be ingested a second time. The owner would get duplicate
vouchers with no visible cause.

Hashing the received bytes keeps dedupe stable for the life of the system, and
keeps the idempotent-rescan property the dropzone design depends on.

### D3 — Keep the original, store the JPEG as a derived rendition

`stored_path` keeps the HEIC exactly as received — that is the document the
company was given, and it is what an audit trail should hold. The JPEG sits
beside it as a derived rendition and is regenerable at any time.

`mime_type` stays `image/heic`: it should stay truthful about what arrived.
Two new nullable columns carry the rendition (§6).

### D4 — `/file` serves the rendition by default

`GET /api/v1/intake/{id}/file` returns the JPEG when a rendition exists, and the
original when it does not. `?original=true` returns the raw HEIC.

Rationale: every consumer can decode JPEG and essentially none can decode HEIC —
including the agent, which is the primary caller. **There is no regression risk**
because HEIC is rejected at upload today, so no stored source has a rendition and
no existing response changes.

### D5 — Apply EXIF orientation, then strip metadata

A receipt photographed sideways is materially harder for the agent to read, and
the orientation tag is routinely ignored by downstream tooling. Rotate the actual
pixels upright (`PIL.ImageOps.exif_transpose`) and drop the EXIF block from the
rendition.

This also drops GPS coordinates. A photo of a lunch receipt otherwise carries the
location where it was taken, persisted for the statutory retention period, for no
accounting purpose.

### D6 — A conversion failure rejects the upload

If the bytes sniff as HEIC but will not decode (corrupt, truncated, an unusual
variant, a depth-map-only capture), return `400 heic_conversion_failed` and
persist nothing. Half-ingested records that no consumer can read are worse than a
clear rejection.

Later, in the dropzone: the file moves to `_Problem/` with a sidecar note.

### D7 — The size cap applies to what arrived

The existing 10 MB cap keeps applying to the uploaded original. The rendition is
not re-checked against it, but is bounded independently by the downscale rule in
§5 so a large capture cannot produce an unbounded JPEG.

---

## 3. Out of scope

- **AVIF.** Shares the ISO-BMFF container and often carries `mif1` as a
  compatible brand, so it must be *explicitly excluded* by §4, not accidentally
  accepted. A separate decision if it is ever wanted.
- **HEIC image sequences / bursts / Live Photos.** Convert the primary image
  only; do not extract frames.
- **Re-rendering existing sources.** No backfill exists to do — HEIC has never
  been accepted, so no stored source needs one.
- **The dropzone scanner itself.** Specified in the batch intake plan. This spec
  only guarantees the conversion path it will call is already in place.
- **Bank inputs.** `bank_inputs` is CSV-only and unaffected.

---

## 4. Detection

Read the first 32 bytes. The file is a HEIC/HEIF candidate when **all** hold:

1. Bytes 4–8 are the ASCII literal `ftyp` (ISO base media file format).
2. The brand set — the major brand at bytes 8–12, plus the compatible brands
   listed from byte 16 onward in 4-byte units, bounded by the box size in bytes
   0–4 — intersects:
   `heic`, `heix`, `heim`, `heis`, `hevc`, `hevx`, `hevm`, `hevs`, `mif1`, `msf1`
3. The major brand is **not** `avif` or `avis`.

The sniff is a cheap classification gate only. `pillow_heif` is the authority on
whether the file actually decodes; a candidate that fails to decode is D6.

Accepted MIME values (recorded, not trusted): `image/heic`, `image/heif`,
`image/heic-sequence`, `image/heif-sequence`. When the sniff succeeds but the
client sent `application/octet-stream` or an empty type, **record the sniffed
type** (`image/heic`) rather than what the client claimed.

Guard against the inverse too: a file *named* `.heic` that does not sniff as HEIC
falls through to the normal allow-list and is rejected as
`unsupported_mime_type`, as it is today.

---

## 5. Conversion

Applied at ingest, in `IntakeService`, before the source row is created:

| Step | Rule |
|------|------|
| Decode | `pillow_heif` registered as a Pillow opener; open the primary image |
| Orientation | `ImageOps.exif_transpose()` — rotate pixels upright (D5) |
| Colour | Convert to `RGB` (HEIC may be 10-bit, greyscale, or carry alpha) |
| Downscale | If the long edge exceeds **4000 px**, scale to 4000 px, LANCZOS. A receipt needs no more, and it bounds rendition size (D7) |
| Encode | JPEG, `quality=85`, `optimize=True`, no EXIF |
| On failure | `IntakeValidationError("heic_conversion_failed", …)` → HTTP 400 (D6) |

Conversion is CPU-bound and runs inside the request. A single iPhone capture
decodes in well under a second, which is acceptable for the current
one-file-per-request API. **If batch upload later fans out 100 concurrent
conversions this becomes the bottleneck** — note it, do not solve it here.

---

## 6. Storage and schema

Layout under the existing per-source directory (`services/intake.py:367-369`):

```
{intake_dir}/{source_id}/{source_id}.heic     ← original, stored_path, hashed
{intake_dir}/{source_id}/{source_id}.jpg      ← rendition, rendition_path
```

**Migration `023_add_intake_source_renditions.sql`** — plain `ADD COLUMN`, in the
style of migration 020 (021 already rebuilt the table; no rebuild is needed
here):

```sql
ALTER TABLE intake_sources ADD COLUMN rendition_path TEXT;
ALTER TABLE intake_sources ADD COLUMN rendition_mime_type TEXT;

INSERT OR IGNORE INTO schema_version (version) VALUES (23);
```

Both nullable; every existing row keeps `NULL` and behaves exactly as today.

Also update:

- `domain/models.py` — `IntakeSource` gains `rendition_path: Optional[str] = None`,
  `rendition_mime_type: Optional[str] = None`
- `repositories/intake_repo.py` — `create_source()` params + INSERT column list +
  `_row_to_source()`
- `services/intake.py` — `_extension_from_mime()` (`:379`) gains `image/heic` → `.heic`
  and `image/heif` → `.heif`, otherwise a HEIC upload with no filename extension
  is stored as `.bin`

**Cleanup:** `_cleanup_stored_file()` (`services/intake.py:371`) currently unlinks one file then rmdirs the
parent. It must remove the rendition too, or the failure path leaves an orphan
JPEG and the `rmdir` silently fails.

**Path safety:** `resolve_source_file()` enforces root containment
(`services/intake.py:149-165`). The rendition needs the identical check — add
`resolve_rendition_file()` or extend the existing method to take the path to
check. Do not serve a rendition path without it; this is the exact surface
PROJECT.md flags as high-risk.

---

## 7. API changes

**`GET /api/v1/intake/{source_id}/file`** (`api/routes/intake.py:197-213`)

- New query param `original: bool = False`
- Default: serve `rendition_path` with `rendition_mime_type` when set, else
  `stored_path` with `mime_type` (unchanged behaviour for every existing row)
- `original=true`: always serve `stored_path`
- Download filename: the original stem with the served extension
  (`kvitto.heic` → `kvitto.jpg` for the rendition)

**Response payloads** — `_source_to_dict()` (`api/routes/intake.py:228`),
`_workspace_source_item()` (`:274`), and the agent queue item
(`api/routes/agent.py:179-196`) each gain:

- `rendition_mime_type` — `null` or `"image/jpeg"`
- `download_mime_type` — what `/file` will actually return

`download_mime_type` is the field that matters for the agent: it tells it the
bytes will be JPEG without it having to reason about renditions at all.

**Documentation:** `docs/to_agent/` states the accepted formats; add HEIC and one
line saying `/file` serves a JPEG rendition for HEIC sources.

---

## 8. Frontend changes

Small, and deliberately so.

1. `frontend-v3/app/vouchers/intake/page.tsx:217` — extend `accept` with
   `.heic,.heif,image/heic,image/heif`. **Include both the extensions and the
   MIME types**: macOS and Windows file dialogs filter on extension, and a MIME
   the OS does not recognise will grey the files out.
2. Error mapping — `heic_conversion_failed` needs its own Swedish message
   ("Bilden kunde inte läsas. Prova att skicka den som JPEG."), distinct from the
   generic filetype rejection. This is the first typed code to get its own
   message; the batch plan's §B5 generalises the pattern later.

Nothing else. The detail page shows `mime_type` as a text field
(`intake/[kind]/[id]/page.tsx:297`) and downloads via blob — there is no `<img>`
preview to fix.

---

## 9. Dependency and packaging

Add to `requirements.txt`:

```
pillow-heif>=1.6.0
```

Verified against PyPI on 2026-09-04:

- **License** BSD-3-Clause; `requires_python >=3.10` (repo runs 3.11 ✓)
- **Wheels for cp311** cover `manylinux_2_28_x86_64`, `manylinux_2_28_aarch64`,
  `musllinux_1_2`, macOS x86_64/arm64, Windows. libheif is bundled.
- The Docker base is `python:3.11-slim` (Debian bookworm, glibc 2.36 ≥ 2.28), so
  the manylinux wheel installs directly on both x86_64 and arm64 — **no new
  `apt-get` packages in the Dockerfile.**

**⚠ The one real integration risk: `pillow-heif` 1.6.0 requires `pillow>=11.1.0`,
while `requirements.txt` currently pins `pillow>=10.0`.** The constraint is
satisfiable, so pip will simply upgrade Pillow to 11.x. Pillow is not imported
directly anywhere in this codebase — its only consumer is `qrcode` in
`services/pdf_export.py:14,106`. Mitigation: bump the pin to `pillow>=11.1` so
the resolution is explicit rather than incidental, and run
`pytest tests/test_pdf_export.py` plus one visual check of an invoice PDF's QR
code before merging. If Pillow 11 turns out to break PDF export, pin
`pillow-heif==1.1.1` instead (last release supporting Pillow 10) and record why.

---

## 10. Error codes

| Code | HTTP | When | Swedish message |
|------|------|------|-----------------|
| `heic_conversion_failed` | 400 | Sniffs as HEIC, will not decode | "Bilden kunde inte läsas. Prova att skicka den som JPEG." |
| `unsupported_mime_type` | 400 | Not HEIC and not in the allow-list — unchanged, incl. `.heic`-named non-HEIC | existing |
| `file_too_large` | 400 | Original over 10 MB — unchanged | existing |
| `intake_file_outside_root` | 403 | Rendition path escapes the storage root | existing |

---

## 11. Test plan

Extend `tests/test_intake_api.py`, following its existing conventions — the
`intake_dir` fixture, the `_UploadFile` helper, `test_db`.

**Fixtures.** Generate HEIC bytes at test time with `pillow_heif` itself
(`Image.new(...).save(buf, format="HEIF")`) rather than committing a binary
fixture. Keeps the repo clean and self-documenting.

| # | Test | Asserts |
|---|------|---------|
| 1 | Upload HEIC with `image/heic` | 201; source created; `rendition_mime_type == "image/jpeg"` |
| 2 | Upload HEIC sent as `application/octet-stream` | 201 — sniffing works (D1); stored `mime_type` is the sniffed `image/heic`, not the claimed type |
| 3 | `.heic`-named file that is not HEIC | 400 `unsupported_mime_type` |
| 4 | An AVIF file | 400 — explicitly not accepted (§3) |
| 5 | sha256 of the stored row | equals `hashlib.sha256(original_bytes)` (D2) — the regression guard for the whole dedupe model |
| 6 | Re-upload of the same HEIC | 409 `duplicate_intake_source` |
| 7 | Rendition on disk | exists, decodes as JPEG, sits inside `intake_dir` |
| 8 | `GET /file` | returns JPEG bytes, `media_type == "image/jpeg"` |
| 9 | `GET /file?original=true` | returns the byte-identical HEIC |
| 10 | Non-HEIC source (a PDF) | `/file` unchanged; `rendition_path` is `NULL` — the no-regression guard |
| 11 | EXIF-rotated input | rendition pixel dimensions reflect the rotation (D5) |
| 12 | Oversized input (>4000 px) | rendition long edge is exactly 4000 |
| 13 | Truncated/corrupt HEIC | 400 `heic_conversion_failed`; **no row created and no file left in `intake_dir`** (D6) |
| 14 | Rendition path outside root | `IntakeFileAccessError` — mirrors the existing `test_intake_file_api_rejects_outside_root_stored_path` |
| 15 | Agent queue item | carries `download_mime_type == "image/jpeg"` |

Also re-run `tests/test_pdf_export.py` for the Pillow bump (§9).

---

## 12. Acceptance criteria

1. A HEIC photo taken on an iPhone uploads successfully through the intake page.
2. The agent fetching that source's `/file` receives decodable JPEG bytes and can
   read the receipt.
3. The original HEIC is still retrievable byte-for-byte via `?original=true`.
4. Re-uploading the same HEIC is rejected as a duplicate, and stays rejected
   across a Pillow/libheif upgrade.
5. A sideways-photographed receipt is upright in the rendition.
6. A corrupt HEIC produces a clear Swedish error and leaves nothing behind.
7. Existing non-HEIC sources behave exactly as before, in storage and over the API.
8. `docker compose build` succeeds with no new system packages.

---

## 13. Task breakdown

| # | Task | Files |
|---|------|-------|
| 1 | Add `pillow-heif`, bump the Pillow pin, verify PDF export | `requirements.txt`, `tests/test_pdf_export.py` |
| 2 | Migration + model + repository columns | `db/migrations/023_…sql`, `domain/models.py`, `repositories/intake_repo.py` |
| 3 | Sniffing + conversion in the service; extension map; cleanup of both files | `services/intake.py` |
| 4 | Rendition path-safety resolver | `services/intake.py` |
| 5 | `/file` rendition serving + `original` param + payload fields | `api/routes/intake.py`, `api/routes/agent.py` |
| 6 | Frontend `accept` + the typed error message | `frontend-v3/app/vouchers/intake/page.tsx` |
| 7 | Tests §11 | `tests/test_intake_api.py` |
| 8 | Agent-facing docs note | `docs/to_agent/` |

Tasks 1–4 are the substance; 5–8 follow mechanically.


---

## 14. Why this is descoped, and when to revisit

**Decided 2026-09-04.** Photos will be saved as JPEG before they reach intake —
either by setting the iPhone camera to "Mest kompatibla" or by exporting as JPEG
when a photo is copied into the queue deliberately. That removes the need for
this work entirely, at the cost of one per-photo habit.

The reasoning holds as long as files are placed into the queue **deliberately**.

**Revisit if** a phone's camera roll is ever auto-synced into `Kvitton/`. At that
point nobody is choosing a format per photo, HEIC becomes the most common
arriving file type, and every one of them lands in `_Problem/` — the silent
pile-up the dropzone's status endpoint exists to prevent, on the highest-volume
input. That is the single condition that flips this back on.

Until then, `DROPZONE-SPEC.md` §12 requires the `_Problem/` note for a HEIC file
to name the fix ("spara om som JPEG"), so a stray HEIC is recoverable in seconds
rather than mysterious.
