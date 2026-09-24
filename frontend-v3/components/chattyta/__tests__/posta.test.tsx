import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import type { UseTrad } from "@/hooks/useTrad";
import { BESLUT_NYCKEL, OVERVIEW_NYCKEL, postaUtkast } from "@/lib/chattyta/api";
import { nyckelForUtkast } from "@/lib/chattyta/idempotens";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { DraftKropp, Inlagg, RaInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_DRAFT, kropp } from "@/lib/chattyta/__fixtures__/inlagg";

/**
 * Postningsknappen och dess sju utfall (SPEC-chattyta.md §8, C12).
 *
 * Nätet mockas, inte `postaUtkast`: utfallen hänger på hur FastAPI formar
 * ett `409`/`422` (`{detail: {...}}`) och på `Idempotent-Replay`-headern,
 * och det ska vara den riktiga `lib/chattyta/api.ts` som tolkar dem.
 * Nyckeln räknas av den riktiga `nyckelForUtkast` (C11).
 *
 * Korten ritas i skalets `ChattKolumn` (med `useTrad` ersatt), inte i en
 * naken `TradRenderare`: `Ändra` ska hitta SIN kolumns `ChattFalt`
 * (testfall 36), och det går bara att pröva i den layout där fältet finns.
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
const URL_POST = `/api/v1/vouchers/${encodeURIComponent(DRAFT_ID)}/post`;

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

// ─── Svar som servern ger dem ─────────────────────────────────────────────

/** `api/schemas.py::VoucherResponse`, de fält kortet läser plus några till. */
const verifikation = (over: Record<string, unknown> = {}) => ({
  id: DRAFT_ID,
  series: "A",
  number: 118,
  date: "2026-09-18",
  period_id: "per-2026-09",
  description: "Kontorsmaterial, Clas Ohlson",
  status: "posted",
  rows: [],
  created_at: "2026-09-18T06:41:00",
  created_by: "agent",
  posted_at: "2026-09-18T06:45:00",
  ...over,
});

const svar200 = (headers: Record<string, string> = {}) => ({
  status: 200,
  data: verifikation(),
  headers,
});

/** Som axios kastar det: `isAxiosError` och FastAPIs `{detail}`-kropp. */
const axiosFel = (status: number, detail: unknown) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail }, headers: {} },
  });

const natverksFel = () =>
  Object.assign(new Error("Network Error"), { isAxiosError: true, response: undefined });

/** `api/routes/vouchers.py::_posting_http_error`, `already_posted`. */
const redanPostad = (nummer = 118) =>
  axiosFel(409, {
    error: "Voucher is already posted (immutable)",
    code: "already_posted",
    details: "voucher.status is already 'posted'",
    voucher: verifikation({ number: nummer }),
  });

/** Samma, `period_locked`. `locked_by` kan vara `null` (SPEC-idempotens.md testfall 9). */
const periodLast = (lockedBy: string | null = "stefan") =>
  axiosFel(409, {
    error: "Period per-2026-09 is locked - cannot post vouchers",
    code: "period_locked",
    details: "period is immutable after locking",
    period_id: "per-2026-09",
    locked_at: "2026-10-12T09:14:03",
    locked_by: lockedBy,
  });

/** SPEC-idempotens.md §6, felsvarstabellen. */
const iFlykt = (ms = 800) =>
  axiosFel(409, {
    error: "A request with this Idempotency-Key is in flight",
    code: "request_in_flight",
    details: "Retry with the same key to get the stored response",
    retry_after_ms: ms,
  });

const nyckelAteranvand = () =>
  axiosFel(422, {
    error: "Idempotency-Key already used for a different request",
    code: "idempotency_key_reuse",
    details: "The same key must carry the same request body",
    original_fingerprint: "abc",
  });

function uppskjutet<T>() {
  let losa!: (v: T) => void;
  let vagra!: (e: unknown) => void;
  const lofte = new Promise<T>((l, v) => {
    losa = l;
    vagra = v;
  });
  return { lofte, losa, vagra };
}

