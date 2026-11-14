import { describe, expect, it } from "vitest";
import { balansVy, resultatVy, verifikationerVy, type Balansrakning, type Resultatrakning } from "@/lib/skal/bocker";
import { formatBeloppHela } from "@/lib/skal/format";
import type { Rattelse } from "@/lib/skal/bocker";
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

  it("titeln är verifikationens text, radens egen text står i metan", () => {
    const vy = huvudbokVy(
      AR,
      huvudbok({
        transactions: [
          {
            ...huvudbok().transactions[0],
            description: "Kortbetalning Visa - 7984",
            voucher_description: "Anthropic Claude Pro, prenumeration",
            row_description: "Kortbetalning Visa - 7984",
          },
        ],
      })
    );
    expect(rader(vy)[1]).toMatchObject({
      titel: "Anthropic Claude Pro, prenumeration",
      meta: "A-12 · 2026-03-04 · Kortbetalning Visa - 7984 · saldo 700",
    });
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

  describe("rättelser", () => {
    const A17 = { id: "a17", series: "A", number: 17 };
    const B1 = { id: "b1", series: "B", number: 1 };
    const rattelse = (accounts: Rattelse["accounts"], kind: Rattelse["kind"] = "makulering"): Rattelse => ({
      kind,
      title: "Makulering av A-17: Avdragen skatt",
      original: A17,
      original_description: "Avdragen skatt",
      correction: B1,
      correction_date: "2026-02-28",
      correction_status: "posted",
      reason: "Dubbelbokad",
      before_total: 1300000,
      after_total: kind === "makulering" ? 0 : 1300000,
      accounts,
    });
    const rad = (voucher: typeof A17, debit: number, credit: number, correction: Rattelse) => ({
      date: voucher === A17 ? "2026-02-12" : "2026-02-28",
      voucher_id: voucher.id,
      series: voucher.series,
      number: voucher.number,
      description: voucher === A17 ? "Avdragen skatt" : "Återföring",
      debit,
      credit,
      balance: 0,
      correction,
    });

    it("en makulerad verifikation stryks över och rättelsen upprepar inte beloppet", () => {
      const r = rattelse([{ account_code: "1930", before: -1300000, after: 0 }]);
      const vy = huvudbokVy(AR, huvudbok({ transactions: [rad(A17, 0, 1300000, r), rad(B1, 1300000, 0, r)] }));
      const [, original, b1] = rader(vy);
      expect(original).toMatchObject({ struken: true, hoger: formatBeloppHela(-1300000) });
      expect(original.meta).toContain("makulerad av B-1 2026-02-28");
      expect(b1).toMatchObject({ titel: "Makulering av A-17", hoger: "" });
      expect(b1.struken).toBeUndefined();
      expect(b1.meta).toContain("Dubbelbokad");
    });

    it("en ändrad kontering visar beloppet före överstruket och beloppet efter", () => {
      const r = rattelse([{ account_code: "1930", before: -1300000, after: -1000000 }], "andring");
      const vy = huvudbokVy(AR, huvudbok({ transactions: [rad(A17, 0, 1300000, r), rad(B1, 300000, 0, r)] }));
      const [, original, b1] = rader(vy);
      expect(original).toMatchObject({ hoger: formatBeloppHela(-1000000), hogerFore: formatBeloppHela(-1300000) });
      expect(original.struken).toBeUndefined();
      expect(b1).toMatchObject({ titel: "Ändring av A-17", hoger: "" });
    });

    it("utan originalet i huvudboken visar rättelsen sitt belopp", () => {
      const r = rattelse([{ account_code: "1930", before: -1300000, after: 0 }]);
      const vy = huvudbokVy(AR, huvudbok({ transactions: [rad(B1, 1300000, 0, r)] }));
      expect(rader(vy)[1]).toMatchObject({ titel: "Makulering av A-17", hoger: formatBeloppHela(1300000) });
    });
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

  it("en verifikation som en lön bokför säger det och leder tillbaka till Löner", () => {
    const vy = verifikationVy(
      verifikation({
        origin: { kind: "payslip", title: "Lön Anna Andersson · oktober 2026", view_key: "betala.loner" },
      })
    );
    const ursprung = vy.sektioner.find((s) => s.titel === "Uppstod ur");
    expect(ursprung?.rader[0]).toMatchObject({
      titel: "Lön Anna Andersson · oktober 2026",
      meta: "i Löner",
      mal: { typ: "vy", key: "betala.loner" },
    });
    // Direkt efter konteringarna.
    expect(vy.sektioner[1].titel).toBe("Uppstod ur");
  });

  it("utan ursprung ingen sektion", () => {
    expect(verifikationVy(verifikation()).sektioner.map((s) => s.titel)).not.toContain("Uppstod ur");
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

  it("kommentaren står efter konteringarna, ett stycke per rad", () => {
    const vy = verifikationVy(
      verifikation({
        comment:
          "Omräknat 20,00 USD × 9,45 SEK/USD = 189,00 kr. Riksbankens dagliga mittkurs (serie SEKUSDPMI) för 2026-10-14, köpdatum. Källa: Sveriges Riksbank, https://api.riksbank.se/swea/v1/Observations/SEKUSDPMI/2026-10-14/2026-10-14\nOmvänd skattskyldighet: SaaS-tjänst från säljare i USA, ruta 22.",
      })
    );
    expect(vy.sektioner[1].titel).toBe("Kommentar");
    expect(vy.sektioner[1].rader.map((r) => r.titel)).toEqual([
      expect.stringContaining("Riksbankens dagliga mittkurs"),
      "Omvänd skattskyldighet: SaaS-tjänst från säljare i USA, ruta 22.",
    ]);
  });

  it("utan kommentar ingen sektion", () => {
    expect(verifikationVy(verifikation({ comment: null })).sektioner.map((s) => s.titel)).not.toContain("Kommentar");
    expect(verifikationVy(verifikation({ comment: "  " })).sektioner.map((s) => s.titel)).not.toContain("Kommentar");
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
    expect(positionsUrl("bocker", vy, { typ: "konto", kod: "1930" })).toBe("/?sida=bocker&vy=verifikationer&konto=1930");
    const url = new URL(positionsUrl("bocker", vy, { typ: "ver", id: "a b" }), "http://x");
    expect(lasDetalj(url.searchParams.get("konto"), url.searchParams.get("ver"))).toEqual({ typ: "ver", id: "a b" });
  });
});

describe("verifikationens rättelse och historik", () => {
  it("en postad verifikation har länken som ber agenten rätta, i Verifikationers chatt", () => {
    const ratta = rader(verifikationVy(verifikation())).find((r) => r.id === "ratta");
    expect(ratta?.fraga).toEqual({ viewKey: "bocker.verifikationer", text: "Rätta A-12: ", etikett: "be agenten rätta" });
  });

  it("ett utkast och en redan rättad verifikation har den inte", () => {
    expect(rader(verifikationVy(verifikation({ status: "draft", number: null }))).find((r) => r.id === "ratta")).toBeUndefined();
    const rattad = verifikation({ corrected_by: { id: "b1", series: "B", number: 3 } as never });
    expect(rader(verifikationVy(rattad)).find((r) => r.id === "ratta")).toBeUndefined();
  });

  it("visar behandlingshistoriken: vad, vem och när", () => {
    const vy = verifikationVy(verifikation(), [
      { id: "h1", action: "created", actor: "agent", timestamp: "2026-03-05T07:59:00" },
      { id: "h2", action: "posted", actor: "admin", timestamp: "2026-03-05T08:00:00" },
    ]);
    const handelser = vy.sektioner.find((s) => s.titel === "Händelser")!.rader;
    expect(handelser.map((r) => [r.titel, r.meta])).toEqual([
      ["Skapad", "agenten · 2026-03-05 07:59"],
      ["Bokförd", "admin · 2026-03-05 08:00"],
    ]);
  });
});
