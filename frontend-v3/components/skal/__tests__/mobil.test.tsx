import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Skal } from "@/components/skal/Skal";
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
  it("lägger vyn överst och chatten nederst i varje vy", () => {
    const { container } = renderaSkal();
    // Inaktiva vyer är aria-hidden (de ligger utanför skärmen i svepraden),
    // så de räknas i DOM:en och inte via rollfrågor.
    const listar = container.querySelectorAll('[aria-label="Visa eller minimera chatten"]');
    expect(listar).toHaveLength(3);
    expect(container.querySelectorAll("[data-view-key]")).toHaveLength(3);
  });

  it("har ingen desktopfot med prickar — prickarna ligger i headern", () => {
    const { container } = renderaSkal();
    expect(container.querySelector(".h-\\[48px\\]")).toBeNull();
    expect(screen.getByRole("button", { name: "Verifikationer" })).toBeInTheDocument();
  });

  it("visar märket för väntande beslut på chattlisten", () => {
    renderaSkal();
    const marken = screen.getAllByTestId("chattlist-marke");
    expect(marken.some((m) => m.textContent?.includes("väntar"))).toBe(true);
  });

  it("visar Agenten pausad även i mobilheadern", async () => {
    renderaSkal();
    expect(await screen.findByText("Agenten pausad")).toBeInTheDocument();
    expect(agentLage.state).toBe("pausad");
  });
});