// ─── Hjälpare ─────────────────────────────────────────────────────────────

let qc: QueryClient;
const medKlient = (barn: ReactNode, klient = qc) => (
  <QueryClientProvider client={klient}>{barn}</QueryClientProvider>
);

const VY = "bocker.verifikationer";
const rendera = () => render(medKlient(<ChattKolumn vyTitel="Verifikationer" viewKey={VY} />));

/** Nyckeln i anrop nummer `i`, som den stod i headern. */
const nyckelI = (i: number) =>
  (post.mock.calls[i][2] as { headers: Record<string, string> }).headers["Idempotency-Key"];

const postaKnapp = (yta: HTMLElement | Document = document) =>
  within(yta as HTMLElement).getByRole("button", { name: /^Posta/ });

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  useTrad.mockClear();
  tradInlagg = [typad(FIXTUR_DRAFT)];
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  vi.useRealTimers();
});

// ─── postaUtkast: anropet och tolkningen ──────────────────────────────────

describe("postaUtkast — anropet (SPEC §8 steg 1, §15.1)", () => {
  it("POST /vouchers/{draft_id}/post med Idempotency-Key = nyckelForUtkast(draft_id)", async () => {
    post.mockResolvedValue(svar200());
    await postaUtkast(DRAFT_ID);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toBe(URL_POST);
    expect(nyckelI(0)).toBe(await nyckelForUtkast(DRAFT_ID));
  });

  it("testfall 25: två samtidiga anrop bär samma nyckel — den är härledd, inte slumpad", async () => {
    post.mockResolvedValueOnce(svar200()).mockRejectedValueOnce(redanPostad());
    await Promise.all([postaUtkast(DRAFT_ID), postaUtkast(DRAFT_ID)]);
    expect(post).toHaveBeenCalledTimes(2);
    expect(nyckelI(0)).toBe(nyckelI(1));
  });

  it("anropar aldrig PUT — förslag ändras i samtalet, inte i kortet (§8 steg 4)", async () => {
    post.mockResolvedValue(svar200());
    await postaUtkast(DRAFT_ID);
    // Klienten har ingen `put` alls i mocken; ett PUT-anrop hade kastat.
    expect(post.mock.calls[0][0]).toMatch(/\/post$/);
  });

  it("200 → postad; Idempotent-Replay: true → postad, uppspelad", async () => {
    post.mockResolvedValueOnce(svar200()).mockResolvedValueOnce(
      svar200({ "idempotent-replay": "true" })
    );
    const forsta = await postaUtkast(DRAFT_ID);
    const andra = await postaUtkast(DRAFT_ID);
    expect(forsta).toMatchObject({ utfall: "postad", uppspelad: false });
    expect(andra).toMatchObject({ utfall: "postad", uppspelad: true });
    expect(andra.utfall === "postad" && andra.verifikation.number).toBe(118);
  });

  it("409 already_posted → redan_postad med verifikationen ur kroppen", async () => {
    post.mockRejectedValue(redanPostad(119));
    const utfall = await postaUtkast(DRAFT_ID);
    expect(utfall).toMatchObject({ utfall: "redan_postad" });
    expect(utfall.utfall === "redan_postad" && utfall.verifikation?.number).toBe(119);
  });

  it("409 request_in_flight → pagar med retry_after_ms", async () => {
    post.mockRejectedValue(iFlykt(700));
    expect(await postaUtkast(DRAFT_ID)).toEqual({ utfall: "pagar", retry_after_ms: 700 });
  });

  it("422 idempotency_key_reuse → nyckel_ateranvand", async () => {
    post.mockRejectedValue(nyckelAteranvand());
    expect(await postaUtkast(DRAFT_ID)).toEqual({ utfall: "nyckel_ateranvand" });
  });

  it("409 period_locked → period_last med period_id, locked_at, locked_by", async () => {
    post.mockRejectedValue(periodLast(null));
    expect(await postaUtkast(DRAFT_ID)).toEqual({
      utfall: "period_last",
      period_id: "per-2026-09",
      locked_at: "2026-10-12T09:14:03",
      locked_by: null,
    });
  });

  it("nätverksfel och 5xx → natverk", async () => {
    post.mockRejectedValueOnce(natverksFel()).mockRejectedValueOnce(axiosFel(503, "down"));
    expect(await postaUtkast(DRAFT_ID)).toEqual({ utfall: "natverk", status: null });
    expect(await postaUtkast(DRAFT_ID)).toEqual({ utfall: "natverk", status: 503 });
  });

  it("allt annat kastas vidare (t.ex. 400 voucher_date_outside_period, 404)", async () => {
    post.mockRejectedValueOnce(axiosFel(400, { code: "voucher_date_outside_period" }));
    await expect(postaUtkast(DRAFT_ID)).rejects.toThrow(/400/);
    post.mockRejectedValueOnce(axiosFel(404, "Voucher not found"));
    await expect(postaUtkast(DRAFT_ID)).rejects.toThrow(/404/);
  });
});

