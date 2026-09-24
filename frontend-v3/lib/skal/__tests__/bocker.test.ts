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
import type { BeslutSvar, ForslagStatusSvar } from "@/lib/chattyta/api";

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
    // §11.1: Väntar på beslut, Postade, Utkast — i den ordningen.
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Postade", "Utkast"]);
    expect(vy.lage).toBe("vantar");
    const [saknar, vanlig, utkast] = rader(vy);
    expect(utkast.variant).toBe("vantar");
    expect(saknar.variant).toBe("saknar");
    expect(saknar.meta).toBe("A-1 · 2026-09-04 · saknar underlag");
    expect(vanlig.variant).toBeUndefined();
  });

  it("visar Utkast i stället för nummer på ett utkast (testfall 13)", () => {
    const vy = verifikationerVy(
      AR,
      { total: 0, vouchers: [] },
      {
        total: 2,
        vouchers: [
          v({ id: "u1", status: "draft", number: null }),
          v({ id: "u2", status: "draft", number: null }),
        ],
      }
    );
    const [u1, u2] = rader(vy);
    expect(u1.meta).toBe("Utkast · 2026-09-04");
    expect(u1.meta).not.toMatch(/null|NaN|A-/);
    // Två utkast har båda `null`; identiteten är id.
    expect([u1.id, u2.id]).toEqual(["u1", "u2"]);
  });

  it("säger rättad av och rättar i metan (§7.5)", () => {
    const vy = verifikationerVy(
      AR,
      {
        total: 2,
        vouchers: [
          v({ id: "b7", series: "B", number: 7, corrects: { id: "a118", series: "A", number: 118 } }),
          v({ id: "a118", number: 118, corrected_by: { id: "b7", series: "B", number: 7 } }),
        ],
      },
      { total: 0, vouchers: [] }
    );
    const [b7, a118] = rader(vy);
    expect(b7.meta).toBe("B-7 · 2026-09-04 · rättar A-118");
    expect(a118.meta).toBe("A-118 · 2026-09-04 · rättad av B-7");
  });

  it("säger i foten när listan är avkortad", () => {
    const vy = verifikationerVy(AR, { total: 90, vouchers: [v({})] }, { total: 0, vouchers: [] });
    expect(vy.fot).toMatch(/Visar de 1 senaste/);
    expect(vy.status).toBe("90 postade");
  });
});

// ─── Testfall 45: sektionerna och radlägena (flode-verifikationer §11.1) ─────

