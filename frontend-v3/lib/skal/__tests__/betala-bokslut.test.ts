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
import { arsnamn, atgarderVy } from "@/lib/skal/bokslut";

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
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Summering", "Obetalda", "Utkast", "Senast betalda"]);
    expect(vy.sektioner[1].rader[0].variant).toBe("fel");
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

  it("visar fakturor bokförda utanför BokAI, med betalningen när den hittats", () => {
    const vy = faktureringVy({
      total: 0,
      invoices: [],
      ledger_invoices: [
        {
          voucher_id: "v2",
          voucher_number: "A49",
          date: "2026-04-30",
          description: "Faktura #101269 skickad",
          amount_inc_vat: 12555000,
          vat_amount: 2511000,
          paid: false,
          payment_voucher_id: null,
          payment_date: null,
        },
        {
          voucher_id: "v1",
          voucher_number: "A6",
          date: "2026-01-29",
          description: "Faktura #101266 skickad",
          amount_inc_vat: 9720000,
          vat_amount: 1944000,
          paid: true,
          payment_voucher_id: "v1-bet",
          payment_date: "2026-03-25",
        },
      ],
    });
    expect(vy.lage).toBe("normal");
    expect(vy.status).toBe("1 obetald");
    const [, sektion] = vy.sektioner;
    expect(sektion.titel).toBe("Bokförda utanför BokAI");
    expect(sektion.rader.map((r) => r.titel)).toEqual(["Faktura #101269 skickad", "Faktura #101266 skickad"]);
    expect(sektion.rader[0].meta).toBe("A49 · 2026-04-30 · ingen matchande betalning");
    expect(sektion.rader[1].meta).toBe("A6 · 2026-01-29 · betald 2026-03-25");
    expect(sektion.rader[1].mal).toEqual({ typ: "ver", id: "v1" });
    expect(sektion.rader[1].lankar).toEqual([{ text: "betalning", mal: { typ: "ver", id: "v1-bet" } }]);
  });
});

describe("Summering", () => {
  const tal = (s: string) => s.replace(/\s/g, "");

  it("Fakturering summerar fakturerat, betalt, obetalt och förfallet, utan utkast och makulerade", () => {
    const vy = faktureringVy({
      total: 5,
      invoices: [
        faktura({ id: "a", amount_inc_vat: 125000, vat_amount: 25000, status: "overdue", is_overdue: true }),
        faktura({ id: "b", amount_inc_vat: 250000, vat_amount: 50000, remaining_amount: 100000 }),
        faktura({ id: "c", amount_inc_vat: 500000, vat_amount: 100000, remaining_amount: 0, status: "paid" }),
        faktura({ id: "d", amount_inc_vat: 999900, status: "draft" }),
        faktura({ id: "e", amount_inc_vat: 777700, remaining_amount: 0, status: "cancelled" }),
      ],
      ledger_invoices: [
        {
          voucher_id: "v1",
          voucher_number: "A6",
          date: "2026-01-29",
          description: "Faktura #101266 skickad",
          amount_inc_vat: 1000000,
          vat_amount: 200000,
          paid: false,
          payment_voucher_id: null,
          payment_date: null,
        },
      ],
    });
    const summering = vy.sektioner.find((s) => s.titel === "Summering")!;
    expect(summering.rader.map((r) => [r.titel, tal(r.hoger)])).toEqual([
      ["Fakturerat", "18750"],
      ["Betalt", "6750"],
      ["Obetalt", "12000"],
      ["Varav förfallet", "1000"],
    ]);
    expect(tal(summering.rader[0].meta!)).toBe("4fakturor·varavmoms3750");
    expect(summering.rader[2].meta).toBe("3 fakturor");
  });

  it("Löner visar skatt och sociala avgifter betalda under året, och summan till Skatteverket", () => {
    const vy = lonerVy(
      {
        payroll_runs: [],
        summary: {
          gross_salary: 8000000,
          tax_withheld: 2400000,
          tax_paid: 2400000,
          employer_fee_charged: 2513600,
          employer_fee_paid: 1256800,
        },
      },
      { beslut: [], ar: { start: "2026-01-01", end: "2026-12-31" } }
    );
    expect(vy.lage).toBe("normal");
    const [summering] = vy.sektioner;
    expect(summering.titel).toBe("Summering");
    expect(summering.rader.map((r) => [r.titel, tal(r.hoger)])).toEqual([
      ["Löner", "80000"],
      ["Skatt betald", "24000"],
      ["Sociala avgifter betalda", "12568"],
      ["Betalt till Skatteverket", "36568"],
    ]);
    expect(tal(summering.rader[2].meta!)).toBe("påfördaunderåret25136");
    expect(summering.rader[3].summa).toBe(true);
    expect(vy.period).toBe("2026-01-01 – 2026-12-31 · inga lönekörningar");
  });

  it("Löner utan något bokfört har ingen summering", () => {
    const noll = { gross_salary: 0, tax_withheld: 0, tax_paid: 0, employer_fee_charged: 0, employer_fee_paid: 0 };
    const vy = lonerVy({ payroll_runs: [], summary: noll });
    expect(vy.lage).toBe("tomt");
    expect(vy.sektioner).toEqual([]);
  });
});

