import { describe, expect, it } from "vitest";
import {
  type Balansrakning,
  type Resultatrakning,
  type Verifikation,
  balansVy,
  resultatVy,
  verifikationerVy,
} from "@/lib/skal/bocker";
import { formatBeloppHela } from "@/lib/skal/format";

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

function konto(code: string, name: string, closing: number) {
  return { code, name, opening_balance: 0, change: closing, closing_balance: closing };
}

// Tillgångar 1 500, klass 2 är 1 000, årets resultat 500.
const BALANS: Balansrakning = {
  closing_assets: 150000,
  closing_equity_liabilities: 100000,
  has_ib_vouchers: true,
  fixed_assets_details: [],
  receivables_details: [konto("1510", "Kundfordringar", 50000)],
  bank_and_cash_details: [konto("1930", "Företagskonto", 100000), konto("1940", "Tomt", 0)],
  current_assets_details: [],
  equity_details: [konto("2081", "Aktiekapital", 50000)],
  long_term_liabilities_details: [],
  current_liabilities_details: [konto("2440", "Leverantörsskulder", 50000)],
};

const RESULTAT: Resultatrakning = {
  revenue: 80000,
  costs: 29000,
  financial: 1000,
  operating_profit: 51000,
  profit: 50000,
  revenue_details: [{ code: "3010", name: "Försäljning", amount: 80000 }],
  cost_details: [{ code: "5010", name: "Lokalhyra", amount: 29000 }],
  financial_details: [{ code: "8423", name: "Räntekostnader", amount: 1000 }],
  voucher_count: 7,
};

function rader(vy: ReturnType<typeof balansVy>) {
  return vy.sektioner.flatMap((s) => s.rader);
}

describe("balansVy", () => {
  it("lägger årets resultat till eget kapital så att summorna möts", () => {
    const vy = balansVy(AR, BALANS, RESULTAT);
    expect(vy.lage).toBe("normal");
    expect(vy.status).toBe("balanserar");
    const titlar = vy.sektioner[1].rader.map((r) => r.titel);
    // Resultatraden efter eget kapital, före skulderna.
    expect(titlar).toEqual([
      "Aktiekapital",
      "Årets resultat, ej bokfört",
      "Leverantörsskulder",
      "Summa eget kapital och skulder",
    ]);
    const summor = rader(vy).filter((r) => r.summa).map((r) => r.hoger);
    expect(summor).toEqual([formatBeloppHela(150000), formatBeloppHela(150000)]);
  });

  it("utelämnar konton med noll i utgående balans", () => {
    const vy = balansVy(AR, BALANS, RESULTAT);
    expect(rader(vy).map((r) => r.id)).not.toContain("1940");
  });

  it("är i felläge med en banner när summorna inte möts", () => {
    const vy = balansVy(AR, BALANS, { ...RESULTAT, profit: 40000 });
    expect(vy.lage).toBe("fel");
    expect(vy.banner?.ton).toBe("fel");
    expect(vy.status).toBe(`differens ${formatBeloppHela(10000)}`);
  });
});

describe("resultatVy", () => {
  it("visar kostnader och finansiella kostnader med minustecken", () => {
    const vy = resultatVy(AR, RESULTAT);
    const hyra = rader(vy).find((r) => r.id === "5010");
    expect(hyra?.hoger).toBe(formatBeloppHela(-29000));
    const ranta = rader(vy).find((r) => r.id === "8423");
    expect(ranta?.hoger).toBe(formatBeloppHela(-1000));
    const res = rader(vy).find((r) => r.id === "res");
    expect(res?.hoger).toBe(formatBeloppHela(50000));
    expect(vy.status).toBe(`vinst ${formatBeloppHela(50000)}`);
  });

  it("är tomt utan bokförda konton", () => {
    const vy = resultatVy(AR, {
      ...RESULTAT,
      revenue_details: [],
      cost_details: [],
      financial_details: [],
    });
    expect(vy.lage).toBe("tomt");
    expect(vy.sektioner).toEqual([]);
  });
});

describe("verifikationerVy", () => {
  const v = (over: Partial<Verifikation>): Verifikation => ({
    id: "x",
    series: "A",
    number: 1,
    date: "2026-09-04",
    description: "Hyra",
    status: "posted",
    total_debit: 12345,
    missing_attachment: false,
    ...over,
  });

  it("visar utkast före postade och märker saknat underlag", () => {
    const vy = verifikationerVy(
      AR,
      { total: 2, vouchers: [v({ id: "a", missing_attachment: true }), v({ id: "b", number: 2 })] },
      { total: 1, vouchers: [v({ id: "u", status: "draft" })] }
    );
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Utkast", "Senast postade"]);
    expect(vy.lage).toBe("vantar");
    const [utkast, saknar, vanlig] = rader(vy);
    expect(utkast.variant).toBe("vantar");
    expect(saknar.variant).toBe("saknar");
    expect(saknar.meta).toBe("A-1 · 2026-09-04 · saknar underlag");
    expect(vanlig.variant).toBeUndefined();
  });

  it("säger i foten när listan är avkortad", () => {
    const vy = verifikationerVy(AR, { total: 90, vouchers: [v({})] }, { total: 0, vouchers: [] });
    expect(vy.fot).toMatch(/Visar de 1 senaste/);
    expect(vy.status).toBe("90 postade");
  });
});
