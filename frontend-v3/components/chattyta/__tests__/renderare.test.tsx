import { readFileSync } from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TradRenderare } from "@/components/chattyta/TradRenderare";
import { ChattFalt } from "@/components/skal/ChattFalt";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import type { MeddelandeSvar, TradSvar } from "@/lib/chattyta/api";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { StromAlternativ } from "@/lib/chattyta/strom";
import type { Strommande } from "@/lib/chattyta/trad";
import type { Inlagg, RaInlagg } from "@/lib/chattyta/typer";
import {
  FIXTUR_AGENT_TEXT,
  FIXTUR_DECISION,
  FIXTUR_DRAFT,
  FIXTUR_ERROR,
  FIXTUR_OPTIONS,
  FIXTUR_RECEIPT,
  FIXTUR_USER_FILE,
  FIXTUR_USER_TEXT,
  kropp,
  medKropp,
} from "@/lib/chattyta/__fixtures__/inlagg";
import * as skalMock from "@/lib/skal/mock";

// ─── Mockar ───────────────────────────────────────────────────────────────
// Nätet, inte hooken: testfall 12 och 19 prövar hela kedjan ChattFalt →
// useTrad → POST, så `useTrad` och reducern är de riktiga.

const hamtaTrad = vi.fn();
const skickaMeddelande = vi.fn();
vi.mock("@/lib/chattyta/api", async (original) => ({
  ...(await original<typeof import("@/lib/chattyta/api")>()),
  hamtaTrad: (...a: unknown[]) => hamtaTrad(...a),
  skickaMeddelande: (...a: unknown[]) => skickaMeddelande(...a),
}));

/** Strömmen står öppen tills signalen avbryts, som den riktiga. */
vi.mock("@/lib/chattyta/strom", () => ({
  oppnaStrom: (a: StromAlternativ) =>
    new Promise<void>((klar) => a.signal.addEventListener("abort", () => klar())),
}));

// ─── Hjälpare ─────────────────────────────────────────────────────────────

// Renderaren tar bara det `parseInlagg` släppt igenom (§4.1) — testerna går
// samma väg i stället för att bygga typade inlägg för hand.
function typad(raw: RaInlagg): Inlagg {
  const inlagg = parseInlagg(raw);
  if (!inlagg) throw new Error(`fixturen ${raw.id} tolkades inte`);
  return inlagg;
}

function rendera(inlagg: Inlagg[], strommande: Strommande | null = null) {
  return render(<TradRenderare inlagg={inlagg} strommande={strommande} />);
}

const OKANT = /^kortet kunde inte visas · /;

function uppskjutet<T>() {
  let losa!: (v: T) => void;
  let vagra!: (e: unknown) => void;
  const lofte = new Promise<T>((l, v) => {
    losa = l;
    vagra = v;
  });
  return { lofte, losa, vagra };
}

const tomTradSvar = (over: Partial<TradSvar> = {}): TradSvar => ({
  view_key: "bocker.balans",
  thread_id: null,
  fiscal_year_id: "fy-2026",
  model: null,
  posts: [],
  cursor: 0,
  archive_fiscal_year_ids: [],
  ...over,
});

function medKlient(barn: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{barn}</QueryClientProvider>;
}

beforeEach(() => {
  hamtaTrad.mockReset();
  skickaMeddelande.mockReset();
});

// ─── Switchen ─────────────────────────────────────────────────────────────

