import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FakturaForslag, UtfardaKnappar, formatAntal } from "@/components/chattyta/FakturaForslag";
import { InlaggRenderare } from "@/components/chattyta/TradRenderare";
import type { ForslagStatusSvar } from "@/lib/chattyta/api";
import { _glomVarnadeTyper, parseInlagg } from "@/lib/chattyta/parse";
import type { FakturaDraftInlagg, Inlagg } from "@/lib/chattyta/typer";
import { UTFARDANDEN_NYCKEL, type Utfardande } from "@/lib/chattyta/utfardanden";
import {
  FIXTUR_DRAFT,
  FIXTUR_FAKTURA_DRAFT,
  FIXTUR_FAKTURA_RECEIPT,
  FIXTUR_RECEIPT,
  kropp,
  kroppUtan,
  medKropp,
} from "@/lib/chattyta/__fixtures__/inlagg";
import { faktureringVy } from "@/lib/skal/betala";

/**
 * Fakturaförslaget i tråden (SPEC-fakturering-f1.md §13.3, testfall 33–37).
 * Nätet mockas, inte `utfardaFaktura`: utfallen hänger på hur FastAPI
 * formar `409`/`422`, och det ska vara den riktiga `lib/chattyta/api.ts` som
 * tolkar dem.
 */

const post = vi.fn();
const get = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));

