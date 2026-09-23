import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthContext, type AuthContextType } from "@/hooks/useAuth";
import { useTrad } from "@/hooks/useTrad";
import { BESLUT_NYCKEL, OVERVIEW_NYCKEL, type TradSvar } from "@/lib/chattyta/api";
import type { SseHandelse, StromAlternativ } from "@/lib/chattyta/strom";
import type { RaInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_AGENT_TEXT, FIXTUR_USER_TEXT } from "@/lib/chattyta/__fixtures__/inlagg";

// ─── Mockar ───────────────────────────────────────────────────────────────

const hamtaTrad = vi.fn();
const skickaMeddelande = vi.fn();
vi.mock("@/lib/chattyta/api", async (original) => ({
  ...(await original<typeof import("@/lib/chattyta/api")>()),
  hamtaTrad: (...a: unknown[]) => hamtaTrad(...a),
  skickaMeddelande: (...a: unknown[]) => skickaMeddelande(...a),
}));

/** Strömmen står öppen tills signalen avbryts, som den riktiga. */
const oppnaStrom = vi.fn(
  (a: StromAlternativ) =>
    new Promise<void>((klar) => a.signal.addEventListener("abort", () => klar()))
);
vi.mock("@/lib/chattyta/strom", () => ({
  oppnaStrom: (a: StromAlternativ) => oppnaStrom(a),
}));

// ─── Hjälpare ─────────────────────────────────────────────────────────────

const agent = (id: string, seq: number, text: string, run_id: string | null = null): RaInlagg => ({
  ...FIXTUR_AGENT_TEXT,
  id,
  seq,
  body: { text },
  traces: null,
  run_id,
});
const du = (id: string, seq: number, text: string): RaInlagg => ({
  ...FIXTUR_USER_TEXT,
  id,
  seq,
  body: { text },
});

const trad = (over: Partial<TradSvar> = {}): TradSvar => ({
  view_key: "verifikationer",
  thread_id: "t-1",
  fiscal_year_id: "fy-2026",
  model: null,
  posts: [],
  cursor: 0,
  archive_fiscal_year_ids: [],
  ...over,
});

/** Ett löfte som testet självt löser — för att se läget medan POST är i flykt. */
function uppskjutet<T>() {
  let losa!: (v: T) => void;
  let avvisa!: (e: unknown) => void;
  const lofte = new Promise<T>((l, a) => {
    losa = l;
    avvisa = a;
  });
  return { lofte, losa, avvisa };
}

let qc: QueryClient;
const logout = vi.fn();

function montera(viewKey = "verifikationer") {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <AuthContext.Provider value={{ logout } as unknown as AuthContextType}>
        {children}
      </AuthContext.Provider>
    </QueryClientProvider>
  );
  return renderHook(({ vk }) => useTrad(vk), { wrapper, initialProps: { vk: viewKey } });
}

/** Skickar en händelse genom den senast öppnade strömmen. */
function sand(event: string, data: unknown, index = oppnaStrom.mock.calls.length - 1) {
  const { onHandelse } = oppnaStrom.mock.calls[index][0];
  act(() => onHandelse({ event, data } satisfies SseHandelse));
}

const idn = (r: { current: ReturnType<typeof useTrad> }) => r.current.inlagg.map((i) => i.id);

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  hamtaTrad.mockReset();
  skickaMeddelande.mockReset();
  oppnaStrom.mockClear();
  logout.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ─── GET och strömmen ─────────────────────────────────────────────────────