// ─── Knapparna ────────────────────────────────────────────────────────────

describe("VerifikationsForslag har Posta och Ändra (SPEC §8)", () => {
  it("primär Posta, sekundär Ändra, notisen kvar — inga knappar före ett tryck gör något", () => {
    rendera();
    const rad = screen.getByTestId("forslag-knapprad");
    expect(within(rad).getByRole("button", { name: "Posta" })).toBeInTheDocument();
    expect(within(rad).getByRole("button", { name: "Ändra" })).toBeInTheDocument();
    expect(within(rad).getByText(UTKAST.consequence)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("200 → Postad · A-118 i klartoner, knapparna borta; overview och beslut invalideras", async () => {
    const invalidera = vi.spyOn(qc, "invalidateQueries");
    post.mockResolvedValue(svar200());
    rendera();
    await userEvent.click(postaKnapp());
    const klart = await screen.findByTestId("posta-klart");
    expect(klart).toHaveTextContent("Postad · A-118");
    expect(klart.className).toMatch(/bok-klart/);
    const rad = screen.getByTestId("forslag-knapprad");
    expect(within(rad).queryAllByRole("button")).toHaveLength(0);
    expect(invalidera).toHaveBeenCalledWith({ queryKey: OVERVIEW_NYCKEL });
    expect(invalidera).toHaveBeenCalledWith({ queryKey: BESLUT_NYCKEL });
  });

  it("200 + Idempotent-Replay: true → samma klara läge", async () => {
    post.mockResolvedValue(svar200({ "idempotent-replay": "true" }));
    rendera();
    await userEvent.click(postaKnapp());
    expect(await screen.findByTestId("posta-klart")).toHaveTextContent("Postad · A-118");
  });

  it("i flykt: Postar…, låst med aria-disabled (inte disabled — fokus stannar), ett anrop", async () => {
    const d = uppskjutet<unknown>();
    post.mockReturnValue(d.lofte);
    rendera();
    const knapp = postaKnapp();
    await userEvent.click(knapp);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(knapp).toHaveTextContent("Postar…");
    expect(knapp).toHaveAttribute("aria-disabled", "true");
    expect(knapp).not.toBeDisabled();
    // Ändra är låst också: medan postningen pågår finns inget att ändra.
    expect(screen.getByRole("button", { name: "Ändra" })).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(knapp);
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => d.losa(svar200()));
    expect(await screen.findByTestId("posta-klart")).toBeInTheDocument();
  });
});

describe("testfall 25: Posta två gånger utan väntan → samma nyckel, en verifikation", () => {
  it("testfall 25: två flikar trycker innan någon hunnit svara — två anrop, SAMMA Idempotency-Key, båda i klart läge med samma nummer", async () => {
    // Låsningen i en flik är bekvämlighet (§8 steg 2). Två flikar har var
    // sitt lås och trycker båda — det är just det nyckeln ska klara.
    const forsta = uppskjutet<unknown>();
    const andra = uppskjutet<unknown>();
    post.mockReturnValueOnce(forsta.lofte).mockReturnValueOnce(andra.lofte);

    const flikA = render(medKlient(<ChattKolumn vyTitel="Verifikationer" viewKey={VY} />));
    const flikB = render(
      medKlient(
        <ChattKolumn vyTitel="Verifikationer" viewKey={VY} />,
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      )
    );

    fireEvent.click(postaKnapp(flikA.container));
    fireEvent.click(postaKnapp(flikB.container));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));

    expect(nyckelI(0)).toBe(nyckelI(1));
    expect(nyckelI(0)).toBe(await nyckelForUtkast(DRAFT_ID));

    // Servern: den första postar, den andra hittar den redan postad.
    await act(async () => forsta.losa(svar200()));
    await act(async () => andra.vagra(redanPostad(118)));

    expect(await within(flikA.container).findByTestId("posta-klart")).toHaveTextContent(
      "Postad · A-118"
    );
    expect(await within(flikB.container).findByTestId("posta-klart")).toHaveTextContent(
      "Postad · A-118"
    );
  });

  it("testfall 25: en omladdning mitt i ger samma nyckel som före", async () => {
    post.mockReturnValueOnce(new Promise(() => {})).mockResolvedValueOnce(svar200());
    const forsta = rendera();
    fireEvent.click(postaKnapp());
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    forsta.unmount();

    rendera();
    fireEvent.click(postaKnapp());
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(nyckelI(1)).toBe(nyckelI(0));
    expect(await screen.findByTestId("posta-klart")).toHaveTextContent("Postad · A-118");
  });
});

