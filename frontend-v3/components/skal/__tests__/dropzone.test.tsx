import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DropzoneVy } from "@/components/skal/DropzoneVy";
import { type DropzoneOversikt, dropzoneStatus } from "@/lib/skal/dropzone";
import { allaVyer } from "@/lib/skal/vyer";

/** Dropzonen i webben: mapparna är släppytor, filen läggs i mappen på servern. */

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

const NU = Date.parse("2026-11-08T12:00:00Z");

const oversikt = (over: Partial<DropzoneOversikt> = {}): DropzoneOversikt => ({
  enabled: true,
  quiet_seconds: 30,
  scan_interval_seconds: 60,
  max_bytes: 10 * 1024 * 1024,
  targets: [
    { folder: "Kvitton", label: "Kvitton", kind: "voucher_source", source_type: "receipt", account_code: null, account_name: null, pending_count: 0 },
    { folder: "Kontoutdrag/1930 Företagskonto", label: "1930 Företagskonto", kind: "bank_input", source_type: null, account_code: "1930", account_name: "Företagskonto", pending_count: 0 },
    { folder: "SIE4-import", label: "SIE4-import", kind: "sie4_import", source_type: null, account_code: null, account_name: null, pending_count: 0 },
  ],
  pending: [],
  problems: [],
  ingested: [],
  status: {
    enabled: true,
    dropzone_dir: "/app/dropzone",
    scan_interval_seconds: 60,
    last_scan_at: "2026-11-08T11:59:30Z",
    last_scan_duration_ms: 3,
    pending_file_count: 0,
    ingested_total: 0,
    problem_file_count: 0,
    unknown_account_folders: [],
    last_error: null,
  },
  ...over,
});

function visa() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DropzoneVy titel="Dropzone" variant="desktop" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("kartan", () => {
  it("dropzonen är en vy på Böcker som chattar i Verifikationers tråd", () => {
    const vy = allaVyer().find((v) => v.key === "bocker.dropzone");
    expect(vy).toMatchObject({ sida: "bocker", slug: "dropzone", trad: "bocker.verifikationer" });
  });
});

describe("statusraden", () => {
  it("säger när skannern har stannat, när den är avstängd och vad som väntar", () => {
    const gammal = { ...oversikt().status, last_scan_at: "2026-11-08T11:00:00Z" };
    expect(dropzoneStatus(oversikt({ status: gammal }), false, NU).lage).toBe("fel");
    expect(dropzoneStatus(oversikt({ enabled: false }), false, NU).text).toBe("avstängd på servern");
    const fil = { folder: "Kvitton", filename: "a.pdf", size_bytes: 1, modified_at: "2026-11-08T11:59:00Z" };
    expect(dropzoneStatus(oversikt({ pending: [fil] }), false, NU).text).toBe("1 väntar på hämtning");
    expect(dropzoneStatus(oversikt(), false, NU).text).toBe("inget väntar");
  });
});

describe("släpp", () => {
  it("flera filer som släpps på en mapp skickas i ett anrop till den mappen", async () => {
    get.mockResolvedValue({ data: oversikt() });
    post.mockResolvedValue({
      data: {
        folder: "Kvitton",
        results: [
          { ok: true, original_filename: "taxi.pdf", folder: "Kvitton", filename: "taxi.pdf", size_bytes: 3 },
          { ok: true, original_filename: "lunch.pdf", folder: "Kvitton", filename: "lunch (2).pdf", size_bytes: 3 },
          { ok: false, original_filename: "notis.txt", error: "En .txt-fil läses aldrig som underlag", code: "sidecar_filename" },
        ],
      },
    });
    visa();

    const ruta = await screen.findByTestId("dropzone-mal-Kvitton");
    const filer = [
      new File(["pdf"], "taxi.pdf", { type: "application/pdf" }),
      new File(["pdf"], "lunch.pdf", { type: "application/pdf" }),
      new File(["x"], "notis.txt", { type: "text/plain" }),
    ];
    fireEvent.drop(ruta, { dataTransfer: { files: filer, types: ["Files"] } });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, form] = post.mock.calls[0] as [string, FormData];
    expect(url).toBe("/api/v1/intake/dropzone/files");
    expect(form.get("folder")).toBe("Kvitton");
    expect(form.getAll("files").map((f) => (f as File).name)).toEqual(["taxi.pdf", "lunch.pdf", "notis.txt"]);
    expect(form.get("comment")).toBeNull();
    expect(await screen.findByText("lunch (2).pdf")).toBeInTheDocument();
    expect(screen.getAllByText(/lagd i Kvitton\//)).toHaveLength(2);
    expect(screen.getByText(/läses aldrig som underlag/)).toBeInTheDocument();
  });

  it("filväljaren tar flera filer, och det finns inget kommentarsfält", async () => {
    get.mockResolvedValue({ data: oversikt() });
    const { container } = visa();
    await screen.findByTestId("dropzone-mal-Kvitton");
    const valjare = container.querySelectorAll('input[type="file"]');
    expect(valjare.length).toBe(3);
    valjare.forEach((v) => expect(v).toHaveAttribute("multiple"));
    expect(container.querySelector("textarea")).toBeNull();
  });

  it("mapparna står som i utdelningen, kontomapparna under Kontoutdrag/", async () => {
    get.mockResolvedValue({ data: oversikt() });
    visa();
    await screen.findByTestId("dropzone-mal-Kvitton");
    expect(screen.getByText("Kvitton/")).toBeInTheDocument();
    expect(screen.getByText("Kontoutdrag/")).toBeInTheDocument();
    expect(screen.getByText("1930 Företagskonto/")).toBeInTheDocument();
    expect(screen.getByText("SIE4-import/")).toBeInTheDocument();
  });

  it("serverns avvisning av hela släppet står på varje fil", async () => {
    get.mockResolvedValue({ data: oversikt() });
    post.mockRejectedValue({ response: { data: { detail: { error: "Mappen finns inte i dropzonen.", code: "unknown_dropzone_folder" } } } });
    visa();

    const ruta = await screen.findByTestId("dropzone-mal-SIE4-import");
    fireEvent.drop(ruta, { dataTransfer: { files: [new File(["x"], "a.se"), new File(["y"], "b.se")], types: ["Files"] } });

    await waitFor(() => expect(screen.getAllByText("Mappen finns inte i dropzonen.")).toHaveLength(2));
  });

  it("avstängd dropzone tar inte emot filer", async () => {
    get.mockResolvedValue({ data: oversikt({ enabled: false }) });
    visa();

    const ruta = await screen.findByTestId("dropzone-mal-Kvitton");
    expect(screen.getByRole("button", { name: "Lägg filer i Kvitton" })).toBeDisabled();
    fireEvent.drop(ruta, { dataTransfer: { files: [new File(["x"], "a.pdf")], types: ["Files"] } });
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText(/avstängd på servern \(DROPZONE_ENABLED\)/)).toBeInTheDocument();
  });

  it("_Problem visar varför filen avvisades", async () => {
    get.mockResolvedValue({
      data: oversikt({
        problems: [{ folder: "_Problem", filename: "trasig.pdf", size_bytes: 1, modified_at: "2026-11-08T11:00:00Z", reason: "Filen kunde inte läsas." }],
      }),
    });
    visa();
    expect(await screen.findByText("trasig.pdf")).toBeInTheDocument();
    expect(screen.getByText(/Filen kunde inte läsas\./)).toBeInTheDocument();
  });
});
