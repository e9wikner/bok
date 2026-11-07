import { describe, expect, it } from "vitest";
import { lasPosition, positionsUrl, skalArPa } from "@/lib/skal/rutt";

describe("fallback i URL:en (testfall 4)", () => {
  it("okänd sida faller tillbaka på bocker och dess första vy", () => {
    expect(lasPosition("installningar", "moms")).toMatchObject({
      sida: "bocker",
      vy: { key: "bocker.balans" },
    });
  });

  it("okänd vy inom en känd sida faller tillbaka på sidans första vy", () => {
    expect(lasPosition("betala", "balans").vy.key).toBe("betala.fakturering");
  });

  it("utan parametrar landar man på bocker.balans", () => {
    expect(lasPosition(null, null).vy.key).toBe("bocker.balans");
    expect(lasPosition(undefined, undefined).sida).toBe("bocker");
  });

  it("kända parametrar respekteras", () => {
    expect(lasPosition("bokslut", "atgarder").vy.key).toBe("bokslut.atgarder");
  });

  it("bygger en URL som läses tillbaka till samma position", () => {
    const p = lasPosition("betala", "loner");
    expect(positionsUrl(p.sida, p.vy)).toBe("/v4?sida=betala&vy=loner");
    expect(lasPosition("betala", "loner").vy.key).toBe(p.vy.key);
  });
});

describe("flaggan (testfall 5)", () => {
  it("är av när variabeln saknas eller är något annat än 1/true", () => {
    expect(skalArPa(undefined)).toBe(false);
    expect(skalArPa("")).toBe(false);
    expect(skalArPa("0")).toBe(false);
    expect(skalArPa("ja")).toBe(false);
  });

  it("är på för 1 och true", () => {
    expect(skalArPa("1")).toBe(true);
    expect(skalArPa("true")).toBe(true);
  });
});
