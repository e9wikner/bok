import { beforeEach, describe, expect, it, vi } from "vitest";
import { laddaUppUnderlag, skickaMeddelande } from "@/lib/chattyta/api";
import {
  bilagor,
  chipStatus,
  kanSkicka,
  kontoutdragsnotiser,
  kontrolleraFil,
  laddaUppChip,
  laddarUpp,
  MAX_STORLEK_BYTE,
  nyttChip,
  TILLATNA_TYPER,
  type FilChip,
} from "@/lib/chattyta/uppladdning";

/**
 * FU19 (SPEC-flode-underlag.md §10.1–§10.3, testfall 46 och 47): filchipets
 * logik och de två anropen. Axios-instansen är mockad; det är den riktiga
 * `lib/chattyta/api.ts` som tolkar svaren.
 */

const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { post: (...a: unknown[]) => post(...a) },
}));

beforeEach(() => post.mockReset());

/** Som axios kastar det: `isAxiosError` och FastAPIs `{detail}`-kropp. */
const axiosFel = (status: number, detail: unknown) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail }, headers: {} },
  });

const natverksFel = () =>
  Object.assign(new Error("Network Error"), { isAxiosError: true, response: undefined });

const fil = (namn = "kvitto-elektronikhuset.pdf", typ = "application/pdf", storlek = 218_000) =>
  new File([new Uint8Array(storlek)], namn, { type: typ });

/** `api/routes/intake.py::_source_to_dict`. */
const kalla = (over: Record<string, unknown> = {}) => ({
  id: "src-1",
  source_type: null,
  status: "pending",
  original_filename: "kvitto-elektronikhuset.pdf",
  mime_type: "application/pdf",
  size_bytes: 218_000,
  sha256: "abc",
  explanation: null,
  agent_guidance: null,
  uploaded_by: "stefan",
  uploaded_at: "2026-06-03T08:16:00",
  deleted_at: null,
  deleted_by: null,
  ...over,
});

const chip = (over: Partial<FilChip> = {}): FilChip => ({
  nyckel: "c-1",
  namn: "kvitto.pdf",
  storlek: 218_000,
  lage: "klar",
  id: "src-1",
  dubblett: false,
  orsak: null,
  ...over,
});

// ─── Speglingen av serverns regler ────────────────────────────────────────

describe("speglingen av IntakeService (services/intake.py)", () => {
  it("typerna är ALLOWED_MIME_TYPES, varken fler eller färre", () => {
    expect([...TILLATNA_TYPER].sort()).toEqual(
      ["application/pdf", "image/gif", "image/jpeg", "image/png", "image/webp"].sort()
    );
  });

  it("storleken är MAX_FILE_SIZE, 10 MiB", () => {
    expect(MAX_STORLEK_BYTE).toBe(10 * 1024 * 1024);
  });
});

describe("kontrolleraFil — nej före uppladdningen (testfall 46)", () => {
  it("en pdf och en bild under gränsen går igenom", () => {
    expect(kontrolleraFil({ type: "application/pdf", size: 218_000 })).toBeNull();
    expect(kontrolleraFil({ type: "image/jpeg", size: 1 })).toBeNull();
    expect(kontrolleraFil({ type: "image/png", size: MAX_STORLEK_BYTE })).toBeNull();
  });

  it("otillåten typ ger en orsak som säger vad som går", () => {
    const orsak = kontrolleraFil({ type: "application/zip", size: 10 });
    expect(orsak).toMatch(/filtypen stöds inte/);
    expect(orsak).toMatch(/pdf/);
  });

  it("en fil utan typ (t.ex. .heic i vissa webbläsare) är otillåten", () => {
    expect(kontrolleraFil({ type: "", size: 10 })).toMatch(/filtypen stöds inte/);
  });

  it("en byte över gränsen är för stor", () => {
    expect(kontrolleraFil({ type: "application/pdf", size: MAX_STORLEK_BYTE + 1 })).toMatch(
      /för stor/
    );
  });
});

describe("nyttChip", () => {
  it("en tillåten fil börjar som `laddar`, utan id", () => {
    const c = nyttChip(fil(), "c-1");
    expect(c).toMatchObject({
      nyckel: "c-1",
      namn: "kvitto-elektronikhuset.pdf",
      storlek: 218_000,
      lage: "laddar",
      id: null,
      orsak: null,
    });
  });

  it("en otillåten fil är `fel` direkt, med orsaken (testfall 46)", () => {
    const c = nyttChip(fil("arkiv.zip", "application/zip"), "c-2");
    expect(c.lage).toBe("fel");
    expect(c.orsak).toMatch(/filtypen stöds inte/);
    expect(c.id).toBeNull();
  });
});

