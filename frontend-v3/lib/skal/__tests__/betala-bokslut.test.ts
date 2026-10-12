import { describe, expect, it } from "vitest";
import { type Faktura, faktureringVy, lonerVy } from "@/lib/skal/betala";
import { arsnamn, atgarderVy, rapporterVy } from "@/lib/skal/bokslut";

const faktura = (over: Partial<Faktura>): Faktura => ({
  id: "f",
  invoice_number: 1,
  customer_name: "Kund AB",
  invoice_date: "2026-05-01",
  due_date: "2026-05-31",
  amount_inc_vat: 100000,
  remaining_amount: 100000,
  status: "sent",
  is_overdue: false,
  ...over,
});

describe("faktureringVy", () => {
  it("är tom utan fakturor, utan sektioner", () => {
    const vy = faktureringVy({ total: 0, invoices: [] });
    expect(vy.lage).toBe("tomt");
    expect(vy.sektioner).toEqual([]);
  });

  it("märker förfallna och delar upp obetalda, utkast och betalda", () => {
    const vy = faktureringVy({
      total: 3,
      invoices: [
        faktura({ id: "a", status: "overdue", is_overdue: true }),
        faktura({ id: "b", status: "draft" }),
        faktura({ id: "c", status: "paid", remaining_amount: 0 }),
      ],
    });
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Obetalda", "Utkast", "Senast betalda"]);
    expect(vy.sektioner[0].rader[0].variant).toBe("fel");
    expect(vy.status).toBe("1 förfallen");
    expect(vy.lage).toBe("vantar");
  });
});

describe("lonerVy", () => {
  it("är tom utan lönekörningar", () => {
    const vy = lonerVy({ payroll_runs: [] });
    expect(vy.lage).toBe("tomt");
    expect(vy.status).toBe("inga lönekörningar");
  });

  it("visar senaste månaden först och väntar på ej bokförda", () => {
    const run = { id: "", payment_date: null, payslip_count: 1, total_gross_salary: 1, total_net_salary: 1 };
    const vy = lonerVy({
      payroll_runs: [
        { ...run, id: "maj", year: 2026, month: 5, status: "booked" },
        { ...run, id: "jun", year: 2026, month: 6, status: "draft" },
      ],
    });
    expect(vy.sektioner[0].rader.map((r) => r.titel)).toEqual(["juni 2026", "maj 2026"]);
    expect(vy.lage).toBe("vantar");
  });
});

describe("rapporterVy", () => {
  it("listar räkenskapsåren nyast först med låsstatus", () => {
    const vy = rapporterVy({
      fiscal_years: [
        { id: "a", start_date: "2015-07-01", end_date: "2016-12-31", locked: true, locked_at: "2017-05-01T10:00:00" },
        { id: "b", start_date: "2026-01-01", end_date: "2026-12-31", locked: false, locked_at: null },
      ],
    });
    expect(vy.sektioner[0].rader.map((r) => [r.titel, r.hoger])).toEqual([
      ["Räkenskapsår 2026", "öppet"],
      ["Räkenskapsår 2015/16", "låst"],
    ]);
    expect(vy.status).toBe("1 av 2 låsta");
  });

  it("namnger brutna år med båda åren", () => {
    expect(arsnamn({ start_date: "2025-01-01", end_date: "2025-12-31" })).toBe("2025");
    expect(arsnamn({ start_date: "2013-07-01", end_date: "2014-06-30" })).toBe("2013/14");
  });
});

describe("atgarderVy", () => {
  it("säger ärligt att inget är registrerat, inte att allt är bra", () => {
    const vy = atgarderVy({ count: 0, issues: [] });
    expect(vy.lage).toBe("tomt");
    expect(vy.status).toBe("inga registrerade");
    expect(vy.fot).toMatch(/körs inte automatiskt/);
  });

  it("sorterar de allvarligaste först", () => {
    const i = { description: null, recommendation: null, deadline: null };
    const vy = atgarderVy({
      count: 2,
      issues: [
        { ...i, id: "w", severity: "warning", title: "Varning" },
        { ...i, id: "c", severity: "critical", title: "Kritisk" },
      ],
    });
    expect(vy.sektioner[0].rader.map((r) => r.id)).toEqual(["c", "w"]);
    expect(vy.lage).toBe("fel");
  });
});