describe("useTrad — GET och strömmen (§6.2)", () => {
  it("läser tråden vid montering och öppnar strömmen från cursor", async () => {
    hamtaTrad.mockResolvedValue(trad({ posts: [agent("p-1", 1, "hej")], cursor: 1 }));
    const { result } = montera();
    expect(result.current.laddar).toBe(true);
    await waitFor(() => expect(result.current.laddar).toBe(false));

    expect(hamtaTrad).toHaveBeenCalledWith("verifikationer");
    expect(idn(result)).toEqual(["p-1"]);
    expect(oppnaStrom).toHaveBeenCalledTimes(1);
    expect(oppnaStrom.mock.calls[0][0]).toMatchObject({ viewKey: "verifikationer", since: 1 });
  });

  it("401 på strömmen går till samma utloggning som resten av appen (§6.2 punkt 6)", async () => {
    hamtaTrad.mockResolvedValue(trad());
    montera();
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalled());
    oppnaStrom.mock.calls[0][0].onObehorig?.();
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("tom tråd: ingen ström öppnas; första POST öppnar den från svarets cursor (testfall 8)", async () => {
    hamtaTrad.mockResolvedValue(trad({ thread_id: null, posts: [], cursor: 0 }));
    const { result } = montera();
    await waitFor(() => expect(result.current.laddar).toBe(false));
    expect(oppnaStrom).not.toHaveBeenCalled();

    skickaMeddelande.mockResolvedValue({
      thread_id: "t-ny",
      view_key: "verifikationer",
      fiscal_year_id: "fy-2026",
      posts: [du("p-1", 1, "Första frågan")],
      cursor: 1,
    });
    await act(() => result.current.skicka("Första frågan"));

    expect(skickaMeddelande).toHaveBeenCalledWith("verifikationer", "Första frågan");
    expect(oppnaStrom).toHaveBeenCalledTimes(1);
    expect(oppnaStrom.mock.calls[0][0]).toMatchObject({ viewKey: "verifikationer", since: 1 });
    expect(idn(result)).toEqual(["p-1"]);
  });

  it("en andra POST öppnar ingen andra ström (testfall 8)", async () => {
    hamtaTrad.mockResolvedValue(trad({ posts: [agent("p-1", 1, "hej")], cursor: 1 }));
    const { result } = montera();
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalledTimes(1));

    skickaMeddelande.mockResolvedValue({
      thread_id: "t-1",
      view_key: "verifikationer",
      fiscal_year_id: "fy-2026",
      posts: [du("p-2", 2, "igen")],
      cursor: 2,
    });
    await act(() => result.current.skicka("igen"));
    await act(() => result.current.skicka("igen"));
    expect(oppnaStrom).toHaveBeenCalledTimes(1);
  });

  it("strömmens händelser når tråden: deltan, sedan det lagrade inlägget (testfall 10)", async () => {
    hamtaTrad.mockResolvedValue(trad({ posts: [du("p-1", 1, "fråga")], cursor: 1 }));
    const { result } = montera();
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalled());

    sand("message.created", { id: "streaming-r-1", type: "agent_text", actor: "agent", run_id: "r-1" });
    sand("message.delta", { id: "streaming-r-1", activity: "las_bankhandelser" });
    expect(result.current.strommande).toMatchObject({ text: "", activity: "las_bankhandelser" });
    sand("message.delta", { id: "streaming-r-1", text: "Ihopsamlad" });
    expect(result.current.strommande?.text).toBe("Ihopsamlad");

    sand("message.completed", agent("p-2", 2, "Lagrad.", "r-1"));
    expect(result.current.strommande).toBeNull();
    expect(result.current.inlagg.map((i) => ("body" in i && "text" in i.body ? i.body.text : null))).toEqual([
      "fråga",
      "Lagrad.",
    ]);
  });

  it("återuppspelat inlägg ger ingen dubblett (testfall 7)", async () => {
    hamtaTrad.mockResolvedValue(trad({ posts: [agent("p-1", 1, "hej")], cursor: 1 }));
    const { result } = montera();
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalled());
    sand("message.completed", agent("p-1", 1, "hej"));
    sand("message.completed", agent("p-1", 1, "hej"));
    expect(idn(result)).toEqual(["p-1"]);
  });

  it("ett misslyckat GET sätter fel och öppnar ingen ström", async () => {
    hamtaTrad.mockRejectedValue(new Error("nätet"));
    const { result } = montera();
    await waitFor(() => expect(result.current.laddar).toBe(false));
    expect(result.current.fel).toBeInstanceOf(Error);
    expect(oppnaStrom).not.toHaveBeenCalled();
  });
});

// ─── Vybyte ───────────────────────────────────────────────────────────────

describe("useTrad — vybyte stänger strömmen (§6.2 punkt 5)", () => {
  it("byter vy: gamla strömmen avbryts, nya vyns tråd läses och strömmas", async () => {
    hamtaTrad.mockImplementation(async (vk: string) =>
      trad({ view_key: vk, posts: [agent(`${vk}-1`, 1, vk)], cursor: 1 })
    );
    const { result, rerender } = montera("verifikationer");
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalledTimes(1));
    const gammal = oppnaStrom.mock.calls[0][0].signal;

    rerender({ vk: "moms" });
    expect(gammal.aborted).toBe(true);
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalledTimes(2));
    expect(oppnaStrom.mock.calls[1][0]).toMatchObject({ viewKey: "moms", since: 1 });
    expect(oppnaStrom.mock.calls[1][0].signal.aborted).toBe(false);
    expect(idn(result)).toEqual(["moms-1"]);
  });

  it("avmontering avbryter strömmen", async () => {
    hamtaTrad.mockResolvedValue(trad());
    const { unmount } = montera();
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalled());
    unmount();
    expect(oppnaStrom.mock.calls[0][0].signal.aborted).toBe(true);
  });

  it("ett POST-svar som kommer efter vybytet hamnar inte i den nya vyns tråd", async () => {
    hamtaTrad.mockImplementation(async (vk: string) =>
      trad({ view_key: vk, thread_id: null, posts: [], cursor: 0 })
    );
    const { result, rerender } = montera("verifikationer");
    await waitFor(() => expect(result.current.laddar).toBe(false));

    const post = uppskjutet<unknown>();
    skickaMeddelande.mockReturnValue(post.lofte);
    let skickat!: Promise<boolean>;
    act(() => {
      skickat = result.current.skicka("till verifikationer");
    });
    rerender({ vk: "moms" });
    await waitFor(() => expect(result.current.laddar).toBe(false));

    await act(async () => {
      post.losa({
        thread_id: "t-v",
        view_key: "verifikationer",
        fiscal_year_id: "fy-2026",
        posts: [du("p-v", 1, "till verifikationer")],
        cursor: 1,
      });
      await skickat;
    });
    expect(idn(result)).toEqual([]);
    expect(oppnaStrom).not.toHaveBeenCalled();
  });
});