describe("chipStatus — det chipet säger", () => {
  it("`laddar upp…`, `klar` och `fel · {orsak}`", () => {
    expect(chipStatus(chip({ lage: "laddar", id: null }))).toBe("laddar upp…");
    expect(chipStatus(chip())).toBe("klar");
    expect(chipStatus(chip({ lage: "fel", id: null, orsak: "för stor" }))).toBe("fel · för stor");
  });

  it("en dubblett är klar och säger att den redan fanns (testfall 47)", () => {
    expect(chipStatus(chip({ dubblett: true }))).toBe("klar · fanns redan");
  });
});

// ─── Uppladdningen ────────────────────────────────────────────────────────

describe("laddaUppUnderlag — POST /api/v1/intake", () => {
  it("skickar filen som multipart i fältet `file`, inget annat", async () => {
    post.mockResolvedValue({ status: 201, data: kalla() });
    const f = fil();
    const svar = await laddaUppUnderlag(f);

    expect(post).toHaveBeenCalledTimes(1);
    const [url, kropp] = post.mock.calls[0];
    expect(url).toBe("/api/v1/intake");
    expect(kropp).toBeInstanceOf(FormData);
    const form = kropp as FormData;
    expect(form.get("file")).toBe(f);
    // Ingen förklaring, ingen typ, ingen vägledning: klienten säger inget om
    // filen (§10.3), agenten läser den i tråden.
    expect([...form.keys()]).toEqual(["file"]);
    expect(svar.id).toBe("src-1");
  });
});

describe("laddaUppChip — utfallen", () => {
  it("201 ger `klar` med källans id", async () => {
    post.mockResolvedValue({ status: 201, data: kalla({ id: "src-9" }) });
    expect(await laddaUppChip(fil())).toEqual({ lage: "klar", id: "src-9", dubblett: false });
  });

  it("409 duplicate_intake_source med existing_id är `klar`, inte fel (testfall 47)", async () => {
    post.mockRejectedValueOnce(
      axiosFel(409, {
        error: "This source file was already uploaded",
        code: "duplicate_intake_source",
        details: "sha256=abc, existing_id=src-gammal",
        existing_id: "src-gammal",
      })
    );
    expect(await laddaUppChip(fil())).toEqual({ lage: "klar", id: "src-gammal", dubblett: true });
  });

  it("409 duplicate_intake_source utan existing_id är fel — id:t läses inte ur `details`", async () => {
    post.mockRejectedValueOnce(
      axiosFel(409, {
        error: "This source file was already uploaded",
        code: "duplicate_intake_source",
        details: "sha256=abc, existing_id=src-gammal",
      })
    );
    const utfall = await laddaUppChip(fil());
    expect(utfall.lage).toBe("fel");
  });

  it("serverns 400 unsupported_mime_type och file_too_large blir samma orsaker som klientens", async () => {
    post.mockRejectedValueOnce(
      axiosFel(400, { error: "File type is not allowed", code: "unsupported_mime_type" })
    );
    const typ = await laddaUppChip(fil());
    expect(typ).toMatchObject({ lage: "fel" });
    expect(typ.lage === "fel" && typ.orsak).toMatch(/filtypen stöds inte/);

    post.mockRejectedValueOnce(axiosFel(400, { error: "File too large", code: "file_too_large" }));
    const stor = await laddaUppChip(fil());
    expect(stor.lage === "fel" && stor.orsak).toMatch(/för stor/);
  });

  it("nätverksfel och 5xx är fel med en kort orsak", async () => {
    post.mockRejectedValueOnce(natverksFel());
    const natet = await laddaUppChip(fil());
    expect(natet.lage === "fel" && natet.orsak).toMatch(/inget svar/);

    post.mockRejectedValueOnce(axiosFel(500, "Internal Server Error"));
    const servern = await laddaUppChip(fil());
    expect(servern.lage === "fel" && servern.orsak).toMatch(/500/);
  });

  it("en otillåten fil laddas aldrig upp (testfall 46)", async () => {
    const utfall = await laddaUppChip(fil("arkiv.zip", "application/zip"));
    expect(utfall.lage).toBe("fel");
    expect(post).not.toHaveBeenCalled();
  });
});

// ─── Vad som följer med vid ↵ ─────────────────────────────────────────────

describe("bilagor — chipens id:n", () => {
  it("bara klara chip följer med; fel och laddande gör det inte (testfall 46)", () => {
    expect(
      bilagor([
        chip({ nyckel: "a", id: "src-1" }),
        chip({ nyckel: "b", lage: "fel", id: null, orsak: "för stor" }),
        chip({ nyckel: "c", lage: "laddar", id: null }),
        chip({ nyckel: "d", id: "src-2", dubblett: true }),
      ])
    ).toEqual(["src-1", "src-2"]);
  });

  it("samma underlag två gånger (en dubblett) skickas en gång", () => {
    expect(
      bilagor([chip({ nyckel: "a", id: "src-1" }), chip({ nyckel: "b", id: "src-1", dubblett: true })])
    ).toEqual(["src-1"]);
  });
});