beforeEach(() => {
  _glomVarnadeTyper();
  post.mockReset();
  get.mockReset();
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

function faktura(): FakturaDraftInlagg {
  const inlagg = parseInlagg(FIXTUR_FAKTURA_DRAFT);
  if (!inlagg || inlagg.type !== "draft" || inlagg.body.kind !== "invoice") {
    throw new Error("FIXTUR_FAKTURA_DRAFT parsas inte till ett fakturaförslag");
  }
  return { ...inlagg, body: inlagg.body };
}

function medKlient(barn: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { qc, ...render(<QueryClientProvider client={qc}>{barn}</QueryClientProvider>) };
}

const axiosFel = (status: number, detail: Record<string, unknown>) =>
  Object.assign(new Error(`status ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });

const rad = (over: Partial<ForslagStatusSvar>): ForslagStatusSvar => ({
  kind: "invoice",
  draft_id: "<invoice_drafts.id>",
  post_id: "p-9",
  decision_id: null,
  correction_of: null,
  status: "pending",
  replaced_by: null,
  posted_at: null,
  voucher: null,
  last_error_code: null,
  created_at: "2026-06-12T10:42:00",
  invoice: null,
  ...over,
});

// ─── 33: parseInlagg ──────────────────────────────────────────────────────

describe("parseInlagg för kind=invoice (testfall 33)", () => {
  it("blir ett draft-inlägg med kroppen orörd", () => {
    const inlagg = parseInlagg(FIXTUR_FAKTURA_DRAFT);
    expect(inlagg?.type).toBe("draft");
    expect(inlagg && "body" in inlagg && inlagg.body).toEqual(FIXTUR_FAKTURA_DRAFT.body);
  });

  it("utan recipient blir det okant_kontrakt", () => {
    const inlagg = parseInlagg(medKropp(FIXTUR_FAKTURA_DRAFT, kroppUtan(FIXTUR_FAKTURA_DRAFT, "recipient")));
    expect(inlagg?.type).toBe("okant_kontrakt");
  });

  it("en rad utan belopp blir okant_kontrakt", () => {
    const body = kropp(FIXTUR_FAKTURA_DRAFT);
    const rows = (body.rows as Record<string, unknown>[]).map((r) => {
      const { amount_ore: _bort, ...rest } = r;
      return rest;
    });
    expect(parseInlagg(medKropp(FIXTUR_FAKTURA_DRAFT, { ...body, rows }))?.type).toBe("okant_kontrakt");
  });

  it("kind=payroll är fortfarande okant_kontrakt", () => {
    const inlagg = parseInlagg(medKropp(FIXTUR_DRAFT, { ...kropp(FIXTUR_DRAFT), kind: "payroll" }));
    expect(inlagg?.type).toBe("okant_kontrakt");
  });

  it("ett fakturakvitto med invoice_id och pdf_url är ett receipt", () => {
    const inlagg = parseInlagg(FIXTUR_FAKTURA_RECEIPT);
    expect(inlagg?.type).toBe("receipt");
  });
});

// ─── 34: FakturaForslag ───────────────────────────────────────────────────

describe("FakturaForslag (testfall 34)", () => {
  it("visar serverns text ordagrant och räknar ingenting", () => {
    render(<FakturaForslag inlagg={faktura()} />);
    expect(screen.getByText("Faktura 1045 · Ateljé Vind AB")).toBeInTheDocument();
    expect(screen.getByText("förslag · fakturadatum 2026-06-12")).toBeInTheDocument();
    expect(screen.getByText("Er referens: Anna Berg")).toBeInTheDocument();
    expect(screen.getByText("24 h")).toBeInTheDocument();
    expect(screen.getByText("Att betala senast 2026-07-12")).toBeInTheDocument();
    expect(screen.getByText(/PDF:en laddar du ner och skickar själv/)).toBeInTheDocument();
    expect(screen.getAllByTestId("faktura-summa")).toHaveLength(3);
  });

  it("skriver decimalt antal med komma", () => {
    expect(formatAntal(750, "h")).toBe("7,5 h");
    expect(formatAntal(2400, "h")).toBe("24 h");
  });

  it("pending: knapparna ritas", () => {
    render(<FakturaForslag inlagg={faktura()} forslag={rad({})} knappar={<button>Utfärda</button>} />);
    expect(screen.getByRole("button", { name: "Utfärda" })).toBeInTheDocument();
  });

  it("issued: Utfärdad med nummer och verifikation, och PDF", () => {
    render(
      <FakturaForslag
        inlagg={faktura()}
        forslag={rad({
          status: "issued",
          invoice: {
            invoice_id: "i-1",
            invoice_number: "1045",
            voucher_id: "v-1",
            voucher: "A-120",
            pdf_url: "/api/v1/invoices/i-1/pdf",
          },
        })}
        knappar={<button>Utfärda</button>}
      />
    );
    expect(screen.getByTestId("utfarda-klart")).toHaveTextContent("Utfärdad · 1045 · A-120");
    expect(screen.getByTestId("oppna-pdf")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Utfärda" })).toBeNull();
  });

  it("superseded och rejected: inga knappar", () => {
    const { rerender } = render(
      <FakturaForslag inlagg={faktura()} forslag={rad({ status: "superseded" })} knappar={<button>Utfärda</button>} />
    );
    expect(screen.getByTestId("forslag-ersatt")).toHaveTextContent("Ersatt av ett nytt förslag");
    expect(screen.queryByRole("button")).toBeNull();
    rerender(
      <FakturaForslag inlagg={faktura()} forslag={rad({ status: "rejected" })} knappar={<button>Utfärda</button>} />
    );
    expect(screen.getByTestId("forslag-forkastat")).toHaveTextContent("Förkastat");
    expect(screen.queryByRole("button")).toBeNull();
  });
});

// ─── 35: Utfärda ──────────────────────────────────────────────────────────

describe("Utfärda (testfall 35)", () => {
  const URL = `/api/v1/invoice-drafts/${encodeURIComponent("<invoice_drafts.id>")}/issue`;

  it("anropar /issue med kortets draft_id, tar bort knappen och visar klart", async () => {
    post.mockResolvedValue({
      data: { invoice_id: "i-1", invoice_number: "1045", voucher_id: "v-1", pdf_url: "/api/v1/invoices/i-1/pdf" },
    });
    const { qc } = medKlient(<UtfardaKnappar inlagg={faktura()} />);
    await userEvent.click(screen.getByRole("button", { name: "Utfärda" }));
    expect(post).toHaveBeenCalledWith(URL);
    await waitFor(() => expect(screen.getByTestId("utfarda-klart")).toHaveTextContent("Utfärdad · 1045"));
    expect(screen.queryByRole("button", { name: "Utfärda" })).toBeNull();
    const rader = qc.getQueryData<Utfardande[]>(UTFARDANDEN_NYCKEL) ?? [];
    expect(rader[0]).toMatchObject({ lage: "utfardad", invoiceId: "i-1" });
  });

  it("409 draft_already_issued är samma sak som klart", async () => {
    post.mockRejectedValue(axiosFel(409, { code: "draft_already_issued", invoice_id: "i-1" }));
    medKlient(<UtfardaKnappar inlagg={faktura()} />);
    await userEvent.click(screen.getByRole("button", { name: "Utfärda" }));
    await waitFor(() => expect(screen.getByTestId("utfarda-klart")).toBeInTheDocument());
  });

  it("409 number_taken: felraden och ingen Utfärda", async () => {
    post.mockRejectedValue(axiosFel(409, { code: "number_taken", invoice_number: "1045" }));
    medKlient(<UtfardaKnappar inlagg={faktura()} />);
    await userEvent.click(screen.getByRole("button", { name: "Utfärda" }));
    await waitFor(() => expect(screen.getByTestId("utfarda-fel")).toHaveTextContent(/redan använt/));
    expect(screen.queryByRole("button", { name: "Utfärda" })).toBeNull();
  });

  it("409 period_locked: Utfärda står kvar (beslut 8)", async () => {
    post.mockRejectedValue(axiosFel(409, { code: "period_locked" }));
    medKlient(<UtfardaKnappar inlagg={faktura()} />);
    await userEvent.click(screen.getByRole("button", { name: "Utfärda" }));
    await waitFor(() => expect(screen.getByTestId("utfarda-fel")).toHaveTextContent(/Perioden är låst/));
    expect(screen.getByRole("button", { name: "Utfärda" })).toBeInTheDocument();
  });

  it("422 draft_rejected: förslaget hann ersättas", async () => {
    post.mockRejectedValue(axiosFel(422, { code: "draft_rejected" }));
    medKlient(<UtfardaKnappar inlagg={faktura()} />);
    await userEvent.click(screen.getByRole("button", { name: "Utfärda" }));
    await waitFor(() => expect(screen.getByTestId("forslag-ersatt")).toBeInTheDocument());
  });

  it("nätverksfel: Försök igen", async () => {
    post.mockRejectedValue(Object.assign(new Error("nät"), { isAxiosError: true }));
    medKlient(<UtfardaKnappar inlagg={faktura()} />);
    await userEvent.click(screen.getByRole("button", { name: "Utfärda" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Försök igen" })).toBeInTheDocument());
  });

  it("en felkod ur GET /drafts efter omladdning: felraden, och knappen bara där den kan lyckas", () => {
    const { unmount } = medKlient(<UtfardaKnappar inlagg={faktura()} serverFel="number_taken" />);
    expect(screen.getByTestId("utfarda-fel")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Utfärda" })).toBeNull();
    unmount();
    medKlient(<UtfardaKnappar inlagg={faktura()} serverFel="company_info_incomplete" />);
    expect(screen.getByRole("button", { name: "Utfärda" })).toBeInTheDocument();
  });
});

// ─── 36: kvittot ──────────────────────────────────────────────────────────

describe("Fakturakvittot (testfall 36)", () => {
  it("Öppna PDF bara med pdf_url", () => {
    const { unmount } = render(<InlaggRenderare inlagg={parseInlagg(FIXTUR_FAKTURA_RECEIPT) as Inlagg} />);
    expect(screen.getByTestId("kvitto-pdf")).toHaveTextContent("Öppna PDF");
    unmount();
    render(<InlaggRenderare inlagg={parseInlagg(FIXTUR_RECEIPT) as Inlagg} />);
    expect(screen.queryByTestId("kvitto-pdf")).toBeNull();
  });

  it("hämtar PDF:en med auth, som blob", async () => {
    get.mockResolvedValue({ data: new Blob(["%PDF"]) });
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x") });
    render(<InlaggRenderare inlagg={parseInlagg(FIXTUR_FAKTURA_RECEIPT) as Inlagg} />);
    await userEvent.click(screen.getByTestId("kvitto-pdf"));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith("/api/v1/invoices/<id>/pdf", { responseType: "blob" })
    );
    expect(open).toHaveBeenCalled();
  });
});

// ─── 37: vyn ──────────────────────────────────────────────────────────────

describe("Vyn Fakturering (testfall 37)", () => {
  const lista = { total: 0, invoices: [] };
  const utkast = [
    {
      id: "d-1",
      invoice_number: "1045",
      customer_name: "Ateljé Vind AB",
      invoice_date: "2026-06-12",
      due_date: "2026-07-12",
      status: "needs_review",
      amount_inc_vat: 3450000,
    },
    {
      id: "d-2",
      invoice_number: null,
      customer_name: "Gammal Sida AB",
      invoice_date: "2026-06-01",
      due_date: "2026-07-01",
      status: "draft",
      amount_inc_vat: 100000,
    },
    {
      id: "d-3",
      invoice_number: "1044",
      customer_name: "Ersatt AB",
      invoice_date: "2026-06-01",
      due_date: "2026-07-01",
      status: "rejected",
      amount_inc_vat: 100000,
    },
  ];

  it("förslaget bara i Väntar på dig, utkast utan kort i Utkast, ersatta inte alls", () => {
    const vy = faktureringVy(lista, {
      utkast,
      forslag: [rad({ draft_id: "d-1" }), rad({ draft_id: "d-3", status: "superseded", replaced_by: "d-1" })],
      beslut: [],
      utfardanden: [],
    });
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Väntar på dig", "Utkast"]);
    expect(vy.sektioner[0].rader[0]).toMatchObject({
      titel: "Ateljé Vind AB",
      meta: "förslag 1045 · fakturadatum 2026-06-12",
      variant: "vantar",
    });
    expect(vy.sektioner[1].rader.map((r) => r.titel)).toEqual(["Gammal Sida AB"]);
    expect(vy.status).toBe("1 väntar på dig");
    expect(vy.fot).toMatch(/Du utfärdar den/);
  });

  it("den optimistiska raden: utfärdas… och sedan ny i Obetalda", () => {
    const forslag = [rad({ draft_id: "d-1" })];
    const pagar = faktureringVy(lista, {
      utkast,
      forslag,
      beslut: [],
      utfardanden: [
        {
          draftId: "d-1",
          lage: "pagaende",
          forslag: { kund: "Ateljé Vind AB", nummer: "1045", belopp: 3450000, forfaller: "2026-07-12" },
        },
      ],
    });
    expect(pagar.sektioner.map((s) => s.titel)).toEqual(["Obetalda", "Utkast"]);
    expect(pagar.sektioner[0].rader[0]).toMatchObject({ meta: "1045 · utfärdas…", variant: "pagaende" });

    const klar = faktureringVy(lista, {
      utkast,
      forslag,
      beslut: [],
      utfardanden: [
        {
          draftId: "d-1",
          lage: "utfardad",
          invoiceId: "i-1",
          klockslag: "10:43",
          forslag: { kund: "Ateljé Vind AB", nummer: "1045", belopp: 3450000, forfaller: "2026-07-12" },
        },
      ],
    });
    expect(klar.sektioner[0].rader[0]).toMatchObject({
      meta: "1045 · utfärdad 10:43 · förfaller 2026-07-12",
      variant: "ny",
    });
  });

  it("ett förslag med felkod står i fel-läget", () => {
    const vy = faktureringVy(lista, {
      utkast,
      forslag: [rad({ draft_id: "d-1", last_error_code: "number_taken" })],
      beslut: [],
      utfardanden: [],
    });
    expect(vy.sektioner[0].rader[0]).toMatchObject({
      meta: "utfärdandet misslyckades · ligger kvar",
      variant: "fel",
    });
  });
});
