import { describe, expect, it } from "vitest";
import { matcha, matchaRad, ordI, sokVy } from "@/lib/skal/sok";
import type { VyData, VyRadData } from "@/lib/skal/vydata";

describe("matcha", () => {
  it("träffar en delsekvens, skiftlägesokänsligt, och ger positionerna", () => {
    expect(matcha("a12", "A-12")?.index).toEqual([0, 2, 3]);
    expect(matcha("tel", "Telia")?.index).toEqual([0, 1, 2]);
    expect(matcha("1234", "1 234")?.index).toEqual([0, 2, 3, 4]);
  });

  it("å, ä och ö är egna tecken", () => {
    expect(matcha("lön", "Löner mars")).not.toBeNull();
    expect(matcha("lon", "Löner mars")).toBeNull();
  });

  it("ingen träff när tecknen saknas eller står i fel ordning", () => {
    expect(matcha("xyz", "Telia")).toBeNull();
    expect(matcha("ailet", "Telia")).toBeNull();
    expect(matcha("", "Telia")).toBeNull();
    expect(matcha("lång fråga", "kort")).toBeNull();
  });

  it("tecken i följd väger tyngre än utspridda", () => {
    const iFoljd = matcha("hyr", "Hyra kontor")!;
    const utspridd = matcha("hyr", "Hotell Yxlan Resa")!;
    expect(iFoljd.poang).toBeGreaterThan(utspridd.poang);
  });

  it("ett ords början väger tyngre än mitt i ett ord", () => {
    const ordstart = matcha("k", "Hyra kontor")!;
    const inne = matcha("k", "Bokföring")!;
    expect(ordstart.poang).toBeGreaterThan(inne.poang);
    // Den bästa placeringen väljs, inte den första.
    expect(matcha("ko", "Bokföring kontor")!.index).toEqual([10, 11]);
  });
});

const rad = (id: string, titel: string, meta: string, hoger: string): VyRadData => ({ id, titel, meta, hoger });

describe("matchaRad", () => {
  it("varje ord söks i titel, meta och belopp; alla ord måste träffa", () => {
    const r = rad("a", "Telia mobil", "A-12 · 2026-03-04", "499");
    const t = matchaRad(ordI("telia a12"), r)!;
    expect(t.traff).toEqual({ titel: [0, 1, 2, 3, 4], meta: [0, 2, 3] });
    expect(matchaRad(ordI("telia xyz"), r)).toBeNull();
    expect(matchaRad(ordI("499"), r)!.traff).toEqual({ hoger: [0, 1, 2] });
  });
});

describe("sokVy", () => {
  const VY: VyData = {
    lage: "vantar",
    status: "1 väntar på dig",
    period: "2026-01-01 – 2026-12-31",
    banner: { ton: "varning", text: "något" },
    sektioner: [
      { titel: "Väntar på beslut", rader: [rad("b", "Kvitto Telia", "väntar på dig", "")] },
      { titel: "Mars", rader: [rad("a", "Hotell Yxlan Resa", "A-2 · 2026-03-02", "900"), rad("c", "Hyra", "A-3 · 2026-03-01", "8 000")] },
      { titel: "Februari", rader: [], tom: "inga postade verifikationer" },
      { titel: "Januari", rader: [rad("c", "Hyra", "A-3 · 2026-03-01", "8 000")] },
    ],
    fot: "Foten",
    harFler: true,
    hamtaFler: () => undefined,
  };

  it("tom fråga lämnar vyn orörd", () => {
    expect(sokVy(VY, "  ")).toBe(VY);
  });

  it("viker ihop sektionerna till en rankad lista, en rad en gång", () => {
    const v = sokVy(VY, "hyr");
    expect(v.sektioner).toHaveLength(1);
    expect(v.sektioner[0].titel).toBe("Träffar");
    expect(v.sektioner[0].rader.map((r) => r.id)).toEqual(["c", "a"]);
    expect(v.sektioner[0].rader[0].traff).toEqual({ titel: [0, 1, 2] });
    expect(v.status).toBe("2 träffar");
    expect(v.lage).toBe("normal");
    expect(v.banner).toBeUndefined();
    expect(v.harFler).toBeUndefined();
    expect(v.hamtaFler).toBeUndefined();
    expect(v.period).toBe(VY.period);
    expect(v.fot).toBe(VY.fot);
  });

  it("lika poäng behåller vyns ordning", () => {
    expect(sokVy(VY, "2026").sektioner[0].rader.map((r) => r.id)).toEqual(["a", "c"]);
  });

  it("inga träffar: en sektion som säger det", () => {
    const v = sokVy(VY, "qqq");
    expect(v.status).toBe("inga träffar");
    expect(v.lage).toBe("tomt");
    expect(v.sektioner).toEqual([{ titel: "Träffar", rader: [], tom: "inga träffar" }]);
    expect(sokVy(VY, "telia").status).toBe("1 träff");
  });
});