describe("kanSkicka — ↵", () => {
  it("avstängt medan ett chip laddar upp, också med text (testfall 48)", () => {
    const chips = [chip({ lage: "laddar", id: null })];
    expect(laddarUpp(chips)).toBe(true);
    expect(kanSkicka("se kvittot", chips)).toBe(false);
  });

  it("text utan chip går", () => {
    expect(kanSkicka("hej", [])).toBe(true);
  });

  it("ett klart chip utan text går (D8)", () => {
    expect(kanSkicka("", [chip()])).toBe(true);
    expect(kanSkicka("   ", [chip()])).toBe(true);
  });

  it("varken text eller klart chip går inte — ett felchip räcker inte", () => {
    expect(kanSkicka("", [])).toBe(false);
    expect(kanSkicka("  ", [chip({ lage: "fel", id: null, orsak: "x" })])).toBe(false);
  });
});

// ─── Meddelandet ──────────────────────────────────────────────────────────

describe("skickaMeddelande — med och utan bilagor", () => {
  const svar = { thread_id: "t-1", view_key: "vk", fiscal_year_id: "fy", posts: [], cursor: 1 };

  it("utan bilagor är kroppen som förut: `attachments: []`", async () => {
    post.mockResolvedValue({ data: svar });
    await skickaMeddelande("bocker.verifikationer", "hej");
    expect(post).toHaveBeenCalledWith("/api/v1/threads/bocker.verifikationer/messages", {
      text: "hej",
      attachments: [],
    });
  });

  it("med bilagor skickas id:na, aldrig filinnehåll", async () => {
    post.mockResolvedValue({ data: svar });
    await skickaMeddelande("bocker.verifikationer", "", ["src-1", "src-2"]);
    expect(post).toHaveBeenCalledWith("/api/v1/threads/bocker.verifikationer/messages", {
      text: "",
      attachments: ["src-1", "src-2"],
    });
  });
});

// ─── Kontoutdrag som CSV (services/statement_match.py) ────────────────────

describe("kontoutdrag — en CSV i chatten", () => {
  const csv = (namn = "1930 september.csv", typ = "text/csv") => fil(namn, typ, 1_200);

  it("en csv godtas, också utan typ", () => {
    expect(kontrolleraFil({ name: "skattekonto.csv", type: "", size: 10 })).toBeNull();
    expect(kontrolleraFil({ name: "x.csv", type: "text/csv", size: 10 })).toBeNull();
  });

  it("laddas upp till /bank-inputs med bank_connection_id=auto, inte till intagskön", async () => {
    post.mockResolvedValue({
      status: 201,
      data: { id: "bi-1", status: "processed", imported_count: 4, skipped_count: 3, account_code: "1630", linked_voucher_count: 2 },
    });
    const utfall = await laddaUppChip(csv("skattekonto.csv"));
    const [url, kropp] = post.mock.calls[0];
    expect(url).toBe("/api/v1/bank-inputs");
    expect((kropp as FormData).get("bank_connection_id")).toBe("auto");
    expect(utfall).toEqual({
      lage: "klar",
      id: null,
      dubblett: false,
      kontoutdrag: { konto: "1630", nya: 4, kopplade: 2 },
    });
  });

  it("samma fil igen är klar, inte fel; okänt konto säger hur filen ska heta", async () => {
    post.mockRejectedValueOnce(axiosFel(409, { error: "dup", code: "duplicate_bank_input" }));
    expect(await laddaUppChip(csv())).toEqual({ lage: "klar", id: null, dubblett: true, kontoutdrag: null });

    post.mockRejectedValueOnce(axiosFel(400, { error: "x", code: "statement_account_unknown" }));
    const okant = await laddaUppChip(csv("utdrag.csv"));
    expect(okant.lage === "fel" && okant.orsak).toMatch(/kontokoden/);
  });

  it("chipet säger vad inläsningen gav, och ↵ går utan text", () => {
    const inlast = chip({ id: null, namn: "skattekonto.csv", kontoutdrag: { konto: "1630", nya: 4, kopplade: 2 } });
    expect(chipStatus(inlast)).toBe("inläst · kontoutdrag 1630 · 4 nya · 2 kopplade");
    expect(chipStatus(chip({ id: null, dubblett: true, kontoutdrag: null }))).toBe("klar · kontoutdraget fanns redan");
    expect(bilagor([inlast])).toEqual([]);
    expect(kanSkicka("", [inlast])).toBe(true);
  });

  it("meddelandet får en rad per kontoutdrag", () => {
    const inlast = chip({ id: null, namn: "skattekonto.csv", kontoutdrag: { konto: "1630", nya: 4, kopplade: 2 } });
    expect(kontoutdragsnotiser([inlast, chip()])).toEqual([
      "[Kontoutdrag skattekonto.csv inläst för konto 1630: 4 nya transaktioner, 2 verifikationer fick underlag.]",
    ]);
  });
});
