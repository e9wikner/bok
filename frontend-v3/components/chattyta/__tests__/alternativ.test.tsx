import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TradRenderare } from "@/components/chattyta/TradRenderare";
import { beslutStatusNyckel } from "@/hooks/useBeslut";
import { BESLUT_NYCKEL, type BeslutListSvar, type BeslutSvar } from "@/lib/chattyta/api";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { Inlagg, OptionsKropp, RaInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_OPTIONS, kropp, medKropp } from "@/lib/chattyta/__fixtures__/inlagg";
import { formatBelopp } from "@/lib/skal/format";

// ─── Mockar ───────────────────────────────────────────────────────────────
// Nätet, inte `svaraBeslut`: testfall 16 hänger på hur ett `409` från
// FastAPI ser ut (`{detail: {...}}`) och det ska vara den riktiga
// `lib/chattyta/api.ts` som tolkar det.

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));

// ─── Hjälpare ─────────────────────────────────────────────────────────────

const VY = "bocker.verifikationer";
const OPTIONS = kropp(FIXTUR_OPTIONS) as unknown as OptionsKropp;
const [REK, OVRIG, UTVAG] = OPTIONS.options;

function typad(raw: RaInlagg): Inlagg {
  const inlagg = parseInlagg(raw);
  if (!inlagg) throw new Error(`fixturen ${raw.id} tolkades inte`);
  return inlagg;
}

const beslut = (over: Partial<BeslutSvar> = {}): BeslutSvar => ({
  id: OPTIONS.decision_id,
  view_key: VY,
  kind: "abstention",
  status: "open",
  title: "Swish 4 500 kr utan referens",
  amount_ore: 450000,
  reason: "…",
  consequence: "…",
  source: null,
  age_days: 1,
  thread_id: "t-1",
  post_id: "p-4",
  options: [],
  ...over,
});

const listSvar = (decisions: BeslutSvar[]): { data: BeslutListSvar } => ({
  data: { decisions, total: decisions.length },
});

/** Som axios kastar det: `isAxiosError` och FastAPIs `{detail}`-kropp. */
const axiosFel = (status: number, detail: unknown) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });

const natverksFel = () =>
  Object.assign(new Error("Network Error"), { isAxiosError: true, response: undefined });

