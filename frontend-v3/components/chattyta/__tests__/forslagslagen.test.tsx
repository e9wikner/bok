import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import type { UseTrad } from "@/hooks/useTrad";
import { DRAFTS_NYCKEL, type ForslagStatusSvar } from "@/lib/chattyta/api";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { DraftKropp, Inlagg, RaInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_DRAFT, FIXTUR_RECEIPT, kropp } from "@/lib/chattyta/__fixtures__/inlagg";

/**
 * Förslagskortets lägen ur `GET /drafts` (SPEC-flode-verifikationer.md §10,
 * testfall 44), de nya postningsfelen (§9) och kvittots chip (§8.2). Som
 * `posta.test.tsx`: nätet mockas, inte `lib/chattyta/api.ts`, och korten
 * ritas i skalets `ChattKolumn` med `useTrad` ersatt.
 */

const post = vi.fn();
const get = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));

const typad = (raw: RaInlagg) => parseInlagg(raw) as Inlagg;
const UTKAST = kropp(FIXTUR_DRAFT) as unknown as DraftKropp;
const DRAFT_ID = UTKAST.draft_id;

let tradInlagg: Inlagg[] = [typad(FIXTUR_DRAFT)];
const useTrad = vi.fn(
  (_vk: string): UseTrad => ({
    inlagg: tradInlagg,
    strommande: null,
    skicka: async () => true,
    laddar: false,
    fel: null,
  })
);
vi.mock("@/hooks/useTrad", () => ({ useTrad: (vk: string) => useTrad(vk) }));

const VY = "bocker.verifikationer";

/** En rad ur `GET /drafts` (`api/routes/drafts.py`). */
const rad = (over: Partial<ForslagStatusSvar> = {}): ForslagStatusSvar => ({
  draft_id: DRAFT_ID,
  post_id: FIXTUR_DRAFT.id,
  decision_id: null,
  correction_of: null,
  status: "pending",
  replaced_by: null,
  posted_at: null,
  voucher: null,
  last_error_code: null,
  created_at: "2026-09-18T06:41:00",
  ...over,
});

/** `GET /drafts` svarar med `rader`; allt annat med ett tomt svar. */
function servern(rader: ForslagStatusSvar[] | Promise<never>) {
  get.mockImplementation(async (url: string) => {
    if (url === "/api/v1/drafts") {
      const r = await rader;
      return { status: 200, data: { drafts: r, total: r.length } };
    }
    return { status: 200, data: {} };
  });
}

const axiosFel = (status: number, detail: unknown) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail }, headers: {} },
  });