describe("verifikationerVy: Väntar på beslut, Postade, Utkast (testfall 45)", () => {
  const v = (over: Partial<Verifikation>): Verifikation => ({
    id: "x",
    series: "A",
    number: null,
    date: "2026-09-18",
    description: "Kontorsmaterial",
    status: "draft",
    total_debit: 89600,
    missing_attachment: false,
    ...over,
  });
  const forslag = (over: Partial<ForslagStatusSvar>): ForslagStatusSvar => ({
    draft_id: "x",
    post_id: "p",
    decision_id: null,
    correction_of: null,
    correction_note_id: null,
    status: "pending",
    replaced_by: null,
    posted_at: null,
    voucher: null,
    last_error_code: null,
    created_at: "2026-09-18T06:41:00",
    ...over,
  });
  const beslut = (over: Partial<BeslutSvar>): BeslutSvar => ({
    id: "d1",
    view_key: "bocker.verifikationer",
    kind: "abstention",
    status: "open",
    title: "Kvitto utan moms",
    amount_ore: 12500,
    reason: "",
    consequence: "",
    source: { kind: "intake_source", id: "s", date: "2026-09-10" },
    age_days: 8,
    thread_id: null,
    post_id: null,
    options: [],
    ...over,
  });
  const TOM = { total: 0, vouchers: [] };
  const sektion = (vy: ReturnType<typeof verifikationerVy>, titel: string) =>
    vy.sektioner.find((s) => s.titel === titel)?.rader ?? [];

  it("ett trådutkast visas bara under Väntar; övriga utkast under Utkast", () => {
    const vy = verifikationerVy(
      AR,
      { total: 1, vouchers: [v({ id: "a1", status: "posted", number: 1 })] },
      {
        total: 3,
        vouchers: [
          v({ id: "trad", description: "Förslaget" }),
          v({ id: "hand", description: "Handskrivet" }),
          v({ id: "ersatt-postad", description: "Postat förslag" }),
        ],
      },
      {
        beslut: [],
        forslag: [
          forslag({ draft_id: "trad" }),
          // En rad i thread_drafts med annan status hör också tråden till.
          forslag({ draft_id: "ersatt-postad", status: "superseded" }),
        ],
      }
    );
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Väntar på beslut", "Postade", "Utkast"]);
    expect(sektion(vy, "Väntar på beslut").map((r) => r.id)).toEqual(["trad"]);
    expect(sektion(vy, "Utkast").map((r) => r.id)).toEqual(["hand"]);
    const alla = vy.sektioner.flatMap((s) => s.rader.map((r) => r.id));
    expect(alla.filter((id) => id === "trad")).toHaveLength(1);
  });

  it("radlägena: beslut, förslag, rättelse och fel", () => {
    const vy = verifikationerVy(AR, TOM, {
      total: 3,
      vouchers: [
        v({ id: "f", date: "2026-09-18" }),
        v({ id: "r", series: "B", corrects: { id: "a118", series: "A", number: 118 } }),
        v({ id: "e" }),
      ],
    }, {
      beslut: [beslut({}), beslut({ id: "gammal", status: "answered" })],
      forslag: [
        forslag({ draft_id: "f" }),
        forslag({ draft_id: "r", correction_of: "a118" }),
        forslag({ draft_id: "e", last_error_code: "period_locked" }),
      ],
    });
    const [b, f, r, e] = sektion(vy, "Väntar på beslut");
    expect(b).toMatchObject({
      id: "d1",
      titel: "Kvitto utan moms",
      meta: "väntar på dig · 2026-09-10",
      variant: "vantar",
      ageDays: 8,
      hoger: formatBeloppHela(12500),
    });
    expect(f).toMatchObject({ id: "f", meta: "förslag väntar · 2026-09-18", variant: "vantar" });
    expect(f.ageDays).toBeUndefined();
    expect(r).toMatchObject({ id: "r", meta: "rättelse av A-118 väntar", variant: "vantar" });
    expect(e).toMatchObject({ id: "e", meta: "postning misslyckades · ligger kvar", variant: "fel" });
    expect(sektion(vy, "Väntar på beslut")).toHaveLength(4);
    expect(vy.lage).toBe("vantar");
    expect(vy.status).toBe("4 väntar på dig");
  });

  it("ett förslag på ett öppet beslut står i beslutets ställe och räknas en gång (§11.3)", () => {
    const vy = verifikationerVy(AR, TOM, {
      total: 4,
      vouchers: [v({ id: "f1" }), v({ id: "f2" }), v({ id: "f3" }), v({ id: "rn" })],
    }, {
      beslut: [
        beslut({ id: "d-open" }),
        beslut({ id: "correction:n1", kind: "correction", source: { kind: "voucher", id: "a1", date: "2026-09-01" } }),
      ],
      forslag: [
        forslag({ draft_id: "f1", decision_id: "d-open" }),
        // Två väntande förslag på samma besvarade beslut: två rader, en sak som väntar.
        forslag({ draft_id: "f2", decision_id: "d-answered" }),
        forslag({ draft_id: "f3", decision_id: "d-answered" }),
        forslag({ draft_id: "rn", correction_of: "a1", correction_note_id: "n1" }),
      ],
    });
    expect(sektion(vy, "Väntar på beslut").map((r) => r.id)).toEqual(["f1", "f2", "f3", "rn"]);
    // d-open (via f1) + d-answered (f2, f3) + noteringen n1 (via rn) = 3,
    // samma regel som `count_waiting` och headerns `open_decisions`.
    expect(vy.status).toBe("3 väntar på dig");
  });

  it("utan väntande och utkast säger statusen antalet postade", () => {
    const vy = verifikationerVy(
      AR,
      { total: 1, vouchers: [v({ id: "a1", status: "posted", number: 1 })] },
      TOM,
      { beslut: [beslut({ status: "answered" })], forslag: [forslag({ draft_id: "a1", status: "posted" })] }
    );
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Postade"]);
    expect(vy.status).toBe("1 postade");
    expect(vy.lage).toBe("normal");
  });
});

