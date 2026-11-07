import { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import apiClient, { obehorig } from "@/lib/api";

/**
 * `401` från vilket anrop som helst loggar ut (chattyta, kvarstående fråga e).
 * Före: bara request-interceptorn fanns, så en utgången token gav tysta fel
 * på varje sida i stället för inloggningen.
 *
 * Node 26:s globala `localStorage` skuggar jsdom:s i vitest (chattyta C2),
 * så den stubbas. Navigeringen går genom `obehorig.ga` — jsdom kan inte
 * navigera.
 */

let lagrat: Map<string, string>;
const ga = vi.fn();
const ursprungligAdapter = apiClient.defaults.adapter;

function svaraMed(status: number) {
  apiClient.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    if (status < 400) return { data: {}, status, statusText: "", headers: {}, config };
    throw new AxiosError(`status ${status}`, "ERR_BAD_REQUEST", config, null, {
      data: { detail: "x" },
      status,
      statusText: "",
      headers: {},
      config,
    });
  };
}

beforeEach(() => {
  lagrat = new Map([["auth_token", "gammal-token"]]);
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => lagrat.get(k) ?? null,
    setItem: (k: string, v: string) => lagrat.set(k, v),
    removeItem: (k: string) => lagrat.delete(k),
  });
  ga.mockReset();
  vi.spyOn(obehorig, "ga").mockImplementation(ga);
  vi.spyOn(obehorig, "sokvag").mockReturnValue("/v4");
});

afterEach(() => {
  apiClient.defaults.adapter = ursprungligAdapter;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("401 loggar ut", () => {
  it("tar bort token och går till /login; felet kastas ändå vidare till anroparen", async () => {
    svaraMed(401);
    await expect(apiClient.get("/api/v1/overview")).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(lagrat.has("auth_token")).toBe(false);
    expect(ga).toHaveBeenCalledWith("/login");
  });

  it("på /login självt: ingen omdirigering — annars en loop", async () => {
    vi.spyOn(obehorig, "sokvag").mockReturnValue("/login");
    svaraMed(401);
    await expect(apiClient.get("/api/v1/overview")).rejects.toBeTruthy();
    expect(ga).not.toHaveBeenCalled();
  });

  it.each([403, 404, 500])("%s loggar inte ut", async (status) => {
    svaraMed(status);
    await expect(apiClient.get("/api/v1/overview")).rejects.toBeTruthy();
    expect(lagrat.get("auth_token")).toBe("gammal-token");
    expect(ga).not.toHaveBeenCalled();
  });

  it("ett lyckat svar rör ingenting", async () => {
    svaraMed(200);
    await apiClient.get("/api/v1/overview");
    expect(lagrat.get("auth_token")).toBe("gammal-token");
    expect(ga).not.toHaveBeenCalled();
  });
});
