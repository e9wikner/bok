import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

const ROT = path.resolve(__dirname, "../../..");

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  useSearchParams: () => new URLSearchParams(),
}));

afterEach(() => {
  delete process.env.NEXT_PUBLIC_SKAL;
});

describe("/v4 finns inte utan flaggan (testfall 5)", () => {
  it("svarar notFound() när NEXT_PUBLIC_SKAL saknas", async () => {
    delete process.env.NEXT_PUBLIC_SKAL;
    const { default: V4Page } = await import("@/app/v4/page");
    expect(() => V4Page()).toThrow("NEXT_NOT_FOUND");
  });

  it("renderar skalet när flaggan är satt", async () => {
    process.env.NEXT_PUBLIC_SKAL = "1";
    const { default: V4Page } = await import("@/app/v4/page");
    expect(() => V4Page()).not.toThrow();
  });
});

/**
 * Testfall 18. Modulen `skal` lovar att de 24 gamla sidorna inte märker att
 * den har funnits (SPEC-skal.md §3). Två vakter, för att en av dem alltid
 * ska kunna köras: en statisk som håller i CI utan git-historik, och en
 * git-baserad som är exakt när `main` finns.
 */
describe("skalet håller sig innanför sin gräns (testfall 18)", () => {
  function filerUnder(dir: string): string[] {
    const ut: string[] = [];
    for (const namn of readdirSync(dir)) {
      const full = path.join(dir, namn);
      if (statSync(full).isDirectory()) {
        if (namn === "node_modules" || namn === ".next") continue;
        ut.push(...filerUnder(full));
      } else if (/\.(tsx?|css)$/.test(namn)) {
        ut.push(full);
      }
    }
    return ut;
  }

  it("ingen sida utanför app/v4 känner till skalet", () => {
    const traffar = filerUnder(path.join(ROT, "app"))
      .filter((f) => !f.includes(`${path.sep}v4${path.sep}`))
      .filter((f) => /from "@\/(components|lib|hooks)\/skal/.test(readFileSync(f, "utf8")))
      .map((f) => path.relative(ROT, f));
    expect(traffar).toEqual([]);
  });

  it("AppShellClient är den enda komponenten utanför skalet som rör det", () => {
    // `chattyta` är skalets egen tråd (SPEC-chattyta.md §1: beror på `skal`),
    // inte en av de 24 gamla sidorna som vakten skyddar.
    const traffar = filerUnder(path.join(ROT, "components"))
      .filter((f) => !f.includes(`${path.sep}skal${path.sep}`))
      .filter((f) => !f.includes(`${path.sep}chattyta${path.sep}`))
      .filter((f) => /@\/(components|lib|hooks)\/skal/.test(readFileSync(f, "utf8")))
      .map((f) => path.basename(f));
    expect(traffar).toEqual(["AppShellClient.tsx"]);
  });

  it("rör bara app/v4, app/globals.css och app/layout.tsx jämfört med main", () => {
    let andrade: string[];
    try {
      execFileSync("git", ["rev-parse", "--verify", "main"], { cwd: ROT, stdio: "ignore" });
      andrade = execFileSync("git", ["diff", "--name-only", "main", "--", "app"], {
        cwd: ROT,
        encoding: "utf8",
      })
        .split("\n")
        .filter(Boolean);
    } catch {
      // Grunt klonad CI-checkout utan main: den statiska vakten ovan gäller.
      return;
    }
    const tillatet = (f: string) =>
      f.includes("frontend-v3/app/v4/") ||
      f.endsWith("frontend-v3/app/globals.css") ||
      f.endsWith("frontend-v3/app/layout.tsx");
    expect(andrade.filter((f) => !tillatet(f))).toEqual([]);
  });
});
