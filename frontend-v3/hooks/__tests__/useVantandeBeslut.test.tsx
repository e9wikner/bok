import { readFileSync } from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { beslutMarkeNyckel, useVantandeBeslut } from "@/hooks/useVantandeBeslut";
import {
  BESLUT_NYCKEL,
  hamtaBeslut,
  type BeslutListSvar,
  type BeslutSvar,
} from "@/lib/chattyta/api";
import * as skalMock from "@/lib/skal/mock";

// ─── Mockar ───────────────────────────────────────────────────────────────

const get = vi.fn();
vi.mock("@/lib/api", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

// ─── Hjälpare ─────────────────────────────────────────────────────────────

const beslut = (over: Partial<BeslutSvar> = {}): BeslutSvar => ({
  id: "d-1",
  view_key: "bocker.verifikationer",
  kind: "abstention",
  status: "open",
  title: "Swish-inbetalning utan referens",
  amount_ore: 450000,
  reason: "Ingen referens på inbetalningen.",
  consequence: "Beloppet står kvar på 1930 utan motkonto.",
  source: { kind: "bank_transaction", id: "bt-9", date: "2026-06-12" },
  age_days: 3,
  thread_id: "t-1",
  post_id: "p-1",
  options: [],
  ...over,
});

const svar = (over: Partial<BeslutListSvar> = {}) => ({
  data: { decisions: [], total: 0, ...over } satisfies BeslutListSvar,
});

let qc: QueryClient;
function montera(viewKey: string, aktiv?: boolean) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return renderHook(() => useVantandeBeslut(viewKey, aktiv === undefined ? undefined : { aktiv }), {
    wrapper,
  });
}

beforeEach(() => {
  get.mockReset();
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

// ─── hamtaBeslut ──────────────────────────────────────────────────────────

describe("hamtaBeslut", () => {
  it("läser GET /decisions med serverns parameternamn", async () => {
    get.mockResolvedValue(svar({ total: 2 }));
    const ut = await hamtaBeslut({ viewKey: "bocker.balans", status: "all", limit: 200, offset: 0 });
    expect(get).toHaveBeenCalledWith("/api/v1/decisions", {
      params: { view_key: "bocker.balans", status: "all", limit: 200, offset: 0 },
    });
    expect(ut.total).toBe(2);
  });
});

// ─── Testfall 21: märket ──────────────────────────────────────────────────

describe("märket = serverns total ur status=open (testfall 21)", () => {
  it("frågar status=open, limit=1 för vyn (testfall 21)", async () => {
    get.mockResolvedValue(svar({ total: 1, decisions: [beslut()] }));
    const { result } = montera("bocker.verifikationer");
    await waitFor(() => expect(result.current).toBe(1));
    expect(get).toHaveBeenCalledTimes(1);
    const [url, { params }] = get.mock.calls[0];
    expect(url).toBe("/api/v1/decisions");
    expect(params).toMatchObject({ view_key: "bocker.verifikationer", status: "open", limit: 1 });
  });

  it("syntetiska beslut räknas: märket är total, inte de sidade raderna (testfall 21)", async () => {
    // `limit=1` ger ETT beslut — ett syntetiskt `intake` — men unionen har
    // tre. Klienten räknar inte själv och filtrerar ingenting (§10).
    get.mockResolvedValue(
      svar({
        total: 3,
        decisions: [beslut({ id: "intake:u-7", kind: "intake", thread_id: null, post_id: null })],
      })
    );
    const { result } = montera("bocker.verifikationer");
    await waitFor(() => expect(result.current).toBe(3));
  });

  it("noll väntande ger 0", async () => {
    get.mockResolvedValue(svar({ total: 0 }));
    const { result } = montera("bocker.balans");
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(result.current).toBe(0);
  });

  it("frågenyckeln ligger under BESLUT_NYCKEL, så att useTrads invalidering träffar den (§7)", async () => {
    expect(beslutMarkeNyckel("bocker.balans").slice(0, BESLUT_NYCKEL.length)).toEqual([
      ...BESLUT_NYCKEL,
    ]);
    get.mockResolvedValueOnce(svar({ total: 1 })).mockResolvedValueOnce(svar({ total: 2 }));
    const { result } = montera("bocker.balans");
    await waitFor(() => expect(result.current).toBe(1));
    await qc.invalidateQueries({ queryKey: BESLUT_NYCKEL });
    await waitFor(() => expect(result.current).toBe(2));
  });

  it("aktiv: false frågar inte (desktop har inget märke)", async () => {
    const { result } = montera("bocker.balans", false);
    await new Promise((r) => setTimeout(r, 20));
    expect(get).not.toHaveBeenCalled();
    expect(result.current).toBe(0);
  });
});

// ─── Testfall 32, beslutshalvan ───────────────────────────────────────────

describe("mocken för beslutsmärket är borta (testfall 32)", () => {
  it("lib/skal/mock exporterar ingen mockVantandeBeslut (testfall 32)", () => {
    expect("mockVantandeBeslut" in skalMock).toBe(false);
  });

  it("varken mock.ts eller Skal.tsx nämner mockVantandeBeslut (testfall 32)", () => {
    const rot = path.resolve(__dirname, "../..");
    for (const fil of ["lib/skal/mock.ts", "components/skal/Skal.tsx"]) {
      expect(readFileSync(path.join(rot, fil), "utf8")).not.toMatch(/\bmockVantandeBeslut\b/);
    }
  });
});
