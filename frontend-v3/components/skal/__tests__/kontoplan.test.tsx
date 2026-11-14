import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DetaljProvider } from "@/components/skal/DetaljKontext";
import { KontoplanVy } from "@/components/skal/KontoplanVy";
import { type Konto, kontoklasser, kontoMeta, kontoplanStatus } from "@/lib/skal/kontoplan";
import { allaVyer } from "@/lib/skal/vyer";

/** Kontoplanen i skalet: BAS-kontona per kontoklass, med sökning. */

const get = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a) },
}));

const konto = (code: string, name: string, over: Partial<Konto> = {}): Konto => ({
  code,
  name,
  account_type: "asset",
  vat_code: null,
  sru_code: null,
  active: true,
  ...over,
});

const KONTON = [
  konto("3011", "Försäljning tjänster", { account_type: "revenue", vat_code: "MP1", sru_code: "7410" }),
  konto("1930", "Företagskonto"),
  konto("6110", "Kontorsmateriel", { account_type: "expense" }),
  konto("5010", "Lokalhyra", { account_type: "expense" }),
  konto("1510", "Kundfordringar"),
];

function visa() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <KontoplanVy titel="Kontoplan" variant="desktop" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
});

describe("kartan", () => {
  it("kontoplanen är en vy under Inställningar som chattar i Verifikationers tråd", () => {
    const vy = allaVyer().find((v) => v.key === "installningar.kontoplan");
    expect(vy).toMatchObject({ sida: "installningar", slug: "kontoplan", trad: "bocker.verifikationer" });
  });
});

describe("kontoklasser", () => {
  it("grupperar per kontoklass i ordning, med klass 5 och 6 under en rubrik", () => {
    const klasser = kontoklasser(KONTON);
    expect(klasser.map((k) => [k.klass, k.konton.map((x) => x.code)])).toEqual([
      ["1", ["1510", "1930"]],
      ["3", ["3011"]],
      ["5–6", ["5010", "6110"]],
    ]);
  });

  it("söker på början av numret eller var som helst i namnet", () => {
    expect(kontoklasser(KONTON, "19").flatMap((k) => k.konton.map((x) => x.code))).toEqual(["1930"]);
    expect(kontoklasser(KONTON, "HYRA").flatMap((k) => k.konton.map((x) => x.code))).toEqual(["5010"]);
    expect(kontoklasser(KONTON, "30").flatMap((k) => k.konton.map((x) => x.code))).toEqual(["3011"]);
  });

  it("visar moms- och SRU-kod bara när de finns", () => {
    expect(kontoMeta(KONTON[0])).toBe("moms MP1 · SRU 7410");
    expect(kontoMeta(KONTON[1])).toBe("");
  });

  it("säger hur många konton planen har", () => {
    expect(kontoplanStatus(KONTON, false)).toEqual({ text: "5 konton", lage: "normal" });
    expect(kontoplanStatus(undefined, true).lage).toBe("fel");
  });
});

describe("vyn", () => {
  it("listar kontona under sina klassrubriker och filtrerar på söktermen", async () => {
    get.mockResolvedValue({ data: { accounts: KONTON, total: KONTON.length } });
    visa();

    await waitFor(() => expect(screen.getAllByTestId("konto")).toHaveLength(5));
    expect(get).toHaveBeenCalledWith("/api/v1/accounts");
    expect(screen.getByText("1 · Tillgångar")).toBeInTheDocument();
    expect(screen.getByText("5–6 · Övriga externa kostnader")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Sök konto"), { target: { value: "kund" } });
    expect(screen.getAllByTestId("konto")).toHaveLength(1);
    expect(screen.getByText("Kundfordringar")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Sök konto"), { target: { value: "xyz" } });
    expect(screen.queryAllByTestId("konto")).toHaveLength(0);
    expect(screen.getByText(/Inget konto matchar/)).toBeInTheDocument();
  });

  it("ett konto öppnar sin huvudbok i detaljlagret", async () => {
    get.mockResolvedValue({ data: { accounts: KONTON, total: KONTON.length } });
    const oppna = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <DetaljProvider value={{ stack: [], oppna, bakat: vi.fn(), stang: vi.fn() }}>
          <KontoplanVy titel="Kontoplan" variant="desktop" />
        </DetaljProvider>
      </QueryClientProvider>
    );
    fireEvent.click(await screen.findByText("Företagskonto"));
    expect(oppna).toHaveBeenCalledWith({ typ: "konto", kod: "1930" });
  });

  it("säger till när kontoplanen inte kan läsas", async () => {
    get.mockRejectedValue(new Error("nere"));
    visa();
    expect(await screen.findByText(/Kontoplanen kunde inte läsas/)).toBeInTheDocument();
  });
});
