import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Skal } from "@/components/skal/Skal";

/**
 * Detaljlagret i skalet: konto → huvudbok → verifikation → huvudbok, med
 * bakåtknappen, tillbakalänken och Escape (`components/skal/Detalj.tsx`).
 */

let sokParametrar = new URLSearchParams();
vi.mock("next/navigation", () => ({ useSearchParams: () => sokParametrar }));
vi.mock("@/hooks/useTrad", () => ({
  useTrad: () => ({ inlagg: [], strommande: null, skicka: async () => true, laddar: false, fel: null }),
}));
vi.mock("@/hooks/useVantandeBeslut", () => ({ useVantandeBeslut: () => 0 }));
vi.mock("@/lib/skal/api", () => ({
  skalApi: {
    getOverview: async () => ({
      fiscal_year: { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" },
      period_state: { current_period_id: "p", label: "2026-03", locked: false },
      pages: [],
    }),
    getAgentStatus: async () => ({ state: "vilar", since: null, current_task: null, paused_reason: null }),
  },
}));

const konto = (code: string, name: string, closing: number) => ({
  code,
  name,
  opening_balance: closing,
  change: 0,
  closing_balance: closing,
});

const SVAR: Record<string, unknown> = {
  "/api/v1/reports/balance-sheet": {
    closing_assets: 70000,
    closing_equity_liabilities: 100000,
    opening_balance_source: "stated",
    fixed_assets_details: [],
    receivables_details: [],
    bank_and_cash_details: [konto("1930", "Företagskonto", 70000)],
    current_assets_details: [],
    equity_details: [konto("2081", "Aktiekapital", 100000)],
    long_term_liabilities_details: [],
    current_liabilities_details: [],
  },
  "/api/v1/reports/income-statement": {
    revenue: 0,
    costs: 30000,
    financial: 0,
    operating_profit: -30000,
    profit: -30000,
    revenue_details: [],
    cost_details: [{ code: "5010", name: "Lokalhyra", amount: 30000 }],
    financial_details: [],
    voucher_count: 1,
  },
  "/api/v1/reports/general-ledger/1930": {
    account_code: "1930",
    account_name: "Företagskonto",
    opening_balance: 100000,
    closing_balance: 70000,
    total_debit: 0,
    total_credit: 30000,
    transaction_count: 1,
    transactions: [
      {
        date: "2026-03-04",
        voucher_id: "v1",
        series: "A",
        number: 12,
        description: "Hyra mars",
        debit: 0,
        credit: 30000,
        balance: 70000,
      },
    ],
  },
  "/api/v1/reports/general-ledger/5010": {
    account_code: "5010",
    account_name: "Lokalhyra",
    opening_balance: 0,
    closing_balance: 30000,
    total_debit: 30000,
    total_credit: 0,
    transaction_count: 0,
    transactions: [],
  },
  "/api/v1/vouchers/v1": {
    id: "v1",
    series: "A",
    number: 12,
    date: "2026-03-04",
    description: "Hyra mars",
    status: "posted",
    total_debit: 30000,
    total_credit: 30000,
    missing_attachment: false,
    created_by: "agent",
    posted_at: "2026-03-05T08:00:00",
    rows: [
      { id: "r1", account_code: "5010", account_name: "Lokalhyra", debit: 30000, credit: 0 },
      { id: "r2", account_code: "1930", account_name: "Företagskonto", debit: 0, credit: 30000 },
    ],
  },
};

const get = vi.fn(async (url: string) => ({
  data: SVAR[url] ?? { total: 0, vouchers: [], decisions: [], drafts: [], periods: [], fiscal_years: [] },
}));
vi.mock("@/lib/api", () => ({ default: { get: (url: string) => get(url) } }));

function renderaSkal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Skal />
    </QueryClientProvider>
  );
}

/** Läskolumnen för den aktiva vyn. */
const balansKolumn = () => screen.getAllByText("Balansräkning").length;

beforeEach(() => {
  sokParametrar = new URLSearchParams();
  window.history.replaceState(null, "", "/v4");
  get.mockClear();
});

