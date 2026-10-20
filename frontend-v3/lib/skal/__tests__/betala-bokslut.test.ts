import { describe, expect, it } from "vitest";
import type { BeslutSvar } from "@/lib/chattyta/api";
import {
  type Faktura,
  faktureringVy,
  type LoneAgi,
  type Lonebesked,
  type Lonekorning,
  lonerVy,
} from "@/lib/skal/betala";
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
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["juni 2026", "maj 2026"]);
    expect(vy.lage).toBe("vantar");
    expect(vy.status).toBe("1 ej bokförd");
  });

  const besked = (over: Partial<Lonebesked>): Lonebesked => ({
    id: "p1",
    employee_name: "Anna Andersson",
    payment_date: "2026-03-25",
    gross_salary: 5000000,
    net_salary: 3500000,
    status: "generated",
    voucher_id: null,
    ...over,
  });
  const agi = (over: Partial<LoneAgi>): LoneAgi => ({
    year: 2026,
    month: 3,
    due_date: "2026-04-13",
    total_to_pay: 3071000,
    unbooked_payslips: 0,
    voucher_ids: {},
    booked: false,
    ...over,
  });
  const korning = (over: Partial<Lonekorning>): Lonekorning => ({
    id: "mar",
    year: 2026,
    month: 3,
    payment_date: "2026-03-25",
    status: "generated",
    payslip_count: 1,
    total_gross_salary: 5000000,
    total_net_salary: 3500000,
    ...over,
  });
  const beslut = (over: Partial<BeslutSvar>): BeslutSvar =>
    ({
      id: "d1",
      kind: "approval",
      status: "open",
      view_key: "betala.loner",
      title: "Bokför lön mars 2026 · Anna Andersson",
      amount_ore: 3500000,
      age_days: 2,
      ...over,
    }) as BeslutSvar;

  it("ett lönekort i tråden står under Väntar på beslut och tas upp i chatten", () => {
    const kort = beslut({});
    const vy = lonerVy(
      { payroll_runs: [korning({ payslips: [besked({})], agi: agi({ unbooked_payslips: 1 }) })] },
      { beslut: [kort, beslut({ id: "d0", status: "answered" })] }
    );
    expect(vy.sektioner[0].titel).toBe("Väntar på beslut");
    expect(vy.sektioner[0].rader).toHaveLength(1);
    expect(vy.sektioner[0].rader[0]).toMatchObject({
      titel: "Bokför lön mars 2026 · Anna Andersson",
      meta: "väntar på dig",
      variant: "vantar",
      ageDays: 2,
      beslut: kort,
    });
    expect(vy.status).toBe("1 väntar på dig");
  });

  it("månaden visar lönebeskeden och AGI:n, och det bokförda öppnar sin verifikation", () => {
    const vy = lonerVy({
      payroll_runs: [
        korning({
          status: "booked",
          payslips: [besked({ voucher_id: "v-lon", status: "booked" })],
          agi: agi({ booked: true, voucher_ids: { tax: "v-skatt", employer_fee: "v-avg" } }),
        }),
      ],
    });
    const [lon, deklaration] = vy.sektioner[0].rader;
    expect(lon).toMatchObject({ titel: "Anna Andersson", meta: "bokförd · utbetald 2026-03-25" });
    expect(lon.mal).toEqual({ typ: "ver", id: "v-lon" });
    expect(deklaration).toMatchObject({ titel: "Arbetsgivardeklaration", meta: "bokförd · mars 2026" });
    expect(deklaration.mal).toEqual({ typ: "ver", id: "v-skatt" });
    expect(vy.status).toBe("alla bokförda");
    expect(vy.lage).toBe("normal");
  });

  it("en obokad lön och en AGI som väntar på lönerna är inte klickbara", () => {
    const vy = lonerVy({
      payroll_runs: [korning({ payslips: [besked({})], agi: agi({ unbooked_payslips: 1 }) })],
    });
    const [lon, deklaration] = vy.sektioner[0].rader;
    expect(lon).toMatchObject({ meta: "ej bokförd · utbetalning 2026-03-25", variant: "vantar" });
    expect(lon.mal).toBeUndefined();
    expect(deklaration).toMatchObject({ meta: "väntar på lönerna · senast 2026-04-13", variant: "vantar" });
    expect(deklaration.mal).toBeUndefined();
  });

  it("en körning vars löner är bokförda men inte AGI:n är inte klar", () => {
    const vy = lonerVy({
      payroll_runs: [
        korning({
          status: "booked",
          payslips: [besked({ voucher_id: "v-lon" })],
          agi: agi({}),
        }),
      ],
    });
    expect(vy.sektioner[0].rader[1].meta).toBe("att bokföra · senast 2026-04-13");
    expect(vy.status).toBe("1 ej bokförd");
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
