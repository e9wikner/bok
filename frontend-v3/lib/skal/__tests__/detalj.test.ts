import { describe, expect, it } from "vitest";
import { balansVy, resultatVy, verifikationerVy, type Balansrakning, type Resultatrakning } from "@/lib/skal/bocker";
import { formatBeloppHela } from "@/lib/skal/format";
import { huvudbokVy, verifikationVy, type Huvudbok, type VerifikationDetalj } from "@/lib/skal/detalj";
import { lasDetalj, positionsUrl } from "@/lib/skal/rutt";
import type { VyData, VyRadData } from "@/lib/skal/vydata";
import { forstaVyn } from "@/lib/skal/vyer";

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

const huvudbok = (over: Partial<Huvudbok> = {}): Huvudbok => ({
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
  ...over,
});

const verifikation = (over: Partial<VerifikationDetalj> = {}): VerifikationDetalj => ({
  id: "v1",
  series: "A",
  number: 12,
  date: "2026-03-04",
  description: "Hyra mars",
  status: "posted",
  total_debit: 30000,
  total_credit: 30000,
  missing_attachment: false,
  age_days: 3,
  created_by: "agent",
  posted_at: "2026-03-05T08:00:00",
  rows: [
    { id: "r1", account_code: "5010", account_name: "Lokalhyra", debit: 30000, credit: 0 },
    { id: "r2", account_code: "1930", account_name: "Företagskonto", debit: 0, credit: 30000 },
  ],
  ...over,
});

const rader = (vy: VyData): VyRadData[] => vy.sektioner.flatMap((s) => s.rader);

describe("huvudboken", () => {
  it("ett balanskonto börjar i IB och slutar på utgående saldo", () => {
    const vy = huvudbokVy(AR, huvudbok());
    const [ib, rad, ub] = rader(vy);
    expect(ib).toMatchObject({ titel: "Ingående balans", hoger: formatBeloppHela(100000) });
    expect(rad).toMatchObject({
      titel: "Hyra mars",
      meta: "A-12 · 2026-03-04 · saldo 700",
      hoger: "−300",
      mal: { typ: "ver", id: "v1" },
    });
    expect(ub).toMatchObject({ titel: "Utgående saldo", hoger: "700", summa: true });
    expect(vy.status).toBe("saldo 700");
  });

  it("IB-raden och summan leder ingenstans — IB är ingen verifikation", () => {
    const vy = huvudbokVy(AR, huvudbok());
    const [ib, , ub] = rader(vy);
    expect(ib.mal).toBeUndefined();
    expect(ub.mal).toBeUndefined();
  });

  it("ett resultatkonto har ingen IB-rad", () => {
    const vy = huvudbokVy(AR, huvudbok({ account_code: "5010", opening_balance: 0 }));
    expect(rader(vy).map((r) => r.id)).toEqual(["v1:0", "ub"]);
  });

  it("utan transaktioner och IB är huvudboken tom", () => {
    const vy = huvudbokVy(AR, huvudbok({ opening_balance: 0, closing_balance: 0, transactions: [], transaction_count: 0 }));
    expect(vy.lage).toBe("tomt");
    expect(vy.status).toBe("inga transaktioner");
  });
});

