import { describe, expect, it } from "vitest";
import { verifikationerVy, type Rattelse, type Verifikation, type Verifikationslista } from "@/lib/skal/bocker";
import { verifikationVy, type VerifikationDetalj } from "@/lib/skal/detalj";
import { formatBeloppHela } from "@/lib/skal/format";
import type { VyData, VyRadData } from "@/lib/skal/vydata";

/**
 * En rättad verifikation och dess rättelse läses som ett par (§7.5):
 * makulerat stryks över, ändrat visar före och efter, och rättelsen säger
 * vad den gjorde med vad, när och av vem.
 */

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };
const A53 = { id: "a53", series: "A", number: 53 };
const B1 = { id: "b1", series: "B", number: 1 };

const makulering: Rattelse = {
  kind: "makulering",
  title: "Makulering av A-53: Arbetsgivardeklaration 2026-10, avdragen skatt",
  original: A53,
  original_description: "Arbetsgivardeklaration 2026-10, avdragen skatt",
  correction: B1,
  correction_date: "2026-11-12",
  correction_status: "posted",
  actor: "stefan",
  reason: "Bokförd i fel månad",
  before_total: 1300000,
  after_total: 0,
  accounts: [
    {
      account_code: "2710",
      account_name: "Personalskatt",
      before: 1300000,
      after: 0,
    },
    {
      account_code: "1630",
      account_name: "Skattekonto",
      before: -1300000,
      after: 0,
    },
  ],
};

const andring: Rattelse = {
  ...makulering,
  kind: "andring",
  title: "Ändring av A-69: Moms jan-dec 2025",
  original: { id: "a69", series: "A", number: 69 },
  original_description: "Moms jan-dec 2025",
  correction: { id: "b3", series: "B", number: 3 },
  correction_date: "2026-09-02",
  before_total: 26974500,
  after_total: 26974500,
  accounts: [
    {
      account_code: "1650",
      account_name: "Momsfordran",
      before: 26974500,
      after: 0,
    },
    {
      account_code: "1630",
      account_name: "Skattekonto",
      before: -26974500,
      after: -26974500,
    },
    {
      account_code: "2650",
      account_name: "Momsskuld",
      before: 0,
      after: 26974500,
    },
  ],
};

const v = (over: Partial<Verifikation>): Verifikation => ({
  id: "a53",
  series: "A",
  number: 53,
  date: "2026-11-12",
  description: "Arbetsgivardeklaration 2026-10, avdragen skatt",
  status: "posted",
  total_debit: 1300000,
  missing_attachment: false,
  age_days: 0,
  ...over,
});

const lista = (...vouchers: Verifikation[]): Verifikationslista => ({
  total: vouchers.length,
  vouchers,
});
const rad = (vy: VyData, id: string): VyRadData | undefined =>
  vy.sektioner.flatMap((s) => s.rader).find((r) => r.id === id);

describe("listan", () => {
  it("en makulerad verifikation stryks över och säger av vad", () => {
    const vy = verifikationerVy(AR, lista(v({ corrected_by: B1, correction: makulering })), lista());
    expect(rad(vy, "a53")).toMatchObject({
      titel: "Arbetsgivardeklaration 2026-10, avdragen skatt",
      meta: "A-53 · 2026-11-12 · makulerad av B-1 2026-11-12",
      hoger: formatBeloppHela(1300000),
      struken: true,
    });
    expect(rad(vy, "a53")?.kvitto).toBeUndefined();
  });

  it("makuleringen heter så, och visar beloppet den tog bort", () => {
    const b1 = v({
      id: "b1",
      series: "B",
      number: 1,
      corrects: A53,
      correction: makulering,
    });
    expect(rad(verifikationerVy(AR, lista(b1), lista()), "b1")).toMatchObject({
      titel: "Makulering av A-53: Arbetsgivardeklaration 2026-10, avdragen skatt",
      meta: "B-1 · 2026-11-12 · makulerar A-53 · stefan",
      hogerFore: formatBeloppHela(1300000),
      hoger: "0",
    });
  });

  it("en ändrad verifikation utan beloppsändring visar bara beloppet", () => {
    const a69 = v({
      id: "a69",
      number: 69,
      date: "2026-08-17",
      corrected_by: andring.correction,
      correction: andring,
    });
    const r = rad(verifikationerVy(AR, lista(a69), lista()), "a69");
    expect(r).toMatchObject({
      meta: "A-69 · 2026-08-17 · ändrad av B-3 2026-09-02",
      hoger: formatBeloppHela(26974500),
    });
    expect(r?.hogerFore).toBeUndefined();
    expect(r?.struken).toBeUndefined();
  });

  it("en verifikation daterad framåt väntar på sitt underlag, den saknar det inte", () => {
    const a54 = v({
      id: "a54",
      number: 54,
      missing_attachment: true,
      age_days: -7,
      missing_statement_accounts: ["1630"],
    });
    const vy = verifikationerVy(AR, lista(), lista(), {
      beslut: [],
      forslag: [],
      saknar: lista(a54),
    });
    const r = vy.sektioner.find((s) => s.titel === "Saknar underlag")?.rader[0];
    expect(r?.meta).toBe("A-54 · kontoutdrag 1630 väntas om 7 dgr");
    expect(r?.variant).toBeUndefined();
  });
});

