import { describe, expect, it } from "vitest";
import { formatBelopp, formatBeloppHela, MINUSTECKEN } from "@/lib/skal/format";
import { formatCurrency } from "@/lib/utils";

describe("formatBelopp (testfall 6)", () => {
  it("använder mellanslag som tusentalsavgränsare, inte punkt eller komma", () => {
    const s = formatBelopp(40072000);
    expect(s).toContain("400");
    expect(s).toContain("720");
    expect(s).not.toContain("400.720");
    expect(s).not.toContain("400,720");
    // Avgränsaren är ett mellanslagstecken (Intl sv-SE ger NBSP).
    expect(/400[\s  ]720/.test(s)).toBe(true);
  });

  it("använder − (U+2212) som minustecken, aldrig bindestreck", () => {
    const s = formatBelopp(-40072000);
    expect(s.startsWith(MINUSTECKEN)).toBe(true);
    expect(MINUSTECKEN).toBe("−");
    expect(s.startsWith("-")).toBe(false);
  });

  it("bär inget valutasuffix — vyraderna visar bara talet", () => {
    expect(formatBelopp(40072000)).not.toMatch(/kr|SEK/);
  });

  it("formatBeloppHela ger hela kronor utan decimaler", () => {
    expect(formatBeloppHela(40072000)).not.toContain(",");
  });
});

describe("formatCurrency är oförändrad (testfall 7)", () => {
  it("ger fortfarande belopp med valuta, som de 24 gamla sidorna förväntar sig", () => {
    const s = formatCurrency(40072000);
    expect(s).toMatch(/kr/);
    expect(s).toContain(",00");
  });

  it("är en annan funktion än skalets — de får inte glida ihop", () => {
    expect(formatCurrency(40072000)).not.toBe(formatBelopp(40072000));
  });
});
