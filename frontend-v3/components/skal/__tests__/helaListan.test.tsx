import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { useVyer } from "@/hooks/useVyer";
import { VOUCHERS_NYCKEL } from "@/lib/chattyta/api";
import { VERIFIKATIONER_ANTAL } from "@/lib/skal/bocker";
import type { VyData } from "@/lib/skal/vydata";
import { sidan } from "@/lib/skal/vyer";

/**
 * L5 (SPEC-lasbarhet.md §4.5, M6): Postade hämtas sida för sida, och nästa
 * sida hämtas när vaktelementet sist i vyns skrollyta syns.
 */

const get = vi.fn();
vi.mock("@/lib/api", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

// ─── IntersectionObserver: jsdom har ingen; testet styr när vakten syns ────

class FalskObservator {
  static alla: FalskObservator[] = [];
  element = new Set<Element>();
  constructor(public cb: IntersectionObserverCallback) {
    FalskObservator.alla.push(this);
  }
  observe(el: Element) {
    this.element.add(el);
  }
  unobserve(el: Element) {
    this.element.delete(el);
  }
  disconnect() {
    this.element.clear();
  }
  takeRecords() {
    return [];
  }
}

/** Alla observerade element blir synliga. */
function vaktenSyns() {
  for (const o of FalskObservator.alla) {
    const poster = [...o.element].map(
      (target) => ({ target, isIntersecting: true, intersectionRatio: 1 }) as unknown as IntersectionObserverEntry
    );
    if (poster.length) o.cb(poster, o as unknown as IntersectionObserver);
  }
}

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

const verifikation = (n: number) => ({
  id: `a${n}`,
  series: "A",
  number: n,
  date: "2026-05-01",
  description: `Verifikation ${n}`,
  status: "posted",
  total_debit: 100 * n,
  missing_attachment: false,
  age_days: 0,
});

/** Serverns postade, senast först. */
let postade: ReturnType<typeof verifikation>[];

function svaraGet(url: string, config?: { params?: Record<string, unknown> }) {
  const p = config?.params ?? {};
  if (url === "/api/v1/vouchers") {
    if (p.status === "draft" || p.missing_attachment === true) {
      return Promise.resolve({ data: { total: 0, vouchers: [] } });
    }
    const offset = Number(p.offset ?? 0);
    const limit = Number(p.limit ?? 100);
    return Promise.resolve({ data: { total: postade.length, vouchers: postade.slice(offset, offset + limit) } });
  }
  if (url === "/api/v1/decisions") return Promise.resolve({ data: { decisions: [], total: 0 } });
  if (url === "/api/v1/drafts") return Promise.resolve({ data: { drafts: [], total: 0 } });
  return Promise.reject(new Error(`oväntat GET ${url}`));
}

const postadeAnrop = () =>
  get.mock.calls
    .filter(([url, c]) => url === "/api/v1/vouchers" && c?.params?.status === "posted" && c.params.missing_attachment === false)
    .map(([, c]) => c.params as Record<string, unknown>);

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
const antalRader = () => vyn().queryAllByText(/^Verifikation \d+$/).length;

const serie = (fran: number, antal: number) =>
  Array.from({ length: antal }, (_, i) => verifikation(fran - i));

beforeEach(() => {
  FalskObservator.alla = [];
  vi.stubGlobal("IntersectionObserver", FalskObservator);
  get.mockReset();
  get.mockImplementation(svaraGet);
  postade = serie(120, 120);
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Postade sida för sida (M6)", () => {
  it("första sidan är VERIFIKATIONER_ANTAL från offset 0, och `Laddar fler…` står sist", async () => {
    rendera();
    await waitFor(() => expect(antalRader()).toBe(VERIFIKATIONER_ANTAL));
    expect(postadeAnrop()).toEqual([expect.objectContaining({ offset: 0, limit: VERIFIKATIONER_ANTAL })]);
    expect(vyn().getByText("Laddar fler…")).toBeInTheDocument();
    // Rubriken räknar serverns total, inte de hämtade raderna.
    expect(vyn().getAllByText("120 postade").length).toBeGreaterThan(0);
  });

  it("nästa sida hämtas när vakten syns, tills total är nådd", async () => {
    rendera();
    await waitFor(() => expect(antalRader()).toBe(50));

    act(() => vaktenSyns());
    await waitFor(() => expect(antalRader()).toBe(100));
    expect(postadeAnrop().map((p) => p.offset)).toEqual([0, 50]);
    expect(vyn().getByText("Verifikation 71")).toBeInTheDocument();
    expect(vyn().getByText("Laddar fler…")).toBeInTheDocument();

    act(() => vaktenSyns());
    await waitFor(() => expect(antalRader()).toBe(120));
    expect(postadeAnrop().map((p) => p.offset)).toEqual([0, 50, 100]);
    // Allt är hämtat: ingen rad och ingen fler hämtning.
    expect(vyn().queryByText("Laddar fler…")).toBeNull();
    act(() => vaktenSyns());
    expect(postadeAnrop()).toHaveLength(3);
  });

  it("ingen vakt när allt ryms på första sidan", async () => {
    postade = serie(10, 10);
    rendera();
    await waitFor(() => expect(antalRader()).toBe(10));
    expect(vyn().queryByText("Laddar fler…")).toBeNull();
    act(() => vaktenSyns());
    expect(postadeAnrop()).toHaveLength(1);
  });

  it("en verifikation som hamnar på två sidor står en gång (dedupe på id)", async () => {
    rendera();
    await waitFor(() => expect(antalRader()).toBe(50));
    // En ny postning skjuter listan ett steg: A-71 står nu också på sida två.
    postade = [verifikation(121), ...postade];
    act(() => vaktenSyns());
    await waitFor(() => expect(postadeAnrop()).toHaveLength(2));
    await waitFor(() => expect(vyn().getByText("Verifikation 22")).toBeInTheDocument());
    expect(vyn().getAllByText("Verifikation 71")).toHaveLength(1);
    expect(antalRader()).toBe(99);
  });

  it("invalideringen under VOUCHERS_NYCKEL når den sidade frågan", async () => {
    rendera();
    await waitFor(() => expect(antalRader()).toBe(50));
    act(() => vaktenSyns());
    await waitFor(() => expect(antalRader()).toBe(100));

    postade = [verifikation(121), ...postade];
    act(() => {
      void qc.invalidateQueries({ queryKey: VOUCHERS_NYCKEL });
    });
    await waitFor(() => expect(vyn().getByText("Verifikation 121")).toBeInTheDocument());
    await waitFor(() => expect(vyn().getAllByText("121 postade").length).toBeGreaterThan(0));
  });
});

describe("VyInnehall och VyData", () => {
  const DATA: VyData = {
    lage: "normal",
    status: "3 postade",
    period: "2026",
    sektioner: [{ titel: "Postade", rader: [{ id: "a", titel: "Rad", hoger: "1" }] }],
    fot: "Foten",
  };

  it("en vy utan harFler har ingen vakt och ingen observatör", () => {
    render(<VyInnehall vy={VERIFIKATIONER} data={DATA} />);
    expect(screen.queryByText("Laddar fler…")).toBeNull();
    expect(FalskObservator.alla).toHaveLength(0);
  });

  it("vakten anropar hamtaFler när den syns", () => {
    const hamtaFler = vi.fn();
    render(<VyInnehall vy={VERIFIKATIONER} data={{ ...DATA, harFler: true, hamtaFler }} />);
    expect(screen.getByText("Laddar fler…")).toBeInTheDocument();
    act(() => vaktenSyns());
    expect(hamtaFler).toHaveBeenCalledTimes(1);
  });
});
