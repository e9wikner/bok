import { describe, expect, it } from "vitest";
import type { BeslutSvar, ForslagStatusSvar } from "@/lib/chattyta/api";
import {
  betalaVantar,
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

  it("en faktura leder till sin verifikation, och en betald också till betalningen", () => {
    const vy = faktureringVy({
      total: 3,
      invoices: [
        faktura({ id: "a", voucher_id: "v-a" }),
        faktura({ id: "b", status: "paid", voucher_id: "v-b", payment_voucher_ids: ["v-b-bet"] }),
        faktura({
          id: "c",
          status: "partially_paid",
          voucher_id: "v-c",
          payment_voucher_ids: ["v-c-2", "v-c-1"],
        }),
        faktura({ id: "d" }),
      ],
    });
    const rad = (id: string) => vy.sektioner.flatMap((s) => s.rader).find((r) => r.id === id)!;
    expect(rad("a").mal).toEqual({ typ: "ver", id: "v-a" });
    expect(rad("a").lankar).toBeUndefined();
    expect(rad("b").lankar).toEqual([{ text: "betalning", mal: { typ: "ver", id: "v-b-bet" } }]);
    expect(rad("c").lankar?.map((l) => [l.text, l.mal])).toEqual([
      ["betalning 1", { typ: "ver", id: "v-c-1" }],
      ["betalning 2", { typ: "ver", id: "v-c-2" }],
    ]);
    // En faktura från en äldre server, utan verifikation, är text.
    expect(rad("d").mal).toBeUndefined();
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

  it("en obokad lön utan kort ber agenten, och en AGI som väntar på lönerna är neutral", () => {
    const vy = lonerVy({
      payroll_runs: [korning({ payslips: [besked({})], agi: agi({ unbooked_payslips: 1 }) })],
    });
    const [lon, deklaration] = vy.sektioner[0].rader;
    expect(lon).toMatchObject({ meta: "ej bokförd · utbetalning 2026-03-25", variant: "vantar" });
    expect(lon.fraga).toEqual({ viewKey: "betala.loner", text: "Om lönen för Anna Andersson, mars 2026: " });
    expect(lon.mal).toBeUndefined();
    expect(deklaration).toMatchObject({ meta: "väntar på lönerna · senast 2026-04-13" });
    expect(deklaration.variant).toBeUndefined();
    expect(deklaration.fraga).toBeUndefined();
  });

  it("en lön och en AGI med ett öppet kort tar upp kortet", () => {
    const lonekort = beslut({});
    const agikort = beslut({ id: "d2", title: "Bokför arbetsgivardeklaration mars 2026" });
    const vy = lonerVy(
      {
        payroll_runs: [
          korning({
            payslips: [besked({ pending_decision_id: "d1" })],
            agi: agi({ pending_decision_id: "d2" }),
          }),
        ],
      },
      { beslut: [lonekort, agikort] }
    );
    const [lon, deklaration] = vy.sektioner[1].rader;
    expect(lon).toMatchObject({ meta: "förslag väntar · utbetalning 2026-03-25", beslut: lonekort, ageDays: 2 });
    expect(lon.fraga).toBeUndefined();
    expect(deklaration).toMatchObject({ meta: "förslag väntar · senast 2026-04-13", beslut: agikort });
  });

  it("ett kort som inte längre är öppet leder inte dit", () => {
    const vy = lonerVy(
      { payroll_runs: [korning({ payslips: [besked({ pending_decision_id: "d1" })] })] },
      { beslut: [beslut({ status: "answered" })] }
    );
    const [lon] = vy.sektioner[0].rader;
    expect(lon.beslut).toBeUndefined();
    expect(lon.fraga).toBeDefined();
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
    expect(vy.sektioner[0].rader[1].fraga?.text).toBe("Om arbetsgivardeklarationen för mars 2026: ");
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

describe("betalaVantar", () => {
  const lonekort = {
    id: "d1",
    kind: "approval",
    status: "open",
    view_key: "betala.loner",
    title: "Bokför lön oktober 2026 · Anna Andersson",
    amount_ore: 3900000,
    age_days: 1,
  } as BeslutSvar;
  const forslag = (over: Partial<ForslagStatusSvar>): ForslagStatusSvar =>
    ({
      kind: "invoice",
      draft_id: "u1",
      post_id: "p-9",
      decision_id: null,
      correction_of: null,
      status: "pending",
      replaced_by: null,
      posted_at: null,
      voucher: null,
      last_error_code: null,
      created_at: "2026-10-25T08:00:00",
      ...over,
    }) as ForslagStatusSvar;
  const utkast = {
    id: "u1",
    invoice_number: "1046",
    customer_name: "Ateljé Vind AB",
    invoice_date: "2026-10-25",
    due_date: "2026-11-24",
    status: "needs_review",
    amount_inc_vat: 3450000,
  };

  it("ett lönekort leder till Löner och tas upp där", () => {
    const [rad] = betalaVantar({ lonerBeslut: [lonekort], faktureringForslag: [], fakturautkast: [] });
    expect(rad).toMatchObject({
      titel: "Bokför lön oktober 2026 · Anna Andersson",
      meta: "lön · väntar i Löner",
      variant: "vantar",
      beslut: lonekort,
      mal: { typ: "vy", key: "betala.loner" },
    });
  });

  it("ett fakturaförslag leder till Fakturering och visar sitt inlägg", () => {
    const [rad] = betalaVantar({ lonerBeslut: [], faktureringForslag: [forslag({})], fakturautkast: [utkast] });
    expect(rad).toMatchObject({
      titel: "Faktura 1046 · Ateljé Vind AB",
      meta: "faktura · väntar i Fakturering",
      mal: { typ: "vy", key: "betala.fakturering" },
      inlagg: { viewKey: "betala.fakturering", postId: "p-9" },
    });
    expect(rad.beslut).toBeUndefined();
  });

  it("bara det som väntar: besvarade kort, utfärdade förslag och verifikationsförslag står inte där", () => {
    const rader = betalaVantar({
      lonerBeslut: [{ ...lonekort, status: "answered" }],
      faktureringForslag: [forslag({ status: "issued" }), forslag({ kind: "voucher", draft_id: "v" })],
      fakturautkast: [utkast],
    });
    expect(rader).toEqual([]);
  });
});
