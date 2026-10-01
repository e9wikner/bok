import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { NY_MARKERING_MS } from "@/components/skal/VyRad";
import { VOUCHERS_NYCKEL } from "@/lib/chattyta/api";
import {
  KOPPLINGAR_NYCKEL,
  NY_KOPPLING_MS,
  kopplingBorttagen,
  kopplingKlar,
  lasFrankoppling,
  lasKoppling,
  type Koppling,
} from "@/lib/chattyta/kopplingar";

/** FU21: `Nyss kopplad` ur `view.changed` med `kind: "source_linked"` (§10.4). */

let qc: QueryClient;
beforeEach(() => {
  qc = new QueryClient();
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

const kopplingar = () => qc.getQueryData<Koppling[]>(KOPPLINGAR_NYCKEL) ?? [];

const a118 = {
  id: "a118",
  series: "A",
  number: 118,
  date: "2026-06-03",
  description: "Förbrukningsinventarier",
  status: "posted",
  total_debit: 448000,
  missing_attachment: true,
  age_days: 3,
};

describe("lasKoppling", () => {
  it("läser voucher_id och source_id under `changed`, som servern skickar view.changed", () => {
    expect(
      lasKoppling({
        view_key: "bocker.verifikationer",
        changed: { voucher_id: "a118", source_id: "src-1", kind: "source_linked" },
      })
    ).toEqual({ voucherId: "a118", sourceId: "src-1" });
    expect(
      lasKoppling({ view_key: "x", changed: { voucher_id: "a118", kind: "voucher_posted" } })
    ).toBeNull();
  });

  it("läser voucher_id och source_id ur en koppling i roten", () => {
    expect(lasKoppling({ voucher_id: "a118", source_id: "src-1", kind: "source_linked" })).toEqual({
      voucherId: "a118",
      sourceId: "src-1",
    });
  });

  it("andra slag och trasiga kroppar är ingen koppling", () => {
    expect(lasKoppling({ voucher_id: "a118", kind: "voucher_posted" })).toBeNull();
    expect(lasKoppling({ kind: "source_linked" })).toBeNull();
    expect(lasKoppling(null)).toBeNull();
    expect(lasKoppling("source_linked")).toBeNull();
  });
});

describe("frånkoppling (underlag-ersatt)", () => {
  it("lasFrankoppling läser source_unlinked och inget annat", () => {
    expect(
      lasFrankoppling({
        view_key: "bocker.verifikationer",
        changed: { voucher_id: "a118", source_id: "src-1", kind: "source_unlinked" },
      })
    ).toEqual({ voucherId: "a118" });
    expect(lasFrankoppling({ changed: { voucher_id: "a118", kind: "source_linked" } })).toBeNull();
    expect(lasFrankoppling({ kind: "source_unlinked" })).toBeNull();
    expect(lasKoppling({ voucher_id: "a118", kind: "source_unlinked" })).toBeNull();
  });

  it("kopplingBorttagen tar klientens post om kopplingen", () => {
    kopplingKlar(qc, "a118", "src-1");
    kopplingKlar(qc, "a119", "src-2");
    kopplingBorttagen(qc, "a118");
    expect(kopplingar().map((k) => k.voucherId)).toEqual(["a119"]);
    kopplingBorttagen(qc, "saknas");
    expect(kopplingar()).toHaveLength(1);
  });
});

describe("kopplingKlar", () => {
  it("står under en egen nyckel, utanför vouchers (avvikelse 7)", () => {
    expect(KOPPLINGAR_NYCKEL[0]).not.toBe(VOUCHERS_NYCKEL[0]);
  });

  it("markeringen varar lika länge som VyRads ny", () => {
    expect(NY_KOPPLING_MS).toBe(NY_MARKERING_MS);
  });

  it("tar klockslaget och en ögonblicksbild av verifikationen ur vyns frågor", () => {
    qc.setQueryData([...VOUCHERS_NYCKEL, "skal", "fy", "saknar"], { total: 1, vouchers: [a118] });
    kopplingKlar(qc, "a118", "src-1", new Date(2026, 5, 3, 8, 5));
    const [k] = kopplingar();
    expect(k).toMatchObject({ voucherId: "a118", sourceId: "src-1", klockslag: "08:05", ny: true });
    expect(k.verifikation).toMatchObject({ id: "a118", number: 118, description: "Förbrukningsinventarier" });
  });

  it("överlever en invalidering av vouchers", async () => {
    kopplingKlar(qc, "a118", "src-1");
    await qc.invalidateQueries({ queryKey: VOUCHERS_NYCKEL });
    expect(kopplingar()).toHaveLength(1);
  });

  it("är ny i NY_KOPPLING_MS, sedan står den kvar som kopplad", () => {
    kopplingKlar(qc, "a118", "src-1");
    vi.advanceTimersByTime(NY_KOPPLING_MS - 1);
    expect(kopplingar()[0].ny).toBe(true);
    vi.advanceTimersByTime(1);
    expect(kopplingar()).toHaveLength(1);
    expect(kopplingar()[0].ny).toBe(false);
  });

  it("samma verifikation två gånger är en post, och den nya äger markeringen", () => {
    kopplingKlar(qc, "a118", "src-1", new Date(2026, 5, 3, 8, 0));
    vi.advanceTimersByTime(NY_KOPPLING_MS - 1000);
    kopplingKlar(qc, "a118", "src-1", new Date(2026, 5, 3, 8, 1));
    vi.advanceTimersByTime(1000);
    expect(kopplingar()).toHaveLength(1);
    expect(kopplingar()[0]).toMatchObject({ ny: true, klockslag: "08:01" });
  });
});
