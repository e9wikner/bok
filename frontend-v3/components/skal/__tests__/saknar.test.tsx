import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { useVyer } from "@/hooks/useVyer";
import { VOUCHERS_NYCKEL } from "@/lib/chattyta/api";
import { kopplingKlar } from "@/lib/chattyta/kopplingar";
import { sidan } from "@/lib/skal/vyer";

/**
 * FU21 genom `useVyer` (SPEC-flode-underlag.md §10.4; testfall 49b, 49c):
 * frågorna som vyn ställer, och en koppling som når vyn så som `useTrad`
 * lämnar den — `kopplingKlar`, sedan invalideringen av `vouchers`.
 */

const get = vi.fn();
vi.mock("@/lib/api", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

const verifikation = (over: Record<string, unknown>) => ({
  series: "A",
  status: "posted",
  missing_attachment: false,
  age_days: 0,
  ...over,
});
const a118 = verifikation({
  id: "a118",
  number: 118,
  date: "2026-06-03",
  description: "Förbrukningsinventarier",
  total_debit: 448000,
  missing_attachment: true,
  age_days: 3,
});
const a109 = verifikation({
  id: "a109",
  number: 109,
  date: "2026-05-25",
  description: "Resa Göteborg",
  total_debit: 124000,
  missing_attachment: true,
  age_days: 12,
});
const a117 = verifikation({ id: "a117", number: 117, date: "2026-05-31", description: "Ellevio · elnät maj", total_debit: 218000 });

let server: { postade: unknown[]; saknar: unknown[] };

function svaraGet(url: string, config?: { params?: Record<string, unknown> }) {
  const p = config?.params ?? {};
  if (url === "/api/v1/vouchers") {
    const lista = p.status === "draft" ? [] : p.missing_attachment === true ? server.saknar : server.postade;
    return Promise.resolve({ data: { total: lista.length, vouchers: lista } });
  }
  if (url === "/api/v1/decisions") return Promise.resolve({ data: { decisions: [], total: 0 } });
  if (url === "/api/v1/drafts") return Promise.resolve({ data: { drafts: [], total: 0 } });
  return Promise.reject(new Error(`oväntat GET ${url}`));
}

const VERIFIKATIONER = sidan("bocker").vyer.find((v) => v.key === "bocker.verifikationer")!;

function Vyn() {
  const { data, laddar } = useVyer(AR, "bocker")["bocker.verifikationer"];
  return (
    <div data-testid="vyn">
      <VyInnehall vy={VERIFIKATIONER} data={data} laddar={laddar} />
    </div>
  );
}

let qc: QueryClient;
const rendera = () =>
  render(
    <QueryClientProvider client={qc}>
      <Vyn />
    </QueryClientProvider>
  );
const vyn = () => within(screen.getByTestId("vyn"));
const sektionsTitlar = () =>
  vyn()
    .queryAllByText(/^(Väntar på beslut|Saknar underlag|Postade|Utkast)$/)
    .map((el) => el.textContent);
const radFor = (titel: string) => vyn().getByText(titel).closest("[data-variant]") as HTMLElement;

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(svaraGet);
  server = { postade: [a117], saknar: [a109, a118] };
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe("frågorna (testfall 49b)", () => {
  it("Saknar underlag med missing_attachment=true&sort_by=age; Postade med missing_attachment=false", async () => {
    rendera();
    await waitFor(() => expect(sektionsTitlar()).toEqual(["Saknar underlag", "Postade"]));
    const vouchers = get.mock.calls.filter(([url]) => url === "/api/v1/vouchers").map(([, c]) => c.params);
    expect(vouchers).toContainEqual(
      expect.objectContaining({ status: "posted", missing_attachment: true, sort_by: "age", fiscal_year_id: "fy" })
    );
    expect(vouchers).toContainEqual(
      expect.objectContaining({ status: "posted", missing_attachment: false, sort_by: "date" })
    );
    expect(radFor("Resa Göteborg").getAttribute("data-variant")).toBe("saknar");
    expect(vyn().getByText("A-109 · kvitto saknas sedan 12 dgr")).toBeInTheDocument();
    expect(
      vyn().getByText(
        "Underlag kan släppas i chatten när som helst. Agenten kopplar det till rätt verifikation och säger till om något inte stämmer."
      )
    ).toBeInTheDocument();
  });
});

describe("en koppling (testfall 49c)", () => {
  it("raden flyttar till Postade som ny med `kvitto kopplat HH:MM`, utan omladdning", async () => {
    rendera();
    await waitFor(() => expect(radFor("Förbrukningsinventarier").getAttribute("data-variant")).toBe("saknar"));

    // Servern har kopplat; händelsen kommer som useTrad lämnar den.
    server = { postade: [{ ...a118, missing_attachment: false }, a117], saknar: [a109] };
    act(() => {
      kopplingKlar(qc, "a118", "src-1", new Date(2026, 5, 3, 8, 20));
      void qc.invalidateQueries({ queryKey: VOUCHERS_NYCKEL });
    });

    await waitFor(() => expect(radFor("Förbrukningsinventarier").getAttribute("data-variant")).toBe("ny"));
    // Metaraden bär också kvittolänken (FU23).
    expect(vyn().getByText(/^A-118 · kvitto kopplat 08:20/)).toBeInTheDocument();
    expect(vyn().getAllByText("Förbrukningsinventarier")).toHaveLength(1);
    await waitFor(() => expect(vyn().queryByText("A-118 · kvitto saknas sedan 3 dgr")).toBeNull());
  });

  it("den sista kompletteringen tar sektionen med sig", async () => {
    server = { postade: [a117], saknar: [a118] };
    rendera();
    await waitFor(() => expect(sektionsTitlar()).toEqual(["Saknar underlag", "Postade"]));

    server = { postade: [{ ...a118, missing_attachment: false }, a117], saknar: [] };
    act(() => {
      kopplingKlar(qc, "a118", "src-1");
      void qc.invalidateQueries({ queryKey: VOUCHERS_NYCKEL });
    });
    await waitFor(() => expect(sektionsTitlar()).toEqual(["Postade"]));
  });
});