// ─── skicka ───────────────────────────────────────────────────────────────

describe("useTrad — skicka (§6.3, testfall 12)", () => {
  it("optimistiskt user_text syns direkt och ersätts av serverns på id (testfall 12)", async () => {
    hamtaTrad.mockResolvedValue(trad({ posts: [agent("p-1", 1, "hej")], cursor: 1 }));
    const { result } = montera();
    await waitFor(() => expect(result.current.laddar).toBe(false));

    const post = uppskjutet<unknown>();
    skickaMeddelande.mockReturnValue(post.lofte);
    let skickat!: Promise<boolean>;
    act(() => {
      skickat = result.current.skicka("Vad består kundfordringarna av?");
    });

    // I flykt: människans text står redan i tråden, sist.
    expect(result.current.inlagg).toHaveLength(2);
    expect(result.current.inlagg[1]).toMatchObject({
      type: "user_text",
      body: { text: "Vad består kundfordringarna av?" },
    });
    expect(result.current.inlagg[1].id).not.toBe("p-2");

    await act(async () => {
      post.losa({
        thread_id: "t-1",
        view_key: "verifikationer",
        fiscal_year_id: "fy-2026",
        posts: [du("p-2", 2, "Vad består kundfordringarna av?")],
        cursor: 2,
      });
      expect(await skickat).toBe(true);
    });
    expect(idn(result)).toEqual(["p-1", "p-2"]);
  });

  it("misslyckat POST: det optimistiska tas bort, fel sätts, skicka svarar false", async () => {
    hamtaTrad.mockResolvedValue(trad({ posts: [agent("p-1", 1, "hej")], cursor: 1 }));
    const { result } = montera();
    await waitFor(() => expect(result.current.laddar).toBe(false));

    skickaMeddelande.mockRejectedValue(new Error("500"));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.skicka("försvinner inte ur fältet");
    });
    expect(ok).toBe(false);
    expect(idn(result)).toEqual(["p-1"]);
    expect(result.current.fel).toBeInstanceOf(Error);
  });

  it("ett lyckat POST efter ett fel nollställer felet", async () => {
    hamtaTrad.mockResolvedValue(trad({ posts: [], cursor: 0 }));
    const { result } = montera();
    await waitFor(() => expect(result.current.laddar).toBe(false));

    skickaMeddelande.mockRejectedValueOnce(new Error("500")).mockResolvedValueOnce({
      thread_id: "t-1",
      view_key: "verifikationer",
      fiscal_year_id: "fy-2026",
      posts: [du("p-1", 1, "igen")],
      cursor: 1,
    });
    await act(() => result.current.skicka("igen"));
    expect(result.current.fel).not.toBeNull();
    await act(() => result.current.skicka("igen"));
    expect(result.current.fel).toBeNull();
  });
});

// ─── Invalidering ─────────────────────────────────────────────────────────

describe("useTrad — invalidering av frågorna (§6.3, §7)", () => {
  async function medStrom() {
    hamtaTrad.mockResolvedValue(trad({ cursor: 0 }));
    const spion = vi.spyOn(qc, "invalidateQueries");
    const r = montera();
    await waitFor(() => expect(oppnaStrom).toHaveBeenCalled());
    return { spion, ...r };
  }

  const nycklar = (spion: { mock: { calls: unknown[][] } }) =>
    spion.mock.calls.map((c) => (c[0] as { queryKey: unknown }).queryKey);

  it("view.changed invaliderar overview- och beslutsfrågorna", async () => {
    const { spion } = await medStrom();
    sand("view.changed", {
      view_key: "verifikationer",
      changed: { voucher_id: "v-1", kind: "voucher_posted" },
    });
    expect(nycklar(spion)).toEqual(expect.arrayContaining([OVERVIEW_NYCKEL, BESLUT_NYCKEL]));
  });

  it("overview-nyckeln är skalets (hooks/useSkal.ts)", () => {
    expect(OVERVIEW_NYCKEL).toEqual(["overview"]);
  });

  it.each(["decision", "options", "user_text"])(
    "message.completed av typen %s invaliderar beslutsfrågan (§7)",
    async (typ) => {
      const { spion } = await medStrom();
      sand("message.completed", { ...agent("p-1", 1, "x"), type: typ });
      expect(nycklar(spion)).toContainEqual(BESLUT_NYCKEL);
    }
  );

  it("message.completed av agent_text och deltan invaliderar ingenting", async () => {
    const { spion } = await medStrom();
    sand("message.delta", { id: "streaming-r-1", text: "x" });
    sand("message.completed", agent("p-1", 1, "x", "r-1"));
    expect(spion).not.toHaveBeenCalled();
  });
});