describe("konto → huvudbok → verifikation", () => {
  it("ett konto i balansräkningen öppnar huvudboken, som en post i historiken", async () => {
    const user = userEvent.setup();
    renderaSkal();
    const langdFore = window.history.length;

    await user.click(await screen.findByRole("button", { name: "Företagskonto" }));

    expect(await screen.findByText("1930 Företagskonto")).toBeInTheDocument();
    expect(screen.getByText("Ingående balans")).toBeInTheDocument();
    expect(screen.getByText("A-12 · 2026-03-04 · saldo 700")).toBeInTheDocument();
    expect(window.location.search).toBe("?sida=bocker&vy=balans&konto=1930");
    expect(window.history.length).toBe(langdFore + 1);
  });

  it("en huvudboksrad öppnar verifikationen, och en kontering huvudboken för sitt konto", async () => {
    const user = userEvent.setup();
    renderaSkal();

    await user.click(await screen.findByRole("button", { name: "Företagskonto" }));
    await user.click(await screen.findByRole("button", { name: "Hyra mars" }));

    expect(await screen.findByText("Verifikation A-12")).toBeInTheDocument();
    expect(window.location.search).toBe("?sida=bocker&vy=balans&ver=v1");
    expect(screen.getByRole("button", { name: "← 1930 Företagskonto" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Lokalhyra" }));
    expect(await screen.findByText("5010 Lokalhyra")).toBeInTheDocument();
    expect(screen.queryByText("Ingående balans")).not.toBeInTheDocument();
  });

  it("tillbakalänken och bakåtknappen stegar tillbaka, lager för lager", async () => {
    const user = userEvent.setup();
    renderaSkal();

    await user.click(await screen.findByRole("button", { name: "Företagskonto" }));
    await user.click(await screen.findByRole("button", { name: "Hyra mars" }));
    await screen.findByText("Verifikation A-12");

    await user.click(screen.getByRole("button", { name: "← 1930 Företagskonto" }));
    expect(await screen.findByText("1930 Företagskonto")).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toBe("?sida=bocker&vy=balans&konto=1930"));

    window.history.back();
    await waitFor(() => expect(screen.queryByText("1930 Företagskonto")).not.toBeInTheDocument());
    await waitFor(() => expect(window.location.search).toBe("?sida=bocker&vy=balans"));
  });

  it("Escape stänger lagret", async () => {
    const user = userEvent.setup();
    renderaSkal();

    await user.click(await screen.findByRole("button", { name: "Företagskonto" }));
    await screen.findByText("1930 Företagskonto");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByText("1930 Företagskonto")).not.toBeInTheDocument());
  });

  it("årets resultat i balansräkningen byter till resultaträkningen", async () => {
    const user = userEvent.setup();
    renderaSkal();

    await user.click(await screen.findByRole("button", { name: "Årets resultat, ej bokfört" }));
    await waitFor(() => expect(window.location.search).toBe("?sida=bocker&vy=resultat"));
  });

  it("ett vybyte stänger lagret", async () => {
    const user = userEvent.setup();
    renderaSkal();

    await user.click(await screen.findByRole("button", { name: "Företagskonto" }));
    await screen.findByText("1930 Företagskonto");
    await user.click(screen.getByRole("button", { name: "Verifikationer" }));
    await waitFor(() => expect(window.location.search).toBe("?sida=bocker&vy=verifikationer"));
    expect(screen.queryByText("1930 Företagskonto")).not.toBeInTheDocument();
  });
});

describe("en länk med lagret i", () => {
  it("öppnar verifikationen direkt, och tillbakalänken leder till vyn", async () => {
    sokParametrar = new URLSearchParams("sida=bocker&vy=balans&ver=v1");
    window.history.replaceState(null, "", "/v4?sida=bocker&vy=balans&ver=v1");
    const user = userEvent.setup();
    renderaSkal();

    expect(await screen.findByText("Verifikation A-12")).toBeInTheDocument();
    const lankar = screen.getAllByRole("button", { name: "← Balansräkning" });
    expect(lankar).toHaveLength(1);

    await user.click(lankar[0]);
    await waitFor(() => expect(screen.queryByText("Verifikation A-12")).not.toBeInTheDocument());
    expect(window.location.search).toBe("?sida=bocker&vy=balans");
    expect(balansKolumn()).toBeGreaterThan(0);
  });

  it("ett oläsbart konto ger inget lager", async () => {
    sokParametrar = new URLSearchParams("sida=bocker&vy=balans&konto=abc");
    renderaSkal();
    expect(await screen.findByRole("button", { name: "Företagskonto" })).toBeInTheDocument();
    expect(within(document.body).queryByText(/^← /)).not.toBeInTheDocument();
  });
});