describe("verifikationen", () => {
  it("varje kontering leder till kontots huvudbok", () => {
    const vy = verifikationVy(verifikation());
    const konteringar = vy.sektioner[0].rader;
    expect(konteringar.map((r) => [r.titel, r.hoger, r.mal])).toEqual([
      ["Lokalhyra", "300", { typ: "konto", kod: "5010" }],
      ["Företagskonto", "−300", { typ: "konto", kod: "1930" }],
      ["Omslutning", "300", undefined],
    ]);
    expect(vy.status).toBe("postad · låst");
  });

  it("med underlag: kvittolänken; utan: hur länge det saknats", () => {
    expect(verifikationVy(verifikation()).sektioner[1].rader[0].kvitto).toEqual({ voucherId: "v1", nummer: "A-12" });
    const saknar = verifikationVy(verifikation({ missing_attachment: true }));
    expect(saknar.sektioner[1].rader[0]).toMatchObject({ meta: "saknas sedan 3 dgr", variant: "saknar" });
    expect(saknar.lage).toBe("vantar");
  });

  it("hänvisningarna leder till de andra verifikationerna", () => {
    const vy = verifikationVy(
      verifikation({ corrected_by: { id: "b3", series: "B", number: 3 } })
    );
    const hanvisningar = vy.sektioner.find((s) => s.titel === "Hänvisningar")!;
    expect(hanvisningar.rader[0]).toMatchObject({ titel: "Rättad av", meta: "B-3", mal: { typ: "ver", id: "b3" } });
    expect(vy.banner?.text).toContain("Rättad av B-3");
  });

  it("ett utkast har ingen underlagssektion", () => {
    const vy = verifikationVy(verifikation({ status: "draft", number: null }));
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Konteringar"]);
    expect(vy.status).toBe("utkast");
  });
});

describe("vyernas rader leder vidare", () => {
  const konto = (code: string, name: string, closing: number) => ({
    code,
    name,
    opening_balance: 0,
    change: closing,
    closing_balance: closing,
  });
  const balans: Balansrakning = {
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
  };
  const resultat: Resultatrakning = {
    revenue: 0,
    costs: 30000,
    financial: 0,
    operating_profit: -30000,
    profit: -30000,
    revenue_details: [],
    cost_details: [{ code: "5010", name: "Lokalhyra", amount: 30000 }],
    financial_details: [],
    voucher_count: 1,
  };

  it("balansräkningens konton till huvudboken, årets resultat till resultaträkningen", () => {
    const r = new Map(rader(balansVy(AR, balans, resultat)).map((x) => [x.id, x]));
    expect(r.get("1930")).toMatchObject({ mal: { typ: "konto", kod: "1930" } });
    expect(r.get("arets-resultat")).toMatchObject({ mal: { typ: "vy", key: "bocker.resultat" } });
    expect(r.get("sum-t")).not.toHaveProperty("mal");
  });

  it("resultaträkningens konton till huvudboken", () => {
    const r = rader(resultatVy(AR, resultat));
    expect(r.find((x) => x.id === "5010")?.mal).toEqual({ typ: "konto", kod: "5010" });
  });

  it("verifikationerna till sin detalj", () => {
    const v = {
      id: "v1",
      series: "A",
      number: 12,
      date: "2026-03-04",
      description: "Hyra",
      status: "posted",
      total_debit: 30000,
      missing_attachment: false,
    };
    const vy = verifikationerVy(
      AR,
      { total: 1, vouchers: [v] },
      { total: 0, vouchers: [] },
      { beslut: [], forslag: [], saknar: { total: 1, vouchers: [{ ...v, id: "v2", missing_attachment: true }] } }
    );
    const r = new Map(rader(vy).map((x) => [x.id, x]));
    expect(r.get("v1")).toMatchObject({ mal: { typ: "ver", id: "v1" } });
    expect(r.get("v2")).toMatchObject({ mal: { typ: "ver", id: "v2" } });
  });
});

describe("lagret i URL:en", () => {
  it("läser konto och verifikation, och avstår vid ett oläsbart konto", () => {
    expect(lasDetalj("1930", null)).toEqual({ typ: "konto", kod: "1930" });
    expect(lasDetalj(null, "v1")).toEqual({ typ: "ver", id: "v1" });
    expect(lasDetalj("19x0", null)).toBeNull();
    expect(lasDetalj(null, "  ")).toBeNull();
    expect(lasDetalj(null, null)).toBeNull();
  });

  it("bygger en URL som läses tillbaka till samma lager", () => {
    const vy = forstaVyn("bocker");
    expect(positionsUrl("bocker", vy, { typ: "konto", kod: "1930" })).toBe("/v4?sida=bocker&vy=balans&konto=1930");
    const url = new URL(positionsUrl("bocker", vy, { typ: "ver", id: "a b" }), "http://x");
    expect(lasDetalj(url.searchParams.get("konto"), url.searchParams.get("ver"))).toEqual({ typ: "ver", id: "a b" });
  });
});
