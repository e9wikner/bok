import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PostaKnappar } from "@/components/chattyta/VerifikationsForslag";
import { NY_MARKERING_MS } from "@/components/skal/VyRad";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { useVyer } from "@/hooks/useVyer";
import { NY_POSTNING_MS } from "@/lib/chattyta/postningar";
import { sidan } from "@/lib/skal/vyer";

/**
 * Testfall 46 (flode-verifikationer §11.2): den optimistiska raden.
 *
 * Kortets `Posta` (tråden) och vyn Verifikationer (läskolumnen) är olika
 * komponenter med samma `QueryClient`, som i skalet. Nätet mockas, inte
 * `postaUtkast`, så att den riktiga tolkningen av svaren körs.
 */

const post = vi.fn();
const get = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };
const DRAFT = "draft-1";

const utkastVoucher = {
  id: DRAFT,
  series: "A",
  number: null,
  date: "2026-09-18",
  description: "Kontorsmaterial, Clas Ohlson",
  status: "draft",
  total_debit: 89600,
};
const tidigare = {
  id: "a1",
  series: "A",
  number: 1,
  date: "2026-09-01",
  description: "Hyra",
  status: "posted",
  total_debit: 500000,
  posted_at: "2026-09-01T08:00:00",
};
const postad = {
  ...utkastVoucher,
  number: 2,
  status: "posted",
  period_id: "per",
  posted_at: "2026-09-18T06:45:12",
};
const forslagRad = (over: Record<string, unknown> = {}) => ({
  draft_id: DRAFT,
  post_id: "p1",
  decision_id: null,
  correction_of: null,
  correction_note_id: null,
  status: "pending",
  replaced_by: null,
  posted_at: null,
  voucher: null,
  last_error_code: null,
  created_at: "2026-09-18T06:41:00",
  ...over,
});

/** Serverns tillstånd; testet byter det när servern har "gjort" något. */
let server: {
  postade: unknown[];
  utkast: unknown[];
  drafts: unknown[];
};

function svaraGet(url: string, config?: { params?: Record<string, unknown> }) {
  const params = config?.params ?? {};
  if (url === "/api/v1/vouchers") {
    const lista = params.status === "draft" ? server.utkast : server.postade;
    return Promise.resolve({ data: { total: lista.length, vouchers: lista } });
  }
  if (url === "/api/v1/decisions") return Promise.resolve({ data: { decisions: [], total: 0 } });
  if (url === "/api/v1/drafts") {
    return Promise.resolve({ data: { drafts: server.drafts, total: server.drafts.length } });
  }
  return Promise.reject(new Error(`oväntat GET ${url}`));
}

function uppskjutet<T>() {
  let losa!: (v: T) => void;
  let vagra!: (e: unknown) => void;
  const lofte = new Promise<T>((l, v) => {
    losa = l;
    vagra = v;
  });
  return { lofte, losa, vagra };
}

const axiosFel = (status: number, detail: unknown) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail }, headers: {} },
  });

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
function rendera() {
  return render(
    <QueryClientProvider client={qc}>
      <div data-testid="kortet">
        <PostaKnappar draftId={DRAFT} />
      </div>
      <Vyn />
    </QueryClientProvider>
  );
}