let qc: QueryClient;
const medKlient = (barn: ReactNode) => <QueryClientProvider client={qc}>{barn}</QueryClientProvider>;
const rendera = () => render(medKlient(<ChattKolumn vyTitel="Verifikationer" viewKey={VY} />));
const knapprad = () => screen.getByTestId("forslag-knapprad");
const draftsAnrop = () => get.mock.calls.filter((c) => c[0] === "/api/v1/drafts");

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  tradInlagg = [typad(FIXTUR_DRAFT)];
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe("testfall 44: VerifikationsForslag ur GET /drafts — fyra lägen (§10)", () => {
  it("frågar GET /drafts?view_key=…&status=all&limit=200 under nyckeln [drafts, viewKey]", async () => {
    servern([rad()]);
    rendera();
    await waitFor(() => expect(draftsAnrop()).toHaveLength(1));
    expect(draftsAnrop()[0][1]).toEqual({ params: { view_key: VY, status: "all", limit: 200 } });
    expect(qc.getQueryCache().find({ queryKey: [...DRAFTS_NYCKEL, VY] })).toBeDefined();
  });

  it("ett anrop per vy, inte ett per kort", async () => {
    const andra = { ...FIXTUR_DRAFT, id: "p-9", seq: 9, body: { ...UTKAST, draft_id: "d-2" } };
    tradInlagg = [typad(FIXTUR_DRAFT), typad(andra as RaInlagg)];
    servern([rad(), rad({ draft_id: "d-2", post_id: "p-9" })]);
    rendera();
    await waitFor(() => expect(draftsAnrop()).toHaveLength(1));
    expect(screen.getAllByRole("button", { name: "Posta" })).toHaveLength(2);
    // Ingen statusläsning per kort (`GET /vouchers/{id}`) längre.
    expect(get.mock.calls.filter((c) => String(c[0]).startsWith("/api/v1/vouchers/"))).toHaveLength(0);
  });

  it("innan frågan svarat: kortet som i dag — Posta, Ändra, konsekvensnotisen", () => {
    servern(new Promise<never>(() => {}));
    rendera();
    expect(within(knapprad()).getByRole("button", { name: "Posta" })).toBeInTheDocument();
    expect(within(knapprad()).getByRole("button", { name: "Ändra" })).toBeInTheDocument();
    expect(within(knapprad()).getByText(UTKAST.consequence)).toBeInTheDocument();
  });

  it("pending: Posta, Ändra, konsekvensnotisen", async () => {
    servern([rad()]);
    rendera();
    await waitFor(() => expect(draftsAnrop()).toHaveLength(1));
    expect(within(knapprad()).getByRole("button", { name: "Posta" })).toBeInTheDocument();
    expect(within(knapprad()).getByRole("button", { name: "Ändra" })).toBeInTheDocument();
    expect(within(knapprad()).getByText(UTKAST.consequence)).toBeInTheDocument();
    expect(screen.queryByTestId("posta-fel")).toBeNull();
  });

  it.each([
    ["period_locked", /Perioden är låst.*Ingenting är bokfört/],
    ["source_already_booked", /Underlaget är redan bokfört.*Ingenting är bokfört/],
    ["source_not_linkable", /Underlaget kan inte längre kopplas.*Ingenting är bokfört/],
    ["correction_note_mismatch", /Korrigeringsnoteringen.*Ingenting är bokfört/],
    ["inactive_account", /inaktiverats i kontoplanen.*Ingenting är bokfört/],
    ["account_not_found", /finns inte längre i kontoplanen.*Ingenting är bokfört/],
    ["okand_kod", /Servern nekade postningen · okand_kod.*Ingenting är bokfört/],
  ])("pending + last_error_code %s: felraden kvar, ingen Posta, Ändra kvar", async (kod, text) => {
    servern([rad({ last_error_code: kod })]);
    rendera();
    expect(await screen.findByTestId("posta-fel")).toHaveTextContent(text);
    expect(screen.queryByRole("button", { name: "Posta" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Försök igen" })).toBeNull();
    expect(within(knapprad()).getByRole("button", { name: "Ändra" })).toBeInTheDocument();
    expect(within(knapprad()).getByText(UTKAST.consequence)).toBeInTheDocument();
  });

  it("posted: Postad · {serie}-{nummer} ur voucher, inga knappar", async () => {
    servern([
      rad({ status: "posted", posted_at: "2026-09-18T06:45:00", voucher: { series: "A", number: 121 } }),
    ]);
    rendera();
    expect(await screen.findByTestId("posta-klart")).toHaveTextContent("Postad · A-121");
    expect(within(knapprad()).queryAllByRole("button")).toHaveLength(0);
    expect(post).not.toHaveBeenCalled();
  });

  it("superseded: Ersatt av ett nytt förslag, inga knappar", async () => {
    servern([rad({ status: "superseded", replaced_by: "d-3" })]);
    rendera();
    expect(await screen.findByText("Ersatt av ett nytt förslag")).toBeInTheDocument();
    expect(within(knapprad()).queryAllByRole("button")).toHaveLength(0);
  });

  it("ett utkast som inte finns i svaret: kortet som i dag, utan påstående", async () => {
    servern([rad({ draft_id: "annat" })]);
    rendera();
    await waitFor(() => expect(draftsAnrop()).toHaveLength(1));
    expect(within(knapprad()).getByRole("button", { name: "Posta" })).toBeInTheDocument();
  });

  it("frågan misslyckas: kortet som i dag", async () => {
    get.mockRejectedValue(new Error("Network Error"));
    rendera();
    await waitFor(() => expect(draftsAnrop()).toHaveLength(1));
    expect(within(knapprad()).getByRole("button", { name: "Posta" })).toBeInTheDocument();
  });
});

describe("konsekvensen med \\n (rättelsens andra rad, §7.2)", () => {
  it("renderas på två rader: radbrytningen bevaras", () => {
    const text =
      "Ingenting bokförs förrän du postar.\nRättar A-1 (juni 2026, låst sedan 2026-07-01) · bokförs i september 2026, inte i juni 2026";
    tradInlagg = [
      typad({ ...FIXTUR_DRAFT, body: { ...UTKAST, consequence: text } } as unknown as RaInlagg),
    ];
    servern([rad()]);
    rendera();
    const notis = within(knapprad()).getByText((_, el) => el?.textContent === text && el.tagName === "SPAN");
    expect(notis.className).toContain("whitespace-pre-line");
  });
});

describe("nya postningsfel vid Posta (§9): inline, ingen Försök igen", () => {
  const fall: [string, number, Record<string, unknown>, RegExp][] = [
    [
      "source_already_booked",
      409,
      {
        code: "source_already_booked",
        booked_by: {
          source_kind: "intake_source",
          source_id: "s-1",
          voucher_id: "v-1",
          voucher_number: "A-1",
        },
      },
      /^Underlaget är redan bokfört på A-1\. Ingenting är bokfört\.$/,
    ],
    [
      "source_not_linkable",
      409,
      { code: "source_not_linkable" },
      /^Underlaget kan inte längre kopplas till en verifikation\. Ingenting är bokfört\.$/,
    ],
    ["inactive_account", 400, { code: "inactive_account" }, /inaktiverats i kontoplanen.*Ingenting är bokfört/],
    ["account_not_found", 400, { code: "account_not_found" }, /finns inte längre i kontoplanen.*Ingenting är bokfört/],
    [
      "correction_note_mismatch",
      400,
      { code: "correction_note_mismatch" },
      /Korrigeringsnoteringen.*Ingenting är bokfört/,
    ],
  ];

  it.each(fall)("%s → begriplig text, ingen Posta, ingen Försök igen", async (_k, status, detail, text) => {
    servern([rad()]);
    post.mockRejectedValue(axiosFel(status, { error: "x", details: "y", ...detail }));
    rendera();
    await userEvent.click(within(knapprad()).getByRole("button", { name: "Posta" }));
    expect(await screen.findByTestId("posta-fel")).toHaveTextContent(text);
    expect(screen.queryByRole("button", { name: "Posta" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Försök igen" })).toBeNull();
  });

  it("source_already_booked utan nummer → en annan verifikation", async () => {
    servern([rad()]);
    post.mockRejectedValue(
      axiosFel(409, {
        code: "source_already_booked",
        booked_by: { source_kind: "bank", source_id: "b", voucher_id: null, voucher_number: null },
      })
    );
    rendera();
    await userEvent.click(within(knapprad()).getByRole("button", { name: "Posta" }));
    expect(await screen.findByTestId("posta-fel")).toHaveTextContent(
      "Underlaget är redan bokfört på en annan verifikation. Ingenting är bokfört."
    );
  });

  it("efter varje svar på Posta invalideras drafts-frågan (§10)", async () => {
    servern([rad()]);
    post.mockRejectedValue(axiosFel(409, { code: "source_not_linkable" }));
    const invalidera = vi.spyOn(qc, "invalidateQueries");
    rendera();
    await userEvent.click(within(knapprad()).getByRole("button", { name: "Posta" }));
    await screen.findByTestId("posta-fel");
    expect(invalidera).toHaveBeenCalledWith({ queryKey: DRAFTS_NYCKEL });
  });

  it("klickets eget fel går före serverns rad (den bär mer: numret)", async () => {
    // Frågan hinner hämtas om efter felet och bär då `last_error_code`.
    let rader = [rad()];
    get.mockImplementation(async (url: string) =>
      url === "/api/v1/drafts"
        ? { status: 200, data: { drafts: rader, total: rader.length } }
        : { status: 200, data: {} }
    );
    post.mockImplementation(async () => {
      rader = [rad({ last_error_code: "source_already_booked" })];
      throw axiosFel(409, {
        code: "source_already_booked",
        booked_by: { source_kind: "intake_source", source_id: "s", voucher_id: "v", voucher_number: "A-7" },
      });
    });
    rendera();
    await userEvent.click(within(knapprad()).getByRole("button", { name: "Posta" }));
    await waitFor(() => expect(draftsAnrop().length).toBeGreaterThan(1));
    expect(await screen.findByTestId("posta-fel")).toHaveTextContent("bokfört på A-7");
    expect(screen.getAllByTestId("posta-fel")).toHaveLength(1);
  });
});

describe("kvittots chip (§8.2) renderas", () => {
  it("posta_utkast, rattar, kompletteringsflagga och vantar syns alla", () => {
    servern([]);
    tradInlagg = [
      typad({
        ...FIXTUR_RECEIPT,
        body: { ...(FIXTUR_RECEIPT.body as object), title: "B-3 postad · rättar A-1" },
        traces: [
          { tool: "posta_utkast", label: "verifikation postad", detail: "B-3" },
          { tool: "rattar", label: "rättar A-1", detail: "A-1", voucher_id: "v-1" },
          { tool: "kompletteringsflagga", label: "kompletteringsflagga satt" },
          { tool: "vantar", label: "2 kvar" },
        ],
      } as RaInlagg),
    ];
    rendera();
    const chip = screen.getAllByTestId("sparchip").map((c) => c.textContent);
    expect(chip).toEqual([
      "verifikation postad · B-3",
      "rättar A-1 · A-1",
      "kompletteringsflagga satt",
      "2 kvar",
    ]);
  });
});