describe("testfall 28: 409 already_posted", () => {
  it("testfall 28: klart läge med det befintliga numret — inte ett fel", async () => {
    post.mockRejectedValue(redanPostad(117));
    rendera();
    await userEvent.click(postaKnapp());
    expect(await screen.findByTestId("posta-klart")).toHaveTextContent("Postad · A-117");
    expect(screen.queryByTestId("posta-fel")).toBeNull();
    expect(screen.queryByRole("button", { name: "Posta" })).toBeNull();
  });
});

describe("testfall 27: 409 period_locked", () => {
  it("testfall 27: inline med vem och när; ingenting är bokfört; ingen Försök igen", async () => {
    post.mockRejectedValue(periodLast("stefan"));
    rendera();
    await userEvent.click(postaKnapp());
    const fel = await screen.findByTestId("posta-fel");
    expect(fel).toHaveTextContent("sedan 2026-10-12 09:14 av stefan. Ingenting är bokfört.");
    expect(fel).toHaveTextContent(/^Perioden .*är låst/);
    expect(screen.queryByRole("button", { name: "Försök igen" })).toBeNull();
    // Knappen kommer inte tillbaka: ett nytt tryck kan inte lyckas (§8).
    expect(screen.queryByRole("button", { name: "Posta" })).toBeNull();
  });

  it("testfall 27: locked_by: null → okänd", async () => {
    post.mockRejectedValue(periodLast(null));
    rendera();
    await userEvent.click(postaKnapp());
    expect(await screen.findByTestId("posta-fel")).toHaveTextContent("av okänd. Ingenting är bokfört.");
  });
});

