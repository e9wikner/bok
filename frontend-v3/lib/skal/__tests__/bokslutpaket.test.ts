import { describe, expect, it } from "vitest";
import {
  type Bokslut,
  attAtgarda,
  bokslutStatus,
  bokslutTitel,
  justeringsText,
  kronor,
  rapporterVy,
} from "@/lib/skal/bokslut";
import { lasDetalj, positionsUrl } from "@/lib/skal/rutt";
import { sidan } from "@/lib/skal/vyer";

const AR = {
  id: "fy-2025",
  start_date: "2025-01-01",
  end_date: "2025-12-31",
  locked: false,
  locked_at: null,
};

function bokslut(kontroller: Bokslut["kontroller"], locked = false): Bokslut {
  return {
    fiscal_year: { id: "fy-2025", start: "2025-01-01", end: "2025-12-31", locked },
    kontroller,
  } as unknown as Bokslut;
}

describe("bokslutet i Rapporter", () => {
  it("varje räkenskapsår leder till sitt bokslut", () => {
    const vy = rapporterVy({ fiscal_years: [AR] });
    expect(vy.sektioner[0].rader[0].mal).toEqual({ typ: "bokslut", arId: "fy-2025" });
    expect(vy.fot).toMatch(/bokslutet/);
  });

  it("bokslutet står i URL:en och läses tillbaka", () => {
    const vy = sidan("bokslut").vyer[0];
    const url = positionsUrl("bokslut", vy, { typ: "bokslut", arId: "fy-2025" });
    expect(url).toContain("&bokslut=fy-2025");
    expect(lasDetalj(null, null, "fy-2025")).toEqual({ typ: "bokslut", arId: "fy-2025" });
    expect(lasDetalj(null, null, " ")).toBeNull();
  });
});

describe("bokslutets status", () => {
  it("räknar fel och varningar, inte info", () => {
    const b = bokslut([
      { id: "a", niva: "varning", titel: "Moms", text: "" },
      { id: "b", niva: "info", titel: "Lås", text: "" },
      { id: "c", niva: "ok", titel: "Balans", text: "" },
    ]);
    expect(attAtgarda(b.kontroller).map((k) => k.id)).toEqual(["a"]);
    expect(bokslutStatus(b)).toEqual({ text: "1 att åtgärda", lage: "vantar" });
    expect(bokslutTitel(b)).toBe("Bokslut 2025");
  });

  it("ett fel ger felläge, inget kvar ger klart", () => {
    expect(bokslutStatus(bokslut([{ id: "x", niva: "fel", titel: "", text: "" }])).lage).toBe("fel");
    expect(bokslutStatus(bokslut([], true))).toEqual({ text: "klart · låst", lage: "klart" });
  });
});

// Intl skriver ett hårt mellanslag som tusentalsavgränsare.
const mellanslag = (s: string) => s.replace(/[\u00a0\u202f]/g, " ");

describe("belopp och justeringar", () => {
  it("hela kronor med mellanslag och minustecken", () => {
    expect(mellanslag(kronor(1139320))).toBe("1 139 320");
    expect(mellanslag(kronor(-711504))).toBe("−711 504");
    expect(kronor(null)).toBe("–");
  });

  it("ett angivet belopp säger vad som beräknades", () => {
    const j = { code: "7754", row: "4.5c", label: "", value: 122069, calculated: 120845, override: 122069, basis: "Skattefria konton: 8226, 8314", sources: [] };
    expect(mellanslag(justeringsText(j))).toBe("angivet för hand · beräknat 120 845");
    expect(justeringsText({ ...j, override: null, value: 120845 })).toBe("Skattefria konton: 8226, 8314");
  });
});
