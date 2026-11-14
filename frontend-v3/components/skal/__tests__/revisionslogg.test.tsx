import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DetaljProvider } from "@/components/skal/DetaljKontext";
import { RevisionsloggVy } from "@/components/skal/RevisionsloggVy";
import {
  type Logghandelse,
  handelseMeta,
  handelseText,
  perDag,
  revisionsloggStatus,
  verifikationAv,
} from "@/lib/skal/revisionslogg";
import { formatBeloppHela } from "@/lib/skal/format";
import { allaVyer } from "@/lib/skal/vyer";

/** Revisionsloggen i skalet: behandlingshistoriken, nyast först, hela vägen bakåt. */

const get = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a) },
}));

const h = (over: Partial<Logghandelse>): Logghandelse => ({
  id: "h1",
  entity_type: "voucher",
  entity_id: "v1",
  action: "posted",
  actor: "agent",
  payload: { series: "A", number: 121, total_debit: 870000, total_credit: 870000 },
  timestamp: "2026-11-12T14:32:00",
  ...over,
});

beforeEach(() => {
  get.mockReset();
});

describe("kartan", () => {
  it("revisionsloggen är en vy under Inställningar som chattar i Verifikationers tråd", () => {
    const vy = allaVyer().find((v) => v.key === "installningar.revisionslogg");
    expect(vy).toMatchObject({ sida: "installningar", slug: "revisionslogg", trad: "bocker.verifikationer" });
  });
});

describe("texterna", () => {
  it("säger vad som hände med vad, på svenska", () => {
    expect(handelseText(h({}))).toBe("Verifikation A-121 bokförd");
    expect(handelseText(h({ entity_type: "period", action: "locked", payload: { period: "2025-09" } }))).toBe(
      "Period 2025-09 låst"
    );
    expect(handelseText(h({ entity_type: "payroll_run", action: "created", payload: { year: 2026, month: 2 } }))).toBe(
      "Lönekörning 2026-02 skapad"
    );
    expect(
      handelseText(h({ entity_type: "fiscal_year", action: "locked", payload: { fiscal_year: "2025-01-01 - 2025-12-31" } }))
    ).toBe("Räkenskapsår 2025-01-01 – 2025-12-31 låst");
    expect(handelseText(h({ entity_type: "okand_sak", action: "okand", payload: null }))).toBe("okand_sak okand");
  });

  it("visar vem, när och verifikationens belopp", () => {
    expect(handelseMeta(h({}))).toBe(`agenten · 14:32 · ${formatBeloppHela(870000)}`);
    expect(handelseMeta(h({ entity_type: "period", actor: "admin", payload: null }))).toBe("admin · 14:32");
  });

  it("pekar ut verifikationen, också genom ett lönebesked", () => {
    expect(verifikationAv(h({}))).toBe("v1");
    expect(verifikationAv(h({ entity_type: "payslip", entity_id: "p1", payload: { voucher_id: "v9" } }))).toBe("v9");
    expect(verifikationAv(h({ entity_type: "period", payload: null }))).toBeNull();
  });

  it("delar upp händelserna per dag och behåller ordningen", () => {
    const dagar = perDag([
      h({ id: "a", timestamp: "2026-11-12T15:00:00" }),
      h({ id: "b", timestamp: "2026-11-12T09:00:00" }),
      h({ id: "c", timestamp: "2026-11-10T09:00:00" }),
    ]);
    expect(dagar.map((d) => d.handelser.map((x) => x.id))).toEqual([["a", "b"], ["c"]]);
  });

  it("statusraden säger när det senast hände något", () => {
    expect(revisionsloggStatus({ entries: [], offset: 0, has_more: false }, false).lage).toBe("tomt");
    expect(revisionsloggStatus(undefined, true).lage).toBe("fel");
    expect(revisionsloggStatus({ entries: [h({})], offset: 0, has_more: false }, false).text).toMatch(/^senast /);
  });
});

function visa(oppna = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <DetaljProvider value={{ stack: [], oppna, bakat: vi.fn(), stang: vi.fn() }}>
        <RevisionsloggVy titel="Revisionslogg" variant="desktop" />
      </DetaljProvider>
    </QueryClientProvider>
  );
  return oppna;
}

describe("vyn", () => {
  it("läser äldre sidor och frågar servern om bara urvalet", async () => {
    get.mockImplementation((url: string) => {
      const offset = Number(new URL(url, "http://x").searchParams.get("offset"));
      return Promise.resolve({
        data:
          offset === 0
            ? { entries: [h({ id: "a" })], offset: 0, has_more: true }
            : { entries: [h({ id: "b", entity_type: "period", action: "locked", payload: { period: "2025-09" } })], offset: 1, has_more: false },
      });
    });
    visa();

    await waitFor(() => expect(screen.getAllByTestId("logghandelse")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Visa äldre" }));
    await waitFor(() => expect(screen.getAllByTestId("logghandelse")).toHaveLength(2));
    expect(screen.getByText("Period 2025-09 låst")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Visa äldre" })).not.toBeInTheDocument();
    expect(get.mock.calls[1][0]).toContain("offset=1");

    fireEvent.click(screen.getByRole("button", { name: "Löner" }));
    await waitFor(() => expect(get.mock.calls.at(-1)?.[0]).toContain("entity_type=payroll_run"));
    expect(get.mock.calls.at(-1)?.[0]).toContain("entity_type=payslip");
    expect(screen.getByRole("button", { name: "Löner" })).toHaveAttribute("aria-pressed", "true");
  });

  it("öppnar verifikationen en händelse gäller", async () => {
    get.mockResolvedValue({ data: { entries: [h({})], offset: 0, has_more: false } });
    const oppna = visa();
    fireEvent.click(await screen.findByText("Verifikation A-121 bokförd"));
    expect(oppna).toHaveBeenCalledWith({ typ: "ver", id: "v1" });
  });

  it("säger till när loggen inte kan läsas", async () => {
    get.mockRejectedValue(new Error("nere"));
    visa();
    expect(await screen.findByText(/Revisionsloggen kunde inte läsas/)).toBeInTheDocument();
  });
});
