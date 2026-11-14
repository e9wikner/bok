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
 * Hårdkodad kopia av serverns vy-nycklar, i dess ordning. Den finns för att
 * kartan ska jämföras mot servern och inte mot sig själv — servern svarar 404
 * på allt utanför den här listan.
 */
const SERVERNS_VIEW_KEYS = [
  "bocker.balans",
  "bocker.resultat",
  "bocker.verifikationer",
  "betala.fakturering",
  "betala.loner",
  "bokslut.rapporter",
  "bokslut.atgarder",
];

describe("kartan (testfall 1)", () => {
  it("har fyra sidor: arbetet i den ordning det görs, och sist inställningarna", () => {
    expect(SIDOR.map((s) => s.key)).toEqual(["bocker", "betala", "bokslut", "installningar"]);
  });

  it("fördelar vyerna 4 / 2 / 5 / 7: register och regler står under Inställningar, inte bland arbetet", () => {
    expect(SIDOR.map((s) => s.vyer.length)).toEqual([4, 2, 5, 7]);
  });

  it("bär sidtitlarna", () => {
    expect(SIDOR.map((s) => s.titel)).toEqual(["Bokföring", "Fakturor och löner", "Bokslut", "Inställningar"]);
  });

  it("ingen titel står två gånger i menyn", () => {
    const titlar = allaVyer().map((v) => v.titel);
    expect(new Set(titlar).size).toBe(titlar.length);
  });

  it("en inställningsvy äger ingen tråd: den lånar arbetets", () => {
    for (const vy of allaVyer().filter((v) => v.sida === "installningar")) {
      expect(vy.key).not.toBe(vy.trad);
    }
  });
});

describe("view_key mot serverns lista (testfall 2)", () => {
  it("chattar bara i de sju nycklarna servern validerar mot", () => {
    expect(Array.from(new Set(allaVyer().map((v) => v.trad))).sort()).toEqual([...SERVERNS_VIEW_KEYS].sort());
  });

  it("varje tråd ägs av exakt en vy, den med trådens nyckel", () => {
    expect(allaVyer().filter((v) => v.key === v.trad).map((v) => v.key).sort()).toEqual([...SERVERNS_VIEW_KEYS].sort());
  });

  it("ger varje vy en egen nyckel", () => {
    const nycklar = allaVyer().map((v) => v.key);
    expect(new Set(nycklar).size).toBe(nycklar.length);
  });

  it("härleder view_key ur kartan, inte ur en hopklistrad sträng", () => {
    expect(viewKeyOf("bocker", 0)).toBe("bocker.verifikationer");
    expect(viewKeyOf("bocker", 1)).toBe("bocker.verifikationer");
    expect(viewKeyOf("betala", 1)).toBe("betala.loner");
    expect(viewKeyOf("installningar", 2)).toBe("betala.loner");
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
    expect(forstaVyn("bocker").key).toBe("bocker.verifikationer");
    expect(forstaVyn("betala").key).toBe("betala.fakturering");
    expect(forstaVyn("bokslut").key).toBe("bokslut.rapporter");
    expect(forstaVyn("installningar").key).toBe("installningar.foretaget");
  });

  it("kommer ihåg ingenting — två anrop efter ett vybyte ger samma svar", () => {
    const forst = forstaVyn("bocker");
    // Ett "besök" på tredje vyn får inte påverka nästa sidbyte.
    expect(vyAt("bocker", 2)?.key).toBe("bocker.balans");
    expect(forstaVyn("bocker")).toBe(forst);
  });
});

describe("uppslag och validering", () => {
  it("känner igen en sidnyckel och avvisar allt annat", () => {
    expect(arSidnyckel("bocker")).toBe(true);
    expect(arSidnyckel("bokslut")).toBe(true);
    expect(arSidnyckel("installningar")).toBe(true);
    expect(arSidnyckel("register")).toBe(false);
    expect(arSidnyckel(null)).toBe(false);
  });

  it("slår upp en vy på slug och ger undefined för okänd", () => {
    expect(vyMedSlug("bocker", "resultat")?.key).toBe("bocker.resultat");
    expect(vyMedSlug("bocker", "loner")).toBeUndefined();
    expect(vyMedSlug("bocker", undefined)).toBeUndefined();
  });

  it("ger vyns index inom sidan", () => {
    expect(vyIndex("bocker", "bocker.verifikationer")).toBe(0);
    expect(vyIndex("betala", "bocker.balans")).toBe(-1);
  });
});
