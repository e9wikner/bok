import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BeslutKort } from "@/components/chattyta/BeslutKort";
import { TradRenderare } from "@/components/chattyta/TradRenderare";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import { beslutStatusNyckel } from "@/hooks/useBeslut";
import type { UseTrad } from "@/hooks/useTrad";
import { BESLUT_NYCKEL, type BeslutListSvar, type BeslutSvar } from "@/lib/chattyta/api";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { DecisionInlagg, Inlagg, RaInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_DECISION, FIXTUR_USER_TEXT, kropp, medKropp } from "@/lib/chattyta/__fixtures__/inlagg";
import { formatBelopp } from "@/lib/skal/format";

// ─── Mockar ───────────────────────────────────────────────────────────────
// Nätet, inte hooken: testfall 20 räknar anrop, och det ska vara de riktiga
// `hamtaBeslut` och TanStack Query som gör (eller inte gör) dem.

const get = vi.fn();
vi.mock("@/lib/api", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

// Skalets ytor läser tråden via `useTrad`; här prövas bara att vyns nyckel
// når korten, så tråden är ett fast svar.
let tradSvar: UseTrad;
vi.mock("@/hooks/useTrad", () => ({ useTrad: () => tradSvar }));

// ─── Hjälpare ─────────────────────────────────────────────────────────────

const VY = "bocker.verifikationer";

function typad(raw: RaInlagg): Inlagg {
  const inlagg = parseInlagg(raw);
  if (!inlagg) throw new Error(`fixturen ${raw.id} tolkades inte`);
  return inlagg;
}

/** Ett beslutsinlägg till, med eget inläggs-id och `decision_id`. */
function beslutsInlagg(postId: string, decisionId: string, seq: number, over = {}): Inlagg {
  return typad({
    ...medKropp(FIXTUR_DECISION, { ...kropp(FIXTUR_DECISION), decision_id: decisionId, ...over }),
    id: postId,
    seq,
  });
}

const beslut = (over: Partial<BeslutSvar> = {}): BeslutSvar => ({
  id: "d-1",
  view_key: VY,
  kind: "abstention",
  status: "open",
  title: "Swish 4 500 kr utan referens",
  amount_ore: 450000,
  reason: "Serverns rad — kortet läser inlägget, inte den här.",
  consequence: "Serverns rad.",
  source: { kind: "bank", id: "b-31", date: "2026-09-14" },
  age_days: 3,
  thread_id: "t-1",
  post_id: "p-4",
  options: [],
  ...over,
});

const svar = (decisions: BeslutSvar[]): { data: BeslutListSvar } => ({
  data: { decisions, total: decisions.length },
});

let qc: QueryClient;
const medKlient = (barn: ReactNode) => (
  <QueryClientProvider client={qc}>{barn}</QueryClientProvider>
);

// `null` = ingen vy. Inte `undefined`: då slår standardvärdet till.
function renderaTrad(inlagg: Inlagg[], vy: string | null = VY) {
  const viewKey = vy ?? undefined;
  return render(medKlient(<TradRenderare inlagg={inlagg} strommande={null} viewKey={viewKey} />));
}

const kort = (container: HTMLElement, postId: string) =>
  container.querySelector<HTMLElement>(`[data-inlagg-id="${postId}"]`)!;

/** Kortet direkt, utan fråga: för lägena och kroppen. */
const DECISION = typad(FIXTUR_DECISION) as DecisionInlagg;
const renderaKort = (b?: BeslutSvar, inlagg: DecisionInlagg = DECISION) =>
  render(<BeslutKort inlagg={inlagg} beslut={b} />);

beforeEach(() => {
  get.mockReset();
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

// ─── Testfall 17: tre lägen ───────────────────────────────────────────────

describe("BeslutKort i tre lägen, knappar bara i öppet (testfall 17)", () => {
  it("öppen: väntar-ytan, rubriken, inga knappar av egen del (testfall 17)", () => {
    const { container } = renderaKort(beslut({ status: "open" }));
    const k = kort(container, DECISION.id);
    expect(k.dataset.beslutLage).toBe("oppen");
    expect(k.className).toContain("bg-bok-vantar-yta");
    expect(k.className).toContain("border-bok-vantar-kant");
    expect(screen.getByText("Agenten avstod · behöver ditt beslut")).toBeInTheDocument();
    // Kroppen säger inte vad en primär- eller sekundärknapp skulle göra
    // (todo.md C6, obs). Svaret går via `options`-inlägget (C7) eller
    // fritexten (§7) — kortet självt har ingen knapp än.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("besvarad: `Besvarat`, ingen väntar-ton, inga knappar (testfall 17)", () => {
    const { container } = renderaKort(beslut({ status: "answered" }));
    const k = kort(container, DECISION.id);
    expect(k.dataset.beslutLage).toBe("besvarad");
    expect(within(k).getByTestId("beslut-rubrik")).toHaveTextContent(/^Besvarat$/);
    expect(k.className).not.toContain("bok-vantar");
    expect(screen.queryByText(/behöver ditt beslut/)).toBeNull();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("besvarad utan answered_at: inget klockslag som servern inte gett", () => {
    renderaKort(beslut({ status: "answered" }));
    expect(screen.getByTestId("beslut-rubrik").textContent).not.toMatch(/\d\d:\d\d/);
    expect(screen.queryByTestId("beslut-svar")).toBeNull();
  });

  it("besvarad med fritext: `Besvarat · HH:MM` och svaret ordagrant (§5)", () => {
    renderaKort(
      beslut({
        status: "answered",
        answered_at: "2026-09-18T09:12:00",
        answered_by: "stefan",
        answer_text: "Boka på 6250 – resekostnader.",
      })
    );
    expect(screen.getByTestId("beslut-rubrik")).toHaveTextContent(/^Besvarat · 09:12$/);
    expect(screen.getByTestId("beslut-svar")).toHaveTextContent("Boka på 6250 – resekostnader.");
  });

  it("besvarad med ett alternativ: alternativets titel och konto ur listan", () => {
    renderaKort(
      beslut({
        status: "answered",
        answered_at: "2026-09-18T09:12:00",
        answer_option_id: "o-1",
        options: [
          {
            id: "o-1",
            position: 0,
            title: "Betalning av faktura 1044",
            rationale: "r",
            account: "1510",
            amount_ore: 450000,
            recommended: true,
            is_exit: false,
          },
        ],
      })
    );
    expect(screen.getByTestId("beslut-svar")).toHaveTextContent("Betalning av faktura 1044 · 1510");
  });

  it("besvarad med ett alternativ som inte finns i listan: ingen svarsrad, ingen gissning", () => {
    renderaKort(beslut({ status: "answered", answer_option_id: "o-okand" }));
    expect(screen.queryByTestId("beslut-svar")).toBeNull();
  });

  it("ersatt: `Inte längre aktuellt`, inga knappar (testfall 17)", () => {
    const { container } = renderaKort(beslut({ status: "superseded" }));
    const k = kort(container, DECISION.id);
    expect(k.dataset.beslutLage).toBe("ersatt");
    expect(within(k).getByTestId("beslut-rubrik")).toHaveTextContent(/^Inte längre aktuellt$/);
    expect(k.className).not.toContain("bok-vantar");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("inlägget ändras aldrig: kroppen står kvar ordagrant i alla tre lägen (antagande 2, 3)", () => {
    const k = kropp(FIXTUR_DECISION) as { title: string; reason: string; consequence: string };
    for (const status of ["open", "answered", "superseded"] as const) {
      const { unmount } = renderaKort(beslut({ status }));
      expect(screen.getByText(k.title)).toBeInTheDocument();
      expect(screen.getByText(k.reason)).toBeInTheDocument();
      expect(screen.getByText(k.consequence)).toBeInTheDocument();
      // Serverns listrad bär egna texter; kortet läser inlägget, inte dem.
      expect(screen.queryByText(/Serverns rad/)).toBeNull();
      unmount();
    }
  });

  it("status okänd (inte laddad eller id saknas): öppet läge som inte påstår sorten", () => {
    const { container } = renderaKort(undefined);
    const k = kort(container, DECISION.id);
    expect(k.dataset.beslutLage).toBe("oppen");
    expect(k.dataset.beslutKant).toBe("nej");
    // Varken "Agenten avstod" eller "godkännande": sorten står bara i
    // GET /decisions, inte i inlägget.
    expect(within(k).getByTestId("beslut-rubrik")).toHaveTextContent(/^Behöver ditt beslut$/);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

// ─── Testfall 18: GodkannKort ─────────────────────────────────────────────

describe("kind=approval → GodkannKort-rubriken (testfall 18)", () => {
  it("approval: `Väntar på ditt godkännande` (testfall 18)", () => {
    renderaKort(beslut({ kind: "approval" }));
    expect(screen.getByTestId("beslut-rubrik")).toHaveTextContent(/^Väntar på ditt godkännande$/);
    expect(screen.queryByText(/Agenten avstod/)).toBeNull();
  });

  it("abstention: `Agenten avstod · behöver ditt beslut` (testfall 18)", () => {
    renderaKort(beslut({ kind: "abstention" }));
    expect(screen.getByTestId("beslut-rubrik")).toHaveTextContent(
      /^Agenten avstod · behöver ditt beslut$/
    );
  });

  it("besvarat godkännande säger `Besvarat`, inte att det väntar (testfall 18 + 17)", () => {
    renderaKort(beslut({ kind: "approval", status: "answered" }));
    expect(screen.getByTestId("beslut-rubrik")).toHaveTextContent(/^Besvarat$/);
  });
});

// ─── Kroppen: belopp, källrad, åldern ─────────────────────────────────────

describe("kroppen (komponenter.md §BeslutKort, SPEC §10)", () => {
  it("beloppet är inläggets öre via formatBelopp, mono tabulärt", () => {
    renderaKort(beslut());
    const belopp = screen.getByTestId("beslut-belopp");
    // `textContent`, inte `toHaveTextContent`: den senare normaliserar
    // formatBelopps hårda mellanslag.
    expect(belopp.textContent).toBe(formatBelopp(450000));
    expect(belopp.className).toContain("bok-mono");
    expect(belopp.className).toContain("bok-tal");
  });

  it("amount: null → inget belopp, ingen nolla", () => {
    const utanBelopp = typad(medKropp(FIXTUR_DECISION, { ...kropp(FIXTUR_DECISION), amount: null }));
    renderaKort(beslut(), utanBelopp as DecisionInlagg);
    expect(screen.queryByTestId("beslut-belopp")).toBeNull();
  });

  it("källraden: inläggets källa plus listans datum, mono 12", () => {
    renderaKort(beslut());
    const kalla = screen.getByTestId("beslut-kalla");
    expect(kalla).toHaveTextContent("bank · b-31 · 2026-09-14");
    expect(kalla.className).toContain("bok-mono");
    expect(kalla.className).toContain("text-[12px]");
  });

  it.each([
    [6, "var(--bok-vantar-meta)"],
    [7, "var(--bok-fel-meta)"],
    [30, "var(--bok-fel-meta)"],
  ])("age_days %i → källraden i %s (aldersTon, testfall 22)", (dagar, farg) => {
    renderaKort(beslut({ age_days: dagar }));
    expect(screen.getByTestId("beslut-kalla").style.color).toBe(farg);
  });

  it("utan status: källraden i väntar-tonen, aldrig gissat röd", () => {
    renderaKort(undefined);
    const kalla = screen.getByTestId("beslut-kalla");
    expect(kalla).toHaveTextContent(/^bank · b-31$/);
    expect(kalla.style.color).toBe("var(--bok-vantar-meta)");
  });

  it("besvarat: källraden är inte längre väntande — ingen ålderston", () => {
    renderaKort(beslut({ status: "answered", age_days: 30 }));
    expect(screen.getByTestId("beslut-kalla").style.color).not.toBe("var(--bok-fel-meta)");
  });

  it("utan källa: ingen källrad", () => {
    const utanKalla = typad(medKropp(FIXTUR_DECISION, { ...kropp(FIXTUR_DECISION), source: null }));
    renderaKort(beslut({ source: null }), utanKalla as DecisionInlagg);
    expect(screen.queryByTestId("beslut-kalla")).toBeNull();
  });

  it("konsekvensen är inte metatext (§11): text-bok-text-dampad, inte text-bok-meta", () => {
    renderaKort(beslut());
    const k = kropp(FIXTUR_DECISION) as { consequence: string };
    const notis = screen.getByText(k.consequence);
    expect(notis.className).toContain("text-bok-text-dampad");
    expect(notis.className).not.toContain("text-bok-meta");
  });
});

// ─── Testfall 20: ett GET per vy ──────────────────────────────────────────

describe("beslutsstatus: ett GET /decisions per vy, inte per kort (testfall 20)", () => {
  it("tre beslutsinlägg → ett anrop, status=all, limit=200 (testfall 20)", async () => {
    get.mockResolvedValue(
      svar([
        beslut({ id: "d-1", status: "open" }),
        beslut({ id: "d-2", status: "answered" }),
        beslut({ id: "d-3", status: "superseded", kind: "approval" }),
      ])
    );
    const { container } = renderaTrad([
      beslutsInlagg("p-1", "d-1", 1),
      beslutsInlagg("p-2", "d-2", 2),
      beslutsInlagg("p-3", "d-3", 3),
    ]);

    // Lägena kommer ur det ENDA svaret, uppslaget på `decision_id` (§7).
    await waitFor(() => expect(kort(container, "p-2").dataset.beslutLage).toBe("besvarad"));
    expect(kort(container, "p-1").dataset.beslutLage).toBe("oppen");
    expect(kort(container, "p-3").dataset.beslutLage).toBe("ersatt");

    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith("/api/v1/decisions", {
      params: { view_key: VY, status: "all", limit: 200, offset: undefined },
    });
  });

  it("id som inte finns i listan → öppet läge utan påstående (testfall 20)", async () => {
    get.mockResolvedValue(svar([beslut({ id: "d-annat" })]));
    const { container } = renderaTrad([beslutsInlagg("p-1", "d-1", 1)]);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(qc.isFetching()).toBe(0));
    expect(kort(container, "p-1").dataset.beslutLage).toBe("oppen");
    expect(kort(container, "p-1").dataset.beslutKant).toBe("nej");
  });

  it("en tråd utan beslutsinlägg frågar inte alls (testfall 20)", async () => {
    renderaTrad([typad(FIXTUR_USER_TEXT)]);
    await new Promise((r) => setTimeout(r, 20));
    expect(get).not.toHaveBeenCalled();
  });

  it("utan vy (ingen viewKey) frågar kortet inte, och står öppet (testfall 20)", async () => {
    const { container } = renderaTrad([beslutsInlagg("p-1", "d-1", 1)], null);
    await new Promise((r) => setTimeout(r, 20));
    expect(get).not.toHaveBeenCalled();
    expect(kort(container, "p-1").dataset.beslutLage).toBe("oppen");
  });

  it("nyckeln ligger under BESLUT_NYCKEL: useTrads invalidering hämtar om (§7, testfall 20)", async () => {
    expect(beslutStatusNyckel(VY)).toEqual([...BESLUT_NYCKEL, VY, "all"]);
    get
      .mockResolvedValueOnce(svar([beslut({ id: "d-1", status: "open" })]))
      .mockResolvedValueOnce(svar([beslut({ id: "d-1", status: "answered" })]));
    const { container } = renderaTrad([beslutsInlagg("p-1", "d-1", 1)]);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    await qc.invalidateQueries({ queryKey: BESLUT_NYCKEL });
    await waitFor(() => expect(kort(container, "p-1").dataset.beslutLage).toBe("besvarad"));
    expect(get).toHaveBeenCalledTimes(2);
  });
});

// ─── Vyns nyckel når korten genom skalets ytor ────────────────────────────

describe("skalets ytor ger korten vyns nyckel (testfall 20)", () => {
  beforeEach(() => {
    tradSvar = {
      inlagg: [beslutsInlagg("p-1", "d-1", 1), beslutsInlagg("p-2", "d-2", 2)],
      strommande: null,
      skicka: async () => true,
      laddar: false,
      fel: null,
    };
    get.mockResolvedValue(svar([beslut({ id: "d-1", status: "answered" })]));
  });

  it("desktop: ChattKolumn → ett GET med sin view_key (testfall 20)", async () => {
    const { container } = render(medKlient(<ChattKolumn vyTitel="Verifikationer" viewKey={VY} />));
    await waitFor(() => expect(kort(container, "p-1").dataset.beslutLage).toBe("besvarad"));
    expect(get).toHaveBeenCalledTimes(1);
    expect(get.mock.calls[0][1].params).toMatchObject({ view_key: VY, status: "all" });
  });

  it("mobil: ChattList → ett GET med sin view_key (testfall 20)", async () => {
    const { container } = render(
      medKlient(<ChattList vyTitel="Verifikationer" viewKey={VY} vantandeBeslut={0} />)
    );
    await waitFor(() => expect(kort(container, "p-1").dataset.beslutLage).toBe("besvarad"));
    expect(get).toHaveBeenCalledTimes(1);
    expect(get.mock.calls[0][1].params).toMatchObject({ view_key: VY, status: "all" });
  });
});