const detalj = (over: Partial<VerifikationDetalj>): VerifikationDetalj => ({
  ...v({}),
  total_credit: 1300000,
  created_by: "agent",
  posted_at: "2026-11-05T08:00:00",
  rows: [
    {
      id: "r1",
      account_code: "1630",
      account_name: "Skattekonto",
      debit: 0,
      credit: 26974500,
    },
    {
      id: "r2",
      account_code: "1650",
      account_name: "Momsfordran",
      debit: 26974500,
      credit: 0,
    },
  ],
  ...over,
});

describe("saknar underlag", () => {
  it("en ändrad verifikation som saknar underlag säger av vad", () => {
    const a69 = v({
      id: "a69",
      number: 69,
      missing_attachment: true,
      age_days: 80,
      missing_statement_accounts: ["1630"],
      corrected_by: andring.correction,
      correction: andring,
    });
    const vy = verifikationerVy(AR, lista(), lista(), { beslut: [], forslag: [], saknar: lista(a69) });
    expect(vy.sektioner.find((s) => s.titel === "Saknar underlag")?.rader[0].meta).toBe(
      "A-69 · kontoutdrag 1630 saknas sedan 80 dgr · ändrad av B-3"
    );
  });
});

describe("detaljen", () => {
  it("en ändrad verifikation visar konteringen efter rättelsen, borttaget överstruket, med när och vem", () => {
    const vy = verifikationVy(
      detalj({
        id: "a69",
        number: 69,
        corrected_by: andring.correction,
        correction: andring,
      }),
    );
    expect(vy.sektioner.map((s) => s.titel).slice(0, 2)).toEqual(["Kontering efter B-3", "Som postad"]);
    const [moms, skatt, skuld] = vy.sektioner[0].rader;
    expect(moms).toMatchObject({
      titel: "Momsfordran",
      meta: "1650 · borttagen B-3 2026-09-02 · stefan",
      struken: true,
    });
    expect(skatt).toMatchObject({ meta: "1630", hoger: formatBeloppHela(-26974500) });
    expect(skuld).toMatchObject({
      titel: "Momsskuld",
      meta: "2650 · ny B-3 2026-09-02 · stefan",
      hoger: formatBeloppHela(26974500),
    });
    expect(vy.banner?.text).toContain("Ändrad med B-3 2026-09-02 av stefan — Bokförd i fel månad.");
  });

  it("en makulerad verifikation saknar inget underlag och heter makulerad", () => {
    const vy = verifikationVy(detalj({ corrected_by: B1, correction: makulering }));
    expect(vy.status).toBe("makulerad · låst");
    expect(vy.sektioner[0].titel).toBe("Makulerad med B-1");
    expect(rad(vy, "underlag")?.meta).toBe("makulerad med B-1");
  });

  it("rättelsen visar först vad den ändrar, sedan sina rader som bokförda", () => {
    const vy = verifikationVy(
      detalj({
        id: "b3",
        series: "B",
        number: 3,
        corrects: andring.original,
        correction: andring,
      }),
    );
    expect(vy.sektioner.map((s) => s.titel).slice(0, 2)).toEqual(["Ändrar A-69", "Konteringar som bokförda"]);
  });
});