describe("testfall 34: 409 request_in_flight", () => {
  /**
   * Låter riktiga turer i händelseloopen gå (nyckeln räknas med
   * `crypto.subtle`, som svarar utanför mikrouppgifterna) utan att röra den
   * falska klockan. `vi.waitFor` duger inte här: med falska timers flyttar
   * den själv klockan framåt, och det är just klockan testet mäter.
   */
  const tills = async (villkor: () => boolean) => {
    for (let i = 0; i < 100 && !villkor(); i++) {
      await act(async () => {
        await new Promise((klar) => setImmediate(klar));
      });
    }
    expect(villkor()).toBe(true);
  };

  it("testfall 34: väntar retry_after_ms, frågar igen med samma nyckel, står i Postar… under tiden, slutar i klart läge", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    post.mockRejectedValueOnce(iFlykt(800)).mockResolvedValueOnce(svar200());
    rendera();
    // Kortet frågar `GET /drafts` (F13), och TanStack Query har egna timers.
    // Låt frågan landa först och räkna väntetimern ovanpå dem.
    await tills(() => get.mock.calls.length === 1);
    await tills(() => !qc.isFetching());
    const fore = vi.getTimerCount();

    fireEvent.click(postaKnapp());
    await tills(() => post.mock.calls.length === 1);
    // Låt `409`-utfallet landa och väntetimern startas.
    await tills(() => vi.getTimerCount() === fore + 1);
    expect(postaKnapp()).toHaveTextContent("Postar…");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(799);
    });
    expect(post).toHaveBeenCalledTimes(1);
    expect(postaKnapp()).toHaveTextContent("Postar…");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    await tills(() => post.mock.calls.length === 2);
    expect(nyckelI(1)).toBe(nyckelI(0));
    await tills(() => screen.queryByTestId("posta-klart") !== null);
    expect(screen.getByTestId("posta-klart")).toHaveTextContent("Postad · A-118");
  });
});

