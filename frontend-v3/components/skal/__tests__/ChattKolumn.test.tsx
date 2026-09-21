import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import { mockTrad } from "@/lib/skal/mock";

const trad = mockTrad("bocker.balans");

describe("ChattFalt är ren text — inga förslagschips (spec §2.1)", () => {
  it("har ett textfält och ingen enda knapp under det", () => {
    const { container } = render(<ChattKolumn vyTitel="Balansräkning" inlagg={trad} />);
    const form = container.querySelector("form")!;
    expect(within(form).getByRole("textbox")).toBeInTheDocument();
    // Ett chip är ett förvalt yttrande. Designens egen regel är att
    // ingenting förväljs — lägg inte tillbaka dem.
    expect(within(form).queryAllByRole("button")).toHaveLength(0);
  });

  it("fältet har en etikett som namnger vyn", () => {
    render(<ChattKolumn vyTitel="Balansräkning" inlagg={trad} />);
    expect(screen.getByLabelText(/Fråga om en post i balansräkning/i)).toBeInTheDocument();
  });
});

describe("tråden är skalets, inte chattytans", () => {
  it("renderar agentens text och egen replik", () => {
    render(<ChattKolumn vyTitel="Balansräkning" inlagg={trad} />);
    expect(screen.getByText(/Balansräkningen är uppdaterad/)).toBeInTheDocument();
    expect(screen.getByText("Vad består kundfordringarna av?")).toBeInTheDocument();
  });

  it("annonserar tråden via aria-live", () => {
    render(<ChattKolumn vyTitel="Balansräkning" inlagg={trad} />);
    expect(screen.getByLabelText("Tråd för Balansräkning")).toHaveAttribute(
      "aria-live",
      "polite"
    );
  });

  it("bygger inga kort — bara två inläggstyper", () => {
    // BeslutKort, AlternativLista, VerifikationsForslag, FelKort och
    // JamforelseRader är `chattyta`. Ett halvfärdigt kort som redan ser rätt
    // ut är värre än inget: kontrakten (ingen förvald rekommendation, alltid
    // en väg ut, alltid båda talen) bor i den modulen.
    const typer = new Set(trad.map((m) => m.typ));
    expect([...typer].sort()).toEqual(["agent_text", "user_text"]);
  });
});

describe("ChattList på mobilen (testfall 16)", () => {
  it("visar märket för väntande beslut även när chatten är minimerad", async () => {
    const { getByRole, getByTestId } = render(
      <ChattList vyTitel="Verifikationer" inlagg={trad} vantandeBeslut={1} />
    );
    const knapp = getByRole("button", { name: "Visa eller minimera chatten" });
    expect(getByTestId("chattlist-marke")).toHaveTextContent("1 väntar");

    knapp.click();
    // Minimerad: tråden är borta, märket är kvar.
    expect(getByTestId("chattlist-marke")).toHaveTextContent("1 väntar");
  });

  it("märket bär väntar-färgen bara när något faktiskt väntar", () => {
    const { getByTestId, rerender } = render(
      <ChattList vyTitel="Verifikationer" inlagg={trad} vantandeBeslut={1} />
    );
    expect(getByTestId("chattlist-marke").style.color).toContain("vantar");

    rerender(<ChattList vyTitel="Balansräkning" inlagg={trad} vantandeBeslut={0} />);
    expect(getByTestId("chattlist-marke").style.color).not.toContain("vantar");
  });

  it("listen är minst 50 px hög, som designen kräver", () => {
    const { getByRole } = render(
      <ChattList vyTitel="Verifikationer" inlagg={trad} vantandeBeslut={0} />
    );
    expect(getByRole("button", { name: "Visa eller minimera chatten" }).className).toContain(
      "min-h-[50px]"
    );
  });
});
