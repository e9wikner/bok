"use client";

import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { DRAFTS_NYCKEL, OVERVIEW_NYCKEL } from "@/lib/chattyta/api";
import { arsnamn, type Rakenskapsar } from "@/lib/skal/bokslut";
import { lasApi, periodnamn, type LasData, type Period } from "@/lib/skal/las";

/**
 * Låsen i Rapporter (per räkenskapsår) och Verifikationer (per månad).
 *
 * Ett tryck växlar läget på servern och hämtar sedan om det låset påverkar:
 * åren och perioderna (`["skal", …]`), headerns "september öppen/låst" och
 * väntande förslag, som en låsning märker `period_locked` (F16). Ett fel
 * kastas vidare till knappen, som visar det.
 */
export function useLasning() {
  const qc = useQueryClient();

  const efter = useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["skal"] }),
      qc.invalidateQueries({ queryKey: OVERVIEW_NYCKEL }),
      qc.invalidateQueries({ queryKey: DRAFTS_NYCKEL }),
    ]);
  }, [qc]);

  const ar = useCallback(
    (a: Rakenskapsar): LasData => ({
      last: a.locked,
      vad: `räkenskapsår ${arsnamn(a)}`,
      vaxla: async () => {
        await lasApi.rakenskapsar(a.id, !a.locked);
        await efter();
      },
    }),
    [efter]
  );

  const period = useCallback(
    (p: Period): LasData => ({
      last: p.locked,
      vad: periodnamn(p),
      vaxla: async () => {
        await lasApi.period(p.id, !p.locked);
        await efter();
      },
    }),
    [efter]
  );

  return { ar, period };
}
