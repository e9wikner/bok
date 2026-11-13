import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Skal } from "@/components/skal/Skal";

const sokParametrar = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useSearchParams: () => sokParametrar,
}));

// Tråden är `chattyta`s (C5) och har sina egna tester. Här prövas skalet;
// utan mocken skulle varje vy i svepraden anropa GET /threads mot ingenstans.
vi.mock("@/hooks/useTrad", () => ({
  useTrad: () => ({ inlagg: [], strommande: null, skicka: async () => true, laddar: false, fel: null }),
}));

// Beslutsmärket är `chattyta`s (C8); utan mocken frågar skalet GET /decisions.
vi.mock("@/hooks/useVantandeBeslut", () => ({ useVantandeBeslut: () => 0 }));

vi.mock("@/lib/skal/api", () => ({
  skalApi: {
    getOverview: async () => ({
      fiscal_year: { id: "1", label: "2026", start: "2026-01-01", end: "2026-12-31" },
      period_state: { current_period_id: "p", label: "2026-06", locked: false },
      pages: [
        { key: "bocker", title: "Böcker", waiting: true, meta: "1 väntar på dig", counters: {} },
        { key: "betala", title: "Fakturering och löner", waiting: false, meta: "Inget väntar", counters: {} },
        { key: "bokslut", title: "Bokslut", waiting: false, meta: "Inget väntar", counters: {} },
      ],
    }),
    getAgentStatus: async () => ({
      state: "arbetar",
      since: null,
      current_task: null,
      paused_reason: null,
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
});

describe("skalet i drift", () => {
  it("startar på Böcker · Balansräkning", async () => {
    renderaSkal();
    expect(screen.getByRole("group", { name: "Vyer i Böcker" })).toBeInTheDocument();
    expect(screen.getAllByText("Balansräkning").length).toBeGreaterThan(0);
  });

  it("sätter egen textfärg, så att inget ärver shadcn-temats `--foreground` (#59)", () => {
    const { container } = renderaSkal();
    const rot = container.firstElementChild as HTMLElement;
    expect(rot).toHaveClass("bg-bok-app", "text-bok-text");
  });

  it("växlar mörkt läge med samma klass och sparade val som de gamla sidorna", async () => {
    const user = userEvent.setup();
    localStorage.setItem("darkMode", "false");
    document.documentElement.classList.remove("dark");
    renderaSkal();

    const vaxel = await screen.findByRole("button", { name: /Mörkt läge/ });
    expect(vaxel).toHaveAttribute("aria-pressed", "false");
    await user.click(vaxel);
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("darkMode")).toBe("true");
    expect(screen.getByRole("button", { name: /Ljust läge/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /Ljust läge/ }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("darkMode")).toBe("false");
  });

  it("renderar sidans alla vyer i svepraden, inte bara den aktiva", () => {
    const { container } = renderaSkal();
    const vyer = container.querySelectorAll("[data-view-key]");
    expect([...vyer].map((v) => v.getAttribute("data-view-key"))).toEqual([
      "bocker.balans",
      "bocker.resultat",
      "bocker.verifikationer",
      "bocker.dropzone",
      "bocker.kontoplan",
      "bocker.revisionslogg",
      "bocker.instruktioner",
    ]);
  });

  it("speglar positionen i URL:en utan att lägga en post i historiken", async () => {
    const user = userEvent.setup();
    const langdFore = window.history.length;
    renderaSkal();

    await user.click(screen.getByRole("button", { name: "Verifikationer" }));
    await waitFor(() => {
      expect(window.location.search).toBe("?sida=bocker&vy=verifikationer");
    });
    expect(window.history.length).toBe(langdFore);
  });

  it("sidonavigeringen leder direkt till en vy på en annan sida", async () => {
    const user = userEvent.setup();
    renderaSkal();

    await user.click(screen.getByRole("button", { name: "Åtgärder och nyckeltal" }));

    await waitFor(() => {
      expect(window.location.search).toBe("?sida=bokslut&vy=atgarder");
    });
    expect(screen.getByRole("group", { name: "Vyer i Bokslut" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Åtgärder och nyckeltal" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("hämtar sidornas metarader från servern och visar dem ordagrant", async () => {
    renderaSkal();
    expect(await screen.findByText("1 väntar på dig")).toBeInTheDocument();
  });

  it("visar agentläget från GET /agent/status", async () => {
    renderaSkal();
    expect(await screen.findByText("Agenten arbetar")).toBeInTheDocument();
  });
});
