import { describe, expect, it } from "vitest";
import {
  SIDOR,
  allaVyer,
  arSidnyckel,
  forstaVyn,
  vyAt,
  vyIndex,
  vyMedSlug,
  viewKeyOf,
} from "@/lib/skal/vyer";

/**
 * Hårdkodad kopia av SPEC-tradar.md §5, i specens ordning. Den finns för att
 * kartan ska jämföras mot specen och inte mot sig själv — servern svarar 404
 * på allt utanför den här listan.
 */
const VIEW_KEYS_I_SPEC_TRADAR = [
  "bocker.balans",
  "bocker.resultat",
  "bocker.verifikationer",
  "betala.fakturering",
  "betala.loner",
  "bokslut.rapporter",
  "bokslut.atgarder",
];

describe("kartan (testfall 1)", () => {
  it("har exakt tre sidor i designens ordning", () => {
    expect(SIDOR.map((s) => s.key)).toEqual(["bocker", "betala", "bokslut"]);
  });

  it("har exakt sju vyer", () => {
    expect(allaVyer()).toHaveLength(7);
  });

  it("fördelar vyerna 3 / 2 / 2 som informationsarkitekturen säger", () => {
    expect(SIDOR.map((s) => s.vyer.length)).toEqual([3, 2, 2]);
  });

  it("bär designens sidtitlar ordagrant", () => {
    expect(SIDOR.map((s) => s.titel)).toEqual(["Böcker", "Fakturering och löner", "Bokslut"]);
  });
});

describe("view_key mot SPEC-tradar.md §5 (testfall 2)", () => {
  it("ger exakt de sju nycklarna servern validerar mot, i samma ordning", () => {
    expect(allaVyer().map((v) => v.key)).toEqual(VIEW_KEYS_I_SPEC_TRADAR);
  });

  it("härleder view_key ur kartan, inte ur en hopklistrad sträng", () => {
    expect(viewKeyOf("bocker", 2)).toBe("bocker.verifikationer");
    expect(viewKeyOf("betala", 1)).toBe("betala.loner");
    expect(viewKeyOf("bokslut", 5)).toBeUndefined();
  });

  it("har en nyckel som börjar med sin egen sidnyckel", () => {
    for (const vy of allaVyer()) {
      expect(vy.key.startsWith(`${vy.sida}.`)).toBe(true);
    }
  });
});

describe("sidbyte landar på första vyn (testfall 3)", () => {
  it("ger sidans första vy, aldrig den senast besökta", () => {
    expect(forstaVyn("bocker").key).toBe("bocker.balans");
    expect(forstaVyn("betala").key).toBe("betala.fakturering");
    expect(forstaVyn("bokslut").key).toBe("bokslut.rapporter");
  });

  it("kommer ihåg ingenting — två anrop efter ett vybyte ger samma svar", () => {
    const forst = forstaVyn("bocker");
    // Ett "besök" på tredje vyn får inte påverka nästa sidbyte.
    expect(vyAt("bocker", 2)?.key).toBe("bocker.verifikationer");
    expect(forstaVyn("bocker")).toBe(forst);
  });
});

describe("uppslag och validering", () => {
  it("känner igen en sidnyckel och avvisar allt annat", () => {
    expect(arSidnyckel("bocker")).toBe(true);
    expect(arSidnyckel("bokslut")).toBe(true);
    expect(arSidnyckel("installningar")).toBe(false);
    expect(arSidnyckel(null)).toBe(false);
  });

  it("slår upp en vy på slug och ger undefined för okänd", () => {
    expect(vyMedSlug("bocker", "resultat")?.key).toBe("bocker.resultat");
    expect(vyMedSlug("bocker", "loner")).toBeUndefined();
    expect(vyMedSlug("bocker", undefined)).toBeUndefined();
  });

  it("ger vyns index inom sidan", () => {
    expect(vyIndex("bocker", "bocker.verifikationer")).toBe(2);
    expect(vyIndex("betala", "bocker.balans")).toBe(-1);
  });
});

describe("läsvyerna är märkta i kartan (testfall 17, halva)", () => {
  it("Fakturering och Löner är läsvyer, de andra fem är det inte", () => {
    const lasvyer = allaVyer().filter((v) => v.lasvy).map((v) => v.key);
    expect(lasvyer).toEqual(["betala.fakturering", "betala.loner"]);
  });
});
