import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VyRad } from "@/components/skal/VyRad";
import {
  kvittoKalla,
  verifikationerVy,
  type Kallkontext,
  type Verifikation,
  type Verifikationslista,
} from "@/lib/skal/bocker";

/**
 * FU23 — kvittot från verifikationen (SPEC-flode-underlag.md §10.4,
 * klientdelen av testfall 49d). `/v4` har ingen raddetalj (avvikelse 6):
 * raden får en länk, och källan hämtas ur `GET /vouchers/{id}/source-context`
 * först när länken används.
 */

const get = vi.fn();
vi.mock("@/lib/api", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };
const v = (over: Partial<Verifikation>): Verifikation => ({
  id: "x",
  series: "A",
  number: 1,
  date: "2026-06-01",
  description: "Kontorsmaterial",
  status: "posted",
  total_debit: 100000,
  missing_attachment: false,
  age_days: 0,
  ...over,
});
const lista = (...vouchers: Verifikation[]): Verifikationslista => ({ total: vouchers.length, vouchers });

/** `api/routes/vouchers.py::get_voucher_source_context`, källans form. */
const kalla = (over: Record<string, unknown> = {}) => ({
  kind: "voucher_source",
  id: "src-1",
  status: "processed",
  original_filename: "kvitto-elektronikhuset.pdf",
  mime_type: "application/pdf",
  size_bytes: 218000,
  download_url: "/api/v1/intake/src-1/file",
  linked_at: "2026-06-03T08:20:00",
  linked_by: "agent",
  link_reason: "exact_match interpretation=i-1",
  ...over,
});
const bankfil = { kind: "bank_input", id: "b-1", original_filename: "kontoutdrag.csv" };
const kontext = (source_material: unknown[]): Kallkontext => ({ source_material }) as Kallkontext;

// ─── Vilka rader får länken ───────────────────────────────────────────────

describe("vilka rader bär länken", () => {
  const rader = () => {
    const vy = verifikationerVy(
      AR,
      lista(
        v({ id: "a118", number: 118, referenced_by: { id: "a121", series: "A", number: 121 } }),
        v({ id: "a121", number: 121 }),
        v({ id: "b7", series: "B", number: 7, corrects: { id: "a1", series: "A", number: 1 } })
      ),
      lista(v({ id: "u", status: "draft", number: null })),
      { beslut: [], forslag: [], saknar: lista(v({ id: "a109", number: 109, missing_attachment: true, age_days: 12 })) }
    );
    return new Map(vy.sektioner.flatMap((s) => s.rader).map((r) => [r.id, r]));
  };

  it("postade med underlag: kopplat kvitto (A-118) och hänvisning (A-121)", () => {
    const r = rader();
    expect(r.get("a118")?.kvitto).toEqual({ voucherId: "a118", nummer: "A-118" });
    expect(r.get("a121")?.kvitto).toEqual({ voucherId: "a121", nummer: "A-121" });
  });

  it("inte en rad som saknar underlag, inte ett utkast och inte en rättelse (dess underlag är originalet)", () => {
    const r = rader();
    expect(r.get("a109")?.kvitto).toBeUndefined();
    expect(r.get("u")?.kvitto).toBeUndefined();
    expect(r.get("b7")?.kvitto).toBeUndefined();
  });

  it("vyn hämtar ingenting per rad", () => {
    rader();
    expect(get).not.toHaveBeenCalled();
  });
});

describe("kvittoKalla — vilken källa länken öppnar", () => {
  it("den kopplade källan", () => {
    expect(kvittoKalla(kontext([bankfil, kalla()]))).toBe("src-1");
  });

  it("för A-121: kvittot via A-118 (hänvisningen, FU16)", () => {
    expect(
      kvittoKalla(kontext([kalla({ id: "src-via", via_voucher_id: "a118", via_voucher_number: "A-118" })]))
    ).toBe("src-via");
  });

  it("en direkt kopplad källa före en via hänvisning", () => {
    expect(kvittoKalla(kontext([kalla({ id: "src-via", via_voucher_id: "a118" }), kalla({ id: "src-egen" })]))).toBe(
      "src-egen"
    );
  });

  it("bara bankfiler, eller inget alls: ingen källa", () => {
    expect(kvittoKalla(kontext([bankfil]))).toBeNull();
    expect(kvittoKalla(kontext([]))).toBeNull();
    expect(kvittoKalla({} as Kallkontext)).toBeNull();
  });
});

// ─── Länken ───────────────────────────────────────────────────────────────

describe("länken på raden (49d)", () => {
  const oppna = vi.fn();
  let fonster: { location: { href: string }; close: () => void };

  beforeEach(() => {
    get.mockReset();
    fonster = { location: { href: "" }, close: vi.fn() };
    oppna.mockReset();
    oppna.mockReturnValue(fonster);
    vi.stubGlobal("open", oppna);
    URL.createObjectURL = vi.fn(() => "blob:kvitto") as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
  });
  afterEach(() => vi.unstubAllGlobals());

  const svara = (ctx: unknown) =>
    get.mockImplementation((url: string) =>
      url.endsWith("/source-context")
        ? Promise.resolve({ data: ctx })
        : Promise.resolve({ data: new Blob(["%PDF"], { type: "application/pdf" }) })
    );

  it("hämtar source-context först när länken används, sedan filen som blob", async () => {
    svara({ source_material: [kalla({ id: "src-9" })] });
    render(<VyRad titel="Förbrukningsinventarier" meta="A-118 · 2026-06-03" hoger="4 480" kvitto={{ voucherId: "a118", nummer: "A-118" }} />);
    expect(get).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Öppna kvittot till A-118" }));
    expect(oppna).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(fonster.location.href).toBe("blob:kvitto"));
    expect(get).toHaveBeenNthCalledWith(1, "/api/v1/vouchers/a118/source-context");
    expect(get).toHaveBeenNthCalledWith(2, "/api/v1/intake/src-9/file", { responseType: "blob" });
  });

  it("A-121 öppnar kvittot via A-118", async () => {
    svara({ source_material: [kalla({ id: "src-via", via_voucher_id: "a118", via_voucher_number: "A-118" })] });
    render(<VyRad titel="Korrigering pantavgift" meta="A-121 · 2026-06-03" hoger="120" kvitto={{ voucherId: "a121", nummer: "A-121" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Öppna kvittot till A-121" }));
    await waitFor(() => expect(get).toHaveBeenCalledWith("/api/v1/intake/src-via/file", { responseType: "blob" }));
  });

  it("utan kvitto i kontexten: fönstret stängs och raden säger det", async () => {
    svara({ source_material: [bankfil] });
    render(<VyRad titel="Hyra" meta="A-116 · 2026-06-01" hoger="9 400" kvitto={{ voucherId: "a116", nummer: "A-116" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Öppna kvittot till A-116" }));
    await waitFor(() => expect(screen.getByText("inget kvitto")).toBeInTheDocument());
    expect(fonster.close).toHaveBeenCalled();
  });

  it("ett fel: raden säger att kvittot inte kunde öppnas", async () => {
    get.mockImplementationOnce(() => Promise.reject(new Error("500")));
    render(<VyRad titel="Hyra" meta="A-116 · 2026-06-01" hoger="9 400" kvitto={{ voucherId: "a116", nummer: "A-116" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Öppna kvittot till A-116" }));
    await waitFor(() => expect(screen.getByText("kunde inte öppnas")).toBeInTheDocument());
  });

  it("en rad utan kvitto har ingen länk", () => {
    render(<VyRad titel="Hyra" meta="A-116" hoger="9 400" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