const vyn = () => within(screen.getByTestId("vyn"));
const radFor = (titel: string) => vyn().getByText(titel).closest("[data-variant]") as HTMLElement;
const sektionsTitlar = () =>
  vyn()
    .queryAllByText(/^(Väntar på beslut|Postade|Utkast)$/)
    .map((el) => el.textContent);

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  get.mockImplementation(svaraGet);
  server = { postade: [tidigare], utkast: [utkastVoucher], drafts: [forslagRad()] };
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("den optimistiska raden (testfall 46)", () => {
  it("är samma varaktighet som VyRads ny-markering", () => {
    expect(NY_POSTNING_MS).toBe(NY_MARKERING_MS);
  });

  it("pagaende utan nummer överst i Postade; ny med nummer vid 200", async () => {
    const svar = uppskjutet<unknown>();
    post.mockReturnValue(svar.lofte);
    const user = userEvent.setup();
    rendera();

    await waitFor(() => expect(radFor("Kontorsmaterial, Clas Ohlson")).toBeTruthy());
    expect(sektionsTitlar()).toEqual(["Väntar på beslut", "Postade"]);
    expect(radFor("Kontorsmaterial, Clas Ohlson").getAttribute("data-variant")).toBe("vantar");

    await user.click(screen.getByRole("button", { name: "Posta" }));

    await waitFor(() =>
      expect(radFor("Kontorsmaterial, Clas Ohlson").getAttribute("data-variant")).toBe("pagaende")
    );
    const pagaende = radFor("Kontorsmaterial, Clas Ohlson");
    expect(within(pagaende).getByText("A · postas…")).toBeInTheDocument();
    expect(pagaende.textContent).not.toMatch(/A-2/);
    // Överst i Postade, och händelsen är borta ur Väntar.
    expect(sektionsTitlar()).toEqual(["Postade"]);
    const rader = screen.getByTestId("vyn").querySelectorAll("[data-variant]");
    expect(rader[0]).toBe(pagaende);

    // Servern postar; listorna har inte hunnit hämtas om än.
    await act(async () => {
      svar.losa({ status: 200, data: postad, headers: {} });
    });

    await waitFor(() =>
      expect(radFor("Kontorsmaterial, Clas Ohlson").getAttribute("data-variant")).toBe("ny")
    );
    expect(vyn().getByText("A-2 · postad 06:45 · du · låst")).toBeInTheDocument();
    // En rad, inte två, även när serverns lista har den.
    server = { postade: [postad, tidigare], utkast: [], drafts: [forslagRad({ status: "posted" })] };
    await act(async () => {
      await qc.invalidateQueries();
    });
    expect(vyn().getAllByText("Kontorsmaterial, Clas Ohlson")).toHaveLength(1);
    expect(radFor("Kontorsmaterial, Clas Ohlson").getAttribute("data-variant")).toBe("ny");
  });

  it("uppspelning och already_posted byter också raden mot serverns", async () => {
    post.mockRejectedValue(
      axiosFel(409, { code: "already_posted", error: "", details: "", voucher: postad })
    );
    const user = userEvent.setup();
    rendera();
    await waitFor(() => expect(radFor("Kontorsmaterial, Clas Ohlson")).toBeTruthy());

    await user.click(screen.getByRole("button", { name: "Posta" }));

    await waitFor(() =>
      expect(radFor("Kontorsmaterial, Clas Ohlson").getAttribute("data-variant")).toBe("ny")
    );
    expect(vyn().getByText("A-2 · postad 06:45 · du · låst")).toBeInTheDocument();
  });

  it("vid fel tas raden bort och händelsen går tillbaka till Väntar, med fel", async () => {
    const svar = uppskjutet<unknown>();
    post.mockReturnValue(svar.lofte);
    const user = userEvent.setup();
    rendera();
    await waitFor(() => expect(radFor("Kontorsmaterial, Clas Ohlson")).toBeTruthy());

    await user.click(screen.getByRole("button", { name: "Posta" }));
    await waitFor(() =>
      expect(radFor("Kontorsmaterial, Clas Ohlson").getAttribute("data-variant")).toBe("pagaende")
    );

    // Servern har satt `last_error_code` när den svarar.
    server = { ...server, drafts: [forslagRad({ last_error_code: "period_locked" })] };
    await act(async () => {
      svar.vagra(
        axiosFel(409, {
          code: "period_locked",
          error: "",
          details: "",
          period_id: "per",
          locked_at: "2026-10-12T09:14:03",
          locked_by: "stefan",
        })
      );
    });

    await waitFor(() =>
      expect(radFor("Kontorsmaterial, Clas Ohlson").getAttribute("data-variant")).toBe("fel")
    );
    expect(vyn().getByText("perioden låst · ligger kvar")).toBeInTheDocument();
    expect(sektionsTitlar()).toEqual(["Väntar på beslut", "Postade"]);
    expect(vyn().queryByText(/postas…/)).toBeNull();
  });

  it("efter 3 s utan svar säger knappen Postar fortfarande…", async () => {
    const svar = uppskjutet<unknown>();
    post.mockReturnValue(svar.lofte);
    rendera();
    await waitFor(() => expect(radFor("Kontorsmaterial, Clas Ohlson")).toBeTruthy());

    vi.useFakeTimers({ shouldAdvanceTime: true });
    await act(async () => {
      screen.getByRole("button", { name: "Posta" }).click();
    });
    expect(await screen.findByRole("button", { name: "Postar…" })).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByRole("button", { name: "Postar fortfarande…" })).toBeInTheDocument();

    await act(async () => {
      svar.losa({ status: 200, data: postad, headers: {} });
    });
    await waitFor(() => expect(screen.getByTestId("posta-klart")).toHaveTextContent("Postad · A-2"));
  });
});
