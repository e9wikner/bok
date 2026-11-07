import { describe, expect, it } from "vitest";
import { type Verifikation, VERIFIKATIONER_ANTAL, nastaSida, slaSamman } from "@/lib/skal/bocker";

/** L5 (SPEC-lasbarhet.md §4.5): Postades sidor och hur de läggs ihop. */

const v = (id: string): Verifikation => ({
  id,
  series: "A",
  number: 1,
  date: "2026-05-01",
  description: id,
  status: "posted",
  total_debit: 100,
});

describe("slaSamman", () => {
  it("lägger sidorna efter varandra, varje id en gång, och tar den senaste sidans total", () => {
    const lista = slaSamman([
      { total: 4, vouchers: [v("a"), v("b")] },
      { total: 5, vouchers: [v("b"), v("c")] },
    ]);
    expect(lista.vouchers.map((x) => x.id)).toEqual(["a", "b", "c"]);
    expect(lista.total).toBe(5);
  });

  it("inga sidor är en tom lista", () => {
    expect(slaSamman([])).toEqual({ total: 0, vouchers: [] });
  });
});

describe("nastaSida", () => {
  it("nästa offset är den förra plus sidans rader, så länge total inte är nådd", () => {
    const full = { total: 120, vouchers: Array.from({ length: VERIFIKATIONER_ANTAL }, (_, i) => v(`${i}`)) };
    expect(nastaSida(full, 0)).toBe(50);
    expect(nastaSida(full, 50)).toBe(100);
    expect(nastaSida({ total: 120, vouchers: full.vouchers.slice(0, 20) }, 100)).toBeUndefined();
  });

  it("en tom sida avslutar, också om total säger annat", () => {
    expect(nastaSida({ total: 120, vouchers: [] }, 100)).toBeUndefined();
  });
});