/** `DecisionAnswerResponse`: beslutet i nytt läge, och människans svarsinlägg. */
const svar202 = () => ({
  status: 202,
  data: { decision: beslut({ status: "answered" }), answer_post_id: "p-9", answer_post_seq: 9 },
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

let qc: QueryClient;
const medKlient = (barn: ReactNode) => (
  <QueryClientProvider client={qc}>{barn}</QueryClientProvider>
);

function rendera(raw: RaInlagg = FIXTUR_OPTIONS, vy: string | null = VY) {
  return render(
    medKlient(
      <TradRenderare inlagg={[typad(raw)]} strommande={null} viewKey={vy ?? undefined} />
    )
  );
}

const rader = () => within(screen.getByRole("group")).getAllByRole("button");
const rad = (titel: string) => screen.getByRole("button", { name: new RegExp(titel) });
const ring = (knapp: HTMLElement) => within(knapp).getByTestId("alternativ-ring");

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  // Standard: beslutet är öppet enligt servern.
  get.mockResolvedValue(listSvar([beslut()]));
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

// ─── Testfall 14: ingenting förväljs ──────────────────────────────────────

describe("AlternativLista renderas utan förval (testfall 14, SPEC §4.2)", () => {
  it("testfall 14: en knapp per alternativ, i en grupp — inte en radiogrupp (§11)", () => {
    rendera();
    expect(screen.getByRole("group")).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(rader()).toHaveLength(3);
    for (const knapp of rader()) expect(knapp.tagName).toBe("BUTTON");
  });

  it("testfall 14: ingen rad vald — varje ring tom, inget aria-pressed/checked/selected", () => {
    rendera();
    for (const knapp of rader()) {
      expect(ring(knapp).dataset.fylld).toBe("nej");
      expect(knapp).not.toHaveAttribute("aria-pressed", "true");
      expect(knapp).not.toHaveAttribute("aria-checked");
      expect(knapp).not.toHaveAttribute("aria-selected");
      expect(knapp).not.toHaveAttribute("aria-current");
    }
  });

  it("testfall 14: ingen rad fokuserad", () => {
    rendera();
    expect(document.activeElement).toBe(document.body);
    for (const knapp of rader()) expect(knapp).not.toHaveAttribute("autofocus");
  });

  it("testfall 14: den rekommenderade raden är inte annorlunda stylad — bara RekMarke skiljer", () => {
    rendera();
    const rek = rad(REK.title);
    const ovrig = rad(OVRIG.title);
    // Knappen, ringen och titeln: samma klasser, ingen inline-stil.
    expect(rek.className).toBe(ovrig.className);
    expect(rek.getAttribute("style")).toBe(ovrig.getAttribute("style"));
    expect(ring(rek).className).toBe(ring(ovrig).className);
    expect(within(rek).getByText(REK.title).className).toBe(
      within(ovrig).getByText(OVRIG.title).className
    );
    // Ordningen är agentens: den rekommenderade flyttas inte.
    expect(rader().map((k) => k.dataset.optionId)).toEqual(OPTIONS.options.map((o) => o.option_id));
  });

  it("testfall 14: RekMarke `rekommenderas` på den rekommenderade raden och bara där", () => {
    rendera();
    expect(within(rad(REK.title)).getByText("rekommenderas")).toBeInTheDocument();
    expect(screen.getAllByText("rekommenderas")).toHaveLength(1);
    const marke = screen.getByText("rekommenderas");
    expect(marke.className).toContain("bok-mono");
    expect(marke.className).toContain("text-[11px]");
    expect(marke.className).toContain("rounded-full");
  });

  it("raden: titel 15, konto mono 12, motivering 14/1.5, belopp mono 14 via formatBelopp", () => {
    rendera();
    const k = rad(REK.title);
    expect(within(k).getByText(REK.title).className).toContain("text-[15px]");
    const konto = within(k).getByText(REK.account!);
    expect(konto.className).toContain("bok-mono");
    expect(konto.className).toContain("text-[12px]");
    const motivering = within(k).getByText(REK.rationale);
    expect(motivering.className).toContain("text-[14px]");
    expect(motivering.className).toContain("leading-[1.5]");
    // `textContent`, inte `getByText`: formatBelopp ger hårda mellanslag,
    // som Testing Library normaliserar bort.
    const belopp = within(k).getByTestId("alternativ-belopp");
    expect(belopp.textContent).toBe(formatBelopp(REK.amount_ore!));
    expect(belopp.className).toContain("bok-mono");
    expect(belopp.className).toContain("text-[14px]");
  });

  it("utan konto och belopp (vägen ut): inget konto, inget belopp — ingen nolla", () => {
    rendera();
    const k = rad(UTVAG.title);
    expect(within(k).queryByTestId("alternativ-konto")).toBeNull();
    expect(within(k).queryByTestId("alternativ-belopp")).toBeNull();
  });

  it("fotnoten i mono 12, kopplad till gruppen med aria-describedby (§11)", () => {
    rendera();
    const fot = screen.getByText(OPTIONS.footnote!);
    expect(fot.className).toContain("bok-mono");
    expect(fot.className).toContain("text-[12px]");
    expect(fot.id).not.toBe("");
    expect(screen.getByRole("group")).toHaveAttribute("aria-describedby", fot.id);
  });

  it("utan fotnot: ingen fot och ingen aria-describedby som pekar på ingenting", () => {
    rendera(medKropp(FIXTUR_OPTIONS, { ...kropp(FIXTUR_OPTIONS), footnote: null }));
    expect(screen.getByRole("group")).not.toHaveAttribute("aria-describedby");
  });
});

// ─── Testfall 15: svaret ──────────────────────────────────────────────────

describe("tryck på ett alternativ = svaret (testfall 15)", () => {
  it("testfall 15: POST /decisions/{id}/answer med {option_id} och inget annat", async () => {
    post.mockResolvedValue(svar202());
    rendera();
    await userEvent.click(rad(OVRIG.title));
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(
      `/api/v1/decisions/${OPTIONS.decision_id}/answer`,
      { option_id: OVRIG.option_id }
    );
  });

  it("testfall 15: i flykt är alla rader låsta; ett andra tryck skickar ingenting", async () => {
    const svar = uppskjutet<unknown>();
    post.mockReturnValue(svar.lofte);
    rendera();
    await userEvent.click(rad(OVRIG.title));
    for (const knapp of rader()) expect(knapp).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("group")).toHaveAttribute("aria-busy", "true");
    await userEvent.click(rad(REK.title));
    await userEvent.click(rad(OVRIG.title));
    expect(post).toHaveBeenCalledTimes(1);
    svar.losa(svar202());
    await waitFor(() => expect(rad(OVRIG.title).dataset.vald).toBe("ja"));
  });

  it("202: vald rad markerad (fylld ring, klar-ton), övriga låsta, fokus till den valda (§11)", async () => {
    post.mockResolvedValue(svar202());
    rendera();
    await userEvent.click(rad(OVRIG.title));
    await waitFor(() => expect(rad(OVRIG.title).dataset.vald).toBe("ja"));
    const vald = rad(OVRIG.title);
    expect(ring(vald).dataset.fylld).toBe("ja");
    expect(vald.className).toContain("bok-klart");
    expect(vald).toHaveFocus();
    for (const knapp of rader()) expect(knapp).toHaveAttribute("aria-disabled", "true");
    for (const titel of [REK.title, UTVAG.title]) {
      expect(ring(rad(titel)).dataset.fylld).toBe("nej");
      expect(rad(titel).dataset.vald).toBe("nej");
    }
    expect(screen.getByTestId("alternativ-status")).toHaveTextContent(/^Besvarat/);
    // Låst är låst: ett tryck till skickar inget nytt svar.
    await userEvent.click(rad(REK.title));
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("202 med answered_at i beslutet: `Besvarat · HH:MM` direkt, utan att vänta på listan", async () => {
    post.mockResolvedValue({
      status: 202,
      data: {
        decision: beslut({ status: "answered", answered_at: "2026-09-18T09:12:00" }),
        answer_post_id: "p-9",
        answer_post_seq: 9,
      },
    });
    rendera();
    await userEvent.click(rad(OVRIG.title));
    await waitFor(() =>
      expect(screen.getByTestId("alternativ-status")).toHaveTextContent(/^Besvarat · 09:12$/)
    );
  });

  it("svaret invaliderar beslutsfrågan (§7), så BeslutKort och märket följer med", async () => {
    post.mockResolvedValue(svar202());
    const invalidera = vi.spyOn(qc, "invalidateQueries");
    rendera();
    await userEvent.click(rad(OVRIG.title));
    await waitFor(() =>
      expect(invalidera).toHaveBeenCalledWith({ queryKey: [...BESLUT_NYCKEL] })
    );
  });
});

// ─── Testfall 16: redan besvarat ──────────────────────────────────────────

describe("409 decision_already_answered är inte ett fel (testfall 16, §7)", () => {
  const redan = (over: Record<string, unknown> = {}) =>
    axiosFel(409, {
      error: "Decision already answered",
      code: "decision_already_answered",
      details: "…",
      answered_at: "2026-09-18T07:12:00+00:00",
      answer_post_id: "p-9",
      answer_option_id: REK.option_id,
      answer_text: null,
      ...over,
    });

  it("testfall 16: besvarat läge med svaret ur 409-kroppen, inte det som trycktes", async () => {
    post.mockRejectedValue(redan());
    rendera();
    await userEvent.click(rad(OVRIG.title));
    // Svaret som gäller är det servern redan hade: REK, inte OVRIG.
    await waitFor(() => expect(rad(REK.title).dataset.vald).toBe("ja"));
    expect(rad(OVRIG.title).dataset.vald).toBe("nej");
    expect(rad(REK.title)).toHaveFocus();
    for (const knapp of rader()) expect(knapp).toHaveAttribute("aria-disabled", "true");
  });

  it("testfall 16: inget felkort, ingen felrad", async () => {
    post.mockRejectedValue(redan());
    rendera();
    await userEvent.click(rad(OVRIG.title));
    await waitFor(() => expect(rad(REK.title).dataset.vald).toBe("ja"));
    expect(screen.queryByTestId("alternativ-fel")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("alternativ-status")).toHaveTextContent(/^Besvarat/);
  });

  it("testfall 16: besvarat med fritext → ingen rad markerad, fokus på statusraden", async () => {
    post.mockRejectedValue(redan({ answer_option_id: null, answer_text: "Det är en gåva." }));
    rendera();
    await userEvent.click(rad(OVRIG.title));
    const status = await screen.findByTestId("alternativ-status");
    expect(status).toHaveTextContent(/^Besvarat/);
    for (const knapp of rader()) {
      expect(knapp.dataset.vald).toBe("nej");
      expect(knapp).toHaveAttribute("aria-disabled", "true");
    }
    expect(status).toHaveFocus();
  });
});

// ─── Status ur GET /decisions vid (om)laddning ────────────────────────────

describe("besvarat vid omladdning: låst, ingenting gissat (§7, C6)", () => {
  it("status answered med answer_option_id: den valda raden markerad, tiden ur servern", async () => {
    get.mockResolvedValue(
      listSvar([
        beslut({
          status: "answered",
          answer_option_id: REK.option_id,
          answered_at: "2026-09-18T09:12:00",
        }),
      ])
    );
    rendera();
    await waitFor(() =>
      expect(screen.getByTestId("alternativ-status")).toHaveTextContent(/^Besvarat · 09:12$/)
    );
    for (const knapp of rader()) {
      expect(knapp).toHaveAttribute("aria-disabled", "true");
      const vald = knapp === rad(REK.title);
      expect(knapp.dataset.vald).toBe(vald ? "ja" : "nej");
      expect(ring(knapp).dataset.fylld).toBe(vald ? "ja" : "nej");
    }
    // Ingen fokusflytt vid en omladdning.
    expect(document.activeElement).toBe(document.body);
  });

  it("status answered utan answer_option_id (fritext): alla låsta, ingen markerad, `Besvarat`", async () => {
    get.mockResolvedValue(listSvar([beslut({ status: "answered" })]));
    rendera();
    await waitFor(() =>
      expect(screen.getByTestId("alternativ-status")).toHaveTextContent(/^Besvarat$/)
    );
    for (const knapp of rader()) {
      expect(knapp).toHaveAttribute("aria-disabled", "true");
      expect(knapp.dataset.vald).toBe("nej");
      expect(ring(knapp).dataset.fylld).toBe("nej");
    }
    // Ingen fokusflytt: människan har inte gjort något i den här sessionen.
    expect(document.activeElement).toBe(document.body);
    await userEvent.click(rad(REK.title));
    expect(post).not.toHaveBeenCalled();
  });

  it("status superseded: låst, `Inte längre aktuellt`", async () => {
    get.mockResolvedValue(listSvar([beslut({ status: "superseded" })]));
    rendera();
    await waitFor(() =>
      expect(screen.getByTestId("alternativ-status")).toHaveTextContent("Inte längre aktuellt")
    );
    for (const knapp of rader()) expect(knapp).toHaveAttribute("aria-disabled", "true");
  });

  it("ett GET /decisions för vyn, delat med beslutskortet (testfall 20)", async () => {
    rendera();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(qc.getQueryData(beslutStatusNyckel(VY))).toBeDefined();
  });

  it("status okänd (ingen vy, eller id utanför listan): öppen — ett svar avgör ändå servern", () => {
    rendera(FIXTUR_OPTIONS, null);
    expect(get).not.toHaveBeenCalled();
    for (const knapp of rader()) expect(knapp).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByTestId("alternativ-status")).toBeNull();
  });
});

// ─── Fel ──────────────────────────────────────────────────────────────────

describe("nätverksfel och 5xx: raderna låses upp, en kort neutral rad", () => {
  it.each([
    ["nätverksfel", natverksFel()],
    ["500", axiosFel(500, "Internal Server Error")],
  ])("%s → upplåst, felrad, ingen rad markerad, inget omförsök", async (_namn, fel) => {
    post.mockRejectedValue(fel);
    rendera();
    await userEvent.click(rad(OVRIG.title));
    const felrad = await screen.findByTestId("alternativ-fel");
    expect(felrad).toHaveTextContent("Svaret kom inte fram. Ingenting är besvarat.");
    // Neutral, inte FelKort-rött: ingenting i böckerna har gått fel.
    expect(felrad.className).not.toContain("bok-fel");
    for (const knapp of rader()) {
      expect(knapp).not.toHaveAttribute("aria-disabled", "true");
      expect(knapp.dataset.vald).toBe("nej");
    }
    expect(post).toHaveBeenCalledTimes(1);
    // Ett nytt tryck är människans eget, och det går igenom.
    post.mockResolvedValue(svar202());
    await userEvent.click(rad(OVRIG.title));
    await waitFor(() => expect(rad(OVRIG.title).dataset.vald).toBe("ja"));
    expect(screen.queryByTestId("alternativ-fel")).toBeNull();
  });
});
