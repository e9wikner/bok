import { describe, expect, it } from "vitest";
import { formatVerifikationsnummer } from "@/lib/utils";

// SPEC-flode-verifikationer.md §4.3 och §14.1 testfall 13 (klientdelen):
// ett utkast har inget nummer, och klienten visar `Utkast` i stället.
describe("formatVerifikationsnummer (testfall 13)", () => {
  it("visar serie och nummer för en postad verifikation", () => {
    expect(formatVerifikationsnummer(12, "A")).toBe("A12");
    expect(formatVerifikationsnummer(12, "A", "-")).toBe("A-12");
    expect(formatVerifikationsnummer(12)).toBe("12");
  });

  it("visar Utkast för ett utkast utan nummer", () => {
    for (const nummer of [null, undefined]) {
      const s = formatVerifikationsnummer(nummer, "A", "-");
      expect(s).toBe("Utkast");
      expect(s).not.toMatch(/null|undefined|NaN|000000/);
    }
    expect(formatVerifikationsnummer(null)).toBe("Utkast");
  });
});
