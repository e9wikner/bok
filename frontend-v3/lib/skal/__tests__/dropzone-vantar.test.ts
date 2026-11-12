import { describe, expect, it } from "vitest";
import { vantarText } from "@/lib/skal/dropzone";

/** Vad dropzonen säger om en väntande fil. */

const NU = Date.parse("2026-11-08T12:00:00Z");
const tider = { quiet_seconds: 30, scan_interval_seconds: 60 };
const fil = (sekunderSedan: number) => ({
  folder: "Övrigt",
  filename: "avtal.pdf",
  size_bytes: 1000,
  modified_at: new Date(NU - sekunderSedan * 1000).toISOString(),
});

describe("vantarText", () => {
  it("säger hur länge filen legat och när den läses in", () => {
    expect(vantarText(fil(20), tider, NU)).toEqual({
      text: "lagd för 20 s sedan · läses in inom ~1 min",
      sen: false,
    });
  });

  it("lovar nästa varv när väntetiden passerat", () => {
    expect(vantarText(fil(120), tider, NU).text).toBe("lagd för 2 min sedan · läses in vid nästa varv");
  });

  it("säger till när filen väntat längre än skannern borde", () => {
    expect(vantarText(fil(3 * 3600), tider, NU)).toEqual({
      text: "har väntat 3 h, längre än väntat",
      sen: true,
    });
  });
});

describe("ett fel i skannern", () => {
  it("visar felet i stället för en väntetid", () => {
    expect(vantarText({ ...fil(20), error: "OSError: Read-only file system" }, tider, NU)).toEqual({
      text: "kunde inte läsas in, prövas igen · OSError: Read-only file system",
      sen: true,
    });
  });
});
