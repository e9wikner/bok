import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FelKort } from "@/components/chattyta/FelKort";
import { TradRenderare } from "@/components/chattyta/TradRenderare";
import { klockslag } from "@/components/chattyta/TradInlagg";
import { nyckelForUtkast } from "@/lib/chattyta/idempotens";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { DraftKropp, ErrorInlagg, Inlagg, RaInlagg, Spar } from "@/lib/chattyta/typer";
import { FIXTUR_DRAFT, FIXTUR_ERROR, kropp } from "@/lib/chattyta/__fixtures__/inlagg";

/**
 * `FelKort` (SPEC-chattyta.md §5, §9, §11; komponenter.md §FelKort; C13).
 *
 * Nätet mockas, inte `postaUtkast` eller `usePostaUtkast`: testfall 30 kräver
 * att `Försök igen` bär SAMMA `Idempotency-Key` som `Posta`, och det kan bara
 * prövas om det är den riktiga kedjan hook → `postaUtkast` →
 * `nyckelForUtkast` som räknar fram headern.
 */

const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: vi.fn(),
    post: (...a: unknown[]) => post(...a),
  },
}));

// ─── Hjälpare ─────────────────────────────────────────────────────────────

function typad(raw: RaInlagg): Inlagg {
  const inlagg = parseInlagg(raw);
  if (!inlagg) throw new Error(`fixturen ${raw.id} tolkades inte`);
  return inlagg;
}

const UTKAST = kropp(FIXTUR_DRAFT) as unknown as DraftKropp;
const DRAFT_ID = UTKAST.draft_id;
const URL_POST = `/api/v1/vouchers/${encodeURIComponent(DRAFT_ID)}/post`;

/** Felinlägget som servern skriver det i dag: `retry_draft_id: null`. */
const felUtanOmforsok = () => typad(FIXTUR_ERROR) as ErrorInlagg;

/** Samma inlägg, men med ett utkast att försöka igen med (§9, andra halvan). */
function felMedOmforsok(over: Partial<RaInlagg> = {}): ErrorInlagg {
  return typad({
    ...FIXTUR_ERROR,
    body: { ...kropp(FIXTUR_ERROR), retry_draft_id: DRAFT_ID },
    ...over,
  }) as ErrorInlagg;
}

const SPAR: Spar[] = [
  { tool: "hamta_period", label: "period hämtad", detail: "2026-09" },
  { tool: "posta_verifikation", label: "postning nekad" },
];

let qc: QueryClient;
const medKlient = (barn: ReactNode) => (
  <QueryClientProvider client={qc}>{barn}</QueryClientProvider>
);

/** Nyckeln i anrop nummer `i`, som den stod i headern. */
const nyckelI = (i: number) =>
  (post.mock.calls[i][2] as { headers: Record<string, string> }).headers["Idempotency-Key"];

const svar200 = () => ({
  status: 200,
  data: { id: DRAFT_ID, series: "A", number: 118, status: "posted" },
  headers: {},
});

const axiosFel = (status: number, detail: unknown) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail }, headers: {} },
  });

const natverksFel = () =>
  Object.assign(new Error("Network Error"), { isAxiosError: true, response: undefined });

