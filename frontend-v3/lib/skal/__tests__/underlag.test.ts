import { describe, expect, it } from "vitest";
import type { BeslutSvar } from "@/lib/chattyta/api";
import { formatBeloppHela } from "@/lib/skal/format";
import type { Koppling } from "@/lib/chattyta/kopplingar";
import {
  FOT_UNDERLAG,
  verifikationerVy,
  type Verifikation,
  type Verifikationslista,
} from "@/lib/skal/bocker";
import type { VyData, VyRadData } from "@/lib/skal/vydata";

/**
 * FU21 — sektionen `Saknar underlag`, `Nyss kopplad` och foten
 * (SPEC-flode-underlag.md §10.4; testfall 49b och 49c).
 */

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

const v = (over: Partial<Verifikation>): Verifikation => ({
  id: "x",
  series: "A",
  number: 1,
  date: "2026-06-01",
  description: "Kontorsmaterial",
  status: "posted",
  total_debit: 100000,
  missing_attachment: false,
  age_days: 0,
  ...over,
});

const lista = (...vouchers: Verifikation[]): Verifikationslista => ({ total: vouchers.length, vouchers });
const TOM = lista();

const a118 = v({
  id: "a118",
  number: 118,
  date: "2026-06-03",
  description: "Förbrukningsinventarier",
  total_debit: 448000,
  missing_attachment: true,
  age_days: 3,
});
const a109 = v({
  id: "a109",
  number: 109,
  date: "2026-05-25",
  description: "Resa Göteborg",
  total_debit: 124000,
  missing_attachment: true,
  age_days: 12,
});
const a117 = v({ id: "a117", number: 117, date: "2026-05-31", description: "Ellevio · elnät maj", total_debit: 218000 });

const sektion = (vy: VyData, titel: string): VyRadData[] =>
  vy.sektioner.find((s) => s.titel === titel)?.rader ?? [];
const allaIds = (vy: VyData) => vy.sektioner.flatMap((s) => s.rader.map((r) => r.id));

const beslut = (over: Partial<BeslutSvar> = {}): BeslutSvar => ({
  id: "d-1",
  view_key: "bocker.verifikationer",
  kind: "abstention",
  status: "open",
  title: "Okänd leverantör",
  amount_ore: 50000,
  reason: "",
  consequence: "",
  source: null,
  age_days: 0,
  thread_id: "t",
  post_id: "p",
  options: [],
  ...over,
});

const koppling = (over: Partial<Koppling> = {}): Koppling => ({
  voucherId: "a118",
  sourceId: "src-1",
  klockslag: "08:20",
  ny: true,
  verifikation: null,
  ...over,
});

// ─── 49b ──────────────────────────────────────────────────────────────────

describe("sektionen Saknar underlag (testfall 49b)", () => {
  it("står efter Väntar på beslut och före Postade och Utkast", () => {
    const vy = verifikationerVy(AR, lista(a117), lista(v({ id: "u", status: "draft", number: null })), {
      beslut: [beslut()],
      forslag: [],
      saknar: lista(a109, a118),
    });
    expect(vy.sektioner.map((s) => s.titel)).toEqual([
      "Väntar på beslut",
      "Saknar underlag",
      "Postade",
      "Utkast",
    ]);
  });

  it("i serverns ordning (äldst först), med meta `kvitto saknas sedan {n} dgr` och variant saknar", () => {
    const vy = verifikationerVy(AR, lista(a117), TOM, { beslut: [], forslag: [], saknar: lista(a109, a118) });
    const rader = sektion(vy, "Saknar underlag");
    expect(rader.map((r) => r.id)).toEqual(["a109", "a118"]);
    expect(rader[0]).toMatchObject({
      titel: "Resa Göteborg",
      meta: "A-109 · kvitto saknas sedan 12 dgr",
      hoger: formatBeloppHela(124000),
      variant: "saknar",
      ageDays: 12,
    });
    expect(rader[1].meta).toBe("A-118 · kvitto saknas sedan 3 dgr");
  });

  it("n är serverns age_days, inte räknat ur datumet", () => {
    const vy = verifikationerVy(AR, TOM, TOM, {
      beslut: [],
      forslag: [],
      saknar: lista({ ...a118, age_days: 41 }),
    });
    expect(sektion(vy, "Saknar underlag")[0].meta).toBe("A-118 · kvitto saknas sedan 41 dgr");
  });

  it("är borta när den är tom — den står aldrig tom", () => {
    const vy = verifikationerVy(AR, lista(a117), TOM, { beslut: [], forslag: [], saknar: TOM });
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Postade"]);
  });

  it("en verifikation visas på ett ställe", () => {
    // Om listorna glider (en hämtning i taget) vinner Saknar underlag.
    const vy = verifikationerVy(AR, lista(a117, a118), TOM, {
      beslut: [],
      forslag: [],
      saknar: lista(a118),
    });
    expect(allaIds(vy).filter((id) => id === "a118")).toHaveLength(1);
    expect(sektion(vy, "Saknar underlag").map((r) => r.id)).toEqual(["a118"]);
  });

  it("statusen säger hur många som saknar underlag när inget väntar på beslut", () => {
    const vy = verifikationerVy(AR, lista(a117), TOM, { beslut: [], forslag: [], saknar: lista(a109, a118) });
    expect(vy.status).toBe("2 saknar underlag");
    expect(vy.lage).toBe("vantar");
  });

  it("foten är panelens", () => {
    const vy = verifikationerVy(AR, lista(a117), TOM, { beslut: [], forslag: [], saknar: lista(a118) });
    expect(vy.fot).toBe(FOT_UNDERLAG);
    expect(FOT_UNDERLAG).toBe(
      "Underlag kan släppas i chatten när som helst. Agenten kopplar det till rätt verifikation och säger till om något inte stämmer."
    );
  });
});

