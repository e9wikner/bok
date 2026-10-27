import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { JamforelseRader, RadLista } from "@/components/chattyta/JamforelseRader";
import { parseInlagg } from "@/lib/chattyta/parse";
import { FIXTUR_RECEIPT } from "@/lib/chattyta/__fixtures__/inlagg";
import type { ReceiptKropp } from "@/lib/chattyta/typer";

/**
 * C9 (SPEC-chattyta.md §5, testfall 23). Kroppen går genom `parseInlagg`
 * först — komponenten får aldrig något annat än en typad kropp, och
 * fixturen är §4.3:s JSON ordagrant.
 */
function kvittoUrFixtur(): ReceiptKropp {
  const inlagg = parseInlagg(FIXTUR_RECEIPT);
  if (!inlagg || inlagg.type !== "receipt") throw new Error("fixturen parsar inte som receipt");
  return inlagg.body;
}

describe("JamforelseRader (testfall 23)", () => {
  it("visar rubriken och båda talen i raden, formaterade ur öre (testfall 23)", () => {
    render(<JamforelseRader kropp={kvittoUrFixtur()} />);
    expect(screen.getByText("A-118 postad")).toBeInTheDocument();

    const rad = screen.getByTestId("jamforelse-rad");
    expect(within(rad).getByText("1510")).toBeInTheDocument();
    expect(within(rad).getByText("Kundfordringar")).toBeInTheDocument();
    // 14 850 000 öre och 14 400 000 öre — klienten formaterar, räknar aldrig.
    expect(within(rad).getByText("148 500,00")).toBeInTheDocument();
    expect(within(rad).getByText("144 000,00")).toBeInTheDocument();
  });

  it("tar kolumnetiketterna ur kroppens labels, inte ur komponenten (testfall 23)", () => {
    render(<JamforelseRader kropp={kvittoUrFixtur()} />);
    expect(screen.getByText("var")).toBeInTheDocument();
    expect(screen.getByText("blir")).toBeInTheDocument();

    const annan: ReceiptKropp = { ...kvittoUrFixtur(), labels: ["kvitto", "A-118"] };
    render(<JamforelseRader kropp={annan} />);
    expect(screen.getByText("kvitto")).toBeInTheDocument();
    expect(screen.getByText("A-118")).toBeInTheDocument();
  });

  it("visar båda talen i varje rad, även när de är lika (testfall 23)", () => {
    const kropp: ReceiptKropp = {
      title: "Jämförelse",
      labels: ["var", "blir"],
      rows: [
        { key: "1510", text: "Kundfordringar", left_ore: 14850000, right_ore: 14400000 },
        { key: "1930", text: "Företagskonto", left_ore: 50000, right_ore: 50000 },
        { key: "2440", text: "Leverantörsskulder", left_ore: 0, right_ore: -12000 },
      ],
      voucher_id: null,
    };
    render(<JamforelseRader kropp={kropp} />);
    const rader = screen.getAllByTestId("jamforelse-rad");
    expect(rader).toHaveLength(3);
    for (const rad of rader) {
      expect(within(rad).getAllByTestId("tal")).toHaveLength(2);
    }
    // Oförändrat värde döljs inte: en ensam ny summa är fel (komponenter.md).
    expect(within(rader[1]).getAllByText("500,00")).toHaveLength(2);
    expect(within(rader[2]).getByText("0,00")).toBeInTheDocument();
    expect(within(rader[2]).getByText("−120,00")).toBeInTheDocument();
  });

  it("talen är mono och tabulära (testfall 23)", () => {
    render(<JamforelseRader kropp={kvittoUrFixtur()} />);
    for (const tal of screen.getAllByTestId("tal")) {
      expect(tal).toHaveClass("bok-mono", "bok-tal");
    }
  });
});

describe("RadLista/i-tråd", () => {
  it("samma radkomponent, en kolumn tal och inga etiketter", () => {
    render(
      <RadLista
        rader={[
          { key: "A-118", text: "Kvitto kopplat · kompletteringsflagga borta", amount_ore: 448000 },
          { key: "A-121", text: "Korrigering pantavgift · postad och låst", amount_ore: 12000 },
        ]}
      />
    );
    const rader = screen.getAllByTestId("jamforelse-rad");
    expect(rader).toHaveLength(2);
    expect(within(rader[0]).getAllByTestId("tal")).toHaveLength(1);
    expect(within(rader[0]).getByText("4 480,00")).toBeInTheDocument();
    expect(within(rader[1]).getByText("A-121")).toBeInTheDocument();
    expect(screen.queryByTestId("jamforelse-etiketter")).not.toBeInTheDocument();
  });

  it("renderar ingenting för en tom lista", () => {
    const { container } = render(<RadLista rader={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