beforeEach(() => {
  post.mockReset();
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

// ─── Innehållet ───────────────────────────────────────────────────────────

describe("FelKort — rubrik, orsak och konsekvens (komponenter.md, antagande 3)", () => {
  it("orsak OCH konsekvens ur kroppen, ordagrant", () => {
    render(<FelKort inlagg={felUtanOmforsok()} />);
    const text = screen.getByTestId("fel-text");
    expect(text).toHaveTextContent("period_locked: september 2026");
    expect(text).toHaveTextContent("Ingenting är bokfört.");
  });

  it("rubriken är kort och lugn — konsekvensen bär innehållet", () => {
    render(<FelKort inlagg={felUtanOmforsok()} />);
    expect(screen.getByTestId("fel-rubrik")).toHaveTextContent(/^Något gick fel$/);
  });

  it("metaraden: HH:MM ur created_at och orsakskoden", () => {
    render(<FelKort inlagg={felUtanOmforsok()} />);
    const meta = screen.getByTestId("fel-meta");
    expect(meta).toHaveTextContent(`${klockslag(FIXTUR_ERROR.created_at)} · period_locked`);
    expect(meta.className).toContain("bok-mono");
    expect(meta.className).toContain("text-[12px]");
  });

  it("en orsak utan maskinkod (fri text) upprepas inte i metaraden", () => {
    const inlagg = typad({
      ...FIXTUR_ERROR,
      body: { ...kropp(FIXTUR_ERROR), cause: "okänd orsak" },
    }) as ErrorInlagg;
    render(<FelKort inlagg={inlagg} />);
    expect(screen.getByTestId("fel-meta")).toHaveTextContent(
      new RegExp(`^${klockslag(FIXTUR_ERROR.created_at)}$`)
    );
    expect(screen.getByTestId("fel-text")).toHaveTextContent("okänd orsak");
  });

  it("en orsak som är en kod utan kolon (agent_turn_limit) visas som kod", () => {
    const inlagg = typad({
      ...FIXTUR_ERROR,
      body: { ...kropp(FIXTUR_ERROR), cause: "agent_turn_limit" },
    }) as ErrorInlagg;
    render(<FelKort inlagg={inlagg} />);
    expect(screen.getByTestId("fel-meta")).toHaveTextContent("· agent_turn_limit");
  });

  it("felets toner och kortets mått (komponenter.md §FelKort, README fel-tokens)", () => {
    const { container } = render(<FelKort inlagg={felUtanOmforsok()} />);
    const kort = container.querySelector<HTMLElement>(`[data-inlagg-id="${FIXTUR_ERROR.id}"]`)!;
    for (const k of [
      "bg-bok-fel-yta",
      "border-bok-fel-kant",
      "max-w-[560px]",
      "rounded-[12px]",
      "px-[22px]",
      "py-[20px]",
    ]) {
      expect(kort.className).toContain(k);
    }
    const rubrik = screen.getByTestId("fel-rubrik");
    expect(rubrik.className).toContain("text-bok-fel-rubrik");
    expect(rubrik.className).toContain("text-[14px]");
    expect(rubrik.className).toContain("font-medium");
    expect(screen.getByTestId("fel-meta").className).toContain("text-bok-fel-meta");
    const text = screen.getByTestId("fel-text");
    expect(text.className).toContain("text-bok-fel-text");
    expect(text.className).toContain("text-[14px]");
    expect(text.className).toContain("leading-[1.55]");
    // Felorsaken är inte metatext (§11): aldrig metagrått.
    expect(text.className).not.toContain("text-bok-meta");
  });
});

// ─── Försök igen ──────────────────────────────────────────────────────────

describe("FelKort — Försök igen (SPEC §9)", () => {
  it("testfall 29: utan retry_draft_id finns ingen primärknapp — bara Visa vad som hände", () => {
    // Renderas UTAN QueryClientProvider: utan utkast finns ingen postning,
    // och kortet får då inte kräva en (ChattKolumn-testerna ritar det så).
    render(<FelKort inlagg={felUtanOmforsok()} />);
    expect(screen.queryByRole("button", { name: /Försök igen/ })).toBeNull();
    const knappar = screen.getAllByRole("button");
    expect(knappar).toHaveLength(1);
    expect(knappar[0]).toHaveTextContent("Visa vad som hände");
    expect(post).not.toHaveBeenCalled();
  });

  it("testfall 30: med retry_draft_id postar Försök igen med nyckelForUtkast(retry_draft_id)", async () => {
    post.mockResolvedValue(svar200());
    const user = userEvent.setup();
    render(medKlient(<FelKort inlagg={felMedOmforsok()} />));

    await user.click(screen.getByRole("button", { name: "Försök igen" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe(URL_POST);
    expect(nyckelI(0)).toBe(await nyckelForUtkast(DRAFT_ID));
    // Hookens utfall: postad, med numret, och ingen knapp att trycka igen.
    expect(await screen.findByTestId("fel-postad")).toHaveTextContent("Postad · A-118");
    expect(screen.queryByRole("button", { name: "Försök igen" })).toBeNull();
  });

  it("testfall 30: samma nyckel som förslagskortets Posta för samma utkast", async () => {
    post.mockResolvedValueOnce(svar200()).mockResolvedValueOnce(svar200());
    const user = userEvent.setup();
    render(
      medKlient(
        <TradRenderare
          inlagg={[typad(FIXTUR_DRAFT), felMedOmforsok()]}
          strommande={null}
        />
      )
    );

    await user.click(screen.getByRole("button", { name: "Posta" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Försök igen" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));

    expect(nyckelI(0)).toBe(nyckelI(1));
    expect(post.mock.calls[1][0]).toBe(URL_POST);
  });

  it("nätverksfel: hookens text, och Försök igen står kvar med samma nyckel", async () => {
    post.mockRejectedValueOnce(natverksFel()).mockResolvedValueOnce(svar200());
    const user = userEvent.setup();
    render(medKlient(<FelKort inlagg={felMedOmforsok()} />));

    await user.click(screen.getByRole("button", { name: "Försök igen" }));
    const utfall = await screen.findByTestId("fel-utfall");
    // Klienten vet inte om servern hann (C12) — inget `Ingenting är bokfört`.
    expect(utfall).not.toHaveTextContent("Ingenting är bokfört");
    expect(utfall).toHaveTextContent("oklart");

    await user.click(screen.getByRole("button", { name: "Försök igen" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(nyckelI(0)).toBe(nyckelI(1));
    expect(await screen.findByTestId("fel-postad")).toHaveTextContent("Postad · A-118");
  });

  it("409 period_locked: vem och när, och ingen Försök igen — det kan inte lyckas", async () => {
    post.mockRejectedValueOnce(
      axiosFel(409, {
        code: "period_locked",
        period_id: "per-2026-09",
        locked_at: "2026-10-12T09:14:03",
        locked_by: null,
      })
    );
    const user = userEvent.setup();
    render(medKlient(<FelKort inlagg={felMedOmforsok()} />));

    await user.click(screen.getByRole("button", { name: "Försök igen" }));
    const utfall = await screen.findByTestId("fel-utfall");
    expect(utfall).toHaveTextContent("2026-10-12 09:14");
    expect(utfall).toHaveTextContent("okänd");
    expect(utfall).toHaveTextContent("Ingenting är bokfört.");
    expect(screen.queryByRole("button", { name: "Försök igen" })).toBeNull();
  });

  it("i flykt: Postar… och låst med aria-disabled, inte disabled", async () => {
    let losa!: (v: unknown) => void;
    post.mockReturnValueOnce(new Promise((l) => (losa = l)));
    const user = userEvent.setup();
    render(medKlient(<FelKort inlagg={felMedOmforsok()} />));

    await user.click(screen.getByRole("button", { name: "Försök igen" }));
    const knapp = await screen.findByRole("button", { name: "Postar…" });
    expect(knapp).toHaveAttribute("aria-disabled", "true");
    expect(knapp).not.toBeDisabled();
    await user.click(knapp);
    expect(post).toHaveBeenCalledTimes(1);

    losa(svar200());
    expect(await screen.findByTestId("fel-postad")).toBeInTheDocument();
  });
});

// ─── Visa vad som hände ───────────────────────────────────────────────────

describe("FelKort — Visa vad som hände (SPEC §5)", () => {
  it("fäller ut traces[] på plats som SparChip, och in igen; aria-expanded följer", async () => {
    const user = userEvent.setup();
    render(<FelKort inlagg={{ ...felUtanOmforsok(), traces: SPAR }} />);
    const knapp = screen.getByRole("button", { name: "Visa vad som hände" });

    expect(knapp).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryAllByTestId("sparchip")).toHaveLength(0);

    await user.click(knapp);
    expect(knapp).toHaveAttribute("aria-expanded", "true");
    const chips = screen.getAllByTestId("sparchip");
    expect(chips.map((c) => c.textContent)).toEqual([
      "period hämtad · 2026-09",
      "postning nekad",
    ]);
    // Knappen pekar ut ytan den styr.
    const yta = document.getElementById(knapp.getAttribute("aria-controls")!);
    expect(yta).not.toBeNull();
    expect(within(yta!).getAllByTestId("sparchip")).toHaveLength(2);

    await user.click(knapp);
    expect(knapp).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryAllByTestId("sparchip")).toHaveLength(0);
  });

  it("utan spår: en neutral rad i stället för en tom yta", async () => {
    const user = userEvent.setup();
    render(<FelKort inlagg={felUtanOmforsok()} />);
    await user.click(screen.getByRole("button", { name: "Visa vad som hände" }));
    expect(screen.getByTestId("fel-inga-spar")).toHaveTextContent(
      "Inga spår sparades för den här turen."
    );
    expect(screen.queryAllByTestId("sparchip")).toHaveLength(0);
  });

  it("en tom spårlista är samma sak som inga spår", async () => {
    const user = userEvent.setup();
    render(<FelKort inlagg={{ ...felUtanOmforsok(), traces: [] }} />);
    await user.click(screen.getByRole("button", { name: "Visa vad som hände" }));
    expect(screen.getByTestId("fel-inga-spar")).toBeInTheDocument();
  });
});

// ─── I tråden ─────────────────────────────────────────────────────────────

describe("error i renderaren (C13)", () => {
  it("error → FelKort, inte okant_kontrakt-raden", () => {
    const { container } = render(
      <TradRenderare inlagg={[typad(FIXTUR_ERROR)]} strommande={null} />
    );
    expect(container.querySelector(`[data-inlagg-id="${FIXTUR_ERROR.id}"]`)).not.toBeNull();
    expect(screen.queryByTestId("okant-kontrakt")).toBeNull();
    expect(screen.getByTestId("fel-text")).toHaveTextContent("period_locked: september 2026");
  });
});