describe("TradRenderare väljer komponent per type (SPEC §5)", () => {
  it("agent_text → TradInlagg/agent med metarad och spår", () => {
    rendera([typad(FIXTUR_AGENT_TEXT)]);
    expect(screen.getByText(/Jag postar elnätsfakturan från Nordkraft/)).toBeInTheDocument();
    expect(screen.getByText(/^agenten · \d\d:\d\d$/)).toBeInTheDocument();
    expect(screen.getAllByTestId("sparchip")).toHaveLength(2);
    expect(screen.queryByTestId("jamforelse-rad")).toBeNull();
  });

  it("agent_text med rows → RadLista i TradInlaggs slot", () => {
    const raw = medKropp(FIXTUR_AGENT_TEXT, {
      text: "Lönerna i juni:",
      rows: [
        { key: "ap", text: "Anna Pettersson", amount_ore: 3840000 },
        { key: "ml", text: "Mats Lund", amount_ore: 3490000 },
      ],
    });
    rendera([typad(raw)]);
    expect(screen.getByText("Lönerna i juni:")).toBeInTheDocument();
    expect(screen.getAllByTestId("jamforelse-rad")).toHaveLength(2);
    // En kolumn tal, inte två — det är RadLista, inte JamforelseRader.
    expect(screen.getAllByTestId("tal")).toHaveLength(2);
  });

  it("user_text → TradInlagg/du", () => {
    rendera([typad(FIXTUR_USER_TEXT)]);
    const text = screen.getByText("Vad består kundfordringarna av?");
    expect(text.className).toContain("bg-bok-bubbla");
  });

  it("user_file → FilInlagg", () => {
    rendera([typad(FIXTUR_USER_FILE)]);
    expect(screen.getByTestId("filkort")).toHaveTextContent("kvitto-clas-ohlson.pdf");
  });

  it("receipt → JamforelseRader med båda talen", () => {
    rendera([typad(FIXTUR_RECEIPT)]);
    expect(screen.getByTestId("jamforelse")).toHaveTextContent("A-118 postad");
    expect(screen.getAllByTestId("tal")).toHaveLength(2);
  });

  it("draft → VerifikationsForslag, utan knappar tills C12", () => {
    const { container } = rendera([typad(FIXTUR_DRAFT)]);
    expect(container.querySelector(`[data-inlagg-id="${FIXTUR_DRAFT.id}"]`)).not.toBeNull();
    expect(screen.getAllByTestId("konteringsrad")).toHaveLength(3);
    // En knapp utan idempotensnyckeln vore en väg till två verifikationer.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("decision → BeslutKort (C6), inte okant_kontrakt-raden", () => {
    // Beslutskortet läser sin status med TanStack Query (§7); utan vy frågar
    // det inte och står i öppet läge.
    const { container } = render(
      medKlient(<TradRenderare inlagg={[typad(FIXTUR_DECISION)]} strommande={null} />)
    );
    const kort = container.querySelector<HTMLElement>(`[data-inlagg-id="${FIXTUR_DECISION.id}"]`);
    expect(kort?.dataset.beslutLage).toBe("oppen");
    expect(screen.queryByText(OKANT)).toBeNull();
  });

  it.each([
    ["options", FIXTUR_OPTIONS],
    ["error", FIXTUR_ERROR],
  ] as const)("%s har ingen renderare än → okant_kontrakt-raden, inte tomt", (typ, fixtur) => {
    rendera([typad(fixtur)]);
    const rad = screen.getByText(OKANT);
    expect(rad).toHaveTextContent(`kortet kunde inte visas · ${typ} · ${fixtur.id}`);
    expect(rad.className).toContain("bok-mono");
    expect(rad.className).toContain("text-[12px]");
    // Ingen knapp: raden säger att något finns, inte vad man kan göra (§4.4).
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("ett kontraktsbrott → okant_kontrakt med ursprungstypen, aldrig ett halvt kort", () => {
    const tvaRekommenderade = medKropp(FIXTUR_OPTIONS, {
      ...kropp(FIXTUR_OPTIONS),
      options: (kropp(FIXTUR_OPTIONS).options as Record<string, unknown>[]).map((o) => ({
        ...o,
        recommended: true,
      })),
    });
    const inlagg = typad(tvaRekommenderade);
    expect(inlagg.type).toBe("okant_kontrakt");
    rendera([inlagg]);
    expect(screen.getByText(OKANT)).toHaveTextContent(
      `kortet kunde inte visas · options · ${FIXTUR_OPTIONS.id}`
    );
  });

  it("ordningen är den inlägget kom i — renderaren flyttar inget", () => {
    const { container } = rendera([typad(FIXTUR_AGENT_TEXT), typad(FIXTUR_USER_TEXT)]);
    const text = container.textContent ?? "";
    expect(text.indexOf("Jag postar")).toBeLessThan(text.indexOf("Vad består"));
  });
});

describe("det strömmande inlägget (SPEC §6.3, testfall 11)", () => {
  it("ingen platshållare → ingen indikator", () => {
    rendera([typad(FIXTUR_AGENT_TEXT)]);
    expect(screen.queryByTestId("skriver-text")).toBeNull();
  });

  it("utan text än: bara indikatorn, med Läser…", () => {
    rendera([], { id: "streaming-r-9", run_id: "r-9", text: "", activity: null });
    expect(screen.getByTestId("skriver-text")).toHaveTextContent("Läser…");
  });

  it("med text: texten som agentinlägg plus indikatorn med activity, sist i tråden", () => {
    const { container } = rendera([typad(FIXTUR_USER_TEXT)], {
      id: "streaming-r-9",
      run_id: "r-9",
      text: "148 500 kr i tre",
      activity: "las_kontoplan",
    });
    expect(screen.getByText("148 500 kr i tre")).toBeInTheDocument();
    expect(screen.getByTestId("skriver-text").textContent).not.toBe("");
    expect(screen.getByTestId("skriver-text").textContent).not.toBe("Läser…");
    const text = container.textContent ?? "";
    expect(text.indexOf("Vad består")).toBeLessThan(text.indexOf("148 500 kr i tre"));
  });
});

// ─── ChattFalt ────────────────────────────────────────────────────────────

describe("ChattFalt töms bara när meddelandet är lagrat", () => {
  async function skrivOchSkicka(onSkicka: (t: string) => Promise<boolean>) {
    render(<ChattFalt vyTitel="Balansräkning" onSkicka={onSkicka} />);
    const falt = screen.getByRole("textbox");
    await userEvent.type(falt, "  Vad är 1510?  {Enter}");
    return falt as HTMLInputElement;
  }

  it("skickar den trimmade texten och tömmer fältet på true", async () => {
    const onSkicka = vi.fn(async () => true);
    const falt = await skrivOchSkicka(onSkicka);
    expect(onSkicka).toHaveBeenCalledWith("Vad är 1510?");
    await waitFor(() => expect(falt.value).toBe(""));
  });

  it("behåller texten på false — människan ska inte behöva skriva om", async () => {
    const onSkicka = vi.fn(async () => false);
    const falt = await skrivOchSkicka(onSkicka);
    expect(onSkicka).toHaveBeenCalledTimes(1);
    await Promise.resolve();
    expect(falt.value).toBe("  Vad är 1510?  ");
  });

  it("ett andra Enter medan det första är i flykt skickar inte igen", async () => {
    const svar = uppskjutet<boolean>();
    const onSkicka = vi.fn(() => svar.lofte);
    const falt = await skrivOchSkicka(onSkicka);
    await userEvent.type(falt, "{Enter}");
    expect(onSkicka).toHaveBeenCalledTimes(1);
    svar.losa(true);
    await waitFor(() => expect(falt.value).toBe(""));
  });

  it("utan onSkicka skickas ingenting och texten står kvar", async () => {
    render(<ChattFalt vyTitel="Balansräkning" />);
    const falt = screen.getByRole("textbox") as HTMLInputElement;
    await userEvent.type(falt, "hej{Enter}");
    expect(falt.value).toBe("hej");
  });
});

// ─── Kedjan: ChattFalt → useTrad → POST (testfall 12, 19) ─────────────────

describe("ChattKolumn skickar genom tråden", () => {
  const agent: RaInlagg = { ...FIXTUR_AGENT_TEXT, id: "s-1", seq: 1, traces: null };

  async function oppnaKolumn() {
    hamtaTrad.mockResolvedValue(tomTradSvar({ posts: [agent], cursor: 1 }));
    render(medKlient(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />));
    const trad = screen.getByLabelText("Tråd för Balansräkning");
    await within(trad).findByText(/Jag postar elnätsfakturan/);
    return { trad, falt: screen.getByRole("textbox") as HTMLInputElement };
  }

  it("läser vyns tråd med vyns nyckel", async () => {
    await oppnaKolumn();
    expect(hamtaTrad).toHaveBeenCalledWith("bocker.balans");
  });

  it("testfall 12 + 19: optimistiskt inlägg direkt, POST med texten ordagrant, ersatt på id", async () => {
    const svar = uppskjutet<MeddelandeSvar>();
    skickaMeddelande.mockReturnValue(svar.lofte);
    const { trad, falt } = await oppnaKolumn();

    await userEvent.type(falt, "Vad består kundfordringarna av?{Enter}");

    // Syns innan servern svarat.
    expect(within(trad).getByText("Vad består kundfordringarna av?")).toBeInTheDocument();
    // Fritexten går rakt till POST …/messages — ingen tolkning, inget
    // beslut-id gissat ur texten (§7).
    expect(skickaMeddelande).toHaveBeenCalledTimes(1);
    expect(skickaMeddelande).toHaveBeenCalledWith("bocker.balans", "Vad består kundfordringarna av?");
    // Texten står kvar i fältet tills servern lagrat den.
    expect(falt.value).toBe("Vad består kundfordringarna av?");

    svar.losa({
      thread_id: "t-1",
      view_key: "bocker.balans",
      fiscal_year_id: "fy-2026",
      posts: [{ ...FIXTUR_USER_TEXT, id: "s-2", seq: 2, body: { text: "Vad består kundfordringarna av?" } }],
      cursor: 2,
    });

    await waitFor(() => expect(falt.value).toBe(""));
    // Ersatt, inte dubblerat.
    expect(within(trad).getAllByText("Vad består kundfordringarna av?")).toHaveLength(1);
  });

  it("misslyckad POST: inlägget försvinner, texten står kvar, felet syns neutralt", async () => {
    skickaMeddelande.mockRejectedValue(new Error("nätet borta"));
    const { trad, falt } = await oppnaKolumn();

    await userEvent.type(falt, "Vad består kundfordringarna av?{Enter}");

    await waitFor(() =>
      expect(within(trad).queryByText("Vad består kundfordringarna av?")).toBeNull()
    );
    expect(falt.value).toBe("Vad består kundfordringarna av?");
    const fel = screen.getByTestId("trad-fel");
    expect(fel.className).toContain("bok-mono");
    expect(fel.textContent).not.toBe("");
  });

  it("en inaktiv vy läser ingen tråd — en ström per flik, den aktiva vyns (§6.2 punkt 5)", () => {
    hamtaTrad.mockResolvedValue(tomTradSvar());
    render(medKlient(<ChattKolumn vyTitel="Resultaträkning" viewKey="bocker.resultat" aktiv={false} />));
    expect(hamtaTrad).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Tråd för Resultaträkning")).toHaveAttribute("aria-live", "polite");
  });
});

// ─── Testfall 32, trådens halva ───────────────────────────────────────────

describe("mocken för tråden är borta (testfall 32)", () => {
  it("lib/skal/mock exporterar ingen mockTrad", () => {
    expect("mockTrad" in skalMock).toBe(false);
  });

  it("varken mockTrad, TradInlaggData eller TRAD står kvar i källan", () => {
    const kalla = readFileSync(path.resolve(__dirname, "../../../lib/skal/mock.ts"), "utf8");
    expect(kalla).not.toMatch(/\bmockTrad\b/);
    expect(kalla).not.toMatch(/\bTradInlaggData\b/);
    expect(kalla).not.toMatch(/\bconst TRAD\b/);
  });
});
