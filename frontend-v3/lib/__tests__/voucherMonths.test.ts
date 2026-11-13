import { groupByMonth, formatMonthLabel } from "../voucherMonths";

const v = (date: string) => ({ date });

describe("groupByMonth", () => {
  it("grupperar per månad, nyast först", () => {
    const g = groupByMonth([v("2026-01-05"), v("2026-03-01"), v("2026-01-20")]);
    expect(g.map((x) => [x.key, x.vouchers.length])).toEqual([
      ["2026-03", 1],
      ["2026-01", 2],
    ]);
  });

  it("tar med tomma månader inom räkenskapsåret", () => {
    const g = groupByMonth([v("2026-02-10")], { start: "2026-01-01", end: "2026-03-31" });
    expect(g.map((x) => [x.key, x.vouchers.length])).toEqual([
      ["2026-03", 0],
      ["2026-02", 1],
      ["2026-01", 0],
    ]);
  });

  it("klarar brutet räkenskapsår över årsskifte", () => {
    const g = groupByMonth([], { start: "2025-11-01", end: "2026-02-28" });
    expect(g.map((x) => x.key)).toEqual(["2026-02", "2026-01", "2025-12", "2025-11"]);
  });
});

describe("formatMonthLabel", () => {
  it("skriver månad på svenska", () => {
    expect(formatMonthLabel("2026-03")).toBe("mars 2026");
  });
});