// ─── 49c ──────────────────────────────────────────────────────────────────

describe("en koppling via view.changed (testfall 49c)", () => {
  it("raden lämnar Saknar underlag och står överst i Postade som ny, med `kvitto kopplat HH:MM`", () => {
    // Före omhämtningen: listorna är fortfarande de gamla.
    const vy = verifikationerVy(AR, lista(a117), TOM, {
      beslut: [],
      forslag: [],
      saknar: lista(a109, a118),
      kopplingar: [koppling()],
    });
    expect(sektion(vy, "Saknar underlag").map((r) => r.id)).toEqual(["a109"]);
    const [forsta, andra] = sektion(vy, "Postade");
    expect(forsta).toMatchObject({
      id: "a118",
      titel: "Förbrukningsinventarier",
      meta: "A-118 · kvitto kopplat 08:20",
      hoger: formatBeloppHela(448000),
      variant: "ny",
    });
    expect(andra.id).toBe("a117");
    expect(allaIds(vy).filter((id) => id === "a118")).toHaveLength(1);
  });

  it("efter omhämtningen: samma rad, ur Postades lista, en gång", () => {
    const kopplad = { ...a118, missing_attachment: false };
    const vy = verifikationerVy(AR, lista(kopplad, a117), TOM, {
      beslut: [],
      forslag: [],
      saknar: lista(a109),
      kopplingar: [koppling()],
    });
    const rader = sektion(vy, "Postade");
    expect(rader.map((r) => r.id)).toEqual(["a118", "a117"]);
    expect(rader[0].variant).toBe("ny");
  });

  it("med hänvisning: ` · A-121 korrigering` ur referenced_by", () => {
    const kopplad = {
      ...a118,
      missing_attachment: false,
      referenced_by: { id: "a121", series: "A", number: 121 },
    };
    const vy = verifikationerVy(AR, lista(kopplad), TOM, {
      beslut: [],
      forslag: [],
      saknar: TOM,
      kopplingar: [koppling()],
    });
    expect(sektion(vy, "Postade")[0].meta).toBe("A-118 · kvitto kopplat 08:20 · A-121 korrigering");
  });

  it("en verifikation som ingen lista har ritas ur ögonblicksbilden", () => {
    const vy = verifikationerVy(AR, lista(a117), TOM, {
      beslut: [],
      forslag: [],
      saknar: TOM,
      kopplingar: [koppling({ verifikation: a118 })],
    });
    expect(sektion(vy, "Postade")[0]).toMatchObject({ id: "a118", variant: "ny", hoger: formatBeloppHela(448000) });
  });

  it("efter markeringen: vanlig rad på sin plats, `{datum} · kvitto kopplat`", () => {
    const kopplad = { ...a118, missing_attachment: false };
    const vy = verifikationerVy(AR, lista(a117, kopplad), TOM, {
      beslut: [],
      forslag: [],
      saknar: TOM,
      kopplingar: [koppling({ ny: false })],
    });
    const rader = sektion(vy, "Postade");
    expect(rader.map((r) => r.id)).toEqual(["a117", "a118"]);
    expect(rader[1].meta).toBe("A-118 · 2026-06-03 · kvitto kopplat");
    expect(rader[1].variant).toBeUndefined();
  });

  it("den sista kompletteringen: sektionen försvinner helt", () => {
    const vy = verifikationerVy(AR, lista(a117), TOM, {
      beslut: [],
      forslag: [],
      saknar: lista(a118),
      kopplingar: [koppling()],
    });
    expect(vy.sektioner.map((s) => s.titel)).toEqual(["Postade"]);
  });
});
