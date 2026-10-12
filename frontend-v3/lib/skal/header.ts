/**
 * Headerns räkenskapsårsrad.
 *
 * Fälten är serverns (`GET /api/v1/overview`); sammansättningen är
 * klientens formatering, inte en uträkning. Skalet räknar ingenting —
 * det enda som händer här är att två färdiga fält sätts ihop med ` · `,
 * som i designen: "Räkenskapsår 2026 · juni öppen".
 */

import type { Overview, OverviewFiscalYear } from "@/lib/skal/api";
import type { Rakenskapsar } from "@/lib/skal/bokslut";

const MANADER = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

/** "2026-06" → "juni". Okänt format lämnas som det är. */
export function manadsnamn(periodLabel: string): string {
  const m = /^\d{4}-(\d{2})$/.exec(periodLabel);
  if (!m) return periodLabel;
  return MANADER[Number(m[1]) - 1] ?? periodLabel;
}

export function arsrad(overview?: Overview): string {
  if (!overview?.fiscal_year) return "";
  const ar = `Räkenskapsår ${overview.fiscal_year.label}`;
  const p = overview.period_state;
  if (!p) return ar;
  return `${ar} · ${manadsnamn(p.label)} ${p.locked ? "låst" : "öppen"}`;
}

/** Samma etikett som serverns `fiscal_year.label`: "2026", "2025/2026". */
function arsetikett(ar: Rakenskapsar): string {
  const fran = ar.start_date.slice(0, 4);
  const till = ar.end_date.slice(0, 4);
  return fran === till ? fran : `${fran}/${till}`;
}

/** Ett år ur årslistan i översiktens form, så att vyerna kan läsa det. */
export function somOverviewAr(ar: Rakenskapsar): OverviewFiscalYear {
  return { id: ar.id, label: arsetikett(ar), start: ar.start_date, end: ar.end_date };
}

/**
 * Alternativen i headerns årsväljare. Översiktens år bär periodläget
 * (`arsrad`); de andra åren har inget aktuellt period att visa.
 */
export function arsalternativ(
  lista: Rakenskapsar[],
  overview?: Overview
): { id: string; text: string; etikett: string }[] {
  return lista.map((ar) => ({
    id: ar.id,
    etikett: arsetikett(ar),
    text:
      ar.id === overview?.fiscal_year?.id
        ? arsrad(overview)
        : `Räkenskapsår ${arsetikett(ar)}`,
  }));
}
