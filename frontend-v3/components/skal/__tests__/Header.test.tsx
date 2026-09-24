import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Header } from "@/components/skal/Header";
import { AgentStatus } from "@/components/skal/AgentStatus";
import { arsrad } from "@/lib/skal/header";
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
  it("visar serverns meta-sträng ordagrant", () => {
    renderaHeader();
    expect(screen.getByText("3 väntar på dig · 7 saknar underlag")).toBeInTheDocument();
  });

  it("visar serverns sträng även när den inte går att härleda ur några siffror", () => {
    // Servern bestämmer formuleringen (datakontraktets regel 2). Om klienten
    // räknade skulle den här strängen inte kunna uppstå.
    renderaHeader({
      metaPerSida: { bocker: { waiting: false, meta: "Allt är avstämt sedan i morse" } },
    });
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