// ─── Testfall 46, den rena delen: den optimistiska raden i vyn (§11.2) ──────

describe("verifikationerVy: den optimistiska raden (testfall 46)", () => {
  const v = (over: Partial<Verifikation>): Verifikation => ({
    id: "x",
    series: "A",
    number: null,
    date: "2026-09-18",
    description: "Kontorsmaterial",
    status: "draft",
    total_debit: 89600,
    ...over,
  });
  const pending: ForslagStatusSvar = {
    draft_id: "f",
    post_id: "p",
    decision_id: null,
    correction_of: null,
    correction_note_id: null,
    status: "pending",
    replaced_by: null,
    posted_at: null,
    voucher: null,
    last_error_code: null,
    created_at: "2026-09-18T06:41:00",
  };
  const utkast = { total: 1, vouchers: [v({ id: "f" })] };
  const postade = { total: 1, vouchers: [v({ id: "a1", status: "posted", number: 1 })] };

  it("pagaende överst i Postade, utan nummer, och ur Väntar", () => {
    const vy = verifikationerVy(AR, postade, utkast, {
      beslut: [],
      forslag: [pending],
      postningar: [
        { draftId: "f", lage: "pagaende", utkast: { titel: "Kontorsmaterial", serie: "A", belopp: 89600 } },
      ],
    });
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Postade"]);
    const [forsta, andra] = vy.sektioner[0].rader;
    expect(forsta).toMatchObject({ id: "f", variant: "pagaende", meta: "A · postas…", titel: "Kontorsmaterial" });
    expect(forsta.meta).not.toMatch(/\d/);
    expect(andra.id).toBe("a1");
  });

  it("postad: samma nyckel, läget ny, med nummer och tid", () => {
    const vy = verifikationerVy(AR, postade, { total: 0, vouchers: [] }, {
      beslut: [],
      forslag: [{ ...pending, status: "posted" }],
      postningar: [
        {
          draftId: "f",
          lage: "postad",
          utkast: { titel: "Kontorsmaterial", serie: "A", belopp: 89600 },
          verifikation: {
            id: "f",
            series: "A",
            number: 2,
            date: "2026-09-18",
            period_id: "p",
            status: "posted",
            posted_at: "2026-09-18T06:45:12",
          },
        },
      ],
    });
    const [forsta] = vy.sektioner[0].rader;
    expect(forsta).toMatchObject({ id: "f", variant: "ny", meta: "A-2 · postad 06:45 · du · låst" });
  });

  it("när serverns lista redan har verifikationen står den en gång, som ny", () => {
    const vy = verifikationerVy(
      AR,
      { total: 2, vouchers: [v({ id: "f", status: "posted", number: 2, posted_at: "2026-09-18T06:45:00" }), ...postade.vouchers] },
      { total: 0, vouchers: [] },
      {
        beslut: [],
        forslag: [],
        postningar: [{ draftId: "f", lage: "postad", utkast: null, verifikation: null }],
      }
    );
    const ids = vy.sektioner[0].rader.map((r) => r.id);
    expect(ids).toEqual(["f", "a1"]);
    expect(vy.sektioner[0].rader[0]).toMatchObject({ variant: "ny", meta: "A-2 · postad 06:45 · du · låst" });
  });
});
