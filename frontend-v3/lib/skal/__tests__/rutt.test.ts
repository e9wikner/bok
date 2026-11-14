import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));
import { lasPosition, positionsUrl } from "@/lib/skal/rutt";

describe("fallback i URL:en (testfall 4)", () => {
  it("okänd sida faller tillbaka på bocker och dess första vy", () => {
    expect(lasPosition("register", "moms")).toMatchObject({
      sida: "bocker",
      vy: { key: "bocker.verifikationer" },
    });
  });

  it("okänd vy inom en känd sida faller tillbaka på sidans första vy", () => {
    expect(lasPosition("betala", "balans").vy.key).toBe("betala.fakturering");
  });

  it("utan parametrar landar man på bocker.verifikationer", () => {
    expect(lasPosition(null, null).vy.key).toBe("bocker.verifikationer");
    expect(lasPosition(undefined, undefined).sida).toBe("bocker");
  });

  it("kända parametrar respekteras", () => {
    expect(lasPosition("bokslut", "atgarder").vy.key).toBe("bokslut.atgarder");
    expect(lasPosition("installningar", "kontoplan").vy.key).toBe("installningar.kontoplan");
  });

  it("en adress till en vy som flyttat eller gått upp i en annan landar på sidans första vy", () => {
    expect(lasPosition("bocker", "kontoplan").vy.key).toBe("bocker.verifikationer");
    expect(lasPosition("bokslut", "uppgifter").vy.key).toBe("bokslut.rapporter");
  });

  it("bygger en URL som läses tillbaka till samma position", () => {
    const p = lasPosition("betala", "loner");
    expect(positionsUrl(p.sida, p.vy)).toBe("/?sida=betala&vy=loner");
    expect(lasPosition("betala", "loner").vy.key).toBe(p.vy.key);
  });
});

describe("den gamla adressen", () => {
  it("/v4 skickar vidare till / med samma sida, vy och lager", async () => {
    const { default: V4 } = await import("@/app/v4/page");
    await expect(V4({ searchParams: Promise.resolve({ sida: "bocker", vy: "balans", ver: "a b" }) })).rejects.toThrow(
      "NEXT_REDIRECT:/?sida=bocker&vy=balans&ver=a+b"
    );
    await expect(V4({ searchParams: Promise.resolve({}) })).rejects.toThrow("NEXT_REDIRECT:/");
  });
});
