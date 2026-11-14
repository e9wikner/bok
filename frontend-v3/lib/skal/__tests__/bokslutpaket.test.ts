import { describe, expect, it } from "vitest";
import {
  type Bokslut,
  attAtgarda,
  bokslutStatus,
  bokslutTitel,
  justeringsText,
  kronor,
} from "@/lib/skal/bokslut";
import { lasPosition } from "@/lib/skal/rutt";
import { arBokslutsdel, sidan, viewKeyOf } from "@/lib/skal/vyer";

function bokslut(kontroller: Bokslut["kontroller"], locked = false): Bokslut {
  return {
    fiscal_year: { id: "fy-2025", start: "2025-01-01", end: "2025-12-31", locked },
    kontroller,
  } as unknown as Bokslut;
}

describe("bokslutets delar i navigeringen", () => {
  it("står direkt under Bokslut, före Åtgärder", () => {
    expect(sidan("bokslut").vyer.map((v) => v.titel)).toEqual([
      "Översikt",
      "Moms",
      "INK2",
      "Årsredovisning",
      "Åtgärder och nyckeltal",
    ]);
  });

  it("delar Översiktens tråd; Åtgärder har sin egen", () => {
    const vyer = sidan("bokslut").vyer.slice(0, 4);
    expect(vyer.every((v) => v.trad === "bokslut.rapporter")).toBe(true);
    expect(vyer.every((v) => arBokslutsdel(v.key))).toBe(true);
    // SRU-kopplingen delar tråden men står under Inställningar, med sin egen komponent (`SruVy`).
    expect(arBokslutsdel("installningar.sru")).toBe(false);
    expect(arBokslutsdel("bokslut.atgarder")).toBe(false);
    expect(viewKeyOf("bokslut", 1)).toBe("bokslut.rapporter");
    expect(viewKeyOf("bokslut", 4)).toBe("bokslut.atgarder");
  });

  it("varje del nås med sin slug, och den gamla Rapporter-länken landar på Översikt", () => {
    expect(lasPosition("bokslut", "moms").vy.key).toBe("bokslut.moms");
    expect(lasPosition("bokslut", "rapporter").vy.key).toBe("bokslut.rapporter");
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
