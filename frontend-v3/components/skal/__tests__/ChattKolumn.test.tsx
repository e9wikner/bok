import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import type { UseTrad } from "@/hooks/useTrad";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { Inlagg, RaInlagg } from "@/lib/chattyta/typer";
import {
  FIXTUR_AGENT_TEXT,
  FIXTUR_DECISION,
  FIXTUR_USER_TEXT,
} from "@/lib/chattyta/__fixtures__/inlagg";

// Tråden kommer ur `useTrad` sedan chattyta C5 — skalets egen mock är borta.
// Skalets tester prövar layouten, så hooken ersätts med ett fast svar.
const typad = (raw: RaInlagg) => parseInlagg(raw) as Inlagg;
const trad: Inlagg[] = [
  typad({ ...FIXTUR_AGENT_TEXT, body: { text: "Balansräkningen är uppdaterad per i morse." } }),
  typad(FIXTUR_USER_TEXT),
];

const tradSvar: UseTrad = {
  inlagg: trad,
  strommande: null,
  skicka: async () => true,
  laddar: false,
  fel: null,
};
const useTrad = vi.fn((_viewKey: string): UseTrad => tradSvar);
vi.mock("@/hooks/useTrad", () => ({ useTrad: (vk: string) => useTrad(vk) }));

beforeEach(() => {
  useTrad.mockClear();
  useTrad.mockImplementation(() => tradSvar);
});

describe("ChattFalt är ren text — inga förslagschips (spec §2.1)", () => {
  it("har ett textfält och ingen enda knapp under det", () => {
    const { container } = render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    const form = container.querySelector("form")!;
    expect(within(form).getByRole("textbox")).toBeInTheDocument();
    // Ett chip är ett förvalt yttrande. Designens egen regel är att
    // ingenting förväljs — lägg inte tillbaka dem.
    expect(within(form).queryAllByRole("button")).toHaveLength(0);
  });

  it("fältet har en etikett som namnger vyn", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(screen.getByLabelText(/Fråga om en post i balansräkning/i)).toBeInTheDocument();
  });
});

describe("tråden kommer ur useTrad och ritas av chattytans renderare", () => {
  it("läser vyns tråd med vyns nyckel", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(useTrad).toHaveBeenCalledWith("bocker.balans");
  });

  it("renderar agentens text och egen replik", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(screen.getByText(/Balansräkningen är uppdaterad/)).toBeInTheDocument();
    expect(screen.getByText("Vad består kundfordringarna av?")).toBeInTheDocument();
  });

  it("annonserar tråden via aria-live", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(screen.getByLabelText("Tråd för Balansräkning")).toHaveAttribute(
      "aria-live",
      "polite"
    );
  });

  it("skalet bygger inga kort själv — en typ utan renderare blir okant_kontrakt, inte ett halvt kort", () => {
    // BeslutKort, AlternativLista, FelKort … är `chattyta`. Tills de finns
    // säger tråden ärligt att något finns (SPEC-chattyta.md §4.4).
    useTrad.mockImplementation(() => ({ ...tradSvar, inlagg: [typad(FIXTUR_DECISION)] }));
    render(<ChattKolumn vyTitel="Verifikationer" viewKey="bocker.verifikationer" />);
    expect(screen.getByText(`kortet kunde inte visas · decision · ${FIXTUR_DECISION.id}`)).toBeInTheDocument();
  });

  it("tråden är bottenankrad", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(screen.getByLabelText("Tråd för Balansräkning").className).toContain("justify-end");
  });
});

describe("ChattList på mobilen (testfall 16)", () => {
  it("visar märket för väntande beslut även när chatten är minimerad", async () => {
    const { getByRole, getByTestId } = render(
      <ChattList vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={1} />
    );
    const knapp = getByRole("button", { name: "Visa eller minimera chatten" });
    expect(getByTestId("chattlist-marke")).toHaveTextContent("1 väntar");

    knapp.click();
    // Minimerad: tråden är borta, märket är kvar.
    expect(getByTestId("chattlist-marke")).toHaveTextContent("1 väntar");
  });

  it("märket bär väntar-färgen bara när något faktiskt väntar", () => {
    const { getByTestId, rerender } = render(
      <ChattList vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={1} />
    );
    expect(getByTestId("chattlist-marke").style.color).toContain("vantar");

    rerender(<ChattList vyTitel="Balansräkning" viewKey="bocker.balans" vantandeBeslut={0} />);
    expect(getByTestId("chattlist-marke").style.color).not.toContain("vantar");
  });

  it("utan väntande beslut räknar märket trådens inlägg", () => {
    const { getByTestId } = render(
      <ChattList vyTitel="Balansräkning" viewKey="bocker.balans" vantandeBeslut={0} />
    );
    expect(getByTestId("chattlist-marke")).toHaveTextContent(`${trad.length} inlägg`);
  });

  it("läser tråden en gång, inte en gång för listen och en för tråden i den", () => {
    render(<ChattList vyTitel="Balansräkning" viewKey="bocker.balans" vantandeBeslut={0} />);
    expect(new Set(useTrad.mock.calls.map(([vk]) => vk))).toEqual(new Set(["bocker.balans"]));
    // En rendering = ett anrop; två komponenter som båda anropar hooken
    // vore två strömmar mot samma tråd.
    expect(useTrad.mock.calls.length).toBe(1);
  });

  it("listen är minst 50 px hög, som designen kräver", () => {
    const { getByRole } = render(
      <ChattList vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={0} />
    );
    expect(getByRole("button", { name: "Visa eller minimera chatten" }).className).toContain(
      "min-h-[50px]"
    );
  });
});