describe("lonerVy", () => {
  it("är tom utan lönekörningar", () => {
    const vy = lonerVy({ payroll_runs: [] });
    expect(vy.lage).toBe("tomt");
    expect(vy.status).toBe("inga lönekörningar");
  });

  it("visar löner bokförda utanför BokAI, nettolön till höger", () => {
    const vy = lonerVy(
      {
        payroll_runs: [],
        ledger_payouts: [
          {
            voucher_id: "v22",
            voucher_number: "A22",
            date: "2025-02-26",
            description: "Lön till tjänstemän (januari)",
            gross_salary: 4358300,
            preliminary_tax: 1249500,
            net_salary: 3108800,
          },
        ],
      },
      { beslut: [], ar: { start: "2025-01-01", end: "2025-12-31" } }
    );
    expect(vy.lage).toBe("normal");
    expect(vy.status).toBe("alla bokförda");
    expect(vy.period).toBe("2025-01-01 – 2025-12-31 · 1 bokförda utanför BokAI · nettolön");
    const [sektion] = vy.sektioner;
    expect(sektion.titel).toBe("Bokförda utanför BokAI");
    expect(sektion.rader[0].titel).toBe("Lön till tjänstemän (januari)");
    expect(sektion.rader[0].meta).toMatch(/^A22 · 2025-02-26 · skatt 12\s?495/);
    expect(sektion.rader[0].mal).toEqual({ typ: "ver", id: "v22" });
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

describe("arsnamn", () => {
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
    expect(vy.fot).toMatch(/körs när vyn öppnas/);
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

  it("med ett år står bara fakturor med fakturadatum i året med", () => {
    const k = { lonerBeslut: [], faktureringForslag: [forslag({})], fakturautkast: [utkast] };
    expect(betalaVantar({ ...k, ar: { start: "2025-01-01", end: "2025-12-31" } })).toEqual([]);
    expect(betalaVantar({ ...k, ar: { start: "2026-01-01", end: "2026-12-31" } })).toHaveLength(1);
  });
});

describe("Fakturering och Löner följer valt räkenskapsår", () => {
  const ar = { start: "2026-01-01", end: "2026-12-31" };
  const utkast = (id: string, invoice_date: string) => ({
    id,
    invoice_number: id,
    customer_name: `Kund ${id}`,
    invoice_date,
    due_date: invoice_date,
    status: "needs_review",
    amount_inc_vat: 100000,
  });
  const forslag = (draft_id: string) =>
    ({
      kind: "invoice",
      draft_id,
      post_id: `p-${draft_id}`,
      decision_id: null,
      correction_of: null,
      status: "pending",
      replaced_by: null,
      posted_at: null,
      voucher: null,
      last_error_code: null,
      created_at: "2026-10-25T08:00:00",
    }) as ForslagStatusSvar;

  it("Fakturering visar bara årets förslag och utkast, och året i perioden", () => {
    const vy = faktureringVy(
      { total: 0, invoices: [] },
      {
        utkast: [
          utkast("i-ar", "2026-03-01"),
          utkast("i-fjol", "2025-12-31"),
          utkast("u-ar", "2026-12-31"),
          utkast("u-nasta", "2027-01-01"),
        ],
        forslag: [forslag("i-ar"), forslag("i-fjol")],
        beslut: [],
        utfardanden: [],
        ar,
      }
    );
    const ids = vy.sektioner.flatMap((s) => s.rader.map((r) => r.id));
    expect(ids).toEqual(["forslag:i-ar", "utkast:u-ar"]);
    expect(vy.period).toBe("2026-01-01 – 2026-12-31 · 0 fakturor");
  });

  it("Löner visar alla årets körningar och året i perioden", () => {
    const run = { payment_date: null, payslip_count: 1, total_gross_salary: 1, total_net_salary: 1, status: "booked" };
    const korningar = Array.from({ length: 13 }, (_, i) => ({
      ...run,
      id: `k${i}`,
      year: 2026,
      month: (i % 12) + 1,
    }));
    const vy = lonerVy({ payroll_runs: korningar }, { beslut: [], ar });
    expect(vy.sektioner).toHaveLength(13);
    expect(vy.period).toBe("2026-01-01 – 2026-12-31 · 13 lönekörningar · nettolön");
    expect(lonerVy({ payroll_runs: [] }, { beslut: [], ar }).period).toBe(
      "2026-01-01 – 2026-12-31 · inga lönekörningar"
    );
  });
});
