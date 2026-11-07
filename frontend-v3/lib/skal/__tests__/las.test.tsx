import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LasKnapp } from "@/components/skal/LasKnapp";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { type Verifikation, verifikationerVy } from "@/lib/skal/bocker";
import { rapporterVy } from "@/lib/skal/bokslut";
import { type LasData, type Period, lasfel, periodnamn } from "@/lib/skal/las";
import { sidan } from "@/lib/skal/vyer";

/**
 * Låsen: ett per räkenskapsår i Rapporter, ett per månad i Verifikationer.
 * Postade grupperas per månad när perioderna finns.
 */

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

const period = (month: number, locked = false): Period => {
  const mm = String(month).padStart(2, "0");
  return {
    id: `p${month}`,
    fiscal_year_id: "fy",
    year: 2026,
    month,
    start_date: `2026-${mm}-01`,
    end_date: `2026-${mm}-28`,
    locked,
    locked_at: null,
    locked_by: null,
  };
};
const PERIODER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((m) => period(m, m <= 6));

const v = (id: string, date: string): Verifikation => ({
  id,
  series: "A",
  number: Number(id.slice(1)),
  date,
  description: `Verifikation ${id}`,
  status: "posted",
  total_debit: 100000,
  missing_attachment: false,
});

const lista = (...vouchers: Verifikation[]) => ({ total: vouchers.length, vouchers });
const TOM = lista();
const las = (p: Period): LasData => ({ last: p.locked, vad: periodnamn(p), vaxla: async () => {} });

describe("verifikationerVy med månader", () => {
  const manader = (over: Partial<{ idag: string; harFler: boolean }> = {}) => ({
    perioder: PERIODER,
    las,
    idag: "2026-09-15",
    harFler: false,
    ...over,
  });

  it("delar Postade per månad, senaste först, med månadens lås", () => {
    const vy = verifikationerVy(
      AR,
      lista(v("a3", "2026-09-10"), v("a2", "2026-08-02"), v("a1", "2026-06-20")),
      TOM,
      undefined,
      manader()
    );
    expect(vy.sektioner.map((s) => s.titel)).toEqual([
      "September 2026",
      "Augusti 2026",
      "Juli 2026",
      "Juni 2026",
      "Maj 2026",
      "April 2026",
      "Mars 2026",
      "Februari 2026",
      "Januari 2026",
    ]);
    expect(vy.sektioner[0].rader.map((r) => r.id)).toEqual(["a3"]);
    expect(vy.sektioner[2]).toMatchObject({ rader: [], tom: "inga postade verifikationer" });
    expect(vy.sektioner[3].las?.last).toBe(true);
    expect(vy.sektioner[0].las?.last).toBe(false);
    expect(vy.lage).toBe("normal");
  });

  it("visar inte tomma månader efter i dag", () => {
    const vy = verifikationerVy(AR, lista(v("a1", "2026-09-10")), TOM, undefined, manader());
    expect(vy.sektioner.map((s) => s.titel)).not.toContain("Oktober 2026");
  });

  it("med fler sidor visas bara tomma månader som den hämtade listan täcker", () => {
    const vy = verifikationerVy(
      AR,
      lista(v("a3", "2026-09-10"), v("a2", "2026-07-02")),
      TOM,
      undefined,
      manader({ harFler: true })
    );
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["September 2026", "Augusti 2026", "Juli 2026"]);
  });

  it("utan månader: en sektion Postade, som förut", () => {
    const vy = verifikationerVy(AR, lista(v("a1", "2026-09-10")), TOM);
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Postade"]);
  });

  it("utkast står kvar i Utkast, efter månaderna", () => {
    const utkast = { ...v("u1", "2026-09-12"), status: "draft", number: null };
    const vy = verifikationerVy(AR, TOM, lista(utkast), undefined, manader({ idag: "2026-01-15" }));
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Januari 2026", "Utkast"]);
    expect(vy.status).toBe("1 utkast");
  });
});

describe("rapporterVy med lås", () => {
  it("ger varje år sitt lås och ingen text till höger", () => {
    const vy = rapporterVy(
      {
        fiscal_years: [
          { id: "a", start_date: "2025-01-01", end_date: "2025-12-31", locked: true, locked_at: null },
          { id: "b", start_date: "2026-01-01", end_date: "2026-12-31", locked: false, locked_at: null },
        ],
      },
      (a) => ({ last: a.locked, vad: a.id, vaxla: async () => {} })
    );
    expect(vy.sektioner[0].rader.map((r) => [r.hoger, r.las?.last])).toEqual([
      ["", false],
      ["", true],
    ]);
  });
});

describe("LasKnapp", () => {
  it("säger vad ett tryck gör och växlar", async () => {
    const vaxla = vi.fn().mockResolvedValue(undefined);
    render(<LasKnapp last={false} vad="september 2026" vaxla={vaxla} />);
    const knapp = screen.getByRole("button", { name: "Lås september 2026" });
    expect(knapp.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(knapp);
    await waitFor(() => expect(vaxla).toHaveBeenCalledTimes(1));
  });

  it("en låst visar lås upp", () => {
    render(<LasKnapp last vad="räkenskapsår 2025" vaxla={async () => {}} />);
    expect(screen.getByRole("button", { name: "Lås upp räkenskapsår 2025" })).toBeTruthy();
  });

  it("visar serverns vägran bredvid knappen", async () => {
    const fel = { response: { data: { detail: { code: "draft_vouchers_exist" } } } };
    render(<LasKnapp last={false} vad="juni 2026" vaxla={() => Promise.reject(fel)} />);
    fireEvent.click(screen.getByRole("button", { name: "Lås juni 2026" }));
    expect((await screen.findByRole("alert")).textContent).toBe("utkast i perioden");
  });

  it("översätter felkoderna", () => {
    const med = (code: string) => ({ response: { data: { detail: { code } } } });
    expect(lasfel(med("fiscal_year_locked"))).toBe("året är låst");
    expect(lasfel(med("human_only"))).toBe("kräver inloggning");
    expect(lasfel(new Error("nät"))).toBe("gick inte");
  });
});

describe("VyInnehall med månader", () => {
  it("ritar en tom månad med sin text och sitt lås", () => {
    const vy = sidan("bocker").vyer.find((x) => x.key === "bocker.verifikationer")!;
    render(
      <VyInnehall
        vy={vy}
        data={{
          lage: "normal",
          status: "",
          period: "",
          fot: "",
          sektioner: [{ titel: "Juli 2026", rader: [], tom: "inga postade verifikationer", las: las(period(7)) }],
        }}
      />
    );
    expect(screen.getByText("Juli 2026")).toBeTruthy();
    expect(screen.getByText("inga postade verifikationer")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Lås juli 2026" })).toBeTruthy();
  });
});
