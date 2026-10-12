import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Header } from "@/components/skal/Header";
import { AgentStatus } from "@/components/skal/AgentStatus";
import { arsalternativ, arsrad } from "@/lib/skal/header";
import { sidan } from "@/lib/skal/vyer";

const sida = sidan("bocker");
const vy = sida.vyer[0];

function renderaHeader(over: Partial<Parameters<typeof Header>[0]> = {}) {
  return render(
    <Header
      variant="desktop"
      sida={sida}
      aktivVy={vy}
      aktivIndex={0}
      metaPerSida={{ bocker: { waiting: true, meta: "3 väntar på dig · 7 saknar underlag" } }}
      arsrad="Räkenskapsår 2026 · juni öppen"
      vyStatus={{ text: "avstämd", fg: "#6b7280" }}
      onValjSida={vi.fn()}
      onValjVy={vi.fn()}
      {...over}
    />
  );
}

describe("headern räknar ingenting (testfall 8)", () => {
  it("visar serverns meta-sträng ordagrant", async () => {
    renderaHeader();
    await userEvent.setup().click(screen.getByRole("button", { name: "Välj sida" }));
    expect(screen.getByText("3 väntar på dig · 7 saknar underlag")).toBeInTheDocument();
  });

  it("visar serverns sträng även när den inte går att härleda ur några siffror", async () => {
    // Servern bestämmer formuleringen (datakontraktets regel 2). Om klienten
    // räknade skulle den här strängen inte kunna uppstå.
    renderaHeader({
      metaPerSida: { bocker: { waiting: false, meta: "Allt är avstämt sedan i morse" } },
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Välj sida" }));
    expect(screen.getByText("Allt är avstämt sedan i morse")).toBeInTheDocument();
  });

  it("visar räkenskapsår och periodläge", () => {
    renderaHeader();
    expect(screen.getByText("Räkenskapsår 2026 · juni öppen")).toBeInTheDocument();
  });

  it("sätter ihop årsraden ur serverns två fält", () => {
    expect(
      arsrad({
        fiscal_year: { id: "1", label: "2026", start: "2026-01-01", end: "2026-12-31" },
        period_state: { current_period_id: "p", label: "2026-06", locked: false },
        pages: [],
      })
    ).toBe("Räkenskapsår 2026 · juni öppen");
  });

  it("säger 'låst' när perioden är låst", () => {
    expect(
      arsrad({
        fiscal_year: { id: "1", label: "2026", start: "2026-01-01", end: "2026-12-31" },
        period_state: { current_period_id: "p", label: "2026-03", locked: true },
        pages: [],
      })
    ).toBe("Räkenskapsår 2026 · mars låst");
  });
});

describe("årsväljaren", () => {
  const alternativ = [
    { id: "2026", text: "Räkenskapsår 2026 · juni öppen", etikett: "2026" },
    { id: "2025", text: "Räkenskapsår 2025", etikett: "2025" },
  ];

  it("ersätter årsraden med en dropdown och anropar onValj med årets id", async () => {
    const onValj = vi.fn();
    renderaHeader({ arsval: { alternativ, valt: "2026", onValj } });
    const valjare = screen.getByRole("combobox", { name: "Välj räkenskapsår" });
    expect(valjare).toHaveValue("2026");
    await userEvent.setup().selectOptions(valjare, "2025");
    expect(onValj).toHaveBeenCalledWith("2025");
  });

  it("finns i mobilheadern och visar där bara året", async () => {
    const onValj = vi.fn();
    renderaHeader({ variant: "mobil", arsval: { alternativ, valt: "2026", onValj } });
    expect(screen.getByText("2026")).toBeInTheDocument();
    const valjare = screen.getByRole("combobox", { name: "Välj räkenskapsår" });
    await userEvent.setup().selectOptions(valjare, "2025");
    expect(onValj).toHaveBeenCalledWith("2025");
  });

  it("visar årsraden som text när listan saknas", () => {
    renderaHeader();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("ger översiktens år periodläget och de andra bara året", () => {
    expect(
      arsalternativ(
        [
          { id: "b", start_date: "2026-01-01", end_date: "2026-12-31", locked: false, locked_at: null },
          { id: "a", start_date: "2024-07-01", end_date: "2025-06-30", locked: true, locked_at: null },
        ],
        {
          fiscal_year: { id: "b", label: "2026", start: "2026-01-01", end: "2026-12-31" },
          period_state: { current_period_id: "p", label: "2026-06", locked: false },
          pages: [],
        }
      )
    ).toEqual([
      { id: "b", text: "Räkenskapsår 2026 · juni öppen", etikett: "2026" },
      { id: "a", text: "Räkenskapsår 2024/2025", etikett: "2024/2025" },
    ]);
  });
});

describe("AgentStatus faller mjukt (testfall 9)", () => {
  it("visar ingenting när statusanropet inte gick fram", () => {
    const { container } = render(<AgentStatus state={undefined} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/Agenten pausad/)).not.toBeInTheDocument();
  });

  it("visar ingenting i läget vilande — designen ritar ingen indikator", () => {
    const { container } = render(<AgentStatus state="vilande" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("visar de tre namngivna lägena", () => {
    const { rerender } = render(<AgentStatus state="arbetar" />);
    expect(screen.getByText("Agenten arbetar")).toBeInTheDocument();
    rerender(<AgentStatus state="postar" />);
    expect(screen.getByText("Agenten postar")).toBeInTheDocument();
    rerender(<AgentStatus state="pausad" pausadOrsak="dygnstaket nått" />);
    expect(screen.getByText("Agenten pausad")).toBeInTheDocument();
  });
});
