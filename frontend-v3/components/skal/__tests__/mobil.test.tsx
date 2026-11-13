import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Skal } from "@/components/skal/Skal";
import { sidan } from "@/lib/skal/vyer";
import { satteBredd } from "../../../vitest.setup";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("sida=bocker&vy=verifikationer"),
}));

const agentLage = { state: "pausad" as const };

// Tråden är `chattyta`s (C5) och har sina egna tester. Här prövas skalet;
// utan mocken skulle varje vy i svepraden anropa GET /threads mot ingenstans.
vi.mock("@/hooks/useTrad", () => ({
  useTrad: () => ({ inlagg: [], strommande: null, skicka: async () => true, laddar: false, fel: null }),
}));

// Märket är `chattyta`s (C8) och har sina egna tester (testfall 21). Här
// prövas bara att skalet visar hookens tal för den aktiva vyn.
const vantandeBeslut = vi.fn((viewKey: string) => (viewKey === "bocker.verifikationer" ? 3 : 0));
vi.mock("@/hooks/useVantandeBeslut", () => ({
  useVantandeBeslut: (viewKey: string) => vantandeBeslut(viewKey),
}));

vi.mock("@/lib/skal/api", () => ({
  skalApi: {
    getOverview: async () => ({
      fiscal_year: null,
      period_state: null,
      pages: [
        { key: "bocker", title: "Böcker", waiting: true, meta: "1 väntar på dig", counters: {} },
      ],
    }),
    getAgentStatus: async () => ({
      state: "pausad",
      since: null,
      current_task: null,
      paused_reason: "dygnstaket nått",
    }),
  },
}));

function renderaSkal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Skal />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  window.history.replaceState({}, "", "/v4");
  satteBredd(390); // Designens mobilbredd, under brytpunkten 1000.
});

describe("mobilmönstret under 1000 px", () => {
  it("har en chattbubbla för den aktiva vyn, inte en chattlist per vy", () => {
    const { container } = renderaSkal();
    expect(container.querySelectorAll('[aria-label="Visa eller minimera chatten"]')).toHaveLength(0);
    expect(container.querySelectorAll("[data-view-key]")).toHaveLength(sidan("bocker").vyer.length);
    expect(screen.getByRole("button", { name: /Öppna chatten för Verifikationer/ })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("bubblan fäller upp arket; ett vybyte stänger det", () => {
    renderaSkal();
    fireEvent.click(screen.getByRole("button", { name: /Öppna chatten för Verifikationer/ }));
    expect(screen.getByRole("dialog", { name: "Chatt · Verifikationer" })).toBeInTheDocument();
    // Arket täcker bubblan och har sin egen stängknapp.
    expect(screen.queryByRole("button", { name: /Öppna chatten/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Balansräkning" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Öppna chatten för Balansräkning/ })).toBeInTheDocument();
  });

  it("har ingen desktopfot med prickar — prickarna ligger i headern", () => {
    const { container } = renderaSkal();
    expect(container.querySelector(".h-\\[48px\\]")).toBeNull();
    expect(screen.getByRole("button", { name: "Verifikationer" })).toBeInTheDocument();
  });

  it("visar märket för väntande beslut på chattbubblan (testfall 21)", () => {
    renderaSkal();
    // Talet är hookens — serverns `total` — ordagrant, för den aktiva vyn.
    expect(screen.getByTestId("chattbubbla-marke")).toHaveTextContent("3");
    expect(vantandeBeslut).toHaveBeenCalledWith("bocker.verifikationer");
  });

  it("visar pausad även i mobilheadern, i kort form", async () => {
    renderaSkal();
    // Kort form: med Bokslutets sex vyprickar räcker inte bredden till hela texten.
    expect(await screen.findByText("Pausad")).toBeInTheDocument();
    expect(agentLage.state).toBe("pausad");
  });
});
