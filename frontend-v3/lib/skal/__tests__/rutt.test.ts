import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));
import { lasPosition, positionsUrl } from "@/lib/skal/rutt";

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