describe("testfall 35: 422 idempotency_key_reuse", () => {
  it("testfall 35: inline fel, ingenting är bokfört, ingen Försök igen", async () => {
    post.mockRejectedValue(nyckelAteranvand());
    rendera();
    await userEvent.click(postaKnapp());
    expect(await screen.findByTestId("posta-fel")).toHaveTextContent(
      "Förslaget har ändrats sedan du tryckte. Ingenting är bokfört."
    );
    expect(screen.queryByRole("button", { name: "Försök igen" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Posta" })).toBeNull();
  });
});

describe("nätverksfel och 5xx (§8-tabellens sista rad)", () => {
  it("inline fel med Försök igen, som går med SAMMA nyckel och kan sluta i klart läge", async () => {
    post.mockRejectedValueOnce(natverksFel()).mockResolvedValueOnce(svar200());
    rendera();
    await userEvent.click(postaKnapp());
    // Klienten vet inte om servern hann; den påstår inte att ingenting är bokfört.
    const fel = await screen.findByTestId("posta-fel");
    expect(fel).toHaveTextContent(/Försök igen ger samma verifikation, aldrig två/);
    expect(fel).not.toHaveTextContent(/Ingenting är bokfört/);
    await userEvent.click(screen.getByRole("button", { name: "Försök igen" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(nyckelI(1)).toBe(nyckelI(0));
    expect(await screen.findByTestId("posta-klart")).toHaveTextContent("Postad · A-118");
  });

  it("5xx ger samma Försök igen", async () => {
    post.mockRejectedValue(axiosFel(500, "boom"));
    rendera();
    await userEvent.click(postaKnapp());
    expect(await screen.findByRole("button", { name: "Försök igen" })).toBeInTheDocument();
  });

  it("ett annat 4xx (utanför §8) säger att ingenting bokförts, utan Försök igen", async () => {
    post.mockRejectedValue(axiosFel(400, { code: "voucher_date_outside_period" }));
    rendera();
    await userEvent.click(postaKnapp());
    expect(await screen.findByTestId("posta-fel")).toHaveTextContent(
      /voucher_date_outside_period.*Ingenting är bokfört/
    );
    expect(screen.queryByRole("button", { name: "Försök igen" })).toBeNull();
  });
});

describe("testfall 36: Ändra", () => {
  it("testfall 36: lägger fokus i kolumnens ChattFalt, fältet tomt, inget anrop", async () => {
    rendera();
    // Kortet läser utkastets status när det monteras; `Ändra` själv frågar
    // ingenting.
    await waitFor(() => expect(get).toHaveBeenCalled());
    const anropFore = get.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Ändra" }));
    const falt = screen.getByLabelText(/Fråga om en post i verifikationer/i);
    expect(falt).toHaveFocus();
    expect(falt).toHaveValue("");
    expect(post).not.toHaveBeenCalled();
    expect(get).toHaveBeenCalledTimes(anropFore);
  });

  it("testfall 36: med flera kolumner i DOM:en (svepraden) hamnar fokus i kortets egen kolumn", async () => {
    // Svepraden ritar en sidas alla vyer; varje kolumn har ett eget fält
    // med samma id. Fokus ska till fältet i kortets kolumn, inte det första.
    tradInlagg = [typad(FIXTUR_DRAFT)];
    render(
      medKlient(
        <>
          <ChattKolumn vyTitel="Resultaträkning" viewKey="bocker.resultat" aktiv={false} />
          <ChattKolumn vyTitel="Verifikationer" viewKey={VY} />
        </>
      )
    );
    await userEvent.click(screen.getByRole("button", { name: "Ändra" }));
    // Inte `getByLabelText`: etiketternas `for` pekar på ett `id` som finns
    // två gånger, och slår därför upp det FÖRSTA fältet — samma fel som
    // `getElementById` hade gjort i koden.
    const [annan, egen] = screen.getAllByRole("textbox");
    expect(egen).toHaveAttribute("placeholder", "Fråga om en post i verifikationer");
    expect(egen).toHaveFocus();
    expect(annan).not.toHaveFocus();
  });

  it("testfall 36: på mobilen (ChattList) går fokus till listens fält", async () => {
    render(medKlient(<ChattList vyTitel="Verifikationer" viewKey={VY} vantandeBeslut={0} />));
    await userEvent.click(screen.getByRole("button", { name: "Ändra" }));
    const falt = screen.getByLabelText(/Fråga om en post i verifikationer/i);
    expect(falt).toHaveFocus();
    expect(falt).toHaveValue("");
    expect(post).not.toHaveBeenCalled();
  });
});

describe("ett utkast som redan är postat, efter en omladdning", () => {
  // Inlägget ändras aldrig (antagande 2), så `draft`-inlägget ser likadant ut
  // efter postningen. Statusen läses per vy ur `GET /drafts`
  // (flode-verifikationer §10, F13) — inte längre ur `GET /vouchers/{id}`
  // per kort, som C12 gjorde innan producenten fanns.
  const URL_DRAFTS = "/api/v1/drafts";
  const rad = (over: Record<string, unknown>) => ({
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

  it("status posted → klart läge med numret, utan att något postas", async () => {
    get.mockImplementation(async (url: string) =>
      url === URL_DRAFTS
        ? {
            status: 200,
            data: {
              drafts: [rad({ status: "posted", voucher: { series: "A", number: 121 } })],
              total: 1,
            },
          }
        : { data: {} }
    );
    rendera();
    expect(await screen.findByText(/Postad · A-121/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Posta/ })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("status pending → Posta erbjuds som vanligt", async () => {
    get.mockImplementation(async (url: string) =>
      url === URL_DRAFTS ? { status: 200, data: { drafts: [rad({})], total: 1 } } : { data: {} }
    );
    rendera();
    await waitFor(() => expect(get).toHaveBeenCalledWith(URL_DRAFTS, expect.anything()));
    expect(postaKnapp()).toBeInTheDocument();
  });

  it("läsningen misslyckas → Posta erbjuds; nyckeln skyddar ändå mot en andra postning", async () => {
    get.mockImplementation(async (url: string) => {
      if (url === URL_DRAFTS) throw natverksFel();
      return { data: {} };
    });
    rendera();
    await waitFor(() => expect(get).toHaveBeenCalledWith(URL_DRAFTS, expect.anything()));
    expect(postaKnapp()).toBeInTheDocument();
  });
});
